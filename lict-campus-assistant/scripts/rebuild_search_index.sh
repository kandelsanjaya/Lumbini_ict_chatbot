#!/usr/bin/env bash
# Rebuilds data/chunks.json from the current data/data.json knowledge base.
set -e
cd "$(dirname "$0")/.."
python -m src.tools.search_index
echo "Rebuilt data/chunks.json"
