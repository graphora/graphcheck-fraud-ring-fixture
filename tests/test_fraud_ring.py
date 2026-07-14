"""
Acceptance tests for the fraud-ring fixture graph.

Reads fixtures/fraud-ring/manifest.yml (via the shared conftest.py
harness) for expected counts, defect IDs, PII fields, and the drift
baseline -- nothing here is hardcoded that the manifest already states.

Invariants tested, each with a disjoint set of planted defect IDs:
  1. Orphan accounts -- zero relationships of any kind.
  2. Cardinality violations -- owner_count > 1 only. Zero-owner accounts
     are explicitly NOT in scope here; they belong to invariant 1 above.
  3. Transaction invariants -- exactly one SENT and exactly one
     RECEIVED_BY per Transaction, no more and no fewer.
  4. PII field presence -- Customer.tax_id is a PII-shaped field.
  5. Drift -- both that a fresh graph matches the pinned baseline, and
     that mutating the graph is actually detectable as a deviation from it.
"""

FIXTURE_ID = "fraud-ring"


def test_node_counts_roughly_5k(neo4j_driver, manifest):
    expected = manifest["expected_node_count"]
    with neo4j_driver.session() as session:
        result = session.run("MATCH (n) RETURN count(n) AS n").single()
    assert expected["min"] <= result["n"] <= expected["max"], (
        f"expected {expected['min']}-{expected['max']} nodes, got {result['n']}"
    )


def test_orphan_accounts(neo4j_driver, manifest):
    """Orphans are Accounts with zero relationships of any kind.
    Disjoint from the cardinality invariant below by construction --
    an orphan can never also appear in the cardinality violation set,
    since owner_count for a true orphan is 0, not >1.
    """
    expected_ids = set(manifest["defects"]["orphan_accounts"]["ids"])
    with neo4j_driver.session() as session:
        result = session.run(
            """
            MATCH (a:Account)
            WHERE NOT (a)--()
            RETURN a.id AS id
            """
        )
        found_ids = {record["id"] for record in result}
    assert found_ids == expected_ids, (
        f"expected exactly the planted orphans {expected_ids}, found {found_ids}"
    )


def test_cardinality_violations(neo4j_driver, manifest):
    """Cardinality violations are Accounts with MORE THAN ONE owning
    Customer (owner_count > 1). Zero-owner accounts are intentionally
    excluded -- those are orphans, covered by test_orphan_accounts above.
    This makes the two invariants disjoint: no ID is ever asserted by both.
    """
    expected_ids = set(manifest["defects"]["cardinality_violations"]["ids"])
    with neo4j_driver.session() as session:
        result = session.run(
            """
            MATCH (c:Customer)-[:OWNS]->(a:Account)
            WITH a, count(c) AS owner_count
            WHERE owner_count > 1
            RETURN a.id AS id
            """
        )
        found_ids = {record["id"] for record in result}
    assert found_ids == expected_ids, (
        f"expected exactly these cardinality violations {expected_ids}, "
        f"found {found_ids}"
    )


def test_transaction_invariants(neo4j_driver):
    """Every Transaction must have EXACTLY one SENT (incoming) and EXACTLY
    one RECEIVED_BY (outgoing) edge -- not merely "at least one". A
    Transaction with two senders or two receivers must also fail this
    test, which the previous version of this test did not catch. Also
    covers TXN-625, previously dropped by a sender/receiver formula
    collision.
    """
    with neo4j_driver.session() as session:
        sent_counts = session.run(
            """
            MATCH (t:Transaction)
            OPTIONAL MATCH (sender:Account)-[:SENT]->(t)
            WITH t, count(sender) AS sent_count
            WHERE sent_count <> 1
            RETURN t.id AS id, sent_count
            """
        )
        bad_sent = {record["id"]: record["sent_count"] for record in sent_counts}

        received_counts = session.run(
            """
            MATCH (t:Transaction)
            OPTIONAL MATCH (t)-[:RECEIVED_BY]->(receiver:Account)
            WITH t, count(receiver) AS received_count
            WHERE received_count <> 1
            RETURN t.id AS id, received_count
            """
        )
        bad_received = {record["id"]: record["received_count"] for record in received_counts}

    assert not bad_sent, (
        f"transactions without exactly one SENT edge: {bad_sent}"
    )
    assert not bad_received, (
        f"transactions without exactly one RECEIVED_BY edge: {bad_received}"
    )


def test_pii_fields_present(neo4j_driver, manifest):
    """Every Customer should have the PII-shaped field(s) declared in
    manifest.yml, so PII-detection checks have real data to find."""
    for field in manifest["pii_fields"]:
        label = field["node_label"]
        prop = field["property"]
        with neo4j_driver.session() as session:
            result = session.run(
                f"""
                MATCH (n:{label})
                WHERE n.{prop} IS NULL
                RETURN count(n) AS missing
                """
            ).single()
        assert result["missing"] == 0, (
            f"{result['missing']} {label} nodes missing required PII field '{prop}'"
        )


def test_drift_matches_baseline_on_fresh_graph(neo4j_driver, manifest):
    """A freshly-seeded graph's node count should match the pinned
    baseline in manifest.yml exactly. This is the "no false positive"
    half of drift detection: a clean, unmodified graph must not be
    reported as drifted.
    """
    baseline = manifest["baseline_node_count"]
    with neo4j_driver.session() as session:
        result = session.run("MATCH (n) RETURN count(n) AS n").single()
    assert result["n"] == baseline, (
        f"expected exactly {baseline} nodes (fresh baseline), got {result['n']}"
    )


def test_drift_is_detected_after_mutation(neo4j_driver, manifest):
    """This is the "actually exercises drift" half: mutate a freshly
    seeded graph (add extra nodes), then prove the resulting count no
    longer matches the pinned baseline -- demonstrating the fixture
    supports the documented drift-detection scenario, not just a
    trivial self-comparison against an untouched graph.
    """
    baseline = manifest["baseline_node_count"]

    with neo4j_driver.session() as session:
        before = session.run("MATCH (n) RETURN count(n) AS n").single()["n"]
    assert before == baseline, (
        f"precondition failed: expected fresh graph at baseline {baseline}, got {before}"
    )

    injected_count = 7
    with neo4j_driver.session() as session:
        session.run(
            """
            UNWIND range(1, $count) AS i
            CREATE (:DriftProbe {id: 'DRIFT-PROBE-' + toString(i)})
            """,
            count=injected_count,
        )
        after = session.run("MATCH (n) RETURN count(n) AS n").single()["n"]

    assert after == before + injected_count, (
        f"expected node count to rise by exactly {injected_count} after "
        f"mutation, went from {before} to {after}"
    )
    assert after != baseline, (
        f"mutated graph's node count ({after}) should differ from the "
        f"baseline ({baseline}), but it did not -- drift would go undetected"
    )