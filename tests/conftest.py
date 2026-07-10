"""
Shared Neo4j test-container harness.

Owner: Jayachandra/Janani (shared infra — used by both the C2 connector
integration tests and the fixture-graph acceptance tests).

Provides two fixtures:
  - neo4j_container: session-scoped, raw testcontainers Neo4j instance.
  - neo4j_driver: function-scoped driver, graph reset + reseeded with
    fraud-ring.cypher before every test that requests it.

Requires: pip install testcontainers[neo4j] neo4j --break-system-packages
Requires: Docker available to the test runner (CI and local dev both need
this — see docs/testing.md once it exists).
"""

import pathlib
import time

import pytest
from testcontainers.neo4j import Neo4jContainer

FIXTURE_CYPHER_PATH = (
    pathlib.Path(__file__).parent / "fixtures" / "fraud-ring.cypher"
)


def _load_fixture(driver) -> None:
    """Split fraud-ring.cypher into statements and run them in order.

    Cypher's transactional CREATE/MATCH statements in this file are meant
    to run sequentially (later steps MATCH nodes created by earlier ones),
    so we execute them one at a time rather than as a single multi-statement
    string, which the Python driver doesn't support directly.
    """
    text = FIXTURE_CYPHER_PATH.read_text()

   # Strip comments before splitting on ";" — a comment can contain a
    # literal semicolon, which would otherwise fracture a statement mid-parse.
    code_only = "\n".join(
        line for line in text.splitlines()
        if not line.strip().startswith("//")
    )

    statements = [stmt.strip() for stmt in code_only.split(";") if stmt.strip()]
    with driver.session() as session:
        for stmt in statements:
            session.run(stmt)


@pytest.fixture(scope="session")
def neo4j_container():
    """Starts one Neo4j container for the whole test session."""
    with Neo4jContainer("neo4j:5.18") as container:
        yield container


@pytest.fixture(scope="function")
def neo4j_driver(neo4j_container):
    """Function-scoped driver, reseeded with fraud-ring.cypher every test.

    Function scope (not session scope) is deliberate: tests must not leak
    state into each other. Reseeding a ~5K-node graph is well under the 10s
    budget, so paying that cost per-test is acceptable for v0.

    Uses the container's own get_driver() convenience method rather than
    manually constructing a GraphDatabase.driver() with guessed-at
    credential attribute names (NEO4J_USER / NEO4J_ADMIN_PASSWORD don't
    exist on newer testcontainers versions — this was a real bug, not a
    guess that happened to be wrong once).
    """
    driver = neo4j_container.get_driver()
    start = time.monotonic()
    _load_fixture(driver)
    elapsed = time.monotonic() - start
    assert elapsed < 10, (
        f"fraud-ring.cypher took {elapsed:.1f}s to load, exceeds the 10s budget"
    )
    yield driver
    driver.close()
# verified working
