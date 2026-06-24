#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
python3 -m delta_ratio_bot --config config.toml --health-check
