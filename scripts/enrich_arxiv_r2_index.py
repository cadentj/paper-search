#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "beautifulsoup4>=4.12.0",
#   "boto3>=1.34.0",
#   "httpx>=0.27.0",
#   "lxml>=5.0.0",
#   "tqdm>=4.66.0",
# ]
# ///
"""Deprecated wrapper. Use scripts/migrate_arxiv_r2_index.py instead."""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from migrate_arxiv_r2_index import main

if __name__ == "__main__":
    print("Note: enrich_arxiv_r2_index.py is deprecated. Use migrate_arxiv_r2_index.py.")
    main()
