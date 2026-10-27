#!/usr/bin/env python3
"""Rebuild the local SQLite catalogue and emit a factual data-quality report."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import dawaling_core as core

parser = argparse.ArgumentParser()
parser.add_argument("--force", action="store_true", help="Rebuild SQLite even when the source file is unchanged")
args = parser.parse_args()
result = core.ensure_database(force=args.force)
out = core.ROOT / "data" / "processed"
out.mkdir(parents=True, exist_ok=True)
report_path = out / "data_quality_report.json"
report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(result, ensure_ascii=False, indent=2))
print(f"Data quality report: {report_path.relative_to(core.ROOT)}")
