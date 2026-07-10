# GraphCheck — Fraud-Ring Fixture

A synthetic Neo4j fixture graph built for [GraphCheck](https://github.com) v0 — a small, fully reproducible fraud-ring dataset with deliberately planted defects, used to prove that conformance checks actually catch real problems.

## What's in here

| File | Purpose |
|---|---|
| `tests/fixtures/SCHEMA.md` | The contract — node types, relationship types, and cardinality invariants the graph is built to satisfy |
| `tests/fixtures/fraud-ring.cypher` | The seed script — builds ~5,011 nodes from scratch, fully idempotent via `MERGE` |
| `tests/fixtures/test_fraud_ring_acceptance.py` | Automated `pytest` checks — node count, exact defect IDs |
| `tests/conftest.py` | Shared Neo4j test-container harness — spins up a temporary Neo4j via Docker automatically for any test in this repo |

## Quick start

```bash
pip install testcontainers[neo4j] neo4j pytest
pytest tests/fixtures/test_fraud_ring_acceptance.py -v
```

Requires Docker running locally. No manual database setup needed — `conftest.py` handles it automatically.

## The graph

- **~5,011 nodes**: 1,500 Customers, 2,500 Accounts, 1,000 Transactions, plus a handful of deliberately planted defect nodes
- **Fully synthetic** — generated entirely by loops in the seed script, no external dataset
- **Idempotent** — verified via double-run against a live Neo4j instance; identical node/relationship counts both times

## Planted defects (this pass)

| Defect | ID(s) | Detail |
|---|---|---|
| Orphan account | `ACC-ORPHAN-0001` | Zero relationships |
| Orphan account | `ACC-ORPHAN-0002` | Zero relationships |
| Orphan account | `ACC-ORPHAN-0003` | Zero relationships |
| Cardinality violation | `ACC-CARD-0001` | Owned by 2 Customers (`CUST-CARD-0001`, `CUST-CARD-0002`) instead of exactly 1 |

PII and induced-drift defects are a separate, follow-up pass — see `SCHEMA.md` for details.

## Verification

Every claim above is independently checked two ways:
1. **Manually** — direct Cypher queries run against Neo4j Desktop
2. **Automatically** — the `pytest` suite in `tests/fixtures/test_fraud_ring_acceptance.py`, using a disposable Docker-based Neo4j container via `testcontainers`
