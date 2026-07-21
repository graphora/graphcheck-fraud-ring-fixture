# GraphCheck Fixtures

Reusable fixture graphs for GraphCheck conformance testing -- synthetic
Neo4j datasets with deliberately planted defects, used to prove that
conformance checks actually catch real problems.

This repo is a catalog, not a single scenario. Each fixture lives in its
own folder under `fixtures/`, with its own manifest, schema doc, and seed
script. The shared test harness in `tests/conftest.py` loads any fixture
by reading its `manifest.yml` -- adding a new fixture means adding a new
`fixtures/<id>/` folder, not touching the harness.

## Source of truth

This repo is the canonical source for the fraud-ring fixture (and any
future fixtures added here). The main `graphcheck` product repo should
consume fixture data from here rather than maintaining an independent
copy -- specifically, `graphcheck` PR #23's PII and drift work has been
ported into `fixtures/fraud-ring/` in this repo (`seed.cypher` and
`seed-drifted.cypher`), and that independent copy should be retired in
favor of this one. If `graphcheck` needs to load this fixture at
runtime, it should reference this repo directly (e.g. as a git
submodule, a pinned dependency, or by fetching the relevant files at
build time) rather than re-implementing the seed data.

## Structure

    graphcheck-fixtures/
        README.md
        pyproject.toml
        fixtures/
            fraud-ring/
                README.md
                manifest.yml
                schema.md
                seed.cypher
                seed-drifted.cypher
        examples/
            fraud-ring-cqs.yml
        tests/
            conftest.py
            cypher_utils.py
            test_cypher_utils.py
            test_fraud_ring.py
            test_example_cqs.py
        .github/workflows/ci.yml

## Fixtures

| Fixture | Description |
|---|---|
| [`fraud-ring`](fixtures/fraud-ring/README.md) | Synthetic financial network with dense sub-clusters, transaction chains, and planted orphan/cardinality defects |

## Example CQ library

`examples/fraud-ring-cqs.yml` holds 10 example competency questions (CQs)
against the fraud-ring fixture: 8 shape-pattern CQs (cq-001 to cq-008)
plus 2 regression overlays (cq-009, cq-010). Each one is verified by
`tests/test_example_cqs.py`, which runs every query against a live
fixture graph and checks the result against its declared shape.

## Quick start

```bash
pip install -e .
pytest tests/ -v
```

Requires Docker running locally -- `conftest.py` spins up a disposable
Neo4j container automatically for any test, no manual database setup needed.

## Adding a new fixture

1. Create `fixtures/<your-fixture-id>/` with `manifest.yml`, `schema.md`,
   and a seed script
2. Create `tests/test_<your-fixture-id>.py` with `FIXTURE_ID = "<your-fixture-id>"`
   at module level, and write tests using the shared `neo4j_driver` and
   `manifest` fixtures
3. No changes needed to `tests/conftest.py` -- it reads everything from
   your manifest

See `fixtures/fraud-ring/manifest.yml` for a complete example of what a
manifest should declare: fixture identity, Neo4j version, load budget,
expected node counts, planted defect IDs, PII fields, and drift baseline.