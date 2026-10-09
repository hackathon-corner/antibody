import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from adapters.check_worker import FIXTURE_FILE, SUITE_FILE, suite_hash

TARGET = json.loads((ROOT / "config" / "targets" / "juice-shop.json").read_text(encoding="utf-8"))


def test_pinned_suite_files_are_the_ones_the_worker_runs():
    pinned = [ROOT / p for p in TARGET["check_suite"]["files"]]
    assert pinned == [SUITE_FILE, FIXTURE_FILE]


def test_pinned_suite_hash_matches_checkout():
    assert suite_hash() == TARGET["check_suite"]["sha256"]
