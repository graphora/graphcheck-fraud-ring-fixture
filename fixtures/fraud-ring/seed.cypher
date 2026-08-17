// seed.cypher - see schema.md for the full contract. This is the BASELINE
// state (1,500 customers) -- see manifest.yml drift_seed_script for the
// drifted "current" state (1,320 customers) used by the drift test.
// Requires an empty data graph (no nodes or relationships); compatible
// constraints may remain. Reset/lifecycle management belongs to the loader.
// MERGE makes rerunning this same variant safe, but does not make switching
// between fixture variants safe. Expected size: ~5,011 nodes, load: <10s.
// Planted defects: 3 orphan accounts, 1 cardinality violation
// (exact IDs in section 3 below). PII fields declared in manifest.yml.
// ---- 0. Constraints (required for MERGE-by-id to be fast and safe) -------
CREATE CONSTRAINT customer_id IF NOT EXISTS FOR (c:Customer) REQUIRE c.id IS UNIQUE;
CREATE CONSTRAINT account_id IF NOT EXISTS FOR (a:Account) REQUIRE a.id IS UNIQUE;
CREATE CONSTRAINT transaction_id IF NOT EXISTS FOR (t:Transaction) REQUIRE t.id IS UNIQUE;

// ---- 1. Customers (1,500) ------------------------------------------------
UNWIND range(1, 1500) AS i
MERGE (c:Customer {id: 'CUST-' + toString(i)})
ON CREATE SET
  c.name = 'Customer ' + toString(i),
  c.tax_id = toString(100000000 + i);

// ---- 1b. Planted PII -------------------------------------------------
// Adds two PII properties to every base Customer:
//   - email
//   - national_id
// national_id alternates between Singapore NRIC-style and Indian
// Aadhaar-style values so the PII pack has both formats to detect.
UNWIND range(1, 1500) AS i
MATCH (c:Customer {id: 'CUST-' + toString(i)})
SET c.email = 'customer' + toString(i) + '@example.com',
    c.national_id = CASE WHEN i % 2 = 0
      THEN 'S' + toString(1000000 + i) + 'D'
      ELSE toString(200000000000 + i) END;

// ---- 2. Accounts (2,500) - mostly 'checking'/'savings', some 'shell' -----
UNWIND range(1, 2500) AS i
MERGE (a:Account {id: 'ACC-' + toString(i)})
ON CREATE SET
  a.type = CASE WHEN i % 10 = 0 THEN 'shell'
                WHEN i % 2 = 0 THEN 'savings'
                ELSE 'checking' END,
  a.balance = (i * 137) % 50000;

// ---- 3. Transactions (1,000) ---------------------------------------------
UNWIND range(1, 1000) AS i
MERGE (t:Transaction {id: 'TXN-' + toString(i)})
ON CREATE SET
  t.amount = (i * 91) % 10000,
  t.ts = datetime({epochSeconds: 1750000000 + i * 3600});

// ---- 4. OWNS: assigns one owning Customer to every base Account ----
// (the contract allows at most one owner; this loop happens to give
// every base account exactly one, deliberately violated later by
// ACC-CARD-0001)
UNWIND range(1, 2500) AS i
MATCH (a:Account {id: 'ACC-' + toString(i)})
MATCH (c:Customer {id: 'CUST-' + toString(((i - 1) % 1500) + 1)})
MERGE (c)-[:OWNS]->(a);

MATCH (c:Customer)
WHERE toInteger(split(c.id, '-')[1]) % 3 = 0
MATCH (a:Account {id: 'ACC-' + toString(((toInteger(split(c.id, '-')[1]) + 1499) % 2500) + 1)})
MERGE (c)-[:CONTROLS]->(a);

// ---- 5. CONTROLS: baseline chainable control edges (feeds CQ*1..4) -------
MATCH (c:Customer)
WHERE toInteger(split(c.id, '-')[1]) % 5 = 0
MATCH (a:Account {id: 'ACC-' + toString(2000 + (toInteger(split(c.id, '-')[1]) % 400))})
MERGE (c)-[:CONTROLS]->(a);

