"""
Unit tests for the safe Cypher statement splitter.

These run with zero dependencies (no Neo4j, no Docker) since they only
test string parsing logic in isolation.
"""

from cypher_utils import split_statements


def test_splits_simple_statements():
    text = "MATCH (n) RETURN n; MATCH (m) RETURN m;"
    result = split_statements(text)
    assert result == ["MATCH (n) RETURN n", "MATCH (m) RETURN m"]


def test_semicolon_inside_single_quoted_string_is_not_a_split_point():
    """This is the exact case Ezhil flagged: 'a;b' must not be split."""
    text = "MERGE (n {id: 'a;b'})"
    result = split_statements(text)
    assert result == ["MERGE (n {id: 'a;b'})"]


def test_semicolon_inside_double_quoted_string_is_not_a_split_point():
    text = 'MERGE (n {id: "a;b"})'
    result = split_statements(text)
    assert result == ['MERGE (n {id: "a;b"})']


def test_inline_comment_containing_semicolon_is_stripped_not_split():
    """The other case Ezhil flagged: an inline // comment with a semicolon
    inside it must not fracture the statement."""
    text = "MATCH (n) RETURN n // comment; with a semicolon\n"
    result = split_statements(text)
    assert result == ["MATCH (n) RETURN n"]


def test_full_line_comment_is_stripped():
    text = "// just a comment\nMATCH (n) RETURN n;"
    result = split_statements(text)
    assert result == ["MATCH (n) RETURN n"]


def test_multiple_statements_with_mixed_strings_and_comments():
    text = (
        "// header comment\n"
        "MERGE (a {id: 'x;y'}) // inline; comment\n"
        "MERGE (b {id: \"p;q\"});\n"
        "MATCH (n) RETURN n;"
    )
    result = split_statements(text)
    assert len(result) == 2
    assert "MERGE (a {id: 'x;y'})" in result[0]
    assert "MERGE (b {id: \"p;q\"})" in result[0]
    assert result[1] == "MATCH (n) RETURN n"


def test_empty_input_returns_no_statements():
    assert split_statements("") == []
    assert split_statements("   \n  ") == []


def test_trailing_statement_without_final_semicolon_is_still_captured():
    text = "MATCH (n) RETURN n"
    result = split_statements(text)
    assert result == ["MATCH (n) RETURN n"]