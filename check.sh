#!/bin/sh
uv run ruff check . || exit 1
uv run pytest || exit 1
test -z "$(git status --porcelain)" || { echo "NOT COMMITTED:"; git status --porcelain; exit 1; }
echo "ALL GREEN"
