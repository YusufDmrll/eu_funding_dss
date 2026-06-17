import unittest

from core.input_quality import (
    NON_PROJECT_INPUT_WARNING,
    WEAK_INPUT_GUIDANCE,
    evaluate_project_description,
    evaluate_project_intent,
)


class InputQualityTests(unittest.TestCase):
    def test_meaningful_project_description_passes_validation(self) -> None:
        result = evaluate_project_description(
            "We are building a digital platform to help manufacturing SMEs improve "
            "energy efficiency through analytics, monitoring, and operational guidance."
        )

        self.assertTrue(result["is_valid"])
        self.assertIn(result["quality_level"], {"broad", "detailed"})

    def test_very_short_or_random_text_fails_validation(self) -> None:
        short_result = evaluate_project_description("abc xyz")
        random_result = evaluate_project_description("!!! 123 @@")

        self.assertFalse(short_result["is_valid"])
        self.assertFalse(short_result["can_screen"])
        self.assertFalse(random_result["is_valid"])
        self.assertFalse(random_result["can_screen"])

    def test_dutch_and_turkish_latin_descriptions_pass_validation(self) -> None:
        dutch_result = evaluate_project_description(
            "Wij ontwikkelen een digitaal platform voor energie efficientie in productiebedrijven "
            "met voorspellende analyses en praktische dashboards."
        )
        turkish_result = evaluate_project_description(
            "Sanayi KOBI'lerinin enerji verimliligini artirmak icin analitik ve karar destek "
            "panolari sunan dijital bir platform gelistiriyoruz."
        )

        self.assertTrue(dutch_result["is_valid"])
        self.assertTrue(turkish_result["is_valid"])

    def test_short_valid_description_is_marked_broad(self) -> None:
        result = evaluate_project_description(
            "A digital platform supports regional innovation partners and project collaboration."
        )

        self.assertTrue(result["is_valid"])
        self.assertTrue(result["is_broad"])
        self.assertEqual(result["quality_level"], "broad")
        self.assertTrue(result["needs_more_detail"])
        self.assertEqual(result["guidance_message"], WEAK_INPUT_GUIDANCE)

    def test_meaningful_short_input_can_run_with_guardrails(self) -> None:
        result = evaluate_project_description(
            "Port energy lowers vessel emissions"
        )

        self.assertFalse(result["is_valid"])
        self.assertTrue(result["can_screen"])
        self.assertEqual(result["quality_level"], "insufficient")
        self.assertTrue(result["needs_more_detail"])

    def test_detailed_input_does_not_request_more_detail(self) -> None:
        result = evaluate_project_description(
            "We are developing a pilot process to recover rare earth elements from industrial "
            "and electronic waste. The technology combines selective separation, material "
            "traceability, and quality validation with European manufacturing partners. It is "
            "intended for recycling operators and industrial supply chains, and aims to reduce "
            "dependence on imported critical materials while increasing high-quality secondary "
            "raw material use across Europe."
        )

        self.assertTrue(result["is_valid"])
        self.assertTrue(result["can_screen"])
        self.assertEqual(result["quality_level"], "detailed")
        self.assertFalse(result["needs_more_detail"])
        self.assertEqual(result["guidance_message"], "")

    def test_codex_log_style_input_is_detected_as_non_project(self) -> None:
        result = evaluate_project_intent(
            "Codex output. Files changed: scripts/enrich.py and tests/test_enrichment.py. "
            "Processed 50 records. Validation: 59 tests passed. SQLite hash unchanged."
        )

        self.assertTrue(result["is_likely_non_project"])
        self.assertFalse(result["is_project_like"])
        self.assertEqual(result["project_intent_warning"], NON_PROJECT_INPUT_WARNING)

    def test_detailed_project_with_validation_language_is_not_falsely_flagged(self) -> None:
        result = evaluate_project_description(
            "We are developing a shore-power energy management solution for European ports. "
            "Port authorities and terminal operators will use it to coordinate grid demand, "
            "battery storage, and vessel charging. The project will validate the technology "
            "in two operational ports and reduce emissions from ships at berth."
        )

        self.assertFalse(result["is_likely_non_project"])
        self.assertTrue(result["is_project_like"])


if __name__ == "__main__":
    unittest.main()
