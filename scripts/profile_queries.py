#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.environ["APP_PASSWORD"] = "performance-audit-only"
os.environ["SECRET_KEY"] = "performance-audit-only"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from app.services.performance_audit import (
    build_audit_artifacts,
    create_performance_fixture,
    run_audit_suite,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Profile NSFWTrack queries against disposable SQLite fixtures."
    )
    parser.add_argument(
        "--sizes",
        nargs="+",
        type=int,
        default=[100, 1000, 10000],
        help="Item counts for disposable fixtures (default: 100 1000 10000).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional JSON output path. Results are printed when omitted.",
    )
    return parser


def run(sizes: list[int]) -> dict[str, Any]:
    if not sizes or any(size <= 0 for size in sizes):
        raise ValueError("all sizes must be positive")
    datasets: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="nsfwtrack-performance-") as temp_dir:
        for size in sizes:
            database_path = Path(temp_dir) / f"audit-{size}.db"
            engine = create_engine(
                f"sqlite:///{database_path}",
                connect_args={"check_same_thread": False},
                future=True,
            )
            try:
                fixture = create_performance_fixture(engine, size)
                artifacts = build_audit_artifacts(engine, size)
                results = run_audit_suite(engine, artifacts, dataset_size=size)
                datasets.append(
                    {
                        "size": size,
                        "fixture": fixture,
                        "results": [result.to_dict() for result in results],
                    }
                )
            finally:
                engine.dispose()
    return {
        "schema": "nsfwtrack.performance-audit.v1",
        "sizes": sizes,
        "temporary_databases_removed": True,
        "datasets": datasets,
    }


def main() -> None:
    args = _parser().parse_args()
    report = run(args.sizes)
    rendered = json.dumps(report, ensure_ascii=True, indent=2)
    if args.output:
        args.output.write_text(f"{rendered}\n", encoding="utf-8")
        print(args.output)
    else:
        print(rendered)


if __name__ == "__main__":
    main()
