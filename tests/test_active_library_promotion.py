import unittest

from scripts.expand_dataset_from_eu_api import CSV_COLUMNS
from scripts.promote_active_call_library import _select_candidates, _split_main_records


def _record(call_id: str, deadline: str, **overrides: str) -> dict[str, str]:
    record = {column: "" for column in CSV_COLUMNS}
    record.update(
        {
            "call_id": call_id,
            "program": "Horizon Europe",
            "call_title": f"Call {call_id}",
            "topic_title": f"Topic {call_id}",
            "description": "A sufficiently detailed official topic description for testing.",
            "deadline_utc": deadline,
            "source_url": f"https://example.eu/{call_id}",
        }
    )
    record.update(overrides)
    return record


class ActiveLibraryPromotionTests(unittest.TestCase):
    def test_split_main_records_archives_non_active_deadlines(self):
        active, archived, counts = _split_main_records(
            [
                _record("ACTIVE", "2099-01-01T17:00:00Z"),
                _record("EXPIRED", "2020-01-01T17:00:00Z"),
                _record("INVALID", "not-a-date"),
            ]
        )

        self.assertEqual([record["call_id"] for record in active], ["ACTIVE"])
        self.assertEqual({record["call_id"] for record in archived}, {"EXPIRED", "INVALID"})
        self.assertEqual(counts["open_or_upcoming"], 1)
        self.assertEqual(counts["expired"], 1)
        self.assertEqual(counts["invalid_deadline"], 1)

    def test_select_candidates_filters_existing_expired_and_incomplete_records(self):
        selected, skipped = _select_candidates(
            [
                _record("EXISTING", "2099-01-01T17:00:00Z"),
                _record("EXPIRED", "2020-01-01T17:00:00Z"),
                _record("NO_SOURCE", "2099-01-01T17:00:00Z", source_url=""),
                _record("GOOD", "2099-01-01T17:00:00Z"),
            ],
            existing_ids={"EXISTING"},
            needed=2,
        )

        self.assertEqual([record["call_id"] for record in selected], ["GOOD"])
        self.assertEqual(skipped["duplicate_or_existing_call_id"], 1)
        self.assertEqual(skipped["expired"], 1)
        self.assertEqual(skipped["missing_required_field"], 1)

    def test_select_candidates_adds_nothing_when_target_is_already_reached(self):
        selected, skipped = _select_candidates(
            [_record("NEW", "2099-01-01T17:00:00Z")],
            existing_ids={"EXISTING"},
            needed=0,
        )

        self.assertEqual(selected, [])
        self.assertEqual(skipped["not_needed_after_target_reached"], 1)


if __name__ == "__main__":
    unittest.main()
