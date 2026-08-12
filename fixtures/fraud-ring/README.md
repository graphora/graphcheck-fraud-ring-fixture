# Fraud-Ring Fixture

A synthetic Neo4j fixture graph for GraphCheck -- a small, fully reproducible
fraud-ring dataset with deliberately planted defects, used to prove
conformance checks actually catch real problems.

See `schema.md` for the full node/relationship contract and invariants,
and `manifest.yml` for machine-readable fixture metadata (load budget,
expected counts, defect IDs, PII fields, drift baseline).

Run `seed.cypher` against a Neo4j instance to build the graph. It is
idempotent (safe to re-run) via `MERGE`, and completes in well under the
10-second load budget defined in `manifest.yml`.

## Fixture variants

### `seed.cypher` -- baseline/demo state

The baseline contains exactly 5,011 nodes and the documented planted
findings:

- Exactly 3 orphan Accounts: `ACC-ORPHAN-0001`, `ACC-ORPHAN-0002`, and
  `ACC-ORPHAN-0003`.
- Exactly 1 ownership-cardinality finding: `ACC-CARD-0001`, with exactly
  two owners.

Every Transaction has exactly one incoming `SENT` relationship and exactly
one outgoing `RECEIVED_BY` relationship. Base Customer PII fields are present
as defined by `manifest.yml`.

### `seed-clean.cypher` -- clean state

The clean variant contains exactly 5,005 nodes, no orphan Accounts, no
ownership-cardinality violations, and none of the planted defect IDs. Every
Account has exactly one incoming `OWNS` relationship, and every Transaction
has exactly one incoming `SENT` and one outgoing `RECEIVED_BY` relationship.

### `seed-drifted.cypher` -- drift state

The drift variant contains exactly 4,831 nodes, including 1,327 Customer
nodes. This is a decrease of exactly 180 Customers from the baseline. The
planted orphan and ownership-cardinality findings remain, Transaction
invariants remain valid, and base Customer PII coverage remains valid.

## Neo4j compatibility

The fixture is tested against Neo4j 4.4.48 and Neo4j 5.18. Both versions use
the same seed scripts and shared manifest-driven loader; there are no
Neo4j-version-specific seed loaders. The `FOR ... REQUIRE` constraint syntax
is used intentionally because it is shared by both tested Neo4j versions.

## Running the tests

```bash
pip install -e .
pytest tests/ -v
```

The Neo4j versions tested by the fixture are declared in `manifest.yml`.
