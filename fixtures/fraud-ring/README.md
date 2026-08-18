# Fraud-Ring Fixture

A synthetic Neo4j fixture graph for GraphCheck -- a small, fully reproducible
fraud-ring dataset with deliberately planted defects, used to prove
conformance checks actually catch real problems.

See `schema.md` for the full node/relationship contract and invariants,
and `manifest.yml` for machine-readable fixture metadata (load budget,
expected counts, defect IDs, PII fields, drift baseline).

Run `seed.cypher` against an empty Neo4j data graph to build the graph. All
fixture variants require an empty data graph before loading: "empty" means
there are no existing nodes or relationships. Existing compatible constraints
may remain.

Reset and lifecycle management are the responsibility of the consumer or
loader. The shared test helper in `tests/conftest.py` resets the database with
`MATCH (n) DETACH DELETE n` before loading each named script. The seed scripts
do not perform that destructive operation themselves.

The scripts use `MERGE`, so repeatedly loading the same variant is idempotent.
This does not make switching between variants safe: loading one variant over
another can preserve nodes, relationships, or properties that the new variant
does not declare. Reset the data graph before changing variants. Each load
completes in well under the 10-second load budget defined in `manifest.yml`.

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
It is not a cleanup or migration script. Loading it after the baseline or
drift variant without first resetting the data graph is unsupported and will
leave planted defects or other stale state in place.

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
