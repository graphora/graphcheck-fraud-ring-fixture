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
    text = "MERGE (n {id: 'a;b'})"
    result = split_statements(text)
    assert result == ["MERGE (n {id: 'a;b'})"]


def test_semicolon_inside_double_quoted_string_is_not_a_split_point():
    text = 'MERGE (n {id: "a;b"})'
    result = split_statements(text)
    assert result == ['MERGE (n {id: "a;b"})']


def test_inline_comment_containing_semicolon_is_stripped_not_split():
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


def test_block_comment_containing_semicolon_is_not_a_split_point():
    text = "MATCH (n) /* comment; still comment */ RETURN n;"
    result = split_statements(text)
    assert result == ["MATCH (n)   RETURN n"]


def test_backtick_quoted_identifier_containing_semicolon_is_not_a_split_point():
    text = "CREATE (n:`Legacy;Customer`);"
    result = split_statements(text)
    assert result == ["CREATE (n:`Legacy;Customer`)"]


def test_block_comment_spanning_multiple_lines_is_stripped():
    text = "MATCH (n)\n/* this is\na multi-line\ncomment; with semicolons */\nRETURN n;"
    result = split_statements(text)
    assert len(result) == 1
    assert "RETURN n" in result[0]
    assert "comment" not in result[0]


def test_removing_block_comment_preserves_token_boundary():
    """Exact case Ezhil reported: stripping a block comment sitting
    directly between two tokens must not weld them together. Deleting
    '/* comment; */' with nothing in its place would turn '1/* ... */AS'
    into the invalid '1AS'; a space must be inserted instead."""
    text = "RETURN 1/* comment; */AS value;"
    result = split_statements(text)
    assert result == ["RETURN 1 AS value"]


def test_escaped_backslash_before_quote_close_is_handled():
    """Exact case Ezhil reported: 'abc\\\\' (an escaped backslash
    followed by a real closing quote) must close the string normally,
    not be mistaken for an escaped quote. Checking only the single
    preceding character gets this wrong; parity of consecutive
    backslashes must be checked instead."""
    text = "RETURN 'abc\\\\'; RETURN 2;"
    result = split_statements(text)
    assert result == ["RETURN 'abc\\\\'", "RETURN 2"]


def test_single_backslash_before_quote_keeps_string_open():
    """Regression guard for the fix above: a genuinely escaped quote
    (single backslash, odd parity) must still keep the string open, so
    a semicolon after it is NOT treated as a statement separator."""
    text = "RETURN 'abc\\'; RETURN n;"
    result = split_statements(text)
    assert len(result) == 1
    assert result[0] == text.strip()