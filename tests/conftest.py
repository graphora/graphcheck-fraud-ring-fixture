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

from cypher_utils import split_statements

FIXTURES_ROOT = pathlib.Path(__file__).parent.parent / "fixtures"


def load_manifest(fixture_id: str) -> dict:
    """Read and parse fixtures/<fixture_id>/manifest.yml."""
    manifest_path = FIXTURES_ROOT / fixture_id / "manifest.yml"
    with manifest_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    data["_fixture_dir"] = FIXTURES_ROOT / fixture_id
    return data


def load_named_script(driver, manifest: dict, script_key: str) -> None:
    """Wipe the database, then run the named script (looked up in the
    manifest by key, e.g. "seed_script" or "drift_seed_script").

    Wiping first (rather than only relying on MERGE) is what actually
    prevents state leaking between loads: MERGE alone never removes
    stray nodes or reverts modified properties from a previous load,
    it only ever adds or matches existing ones.

    Uses split_statements() (tests/cypher_utils.py), a string- and
    comment-aware Cypher statement splitter, rather than a naive
    "strip // lines then split on ;" approach, since that naive approach
    incorrectly splits on semicolons inside string literals, backtick
    identifiers, and block comments.
    """
    script_filename = manifest[script_key]
    script_path = manifest["_fixture_dir"] / script_filename
    text = script_path.read_text(encoding="utf-8")

    with driver.session() as session:
        session.run("MATCH (n) DETACH DELETE n")

    statements = split_statements(text)
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
    """Function-scoped driver. Database is wiped and reseeded with the
    manifest's baseline seed_script before every test that requests this
    fixture, so no test can leak state into another.

    A throwaway warmup query runs before the timer starts, so the load
    budget assertion measures actual fixture load time, not Neo4j's
    one-time cold-start JIT/query-plan-cache warmup.
    """
    driver = neo4j_container.get_driver()
    with driver.session() as warmup_session:
        warmup_session.run("RETURN 1").consume()

    start = time.monotonic()
    load_named_script(driver, manifest, "seed_script")
    elapsed = time.monotonic() - start
    budget = manifest["load_budget_seconds"]
    assert elapsed < budget, (
        f"{manifest['id']} seed took {elapsed:.1f}s to load, "
        f"exceeds the {budget}s budget"
    )
    yield driver
    driver.close()