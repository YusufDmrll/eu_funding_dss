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
from scripts.promote_active_call_library import _sha256  # noqa: E402


MAIN_CSV = PROJECT_ROOT / "data" / "imports" / "calls_seed_clean.csv"
SQLITE_DB = PROJECT_ROOT / "data" / "eu_funding.sqlite"
REFRESH_LOG = PROJECT_ROOT / "data" / "evaluation_outputs" / "call_library_refresh_log.json"
AUDIT_OUTPUT = PROJECT_ROOT / "data" / "evaluation_outputs" / "dataset_audit_summary.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _relative(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def _command(label: str, command: list[str], *, allowed_returncodes: set[int] | None = None) -> dict[str, Any]:
    return {
        "label": label,
        "command": command,
        "allowed_returncodes": sorted(allowed_returncodes or {0}),
    }


def build_refresh_commands(args: argparse.Namespace) -> list[dict[str, Any]]:
    python = sys.executable
    commands = [
        _command(
            "Fetch active/upcoming EU Funding Portal records",
            [
                python,
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
            ],
        ),
        _command(
            "Review and rank Gillis-relevant candidates",
            [
                python,
                "scripts/review_eu_expansion_candidates.py",
                "--max-candidates",
                str(args.max_candidates),
                "--minimum-score",
                str(args.minimum_score),
            ],
        ),
        _command(
            "Enrich candidates from official evidence",
            [
                python,
                "scripts/enrich_eu_promotion_candidates.py",
                *(["--skip-live-api"] if args.skip_live_api else []),
            ],
        ),
        _command(
            "Promote active library candidate set",
            [
                python,
                "scripts/promote_active_call_library.py",
                "--target-active",
                str(args.target_active),
                *(["--apply"] if args.apply else []),
            ],
            allowed_returncodes={0, 2},
        ),
    ]

    if args.apply:
        commands.extend(
            [
                _command("Rebuild SQLite schema", [python, "scripts/init_db.py"]),
                _command("Import refreshed active library into SQLite", [python, "scripts/import_calls.py", "--replace"]),
                _command(
                    "Audit refreshed active library",
                    [
                        python,
                        "scripts/audit_dataset.py",
                        str(MAIN_CSV),
                        "--output",
                        str(AUDIT_OUTPUT),
                    ],
                ),
            ]
        )

    if args.qa in {"quick", "full"}:
        commands.append(
            _command("Run unit tests", [python, "-m", "unittest", "discover", "-s", "tests"])
        )
    if args.qa == "full":
        commands.extend(
            [
                _command("Run semantic stack check", [python, "scripts/check_semantic_stack.py"]),
                _command(
                    "Run Gillis retrieval quality audit",
                    [python, "scripts/run_gillis_retrieval_quality_audit.py"],
                ),
            ]
        )
    return commands


def _run_step(step: dict[str, Any]) -> dict[str, Any]:
    completed = subprocess.run(
        step["command"],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    allowed = set(step.get("allowed_returncodes") or [0])
    return {
        "label": step["label"],
        "command": step["command"],
        "returncode": completed.returncode,
        "ok": completed.returncode in allowed,
        "warning": completed.returncode != 0 and completed.returncode in allowed,
        "stdout_tail": completed.stdout[-5000:],
        "stderr_tail": completed.stderr[-5000:],
    }


def run_refresh(args: argparse.Namespace) -> dict[str, Any]:
    started_at = _utc_now()
    before_hashes = {
        "main_csv": _sha256(MAIN_CSV),
        "sqlite": _sha256(SQLITE_DB),
    }
    before_audit = audit_dataset(MAIN_CSV) if MAIN_CSV.exists() else {}
    commands = build_refresh_commands(args)
    step_results: list[dict[str, Any]] = []

    for step in commands:
        result = _run_step(step)
        step_results.append(result)
        if not result["ok"]:
            break

    after_hashes = {
        "main_csv": _sha256(MAIN_CSV),
        "sqlite": _sha256(SQLITE_DB),
    }
    after_audit = audit_dataset(MAIN_CSV) if MAIN_CSV.exists() else {}
    payload = {
        "generated_at_utc": _utc_now(),
        "started_at_utc": started_at,
        "mode": "apply" if args.apply else "preview",
        "target_active": args.target_active,
        "qa_level": args.qa,
        "official_source": "EU Funding & Tenders Search API",
        "safety": {
            "main_csv": _relative(MAIN_CSV),
            "sqlite": _relative(SQLITE_DB),
            "main_dataset_modified": before_hashes["main_csv"] != after_hashes["main_csv"],
            "sqlite_modified": before_hashes["sqlite"] != after_hashes["sqlite"],
            "backups_are_created_by_promotion_step": bool(args.apply),
            "uncertain_metadata_policy": "Leave TRL, eligibility, consortium, partner, and budget fields blank unless official evidence supports them.",
        },
        "hashes": {
            "before": before_hashes,
            "after": after_hashes,
        },
        "audit": {
            "before": {
                "total_rows": before_audit.get("total_rows"),
                "counts": before_audit.get("counts", {}),
            },
            "after": {
                "total_rows": after_audit.get("total_rows"),
                "counts": after_audit.get("counts", {}),
            },
        },
        "steps": step_results,
        "ok": all(step["ok"] for step in step_results),
        "warnings": [step["label"] for step in step_results if step.get("warning")],
        "next_steps": [
            "If this was a preview, review the generated staging/candidate files before applying.",
            "If this was applied in GitHub Actions, review and merge the generated pull request.",
            "After merging, Streamlit Cloud redeploys from the updated CSV and SQLite files.",
        ],
    }
    _write_json(args.log, payload)
    return payload


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "One-command safe refresh for the active EU call library. Preview mode prepares staging "
            "and promotion candidates only; apply mode backs up, promotes, imports SQLite, and can run QA."
        )
    )
    parser.add_argument("--target-active", type=int, default=300)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--page-size", type=int, default=100)
    parser.add_argument("--max-pages", type=int, default=30)
    parser.add_argument("--theme-threshold", type=int, default=2)
    parser.add_argument("--max-candidates", type=int, default=260)
    parser.add_argument("--minimum-score", type=int, default=40)
    parser.add_argument("--skip-live-api", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--qa", choices=["none", "quick", "full"], default="none")
    parser.add_argument("--log", type=Path, default=REFRESH_LOG)
    return parser


def main() -> int:
    args = _parser().parse_args()
    payload = run_refresh(args)
    print("EU call library refresh")
    print(f"Mode: {payload['mode']}")
    print(f"Target active records: {payload['target_active']}")
    print(f"OK: {payload['ok']}")
    print(f"Warnings: {payload['warnings']}")
    print(f"Rows before: {payload['audit']['before']['total_rows']}")
    print(f"Rows after: {payload['audit']['after']['total_rows']}")
    print(f"Main CSV modified: {payload['safety']['main_dataset_modified']}")
    print(f"SQLite modified: {payload['safety']['sqlite_modified']}")
    print(f"Log: {args.log}")
    for step in payload["steps"]:
        status = "OK" if step["ok"] else "FAILED"
        if step.get("warning"):
            status = "WARNING"
        print(f"- {status}: {step['label']} (code {step['returncode']})")
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
