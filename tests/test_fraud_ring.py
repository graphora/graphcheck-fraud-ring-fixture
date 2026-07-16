"""
Acceptance tests for the fraud-ring fixture graph.

Reads fixtures/fraud-ring/manifest.yml (via the shared conftest.py
harness) for expected counts, defect IDs, PII fields, and drift figures
-- nothing here is hardcoded that the manifest already states.

Invariants tested, each with a disjoint set of planted defect IDs:
  1. Orphan accounts -- zero relationships of any kind.
  2. Cardinality violations -- owner_count > 1 only. Zero-owner accounts
     are explicitly NOT in scope here; they belong to invariant 1 above.
  3. Transaction invariants -- exactly one SENT and exactly one
     RECEIVED_BY per Transaction, no more and no fewer.
  4. PII field presence -- tax_id, email, and national_id are all
     PII-shaped fields present on every base Customer.
  5. Drift -- the documented 12% customer-count reduction between the
     baseline and drifted seed scripts is real and detectable, not a
     trivial self-comparison. The underlying base-population change is
     1,500 to 1,320; the total Customer node count asserted in tests is
     1,507 to 1,327, since both states also carry the same 5 ring-leader
     and 2 cardinality-violator Customer nodes on top of the population.
"""

from conftest import load_named_script

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
    one RECEIVED_BY (outgoing) edge -- not merely "at least one". Also
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
    """Every base-population Customer (CUST-<number>, e.g. CUST-1) should
    have all the PII-shaped fields declared in manifest.yml (tax_id,
    email, national_id), so PII-detection checks have real data to find.

    Deliberately excludes the 5 ring-leader (CUST-RING-LEADER-N) and 2
    cardinality-violator (CUST-CARD-000N) Customer nodes: those exist
    purely as defect markers for other invariants, not as representative
    "typical" customers, so PII coverage was never planted on them.
    """
    for field in manifest["pii_fields"]:
        label = field["node_label"]
        prop = field["property"]
        with neo4j_driver.session() as session:
            result = session.run(
                f"""
                MATCH (n:{label})
                WHERE n.id =~ '^CUST-[0-9]+$'
                  AND n.{prop} IS NULL
                RETURN count(n) AS missing
                """
            ).single()
        assert result["missing"] == 0, (
            f"{result['missing']} base-population {label} nodes missing "
            f"required PII field '{prop}'"
        )


def test_drift_matches_baseline_on_fresh_graph(neo4j_driver, manifest):
    """A freshly-seeded baseline graph's node count should match the
    pinned baseline_node_count in manifest.yml exactly."""
    baseline = manifest["baseline_node_count"]
    with neo4j_driver.session() as session:
        result = session.run("MATCH (n) RETURN count(n) AS n").single()
    assert result["n"] == baseline, (
        f"expected exactly {baseline} nodes (fresh baseline), got {result['n']}"
    )


def test_drift_is_detected_between_baseline_and_current(neo4j_driver, manifest):
    """Loads the actual drifted seed script (seed-drifted.cypher) and
    proves the documented 12% customer-count reduction is real: 1,500
    customers in the baseline down to 1,320 in the drifted state, a drop
    of 180. This is a genuine before/after fixture comparison, not an
    ephemeral in-test mutation -- both states are real, persisted fixture
    files a drift check can be pointed at independently.
    """
    drift = manifest["drift"]

    with neo4j_driver.session() as session:
        baseline_customers = session.run(
            "MATCH (c:Customer) RETURN count(c) AS n"
        ).single()["n"]
    assert baseline_customers == drift["baseline_customer_count"], (
        f"expected {drift['baseline_customer_count']} baseline customers, "
        f"got {baseline_customers}"
    )

    load_named_script(neo4j_driver, manifest, "drift_seed_script")

    with neo4j_driver.session() as session:
        drifted_customers = session.run(
            "MATCH (c:Customer) RETURN count(c) AS n"
        ).single()["n"]
        drifted_total_nodes = session.run(
            "MATCH (n) RETURN count(n) AS n"
        ).single()["n"]

    assert drifted_customers == drift["drifted_customer_count"], (
        f"expected {drift['drifted_customer_count']} drifted customers, "
        f"got {drifted_customers}"
    )
    assert drifted_total_nodes == drift["drifted_node_count"], (
        f"expected {drift['drifted_node_count']} total nodes in drifted "
        f"state, got {drifted_total_nodes}"
    )

    actual_drop = baseline_customers - drifted_customers
    expected_drop = drift["baseline_customer_count"] - drift["drifted_customer_count"]
    assert actual_drop == expected_drop, (
        f"expected customer count to drop by exactly {expected_drop}, "
        f"actually dropped by {actual_drop}"
    )