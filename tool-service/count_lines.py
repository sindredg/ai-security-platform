"""Counts the server's lines of code and fails past the limit.

ADR 0016 gives small a number: the server without its tools. A line counts
when it holds code. Blank lines, comments, and docstrings do not count. The
tools directory and the tests are not the server.

Usage: count_lines.py LIMIT FILE...
"""

import ast
import sys
import tokenize


def code_lines(path):
    with open(path, "rb") as handle:
        tree = ast.parse(handle.read())
    docstrings = set()
    for node in ast.walk(tree):
        if not isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            continue
        first = node.body[0] if node.body else None
        if isinstance(first, ast.Expr) and isinstance(
            getattr(first.value, "value", None), str
        ):
            docstrings.update(range(first.lineno, first.end_lineno + 1))
    skip = {
        tokenize.COMMENT,
        tokenize.NL,
        tokenize.NEWLINE,
        tokenize.INDENT,
        tokenize.DEDENT,
        tokenize.ENCODING,
        tokenize.ENDMARKER,
    }
    lines = set()
    with open(path, "rb") as handle:
        for token in tokenize.tokenize(handle.readline):
            if token.type not in skip:
                lines.update(range(token.start[0], token.end[0] + 1))
    return len(lines - docstrings)


def main():
    limit, paths = int(sys.argv[1]), sys.argv[2:]
    if not paths:
        sys.exit("no files to count")
    total = 0
    for path in paths:
        count = code_lines(path)
        total += count
        print(f"{count:5d}  {path}")
    print(f"{total:5d}  total, limit {limit}")
    if total > limit:
        sys.exit(f"the server is {total - limit} lines over the limit")


if __name__ == "__main__":
    main()
