import unittest
from unittest.mock import patch

from core.retrieval import END_USER_RETRIEVAL_FALLBACK_NOTE, execute_retrieval
from core import semantic_retrieval


def build_test_record() -> dict:
    return {
        "call_id": "HE-TEST-001",
        "program": "Horizon Europe",
        "pillar": "Pillar II",
        "cluster": "Climate",
        "call_title": "AI for Energy Efficiency",
        "topic_title": "Topic",
        "description": "Energy efficiency and AI tools for industry.",
        "objectives": "Improve industrial efficiency through analytics.",
        "expected_impact": "Lower energy use and emissions.",
        "action_type": "RIA",
        "deadline_utc": "2099-10-01",
        "budget_min_eur": 1000000,
        "budget_max_eur": 3000000,
        "trl_min": 4,
        "trl_max": 6,
        "eligible_countries": "EU member states and associated countries",
        "eligible_org_types": "SMEs, universities, research organisations",
        "consortium_required": 0,
        "min_partners": 1,
        "keywords": "energy, efficiency, ai, industry",
        "source_url": "https://example.com",
        "source_last_checked_utc": "2026-04-01",
        "verified_status": "preliminary",
    }


class RetrievalTests(unittest.TestCase):
    def tearDown(self) -> None:
        semantic_retrieval.load_semantic_runtime.cache_clear()
        semantic_retrieval._load_numpy_module.cache_clear()
        semantic_retrieval._load_sentence_transformer_class.cache_clear()
        semantic_retrieval._load_model.cache_clear()
        semantic_retrieval._encode_call_texts.cache_clear()

    @patch("core.retrieval.fetch_call_records")
    @patch("core.retrieval._compute_lexical_similarities")
    @patch("core.retrieval._compute_semantic_similarities")
    def test_semantic_retrieval_falls_back_to_lexical_safely(
        self,
        mock_semantic,
        mock_lexical,
        mock_fetch_records,
    ) -> None:
        mock_fetch_records.return_value = [build_test_record()]
        mock_semantic.side_effect = RuntimeError("semantic backend unavailable")
        mock_lexical.return_value = [0.21]

        execution = execute_retrieval(
            project_text="AI platform for industrial energy efficiency and analytics.",
            retrieval_mode="semantic",
            allow_semantic_fallback=True,
        )

        self.assertEqual(execution["retrieval_mode_used"], "lexical")
        self.assertEqual(execution["warning"], END_USER_RETRIEVAL_FALLBACK_NOTE)
        self.assertEqual(execution["results"][0]["similarity_score"], 0.21)

    @patch("core.retrieval.fetch_call_records")
    @patch("core.retrieval._compute_semantic_similarities")
    def test_semantic_retrieval_preserves_result_structure(
        self,
        mock_semantic,
        mock_fetch_records,
    ) -> None:
        mock_fetch_records.return_value = [build_test_record()]
        mock_semantic.return_value = [0.31]

        execution = execute_retrieval(
            project_text="AI platform for industrial energy efficiency and analytics.",
            retrieval_mode="semantic",
            allow_semantic_fallback=False,
        )

        result = execution["results"][0]
        self.assertEqual(execution["retrieval_mode_used"], "semantic")
        self.assertIsNone(execution["warning"])
        self.assertIn("eligibility_status", result)
        self.assertIn("strategic_success_index", result)
        self.assertIn("match_explanation", result)
        self.assertIn("theme_coherence", result)
        self.assertEqual(result["similarity_score"], 0.31)

    @patch("core.retrieval.fetch_call_records")
    @patch("core.retrieval._compute_lexical_similarities")
    @patch("core.semantic_retrieval.import_module")
    def test_semantic_dependency_import_failure_falls_back_without_crashing(
        self,
        mock_import_module,
        mock_lexical,
        mock_fetch_records,
    ) -> None:
        mock_fetch_records.return_value = [build_test_record()]
        mock_lexical.return_value = [0.19]

        def fake_import(name: str):
            if name == "sentence_transformers":
                raise OSError("torch DLL load failed")
            if name == "numpy":
                import numpy
                return numpy
            if name in {"sklearn", "torch"}:
                return object()
            raise ImportError(name)

        mock_import_module.side_effect = fake_import

        execution = execute_retrieval(
            project_text="AI platform for industrial energy efficiency and analytics.",
            retrieval_mode="semantic",
            allow_semantic_fallback=True,
        )

        self.assertEqual(execution["retrieval_mode_used"], "lexical")
        self.assertEqual(execution["warning"], END_USER_RETRIEVAL_FALLBACK_NOTE)
        self.assertEqual(execution["results"][0]["similarity_score"], 0.19)

    @patch("core.semantic_retrieval.import_module")
    def test_semantic_runtime_uses_deterministic_import_order(self, mock_import_module) -> None:
        torch_module = object()
        sentence_transformers_module = object()

        def fake_import(name: str):
            return {
                "sklearn": object(),
                "torch": torch_module,
                "sentence_transformers": sentence_transformers_module,
            }[name]

        mock_import_module.side_effect = fake_import

        runtime = semantic_retrieval.load_semantic_runtime()

        self.assertEqual(runtime, (torch_module, sentence_transformers_module))
        self.assertEqual(
            [call.args[0] for call in mock_import_module.call_args_list],
            ["sklearn", "torch", "sentence_transformers"],
        )

    @patch("core.retrieval.fetch_call_records")
    @patch("core.retrieval._compute_lexical_similarities")
    def test_expired_calls_are_excluded_by_default(self, mock_lexical, mock_fetch_records) -> None:
        expired = build_test_record()
        expired["call_id"] = "HE-EXPIRED"
        expired["deadline_utc"] = "2020-01-01"
        active = build_test_record()
        active["call_id"] = "HE-ACTIVE"
        mock_fetch_records.return_value = [expired, active]
        mock_lexical.return_value = [0.24]

        execution = execute_retrieval(
            project_text="Industrial energy efficiency project",
            retrieval_mode="lexical",
        )

        self.assertEqual([result["call_id"] for result in execution["results"]], ["HE-ACTIVE"])
        self.assertEqual(execution["results"][0]["deadline_status"], "open_or_upcoming")

    @patch("core.retrieval.fetch_call_records")
    @patch("core.retrieval._compute_lexical_similarities")
    def test_include_expired_true_includes_archived_calls(self, mock_lexical, mock_fetch_records) -> None:
        expired = build_test_record()
        expired["call_id"] = "HE-EXPIRED"
        expired["deadline_utc"] = "2020-01-01"
        active = build_test_record()
        active["call_id"] = "HE-ACTIVE"
        mock_fetch_records.return_value = [expired, active]
        mock_lexical.return_value = [0.25, 0.20]

        execution = execute_retrieval(
            project_text="Industrial energy efficiency project",
            retrieval_mode="lexical",
            include_expired=True,
        )

        result_ids = {result["call_id"] for result in execution["results"]}
        self.assertEqual(result_ids, {"HE-EXPIRED", "HE-ACTIVE"})

    @patch("core.retrieval.fetch_call_records")
    @patch("core.retrieval._compute_lexical_similarities")
    def test_invalid_deadline_does_not_crash_or_hide_call(self, mock_lexical, mock_fetch_records) -> None:
        invalid = build_test_record()
        invalid["call_id"] = "HE-INVALID"
        invalid["deadline_utc"] = "6"
        mock_fetch_records.return_value = [invalid]
        mock_lexical.return_value = [0.18]

        execution = execute_retrieval(
            project_text="Industrial energy efficiency project",
            retrieval_mode="lexical",
        )

        self.assertEqual(execution["results"][0]["call_id"], "HE-INVALID")
        self.assertEqual(execution["results"][0]["deadline_status"], "invalid_deadline")


if __name__ == "__main__":
    unittest.main()
