import unittest
from datetime import date

from scripts.audit_dataset import classify_deadline, detect_encoding_artifacts, is_valid_date


class DatasetAuditHelperTests(unittest.TestCase):
    def test_is_valid_date_accepts_iso_date_and_datetime(self) -> None:
        self.assertTrue(is_valid_date("2027-03-30"))
        self.assertTrue(is_valid_date("2027-03-30T15:00:00Z"))

    def test_is_valid_date_rejects_missing_and_numeric_values(self) -> None:
        self.assertFalse(is_valid_date(""))
        self.assertFalse(is_valid_date("6"))
        self.assertFalse(is_valid_date("not-a-date"))

    def test_detect_encoding_artifacts_returns_detected_markers(self) -> None:
        artifacts = detect_encoding_artifacts("TÃ¼rkiye â€” funding")

        self.assertIn("Ã", artifacts)
        self.assertIn("â€”", artifacts)
        self.assertEqual(detect_encoding_artifacts("Türkiye funding"), [])

    def test_classify_deadline_distinguishes_expired_active_and_unknown(self) -> None:
        today = date(2026, 6, 11)

        self.assertEqual(classify_deadline("2026-06-10T15:00:00Z", today), "expired")
        self.assertEqual(classify_deadline("2026-06-11", today), "active_future")
        self.assertEqual(classify_deadline("2027-01-01", today), "active_future")
        self.assertEqual(classify_deadline("6", today), "unknown")


if __name__ == "__main__":
    unittest.main()
