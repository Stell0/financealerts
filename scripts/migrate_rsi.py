"""Backfill local adjusted price CSVs; never contact Yahoo or change alert state."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from registry import read_securities
from yahoo_finance_api import migrate_caches


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", default="data")
    parser.add_argument("--securities", default="config/securities.csv")
    args = parser.parse_args()
    path = Path(args.securities)
    result = migrate_caches(args.data, read_securities(path.read_text()) if path.exists() else [])
    print(json.dumps(result, indent=2, sort_keys=True))
    sys.exit(bool(result["errors"]))
