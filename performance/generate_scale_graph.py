"""
Parameterized graph generator for GraphCheck performance testing.

Builds a graph with the same shape as the fraud-ring demo fixture
(Customer/Account/Transaction, OWNS/CONTROLS/SENT/RECEIVED_BY), scaled
to any target node count. Meant for the dedicated performance
environment referenced by GRAPHCHECK_PERFORMANCE_* -- this script does
not host or manage that environment, it only populates it.

Uses batched CREATE (not MERGE) since this always runs against a
freshly wiped database, so there is no need to pay MERGE's existence-check
cost per row. Constraints are created before any data, so relationship
creation can look nodes up by id through an index instead of a table scan.

Keeps a small number of "hub" customers that control a large share of
accounts directly, so hub_outlier has real degree variance to detect.
Every customer gets the same PII-shaped fields as the demo fixture
(email, national_id) so the PII pack has real data to find.

Usage:
    python generate_scale_graph.py --nodes 100000 --uri bolt://localhost:7687 --password mypassword
"""

import argparse
import time

from neo4j import GraphDatabase

CUSTOMER_RATIO = 0.3
ACCOUNT_RATIO = 0.5
HUB_CUSTOMER_COUNT = 5
HUB_ACCOUNTS_PER_HUB_FRACTION = 0.02


def compute_counts(total_nodes: int) -> tuple[int, int, int]:
    customer_count = int(total_nodes * CUSTOMER_RATIO)
    account_count = int(total_nodes * ACCOUNT_RATIO)
    transaction_count = total_nodes - customer_count - account_count
    return customer_count, account_count, transaction_count


def batched_ranges(total: int, batch_size: int):
    start = 1
    while start <= total:
        end = min(start + batch_size - 1, total)
        yield start, end
        start = end + 1


def create_constraints(session) -> None:
    session.run(
        "CREATE CONSTRAINT perf_customer_id IF NOT EXISTS "
        "FOR (c:Customer) REQUIRE c.id IS UNIQUE"
    )
    session.run(
        "CREATE CONSTRAINT perf_account_id IF NOT EXISTS "
        "FOR (a:Account) REQUIRE a.id IS UNIQUE"
    )
    session.run(
        "CREATE CONSTRAINT perf_transaction_id IF NOT EXISTS "
        "FOR (t:Transaction) REQUIRE t.id IS UNIQUE"
    )


def create_customers(session, count: int, batch_size: int) -> None:
    for start, end in batched_ranges(count, batch_size):
        batch = [
            {
                "id": f"CUST-{i}",
                "name": f"Customer {i}",
                "tax_id": str(100000000 + i),
                "email": f"customer{i}@example.com",
                "national_id": (f"S{1000000 + i}D" if i % 2 == 0 else str(200000000000 + i)),
            }
            for i in range(start, end + 1)
        ]
        session.run(
            "UNWIND $batch AS row "
            "CREATE (c:Customer {id: row.id, name: row.name, tax_id: row.tax_id, "
            "email: row.email, national_id: row.national_id})",
            batch=batch,
        )


def create_accounts(session, count: int, batch_size: int) -> None:
    for start, end in batched_ranges(count, batch_size):
        batch = [
            {
                "id": f"ACC-{i}",
                "type": "shell" if i % 10 == 0 else ("savings" if i % 2 == 0 else "checking"),
                "balance": (i * 137) % 50000,
            }
            for i in range(start, end + 1)
        ]
        session.run(
            "UNWIND $batch AS row "
            "CREATE (a:Account {id: row.id, type: row.type, balance: row.balance})",
            batch=batch,
        )


def create_transactions(session, count: int, batch_size: int) -> None:
    for start, end in batched_ranges(count, batch_size):
        batch = [
            {
                "id": f"TXN-{i}",
                "amount": (i * 91) % 10000,
                "epoch": 1750000000 + i * 3600,
            }
            for i in range(start, end + 1)
        ]
        session.run(
            "UNWIND $batch AS row "
            "CREATE (t:Transaction {id: row.id, amount: row.amount, "
            "ts: datetime({epochSeconds: row.epoch})})",
            batch=batch,
        )


