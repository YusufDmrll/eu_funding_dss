import unittest
from unittest.mock import patch

from scripts.run_retrieval_evaluation import build_evaluation_report, load_evaluation_cases


class RetrievalEvaluationWorkflowTests(unittest.TestCase):
    def test_evaluation_dataset_loads_expected_cases(self) -> None:
        cases = load_evaluation_cases()

        self.assertEqual(len(cases), 7)
        self.assertEqual(cases[0]["eval_id"], "EVAL-01")
        self.assertIn("must_have_signals", cases[0])
        self.assertIn("likely_false_positive_patterns", cases[0])

    @patch("scripts.run_retrieval_evaluation._build_mode_output")
    def test_report_structure_is_manual_review_friendly(self, mock_mode_output) -> None:
        mock_mode_output.return_value = {
            "mode_requested": "lexical",
            "mode_used": "lexical",
            "mode_label_used": "Lexical (TF-IDF)",
            "warning": None,
            "results": [
                {
                    "call_id": "HE-001",
                    "call_title": "Energy Efficiency Call",
                    "program": "Horizon Europe",
                    "cluster": "Climate",
                    "deadline_utc": "2026-10-01",
                    "similarity_score": 0.21,
                    "strategic_fit_score": 74.5,
                    "confidence": "Reliable",
                    "eligibility": "Partially Eligible",
                    "why_this_matched": "Direct overlap in energy and efficiency terms.",
                }
            ],
        }

        report = build_evaluation_report(
            [
                {
                    "eval_id": "EVAL-01",
                    "theme": "green_energy",
                    "project_title": "Test title",
                    "project_description": "Test description",
                    "expected_fit_notes": "Expected notes",
                    "must_have_signals": ["energy"],
                    "likely_false_positive_patterns": ["generic ICT"],
                }
            ]
        )

        evaluation = report["evaluations"][0]
        self.assertEqual(evaluation["ranking_basis"], "strategic_success_index")
        self.assertIn("lexical", evaluation)
        self.assertIn("semantic", evaluation)
        self.assertIn("manual_review", evaluation)
        self.assertEqual(evaluation["manual_review"]["better_mode"], "")


if __name__ == "__main__":
    unittest.main()
