"""
Shared Neo4j test-container harness -- manifest-driven.

Owner: Jayachandra/Janani (shared infra -- used by both the C2 connector
integration tests and per-fixture acceptance tests).

Reads fixtures/<fixture-id>/manifest.yml for fixture identity, Neo4j
version, load budget, and expected counts, rather than hardcoding any
single fixture's file paths. Adding a new fixture means adding a new
fixtures/<id>/ folder with its own manifest.yml -- this file doesn't change.

Note on fixture scope: manifest and neo4j_container are module-scoped,
not session-scoped. pytest does not allow session-scoped fixtures to
access request.module (a session can span multiple test modules, so
there's no single "current module" at that scope) -- module scope is
the widest scope that still lets us read FIXTURE_ID from the test file.
In practice this means the Neo4j container restarts once per test
module rather than once per whole run, which only matters once a
second fixture module is added.

Requires: pip install testcontainers[neo4j] neo4j pyyaml --break-system-packages
Requires: Docker available to the test runner.
"""

import pathlib
import time

import pytest
import yaml
from testcontainers.neo4j import Neo4jContainer

FIXTURES_ROOT = pathlib.Path(__file__).parent.parent / "fixtures"


def load_manifest(fixture_id: str) -> dict:
    """Read and parse fixtures/<fixture_id>/manifest.yml."""
    manifest_path = FIXTURES_ROOT / fixture_id / "manifest.yml"
    with manifest_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    data["_fixture_dir"] = FIXTURES_ROOT / fixture_id
    return data


def _load_fixture(driver, manifest: dict) -> None:
    """Wipe the database, then run the manifest's seed_script in order.

    Wiping first (rather than only relying on MERGE) is what actually
    prevents state leaking between tests: MERGE alone never removes
    stray nodes or reverts modified properties from a previous test run,
    it only ever adds or matches existing ones.

    Comments are stripped before splitting on ';' -- a comment can contain
    a literal semicolon, which would otherwise fracture a statement mid-parse.
    """
    with driver.session() as session:
        session.run("MATCH (n) DETACH DELETE n")

    seed_path = manifest["_fixture_dir"] / manifest["seed_script"]
    text = seed_path.read_text(encoding="utf-8")

    code_only = "\n".join(
        line for line in text.splitlines()
        if not line.strip().startswith("//")
    )

    statements = [stmt.strip() for stmt in code_only.split(";") if stmt.strip()]
    with driver.session() as session:
        for stmt in statements:
            session.run(stmt)


@pytest.fixture(scope="module")
def manifest(request) -> dict:
    """Reads fixture_id from the test module's FIXTURE_ID constant."""
    fixture_id = getattr(request.module, "FIXTURE_ID", None)
    if fixture_id is None:
        raise RuntimeError(
            "Test module must define FIXTURE_ID = '<fixture-folder-name>'"
        )
    return load_manifest(fixture_id)


@pytest.fixture(scope="module")
def neo4j_container(manifest):
    """Starts one Neo4j container per test module, version pinned from
    the fixture's manifest.yml."""
    image = f"neo4j:{manifest['neo4j_version']}"
    with Neo4jContainer(image) as container:
        yield container


@pytest.fixture(scope="function")
def neo4j_driver(manifest, neo4j_container):
    """Function-scoped driver. Database is wiped and reseeded before
    every test that requests this fixture, so no test can leak state
    into another.

    A throwaway warmup query runs before the timer starts, so the load
    budget assertion measures actual fixture load time, not Neo4j's
    one-time cold-start JIT/query-plan-cache warmup.
    """
    driver = neo4j_container.get_driver()
    with driver.session() as warmup_session:
        warmup_session.run("RETURN 1").consume()

    start = time.monotonic()
    _load_fixture(driver, manifest)
    elapsed = time.monotonic() - start
    budget = manifest["load_budget_seconds"]
    assert elapsed < budget, (
        f"{manifest['id']} seed took {elapsed:.1f}s to load, "
        f"exceeds the {budget}s budget"
    )
    yield driver
    driver.close()