MATCH (shell:Account {type: 'shell'})
WITH shell, toInteger(split(shell.id, '-')[1]) AS n
MATCH (target:Account {id: 'ACC-' + toString((n + 7) % 2500 + 1)})
WHERE target.id <> shell.id
MERGE (shell)-[:CONTROLS]->(target);

// ---- 5b. DENSE SUB-CLUSTERS: 5 tight fraud rings of 8 accounts each ------
UNWIND range(0, 4) AS ring_num
MERGE (leader:Customer {id: 'CUST-RING-LEADER-' + toString(ring_num)})
ON CREATE SET leader.name = 'Ring Leader ' + toString(ring_num), leader.tax_id = '999' + toString(ring_num)
WITH ring_num, leader, [j IN range(1, 8) | 2401 + (ring_num * 8) + (j - 1)] AS ring_account_nums
UNWIND ring_account_nums AS acc_num
MATCH (a:Account {id: 'ACC-' + toString(acc_num)})
MERGE (leader)-[:CONTROLS]->(a)
WITH ring_num, ring_account_nums, a, acc_num
UNWIND ring_account_nums AS other_num
WITH a, acc_num, other_num
WHERE other_num <> acc_num
MATCH (b:Account {id: 'ACC-' + toString(other_num)})
MERGE (a)-[:CONTROLS]->(b);

// ---- 6. SENT / RECEIVED_BY: wire transactions between accounts ----------
// FIX (was dropping TXN-625): when sender and receiver formulas collide on
// the same account, shift the receiver by one instead of silently filtering
// the row out - every transaction is now guaranteed a SENT and a
// RECEIVED_BY edge, with no exceptions.
UNWIND range(1, 1000) AS i
MATCH (t:Transaction {id: 'TXN-' + toString(i)})
MATCH (sender:Account {id: 'ACC-' + toString((i * 3) % 2500 + 1)})
WITH i, t, sender, ((i * 7) % 2500 + 1) AS raw_receiver_num
WITH i, t, sender,
     CASE WHEN 'ACC-' + toString(raw_receiver_num) = sender.id
          THEN (raw_receiver_num % 2500) + 1
          ELSE raw_receiver_num END AS receiver_num
MATCH (receiver:Account {id: 'ACC-' + toString(receiver_num)})
MERGE (sender)-[:SENT]->(t)
MERGE (t)-[:RECEIVED_BY]->(receiver);

// ============================================================================
// 3. PLANTED DEFECTS - documented IDs
// ============================================================================

MERGE (o1:Account {id: 'ACC-ORPHAN-0001'}) ON CREATE SET o1.type = 'checking', o1.balance = 100;
MERGE (o2:Account {id: 'ACC-ORPHAN-0002'}) ON CREATE SET o2.type = 'savings',  o2.balance = 250;
MERGE (o3:Account {id: 'ACC-ORPHAN-0003'}) ON CREATE SET o3.type = 'shell',    o3.balance = 0;

MERGE (a:Account {id: 'ACC-CARD-0001'}) ON CREATE SET a.type = 'checking', a.balance = 5000
MERGE (c1:Customer {id: 'CUST-CARD-0001'}) ON CREATE SET c1.name = 'Cardinality Violator A', c1.tax_id = '000000001'
MERGE (c2:Customer {id: 'CUST-CARD-0002'}) ON CREATE SET c2.name = 'Cardinality Violator B', c2.tax_id = '000000002'
MERGE (c1)-[:OWNS]->(a)
MERGE (c2)-[:OWNS]->(a);

// ============================================================================
// End of seed. Expect ~5,011 nodes total: 5,000 base (1,500 Customers +
// 2,500 Accounts + 1,000 Transactions) + 3 orphan accounts + 1 cardinality
// account + 2 cardinality customers + 5 ring-leader customers = 5,011.
// ============================================================================
