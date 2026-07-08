import unittest
from datetime import date

from core.deadlines import (
    CLOSING_SOON,
    EXPIRED,
    INVALID_DEADLINE,
    OPEN_OR_UPCOMING,
    UNKNOWN_DEADLINE,
    classify_deadline,
    classify_deadline_window,
    build_deadline_urgency,
    days_until_deadline,
)


class DeadlineTests(unittest.TestCase):
    def test_classifies_deadlines(self) -> None:
        today = date(2026, 6, 11)

        self.assertEqual(classify_deadline("2026-06-10T15:00:00Z", today), EXPIRED)
        self.assertEqual(classify_deadline("2026-06-11", today), OPEN_OR_UPCOMING)
        self.assertEqual(classify_deadline("2027-01-01", today), OPEN_OR_UPCOMING)
        self.assertEqual(classify_deadline("", today), UNKNOWN_DEADLINE)
        self.assertEqual(classify_deadline(None, today), UNKNOWN_DEADLINE)
        self.assertEqual(classify_deadline("6", today), INVALID_DEADLINE)

    def test_deadline_window_marks_near_active_calls_as_closing_soon(self) -> None:
        today = date(2026, 6, 11)

        self.assertEqual(days_until_deadline("2026-08-01", today), 51)
        self.assertEqual(classify_deadline_window("2026-08-01", today), CLOSING_SOON)
        self.assertEqual(classify_deadline_window("2027-01-01", today), OPEN_OR_UPCOMING)
        self.assertEqual(classify_deadline_window("2026-06-10", today), EXPIRED)
        self.assertEqual(classify_deadline_window("not-a-date", today), INVALID_DEADLINE)

    def test_deadline_urgency_provides_actionable_labels(self) -> None:
        today = date(2026, 6, 11)

        urgent = build_deadline_urgency("2026-06-20", today)
        closing = build_deadline_urgency("2026-07-05", today)
        review = build_deadline_urgency("2026-08-30", today)
        normal = build_deadline_urgency("2027-01-01", today)

        self.assertEqual(urgent["urgency"], "urgent")
        self.assertEqual(urgent["short_text"], "Closes in 9 days")
        self.assertIn("immediately", urgent["action"])
        self.assertEqual(closing["label"], "Closing soon")
        self.assertEqual(review["label"], "Review timing soon")
        self.assertFalse(normal["needs_attention"])

    def test_deadline_urgency_handles_missing_and_invalid_values(self) -> None:
        missing = build_deadline_urgency("", date(2026, 6, 11))
        invalid = build_deadline_urgency("6", date(2026, 6, 11))

        self.assertEqual(missing["urgency"], "needs_confirmation")
        self.assertEqual(invalid["label"], "Deadline needs confirmation")


if __name__ == "__main__":
    unittest.main()
