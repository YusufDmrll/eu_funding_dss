import unittest
from datetime import date, timedelta
from unittest.mock import patch

from core.watchlist import (
    build_watchlist_report,
    flatten_watchlist_rows,
    render_watchlist_markdown,
    status_at_least,
)


def _future_deadline(days: int = 120) -> str:
    return (date.today() + timedelta(days=days)).isoformat()


class WatchlistTests(unittest.TestCase):
    def test_status_order_is_client_facing(self) -> None:
        self.assertTrue(status_at_least("Strong match", "Worth reviewing"))
        self.assertTrue(status_at_least("Worth reviewing", "Worth reviewing"))
        self.assertFalse(status_at_least("Needs more detail", "Worth reviewing"))

    @patch("core.watchlist.execute_retrieval")
    def test_watchlist_report_marks_new_reviewable_calls(self, mock_retrieval) -> None:
        mock_retrieval.return_value = {
            "retrieval_mode_used": "semantic",
            "warning": None,
            "results": [
                {
                    "call_id": "NEW-CALL",
                    "call_title": "Critical raw materials recycling and recovery",
                    "topic_title": "Critical raw materials recycling and recovery",
                    "program": "Horizon Europe",
                    "cluster": "Cluster 4",
                    "description": "Critical raw materials, recycling, recovery, processing, and secondary raw materials.",
                    "objectives": "Improve European secondary raw-material supply.",
                    "expected_impact": "Reduce dependencies on imported strategic materials.",
                    "deadline_utc": _future_deadline(),
                    "source_url": "https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/opportunities/topic-details/NEW-CALL",
                    "similarity_score": 0.66,
                    "strategic_success_index": 74.0,
                    "match_confidence_label": "Reliable",
                    "theme_coherence": {
                        "coherence_level": "strong",
                        "shared_themes": ["critical_materials_circularity"],
                        "guardrails": [],
                        "max_client_status": "Strong match",
                    },
                    "strategic_success_components": {"trl_alignment": 50.0},
                    "consortium_required": "",
                    "match_explanation": "Relevant because it targets critical raw-material recovery and recycling.",
                }
            ],
        }
        items = [
            {
                "id": "critical",
                "title": "Critical materials watch",
                "theme": "critical materials",
                "project_description": (
                    "We are developing a European project to recover rare earth and critical raw materials "
                    "from industrial waste through recycling, processing, and secondary raw-material validation."
                ),
                "country": "Netherlands",
                "organisation_type": "SME",
            }
        ]

        report = build_watchlist_report(items, previous_call_ids={"OLD-CALL"}, top_k=1)
        result = report["evaluations"][0]["results"][0]

        self.assertEqual(result["review_status"], "Strong match")
        self.assertTrue(result["is_new_call"])
        self.assertEqual(report["summary"]["new_reviewable_top_results"], 1)
        self.assertEqual(report["summary"]["watchlist_items_with_new_reviewable_results"], 1)

        markdown = render_watchlist_markdown(report)
        self.assertIn("Gillis Watchlist Match Report", markdown)
        self.assertIn("Critical materials watch", markdown)
        self.assertIn("NEW-CALL", markdown)
        self.assertNotIn("funding probability", markdown.split("## Critical materials watch")[1].lower())

        rows = flatten_watchlist_rows(report)
        self.assertEqual(rows[0]["call_id"], "NEW-CALL")
        self.assertEqual(rows[0]["is_new_call"], True)

    @patch("core.watchlist.execute_retrieval")
    def test_watchlist_report_handles_empty_results(self, mock_retrieval) -> None:
        mock_retrieval.return_value = {
            "retrieval_mode_used": "semantic",
            "warning": None,
            "results": [],
        }
        report = build_watchlist_report(
            [
                {
                    "id": "empty",
                    "title": "Empty watch",
                    "project_description": "A detailed port energy project with shore power and harbour infrastructure.",
                }
            ],
            previous_call_ids=set(),
            top_k=3,
        )

        self.assertEqual(report["evaluations"][0]["results"], [])
        self.assertEqual(report["summary"]["new_reviewable_top_results"], 0)
        self.assertIn("No current active/upcoming matches", render_watchlist_markdown(report))


if __name__ == "__main__":
    unittest.main()
