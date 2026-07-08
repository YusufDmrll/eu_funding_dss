import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from core.dataset_review import (
    CSV_COLUMNS,
    DECISION_APPROVE,
    DECISION_HOLD,
    build_review_rows,
    prepare_approval_batch,
    promotion_blockers,
    read_csv_records,
    write_approval_batch,
    write_csv_records,
)


def _record(call_id: str, *, deadline: str = "2099-01-01") -> dict[str, str]:
    record = {field: "" for field in CSV_COLUMNS}
    record.update(
        {
            "call_id": call_id,
            "program": "Horizon Europe",
            "call_title": f"Topic {call_id}",
            "topic_title": f"Topic {call_id}",
            "description": "A detailed active topic description for review and promotion.",
            "deadline_utc": deadline,
            "source_url": f"https://example.test/{call_id}",
            "source_last_checked_utc": "2026-07-01T00:00:00Z",
        }
    )
    return record


class DatasetReviewTests(unittest.TestCase):
    def test_promotion_blockers_prevent_existing_and_expired_records(self) -> None:
        existing = {"EXISTING"}

        self.assertIn(
            "already exists in main dataset",
            promotion_blockers(_record("EXISTING"), existing_call_ids=existing, today=date(2026, 7, 6)),
        )
        self.assertIn(
            "deadline is expired",
            promotion_blockers(_record("NEW", deadline="2020-01-01"), existing_call_ids=existing, today=date(2026, 7, 6)),
        )

    def test_prepare_approval_batch_keeps_only_safe_approved_records(self) -> None:
        records = [
            _record("APPROVE"),
            _record("HOLD"),
            _record("EXISTING"),
            _record("EXPIRED", deadline="2020-01-01"),
        ]
        batch = prepare_approval_batch(
            records,
            {
                "APPROVE": DECISION_APPROVE,
                "HOLD": DECISION_HOLD,
                "EXISTING": DECISION_APPROVE,
                "EXPIRED": DECISION_APPROVE,
            },
            existing_call_ids={"EXISTING"},
            today=date(2026, 7, 6),
        )

        self.assertEqual([record["call_id"] for record in batch["approved_records"]], ["APPROVE"])
        self.assertEqual(batch["summary"]["blocked"], 2)
        self.assertEqual(batch["summary"]["held_or_rejected"], 1)

    def test_build_review_rows_marks_approvable_records(self) -> None:
        rows = build_review_rows(
            [_record("NEW"), _record("EXISTING")],
            existing_call_ids={"EXISTING"},
            today=date(2026, 7, 6),
        )

        by_id = {row["call_id"]: row for row in rows}
        self.assertTrue(by_id["NEW"]["can_approve"])
        self.assertFalse(by_id["EXISTING"]["can_approve"])
        self.assertIn("already exists", by_id["EXISTING"]["blockers"])

    def test_write_approval_batch_writes_separate_csv_and_log_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source.csv"
            main = root / "main.csv"
            output = root / "approved.csv"
            log_path = root / "approval_log.json"

            write_csv_records(source, [_record("APPROVE"), _record("EXPIRED", deadline="2020-01-01")])
            write_csv_records(main, [_record("EXISTING")])
            before_main = main.read_text(encoding="utf-8-sig")

            log = write_approval_batch(
                source,
                {"APPROVE": DECISION_APPROVE, "EXPIRED": DECISION_APPROVE},
                output_path=output,
                log_path=log_path,
                main_csv_path=main,
                today=date(2026, 7, 6),
            )

            approved = read_csv_records(output)
            self.assertEqual([record["call_id"] for record in approved], ["APPROVE"])
            self.assertEqual(main.read_text(encoding="utf-8-sig"), before_main)
            self.assertFalse(log["main_dataset_modified"])
            self.assertFalse(log["sqlite_modified"])

            loaded_log = json.loads(log_path.read_text(encoding="utf-8"))
            self.assertEqual(loaded_log["summary"]["approved"], 1)
            self.assertEqual(loaded_log["summary"]["blocked"], 1)


if __name__ == "__main__":
    unittest.main()
