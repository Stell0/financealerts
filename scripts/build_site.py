"""Generate the static dashboard from local committed FinanceAlerts inputs only."""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dashboard import build_site


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="site/public")
    args = parser.parse_args()
    manifest = build_site(ROOT, args.output)
    available = sum(row["available"] for row in manifest["securities"])
    print(f"Built {len(manifest['securities'])} securities: {available} available; "
          f"{len(manifest['securities']) - available} unavailable. Data as of {manifest['data_as_of']}.")
