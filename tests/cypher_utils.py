"""
Safe Cypher statement splitting.

Splits a block of Cypher source into individual statements, correctly
ignoring semicolons and comment markers that appear inside string
literals or backtick-quoted identifiers, and stripping full-line,
inline, and block comments -- without ever cutting a statement in the
middle of a string, identifier, or comment.

This exists as its own module (rather than inline in conftest.py) so it
can be unit tested directly, independent of any live Neo4j container.
"""


def _trailing_backslash_count(chars: list[str]) -> int:
    """Count consecutive backslashes at the end of the characters
    accumulated so far. Needed to correctly tell an escaped quote
    (odd number of backslashes, e.g. \\') from an escaped backslash
    immediately followed by a real closing quote (even number, e.g.
    \\\\'). Checking only the single preceding character (as an
    earlier version of this function did) gets \\\\' wrong -- it looks
    like an escaped quote but is actually an escaped backslash plus a
    real close.
    """
    count = 0
    idx = len(chars) - 1
    while idx >= 0 and chars[idx] == "\\":
        count += 1
        idx -= 1
    return count


def split_statements(cypher_text: str) -> list[str]:
    """Split Cypher source into a list of individual statement strings.

    Walks the text one character at a time, tracking whether we're
    currently inside a single-quoted string, double-quoted string,
    backtick-quoted identifier, or a /* block comment */. A semicolon,
    `//`, or `/*` encountered while inside any of these is treated as
    ordinary text, not a statement terminator or comment start.

    Backticks are Cypher's syntax for quoting identifiers (labels,
    property names, variable names) that contain characters like spaces
    or semicolons that would otherwise be ambiguous -- e.g. `Legacy;Customer`.
    Content inside backticks must never be treated as a statement
    separator or comment marker, same as content inside a string literal.

    Stripping a block comment inserts a single space in its place
    rather than nothing, so removing a comment sitting directly between
    two tokens (e.g. `1/* note */AS`) can't accidentally weld them into
    one invalid token (`1AS`).
    """
    statements = []
    current = []
    in_single_quote = False
    in_double_quote = False
    in_backtick = False
    in_block_comment = False
    i = 0
    length = len(cypher_text)

    while i < length:
        char = cypher_text[i]
        next_char = cypher_text[i + 1] if i + 1 < length else ""

        if in_block_comment:
            if char == "*" and next_char == "/":
                in_block_comment = False
                current.append(" ")
                i += 2
                continue
            i += 1
            continue

        if in_single_quote:
            if char == "'" and _trailing_backslash_count(current) % 2 == 0:
                in_single_quote = False
            current.append(char)
            i += 1
            continue

        if in_double_quote:
            if char == '"' and _trailing_backslash_count(current) % 2 == 0:
                in_double_quote = False
            current.append(char)
            i += 1
            continue

        if in_backtick:
            current.append(char)
            if char == "`":
                in_backtick = False
            i += 1
            continue

        if char == "'":
            in_single_quote = True
            current.append(char)
            i += 1
            continue

        if char == '"':
            in_double_quote = True
            current.append(char)
            i += 1
            continue

        if char == "`":
            in_backtick = True
            current.append(char)
            i += 1
            continue

        if char == "/" and next_char == "*":
            in_block_comment = True
            i += 2
            continue

        if char == "/" and next_char == "/":
            while i < length and cypher_text[i] != "\n":
                i += 1
            continue

        if char == ";":
            stmt = "".join(current).strip()
            if stmt:
                statements.append(stmt)
            current = []
            i += 1
            continue

        current.append(char)
        i += 1

    tail = "".join(current).strip()
    if tail:
        statements.append(tail)

    return statements