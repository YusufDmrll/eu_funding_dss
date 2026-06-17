import unittest
from datetime import date

from core.dataset_status import calculate_dataset_status


class DatasetStatusTests(unittest.TestCase):
    def test_calculates_deadline_and_metadata_counts(self) -> None:
        records = [
            {
                "deadline_utc": "2027-01-01T15:00:00Z",
                "eligible_countries": "EU member states",
                "eligible_org_types": "SMEs",
                "trl_min": 4,
                "trl_max": 7,
            },
            {
                "deadline_utc": "2025-01-01",
                "eligible_countries": "",
                "eligible_org_types": None,
                "trl_min": None,
                "trl_max": "",
            },
            {
                "deadline_utc": "",
                "eligible_countries": "Associated countries",
                "eligible_org_types": "Universities",
                "trl_min": 2,
                "trl_max": None,
            },
            {
                "deadline_utc": "6",
                "eligible_countries": None,
                "eligible_org_types": "Companies",
                "trl_min": "",
                "trl_max": 8,
            },
        ]

        status = calculate_dataset_status(records, today=date(2026, 6, 11))

        self.assertEqual(status["total_records"], 4)
        self.assertEqual(status["open_or_upcoming_records"], 1)
        self.assertEqual(status["expired_records"], 1)
        self.assertEqual(status["unknown_deadline_records"], 1)
        self.assertEqual(status["invalid_deadline_records"], 1)
        self.assertEqual(status["missing_eligible_countries"], 2)
        self.assertEqual(status["missing_eligible_org_types"], 1)
        self.assertEqual(status["missing_trl_min"], 2)
        self.assertEqual(status["missing_trl_max"], 2)

    def test_empty_dataset_returns_zero_counts(self) -> None:
        status = calculate_dataset_status([], today=date(2026, 6, 11))

        self.assertTrue(all(value == 0 for value in status.values()))


if __name__ == "__main__":
    unittest.main()