def create_owns(session, account_count: int, customer_count: int, batch_size: int) -> None:
    for start, end in batched_ranges(account_count, batch_size):
        batch = [
            {
                "account_id": f"ACC-{i}",
                "customer_id": f"CUST-{((i - 1) % customer_count) + 1}",
            }
            for i in range(start, end + 1)
        ]
        session.run(
            "UNWIND $batch AS row "
            "MATCH (c:Customer {id: row.customer_id}), (a:Account {id: row.account_id}) "
            "CREATE (c)-[:OWNS]->(a)",
            batch=batch,
        )


def create_hubs(session, account_count: int, batch_size: int) -> None:
    accounts_per_hub = max(1, int(account_count * HUB_ACCOUNTS_PER_HUB_FRACTION))
    for hub_index in range(HUB_CUSTOMER_COUNT):
        hub_id = f"CUST-HUB-{hub_index}"
        session.run(
            "MERGE (c:Customer {id: $id}) "
            "ON CREATE SET c.name = $name, c.tax_id = $tax_id, "
            "c.email = $email, c.national_id = $national_id",
            id=hub_id,
            name=f"Hub Customer {hub_index}",
            tax_id=f"999{hub_index}",
            email=f"hub{hub_index}@example.com",
            national_id=f"999{hub_index}0000000",
        )
        start_account = 1 + hub_index * accounts_per_hub
        end_account = min(start_account + accounts_per_hub - 1, account_count)
        for batch_start, batch_end in batched_ranges(end_account - start_account + 1, batch_size):
            batch = [
                {"account_id": f"ACC-{i}"}
                for i in range(start_account + batch_start - 1, start_account + batch_end - 1 + 1)
            ]
            session.run(
                "UNWIND $batch AS row "
                "MATCH (c:Customer {id: $hub_id}), (a:Account {id: row.account_id}) "
                "CREATE (c)-[:CONTROLS]->(a)",
                batch=batch,
                hub_id=hub_id,
            )


def create_transactions_edges(session, transaction_count: int, account_count: int, batch_size: int) -> None:
    for start, end in batched_ranges(transaction_count, batch_size):
        batch = []
        for i in range(start, end + 1):
            sender_num = (i * 3) % account_count + 1
            raw_receiver_num = (i * 7) % account_count + 1
            receiver_num = (
                (raw_receiver_num % account_count) + 1
                if raw_receiver_num == sender_num
                else raw_receiver_num
            )
            batch.append(
                {
                    "txn_id": f"TXN-{i}",
                    "sender_id": f"ACC-{sender_num}",
                    "receiver_id": f"ACC-{receiver_num}",
                }
            )
        session.run(
            "UNWIND $batch AS row "
            "MATCH (t:Transaction {id: row.txn_id}), "
            "(sender:Account {id: row.sender_id}), "
            "(receiver:Account {id: row.receiver_id}) "
            "CREATE (sender)-[:SENT]->(t) "
            "CREATE (t)-[:RECEIVED_BY]->(receiver)",
            batch=batch,
        )


def generate(uri: str, user: str, password: str, database: str, total_nodes: int, batch_size: int) -> None:
    customer_count, account_count, transaction_count = compute_counts(total_nodes)
    driver = GraphDatabase.driver(uri, auth=(user, password))
    try:
        with driver.session(database=database) as session:
            session.run("MATCH (n) DETACH DELETE n")
            create_constraints(session)

            started = time.monotonic()
            create_customers(session, customer_count, batch_size)
            create_accounts(session, account_count, batch_size)
            create_transactions(session, transaction_count, batch_size)
            create_owns(session, account_count, customer_count, batch_size)
            create_hubs(session, account_count, batch_size)
            create_transactions_edges(session, transaction_count, account_count, batch_size)
            elapsed = time.monotonic() - started

            result = session.run("MATCH (n) RETURN count(n) AS n")
            actual_count = result.single()["n"]
            print(f"Requested {total_nodes} nodes, created {actual_count}, took {elapsed:.1f}s")
    finally:
        driver.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nodes", type=int, required=True, help="Target total node count")
    parser.add_argument("--batch-size", type=int, default=10000)
    parser.add_argument("--uri", required=True)
    parser.add_argument("--user", default="neo4j")
    parser.add_argument("--password", required=True)
    parser.add_argument("--database", default="neo4j")
    args = parser.parse_args()

    generate(
        uri=args.uri,
        user=args.user,
        password=args.password,
        database=args.database,
        total_nodes=args.nodes,
        batch_size=args.batch_size,
    )


if __name__ == "__main__":
    main()