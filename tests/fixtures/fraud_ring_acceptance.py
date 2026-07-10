"""
Acceptance test for the fraud-ring fixture graph.

This is the test that proves this week's "Done" bar from the tracker:
  - base graph loads in under 10s (enforced inside conftest.neo4j_driver)
  - exactly 3 orphan Accounts exist, with the documented IDs
  - exactly 1 cardinality violation exists, with the documented IDs
  - both are the ONLY defects present (no accidental extra orphans, etc.)

Uses the shared neo4j_driver fixture from tests/conftest.py — the same
harness C2's connector integration tests use.
"""


def test_node_counts_roughly_5k(neo4j_driver):
    with neo4j_driver.session() as session:
        result = session.run("MATCH (n) RETURN count(n) AS n").single()
        assert 4900 <= result["n"] <= 5100, (
            f"expected ~5,000 nodes, got {result['n']}"
        )


def test_exactly_three_orphan_accounts(neo4j_driver):
    expected_ids = {"ACC-ORPHAN-0001", "ACC-ORPHAN-0002", "ACC-ORPHAN-0003"}
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


def test_exactly_one_cardinality_violation(neo4j_driver):
    with neo4j_driver.session() as session:
        result = session.run(
            """
            MATCH (c:Customer)-[:OWNS]->(a:Account)
            WITH a, count(c) AS owner_count
            WHERE owner_count <> 1
            RETURN a.id AS id, owner_count
            """
        )
        violations = list(result)
    assert len(violations) == 1, (
        f"expected exactly 1 cardinality violation, found {len(violations)}"
    )
    assert violations[0]["id"] == "ACC-CARD-0001"
    assert violations[0]["owner_count"] == 2
# verified working
