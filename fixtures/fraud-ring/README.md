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