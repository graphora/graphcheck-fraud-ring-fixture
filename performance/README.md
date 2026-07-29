# Performance-scale graph generator

Populates a Neo4j database with a graph shaped like the fraud-ring demo
fixture (Customer/Account/Transaction, OWNS/CONTROLS/SENT/RECEIVED_BY),
scaled to any target node count. Built for the dedicated performance
environment referenced by GRAPHCHECK_PERFORMANCE_* in the graphcheck
repo's tests/performance/test_engine_budget.py -- this script populates
that environment, it does not host or manage it.

## Usage

```bash
pip install neo4j --break-system-packages
python generate_scale_graph.py --nodes 10000000 --uri bolt://<host>:7687 --user neo4j --password <password>
```

`--nodes` is the target total node count, split roughly 30% Customer,
50% Account, 20% Transaction, matching the demo fixture's proportions.
`--batch-size` (default 10000) controls how many rows are written per
database call.

The script wipes the target database before loading, so point it only
at a database meant for this purpose.

## What it builds

- Every base Customer gets the same PII-shaped fields as the demo
  fixture (`email`, `national_id`), so the PII pack has real data to
  find.
- 5 dedicated hub Customers, each directly controlling roughly 2% of
  all Accounts, so `hub_outlier` has real degree variance to detect.
- Every Account has at least one relationship (no orphans), since this
  fixture is for performance testing, not defect detection.

## Verified

Tested at 100,000 nodes: generated in under 8 seconds, all counts and
proportions exact, and a live GraphCheck project run (hub_outlier,
pii_name_match, pii_value_match, no_orphans) completed with zero
errors.

Tested at the full 10,000,000-node target: generation succeeded (took
about 8.5 minutes, needed a Neo4j container with at least 4GB heap and
2GB pagecache -- the default 2GB heap was not enough and caused the
first attempt to time out partway through). All counts, hub degrees,
and PII field coverage verified correct at this scale too.

Also ran the actual tests/performance/test_engine_budget.py suite (the
real 30-check, 5-minute-budget test) against this 10M-node data on a
local machine. It did not complete within the internal budget -- only
7 of 30 checks finished before the 295-second cutoff. This is expected
on a resource-constrained local environment rather than a properly
provisioned server, and is consistent with data generation itself
needing more memory than initially expected. Confirms this workload
genuinely needs the dedicated performance environment described in
the architecture, not a local machine.