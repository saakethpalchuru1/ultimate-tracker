#!/usr/bin/env bash
# Render build hook for the cron service. Plain Python deps, no Chromium.
set -euo pipefail
pip install --upgrade pip
pip install -r requirements.txt
