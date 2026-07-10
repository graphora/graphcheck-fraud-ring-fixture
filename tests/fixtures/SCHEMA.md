# Fraud-Ring Fixture — Schema & Cardinality Contract

Owner: Jayachandra/Janani
Consumers: C1 (Engine tests), C2 (Connector integration tests), C3 (conformance checks), Example CQ library

This is the schema the fixture graph implements. Any check or CQ written
against `fraud-ring.cypher` should assume the shape below and nothing else.
If the shape changes, this file changes first, then the seed script.

## Node types

| Label | Key property | Other properties | Approx count |
|---|---|---|---|
| `Customer` | `id` (e.g. `CUST-0001`) | `name`, `tax_id` | ~1,500 |
| `Account` | `id` (e.g. `ACC-0001`) | `type` (`checking`\|`savings`\|`shell`), `balance` | ~2,500 |
| `Transaction` | `id` (e.g. `TXN-0001`) | `amount`, `ts` | ~1,000 |

Total ≈ 5,000 nodes.

## Relationship types and intended cardinality

| Relationship | Direction | Intended cardinality | Meaning |
|---|---|---|---|
| `OWNS` | `(Customer)-[:OWNS]->(Account)` | **Exactly 1 owning Customer per Account** | Direct legal ownership |
| `CONTROLS` | `(Customer)-[:CONTROLS]->(Account)` and `(Account)-[:CONTROLS]->(Account)` | 0..N, chainable 1..4 hops | Effective control, possibly via shell accounts. This is what the canonical CQ (`cq-001`, see briefing §6) walks with `CONTROLS*1..4` |
| `SENT` | `(Account)-[:SENT]->(Transaction)` | Exactly 1 sending Account per Transaction | Transaction origin |
| `RECEIVED_BY` | `(Transaction)-[:RECEIVED_BY]->(Account)` | Exactly 1 receiving Account per Transaction | Transaction destination |

## Invariants this fixture is built to test

These are the ground-truth rules. A correctly working `conformance` check pack
(C3) should be able to catch every violation planted in §3 of `fraud-ring.cypher`
using exactly these rules — nothing more exotic is needed:

1. **No orphans**: every `Account` should have at least one relationship
   (`OWNS`, `CONTROLS`, `SENT`, or `RECEIVED_BY`).
2. **Cardinality**: every `Account` should have **exactly one** incoming
   `OWNS` relationship — never zero, never two or more.
3. *(reserved for later)* PII pack targets: `Customer.tax_id`-shaped fields.
4. *(reserved for later)* Drift: node/relationship counts vs. a pinned baseline.

Only invariants 1 and 2 are in scope this week. 3 and 4 are documented here
so nobody re-derives the shape later — they'll be planted in a follow-up pass.

## Why this shape

- `OWNS` is a strict 1:1-from-Account edge — the deliberate cardinality
  violation (§3 below) breaks exactly this rule, because it's the simplest,
  most demo-legible invariant to violate and explain.
- `CONTROLS` is intentionally chainable so the CQ pattern in the main
  briefing (`Customer -[:CONTROLS*1..4]-> Account`) has real multi-hop paths
  to walk, including through `shell`-type accounts.
- `SENT`/`RECEIVED_BY` around a `Transaction` node (rather than a direct
  `Account -> Account` edge) exists so transaction-level properties (`amount`,
  `ts`) have somewhere to live, and so hub-outlier detection (C3) has a
  degree distribution to look at on `Transaction`.

**Naming note:** the Week-1 issue refers to this relationship informally as
`TRANSACTED_WITH`. We use `SENT`/`RECEIVED_BY` via an intermediate
`Transaction` node instead of a single direct edge, for the reason above.
Functionally equivalent; flagging so nobody re-derives this from scratch.
# verified working
