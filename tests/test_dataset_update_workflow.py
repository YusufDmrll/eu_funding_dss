import argparse
import unittest
from pathlib import Path

from scripts.run_dataset_update_workflow import build_workflow_plan


class DatasetUpdateWorkflowTests(unittest.TestCase):
    def test_workflow_plan_keeps_main_dataset_changes_manual(self) -> None:
        plan = build_workflow_plan(argparse.Namespace(fetch=True, review=True))

        automatic_main_changes = [
            step
            for step in plan
            if step["automatic"] and step["modifies_main_dataset"]
        ]

        self.assertEqual(automatic_main_changes, [])
        self.assertTrue(any(step["automatic"] for step in plan))
        self.assertTrue(any(step["modifies_main_dataset"] for step in plan))

    def test_fetch_and_review_are_opt_in(self) -> None:
        plan = build_workflow_plan(argparse.Namespace(fetch=False, review=False))

        fetch_step = next(step for step in plan if "Fetch broad" in step["name"])
        review_step = next(step for step in plan if "Review recommended" in step["name"])

        self.assertFalse(fetch_step["automatic"])
        self.assertFalse(review_step["automatic"])

    def test_github_refresh_workflow_uses_one_command_refresh_with_300_target(self) -> None:
        workflow = Path(".github/workflows/monthly-dataset-refresh.yml").read_text(encoding="utf-8")

        self.assertIn("scripts/refresh_call_library.py", workflow)
        self.assertIn("scripts/run_watchlist_report.py", workflow)
        self.assertIn("watchlist_report.md", workflow)
        self.assertIn('default: "300"', workflow)
        self.assertIn("--apply", workflow)
        self.assertIn('--qa "$QA_LEVEL"', workflow)
        self.assertIn("gh pr create", workflow)


if __name__ == "__main__":
    unittest.main()
