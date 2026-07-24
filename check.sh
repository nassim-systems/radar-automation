#!/bin/sh
uv run ruff check . || exit 1
uv run pytest || exit 1
test -z "$(git status --porcelain)" || { echo "NON COMMITÉ :"; git status --porcelain; exit 1; }
echo "TOUT VERT"
