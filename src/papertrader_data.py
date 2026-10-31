"""Read identity (including optional research_role) and assessments at one revision."""

import json
import logging
import os
import re
from pathlib import Path
from urllib.request import Request, urlopen

from registry import read_securities

REPOSITORY = "Kabutojira/PaperTrader"


def fetch_text(url):
    request = Request(
        url,
        headers={
            "User-Agent": "FinanceAlerts",
            "Accept": "application/vnd.github+json",
        },
    )
    with urlopen(request, timeout=30) as response:
        data = response.read(5_000_001)
    if len(data) > 5_000_000:
        raise ValueError("PaperTrader response exceeds size limit")
    return data.decode("utf-8-sig")


def load_snapshot(directory=None, revision=None):
    directory = directory or os.environ.get("PAPERTRADER_DIR")
    if directory:
        tables = Path(directory) / "data" / "tables"
        securities = (tables / "securities.csv").read_text()
        assessments = (
            (tables / "security_assessments.csv").read_text()
            if (tables / "security_assessments.csv").exists()
            else ""
        )
        return read_securities(securities), assessments
    revision = revision or os.environ.get("PAPERTRADER_REVISION")
    if not revision:
        revision = json.loads(
            fetch_text(f"https://api.github.com/repos/{REPOSITORY}/commits/main")
        )["sha"]
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("PAPERTRADER_REVISION must be a full commit SHA")
    base = f"https://raw.githubusercontent.com/{REPOSITORY}/{revision}/data/tables"
    securities = read_securities(fetch_text(f"{base}/securities.csv"))
    try:
        assessments = fetch_text(f"{base}/security_assessments.csv")
    except (OSError, ValueError) as error:
        logging.warning("PaperTrader assessments unavailable: %s", error)
        assessments = ""
    logging.info("PaperTrader snapshot: %s", revision)
    return securities, assessments
