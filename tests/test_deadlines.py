import unittest
from datetime import date

from core.deadlines import (
    EXPIRED,
    INVALID_DEADLINE,
    OPEN_OR_UPCOMING,
    UNKNOWN_DEADLINE,
    classify_deadline,
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


if __name__ == "__main__":
    unittest.main()
