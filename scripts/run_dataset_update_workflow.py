import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.audit_dataset import audit_dataset  # noqa: E402


MAIN_CSV = PROJECT_ROOT / "data" / "imports" / "calls_seed_clean.csv"
DATABASE = PROJECT_ROOT / "data" / "eu_funding.sqlite"
EXPANSION_LOG = PROJECT_ROOT / "data" / "evaluation_outputs" / "eu_dataset_expansion_log.json"
PROMOTION_CANDIDATES = PROJECT_ROOT / "data" / "imports" / "eu_calls_promotion_candidates.csv"
WORKFLOW_LOG = PROJECT_ROOT / "data" / "evaluation_outputs" / "dataset_update_workflow_log.json"


def _run_command(command: list[str]) -> dict[str, Any]:
    completed = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return {
        "command": command,
        "returncode": completed.returncode,
        "stdout_tail": completed.stdout[-4000:],
        "stderr_tail": completed.stderr[-4000:],
        "ok": completed.returncode == 0,
    }


def build_workflow_plan(args: argparse.Namespace) -> list[dict[str, Any]]:
    steps = [
        {
            "name": "Audit current curated dataset",
            "automatic": True,
            "modifies_main_dataset": False,
        },
        {
            "name": "Fetch broad active/upcoming EU API pool into staging",
            "automatic": bool(args.fetch),
            "modifies_main_dataset": False,
        },
        {
            "name": "Review recommended expansion records into promotion candidates",
            "automatic": bool(args.review),
            "modifies_main_dataset": False,
        },
        {
            "name": "Manual enrichment and promotion approval",
            "automatic": False,
            "modifies_main_dataset": True,
        },
        {
            "name": "Promote active library with backups and expired-call archive",
            "automatic": False,
            "modifies_main_dataset": True,
        },
        {
            "name": "Re-import SQLite after explicit promotion",
            "automatic": False,
            "modifies_main_dataset": True,
        },
    ]
    return steps


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the safe EU Funding dataset update workflow. The script can fetch and review "
            "candidate records, but it never modifies calls_seed_clean.csv or SQLite directly."
        )
    )
    parser.add_argument("--fetch", action="store_true", help="Fetch/update staging and recommended expansion files.")
    parser.add_argument("--review", action="store_true", help="Build promotion candidates from the recommended expansion file.")
    parser.add_argument("--limit", type=int, default=0, help="Maximum API records to fetch; 0 means no explicit limit.")
    parser.add_argument("--page-size", type=int, default=100)
    parser.add_argument("--max-pages", type=int, default=8)
    parser.add_argument("--theme-threshold", type=int, default=4)
    parser.add_argument("--max-candidates", type=int, default=220)
    parser.add_argument("--minimum-score", type=int, default=40)
    parser.add_argument("--write-log", action="store_true", help="Write a workflow JSON report.")
    return parser


def main() -> int:
    args = _parser().parse_args()
    started = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    command_results: list[dict[str, Any]] = []
    current_audit = audit_dataset(MAIN_CSV)

    if args.fetch:
        command_results.append(
            _run_command(
                [
                    sys.executable,
                    "scripts/expand_dataset_from_eu_api.py",
                    "--limit",
                    str(args.limit),
                    "--page-size",
                    str(args.page_size),
                    "--max-pages",
                    str(args.max_pages),
                    "--theme-threshold",
                    str(args.theme_threshold),
                    "--write-staging",
                    "--write-recommended",
                ]
            )
        )

    if args.review:
        command_results.append(
            _run_command(
                [
                    sys.executable,
                    "scripts/review_eu_expansion_candidates.py",
                    "--max-candidates",
                    str(args.max_candidates),
                    "--minimum-score",
                    str(args.minimum_score),
                ]
            )
        )

    promotion_audit = audit_dataset(PROMOTION_CANDIDATES) if PROMOTION_CANDIDATES.exists() else None
    payload = {
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "started_at_utc": started,
        "safety": {
            "main_csv": str(MAIN_CSV.relative_to(PROJECT_ROOT)),
            "sqlite": str(DATABASE.relative_to(PROJECT_ROOT)),
            "main_dataset_modified_by_this_script": False,
            "promotion_requires_manual_approval": True,
        },
        "plan": build_workflow_plan(args),
        "current_dataset_audit": current_audit,
        "promotion_candidate_audit": promotion_audit,
        "command_results": command_results,
        "next_manual_steps": [
            "Review promotion candidates and enrichment evidence.",
            "Run scripts/enrich_eu_promotion_candidates.py before promotion when metadata enrichment is needed.",
            "Run scripts/refresh_call_library.py --target-active 300 --skip-live-api --apply --qa full after audit passes.",
            "Run scripts/import_calls.py --replace and the full test suite after promotion.",
            "Run scripts/run_gillis_retrieval_quality_audit.py before client use.",
        ],
    }

    if args.write_log:
        _write_json(WORKFLOW_LOG, payload)

    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if all(result.get("ok", True) for result in command_results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
