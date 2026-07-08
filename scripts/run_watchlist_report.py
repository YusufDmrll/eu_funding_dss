import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.watchlist import (  # noqa: E402
    DEFAULT_WATCHLIST_PATH,
    build_watchlist_report,
    flatten_watchlist_rows,
    load_call_ids_from_csv,
    load_watchlist_items,
    render_watchlist_markdown,
)


OUTPUT_DIR = PROJECT_ROOT / "data" / "evaluation_outputs"
DEFAULT_JSON_OUTPUT = OUTPUT_DIR / "watchlist_report.json"
DEFAULT_MARKDOWN_OUTPUT = OUTPUT_DIR / "watchlist_report.md"
DEFAULT_CSV_OUTPUT = OUTPUT_DIR / "watchlist_report.csv"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys()) if rows else [
        "watchlist_id",
        "watchlist_title",
        "rank",
        "is_new_call",
        "review_status",
        "overall_fit",
        "relevance",
        "deadline",
        "call_id",
        "call_title",
        "why_matched",
        "status_reason",
        "next_action",
        "source_url",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def run_watchlist_report(args: argparse.Namespace) -> dict[str, Any]:
    items = load_watchlist_items(args.watchlist)
    previous_call_ids = load_call_ids_from_csv(args.previous_csv) if args.previous_csv else None
    report = build_watchlist_report(
        items,
        previous_call_ids=previous_call_ids,
        top_k=args.top_k,
        retrieval_mode=args.retrieval_mode,
        sort_by=args.sort_by,
    )
    _write_json(args.output_json, report)
    args.output_markdown.parent.mkdir(parents=True, exist_ok=True)
    args.output_markdown.write_text(render_watchlist_markdown(report), encoding="utf-8")
    _write_csv(args.output_csv, flatten_watchlist_rows(report))
    return report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run saved Gillis project themes against the current active call library. "
            "Use this after dataset refreshes to see which themes gained reviewable calls."
        )
    )
    parser.add_argument("--watchlist", type=Path, default=DEFAULT_WATCHLIST_PATH)
    parser.add_argument("--previous-csv", type=Path, default=None)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--retrieval-mode", choices=["semantic", "lexical"], default="semantic")
    parser.add_argument("--sort-by", choices=["strategic_success_index", "similarity_score"], default="strategic_success_index")
    parser.add_argument("--output-json", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--output-markdown", type=Path, default=DEFAULT_MARKDOWN_OUTPUT)
    parser.add_argument("--output-csv", type=Path, default=DEFAULT_CSV_OUTPUT)
    return parser


def main() -> int:
    args = _parser().parse_args()
    report = run_watchlist_report(args)
    summary = report["summary"]
    print("Gillis watchlist report")
    print(f"Watchlist themes: {report['watchlist_count']}")
    print(f"Retrieval modes used: {summary['retrieval_mode_counts']}")
    if report["previous_library_comparison"]:
        print(f"New reviewable top results: {summary['new_reviewable_top_results']}")
        print(f"Themes with new reviewable results: {summary['watchlist_items_with_new_reviewable_results']}")
    else:
        print("New-call comparison: not run because no previous CSV snapshot was supplied")
    print(f"JSON: {args.output_json}")
    print(f"Markdown: {args.output_markdown}")
    print(f"CSV: {args.output_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
