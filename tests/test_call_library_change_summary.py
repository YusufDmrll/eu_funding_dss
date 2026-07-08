import tempfile
import unittest
from pathlib import Path

from scripts.expand_dataset_from_eu_api import CSV_COLUMNS
from scripts.summarize_call_library_changes import render_markdown, summarize_changes, write_outputs


def _record(call_id: str, *, title: str, deadline: str = "2099-01-01T00:00:00Z", **overrides: str) -> dict[str, str]:
    record = {field: "" for field in CSV_COLUMNS}
    record.update(
        {
            "call_id": call_id,
            "program": "Horizon Europe",
            "cluster": "Cluster 5",
            "call_title": title,
            "topic_title": title,
            "description": "Official topic description for testing maritime port energy and innovation.",
            "deadline_utc": deadline,
            "source_url": f"https://example.eu/topic-details/{call_id}",
            "source_last_checked_utc": "2026-07-08T00:00:00Z",
        }
    )
    record.update(overrides)
    return record


def _write_csv(path: Path, records: list[dict[str, str]]) -> None:
    import csv

    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS, delimiter=";")
        writer.writeheader()
        for record in records:
            writer.writerow(record)


class CallLibraryChangeSummaryTests(unittest.TestCase):
    def test_summary_counts_added_removed_and_modified_records(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            before = root / "before.csv"
            after = root / "after.csv"
            _write_csv(
                before,
                [
                    _record("KEEP", title="Port energy topic"),
                    _record("REMOVE", title="Expired old topic", deadline="2020-01-01T00:00:00Z"),
                ],
            )
            _write_csv(
                after,
                [
                    _record("KEEP", title="Port energy topic", expected_impact="Updated impact."),
                    _record(
                        "ADD",
                        title="Green harbour shore power innovation",
                        description="Port harbour shore power, berth electrification, and clean energy.",
                    ),
                ],
            )

            summary = summarize_changes(before, after)

            self.assertEqual(summary["counts"]["before_rows"], 2)
            self.assertEqual(summary["counts"]["after_rows"], 2)
            self.assertEqual(summary["counts"]["added"], 1)
            self.assertEqual(summary["counts"]["removed_or_archived"], 1)
            self.assertEqual(summary["counts"]["modified_existing"], 1)
            self.assertIn("Maritime / ports / logistics", summary["added_theme_counts"])
            self.assertIn("Green energy / hydrogen", summary["added_theme_counts"])

    def test_markdown_contains_review_ready_sections(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            before = root / "before.csv"
            after = root / "after.csv"
            json_path = root / "summary.json"
            markdown_path = root / "summary.md"
            _write_csv(before, [])
            _write_csv(after, [_record("ADD", title="Critical raw materials recycling")])

            summary = summarize_changes(before, after)
            markdown = render_markdown(summary)
            write_outputs(summary, json_path, markdown_path)

            self.assertIn("Active call library change summary", markdown)
            self.assertIn("Added theme mix", markdown)
            self.assertIn("Automated quality flags", markdown)
            self.assertTrue(json_path.exists())
            self.assertTrue(markdown_path.exists())


if __name__ == "__main__":
    unittest.main()
