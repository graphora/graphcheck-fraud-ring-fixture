"""
Acceptance tests for the fraud-ring fixture graph.

Reads fixtures/fraud-ring/manifest.yml (via the shared conftest.py
harness) for expected counts, defect IDs, PII fields, and drift baseline
-- nothing here is hardcoded that the manifest already states.

Invariants tested, each with a disjoint set of planted defect IDs:
  1. Orphan accounts -- zero relationships of any kind.
  2. Cardinality violations -- owner_count > 1 only. Zero-owner accounts
     are explicitly NOT in scope here; they belong to invariant 1 above.
  3. PII field presence -- Customer.tax_id is a PII-shaped field.
  4. Drift -- total node count vs. the pinned baseline in manifest.yml.
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
    """Every Transaction must have exactly one SENT (incoming) and one
    RECEIVED_BY (outgoing) edge -- no exceptions, including TXN-625, which
    was previously dropped by a sender/receiver formula collision.
    """
    with neo4j_driver.session() as session:
        missing_sent = session.run(
            """
            MATCH (t:Transaction)
            WHERE NOT ()-[:SENT]->(t)
            RETURN t.id AS id
            """
        )
        missing_sent_ids = {record["id"] for record in missing_sent}

        missing_received = session.run(
            """
            MATCH (t:Transaction)
            WHERE NOT (t)-[:RECEIVED_BY]->()
            RETURN t.id AS id
            """
        )
        missing_received_ids = {record["id"] for record in missing_received}

    assert not missing_sent_ids, (
        f"transactions missing a SENT edge: {missing_sent_ids}"
    )
    assert not missing_received_ids, (
        f"transactions missing a RECEIVED_BY edge: {missing_received_ids}"
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


def test_drift_matches_baseline(neo4j_driver, manifest):
    """Total node count should match the pinned drift baseline exactly
    on a freshly-seeded graph. A real drift check downstream would allow
    tolerance over time; this test just proves the baseline is accurate
    right after seeding."""
    baseline = manifest["drift_baseline"]["total_nodes"]
    with neo4j_driver.session() as session:
        result = session.run("MATCH (n) RETURN count(n) AS n").single()
    assert result["n"] == baseline, (
        f"expected exactly {baseline} nodes (drift baseline), got {result['n']}"
    )