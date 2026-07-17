"""
Runs the fraud-ring Example CQ library (examples/fraud-ring-cqs.yml)
against a live fixture graph, verifying each query actually returns
results matching its declared `expect` shape. This is what proves the
CQ library is genuinely runnable, not just plausible-looking YAML.

10 CQs total: cq-001 to cq-004 + cq-002-regression (Jayachandra),
cq-005 to cq-008 + cq-009-regression (Janani).
"""

import pathlib

import pytest
import yaml

FIXTURE_ID = "fraud-ring"

CQ_LIBRARY_PATH = (
    pathlib.Path(__file__).parent.parent / "examples" / "fraud-ring-cqs.yml"
)


def _load_cqs() -> list[dict]:
    with CQ_LIBRARY_PATH.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data["competency"]


def _cq_ids():
    return [cq["id"] for cq in _load_cqs()]


@pytest.mark.parametrize("cq", _load_cqs(), ids=_cq_ids())
def test_cq_matches_declared_shape(neo4j_driver, cq):
    """Runs a single CQ's query and checks the result against its
    declared expect block: row count range, expected columns, uniqueness
    on the identifying column, and (for regression overlays) specific
    pinned values."""
    with neo4j_driver.session() as session:
        result = session.run(cq["query"], **cq["params"])
        records = [dict(record) for record in result]

    expect = cq["expect"]

    if "columns" in expect:
        expected_columns = set(expect["columns"])
        for record in records:
            assert set(record.keys()) == expected_columns, (
                f"{cq['id']}: expected columns {expected_columns}, "
                f"got {set(record.keys())}"
            )

    if "rows" in expect:
        row_bounds = expect["rows"]
        assert row_bounds["min"] <= len(records) <= row_bounds["max"], (
            f"{cq['id']}: expected {row_bounds['min']}-{row_bounds['max']} rows, "
            f"got {len(records)}"
        )

    if expect.get("unique") and "columns" in expect:
        # Only the first declared column is checked for uniqueness (the
        # identifying column, by convention). Other columns in a
        # multi-column result (e.g. a count or a flag) are legitimately
        # allowed to repeat across rows.
        identifying_col = expect["columns"][0]
        values = [record[identifying_col] for record in records]
        assert len(values) == len(set(values)), (
            f"{cq['id']}: expected unique values in identifying column "
            f"'{identifying_col}', found duplicates"
        )

    if "contains" in expect:
        columns = list(records[0].keys()) if records else []
        assert len(columns) == 1, (
            f"{cq['id']}: 'contains' assertions expect a single-column "
            f"result, got columns {columns}"
        )
        actual_values = {record[columns[0]] for record in records} if records else set()
        for expected_value in expect["contains"]:
            assert expected_value in actual_values, (
                f"{cq['id']}: expected value '{expected_value}' not found "
                f"in results {actual_values}"
            )