import unittest

from core.explanations import build_safe_match_explanation, generate_match_explanation


class MatchExplanationTests(unittest.TestCase):
    def test_match_explanation_uses_overlap_fields(self) -> None:
        explanation = generate_match_explanation(
            "We are building an energy efficiency platform for manufacturing SMEs with analytics.",
            {
                "call_title": "Energy Efficiency Solutions for Manufacturing",
                "description": "Support analytics for industrial efficiency improvements.",
                "objectives": "Improve manufacturing sustainability and energy use.",
                "expected_impact": "",
                "keywords": "energy efficiency, manufacturing SMEs, industrial emissions",
            },
        )

        self.assertIn("Relevant because", explanation)
        self.assertIn("energy efficiency", explanation)
        self.assertNotIn("through", explanation)
        self.assertNotIn("developing", explanation)

    def test_safe_match_explanation_returns_fallback_when_no_overlap_exists(self) -> None:
        explanation = build_safe_match_explanation(
            "abc",
            {
                "call_title": None,
                "description": None,
                "objectives": None,
                "expected_impact": None,
                "keywords": None,
            },
        )

        self.assertIn("should be reviewed manually", explanation)

    def test_log_style_input_uses_cautious_explanation(self) -> None:
        explanation = generate_match_explanation(
            "Files changed and 59 tests passed. Processed 50 funding records. "
            "Validation completed and SQLite hash unchanged.",
            {
                "call_title": "EU funding metadata validation",
                "description": "Official evidence and eligibility records for consortium funding.",
                "objectives": "Validate metadata and source records.",
                "expected_impact": "",
                "keywords": "official evidence, metadata, validation, records",
            },
        )

        self.assertIn("broad EU funding terminology", explanation)
        self.assertIn("treated carefully", explanation)

    def test_generic_log_terms_are_not_used_as_match_signals(self) -> None:
        explanation = generate_match_explanation(
            "Our project will improve port resilience. Additional metadata validation records "
            "and source files support the work.",
            {
                "call_title": "Port infrastructure resilience",
                "description": "Improve resilient port infrastructure and terminal operations.",
                "objectives": "Strengthen port resilience.",
                "expected_impact": "",
                "keywords": "port resilience, metadata validation, official source",
            },
        )

        self.assertIn("port", explanation.lower())
        for generic_term in ("metadata", "validation", "official", "source", "files"):
            self.assertNotIn(generic_term, explanation.lower())

    def test_port_explanation_requires_port_context_in_call(self) -> None:
        explanation = generate_match_explanation(
            "Green hydrogen and energy infrastructure for an industrial port and vessel operations.",
            {
                "call_title": "Delivery of industrial CCUS clusters",
                "description": "Carbon capture, storage infrastructure, industrial energy, and emissions reduction.",
                "objectives": "Deploy carbon capture infrastructure for industry.",
                "expected_impact": "Lower industrial emissions.",
                "keywords": "CCUS, carbon capture, industrial energy",
            },
        )

        self.assertNotIn("shore-side", explanation)
        self.assertNotIn("berth", explanation)
        self.assertIn("explicit hydrogen relevance is not clear", explanation)

    def test_battery_material_explanation_avoids_token_dump(self) -> None:
        explanation = generate_match_explanation(
            "Recover imported battery materials and reduce dependency in European supply chains.",
            {
                "call_title": (
                    "Producing battery-grade materials for electrodes through sustainable "
                    "processing and refining of raw materials"
                ),
                "description": "Battery-grade electrode materials and raw-material processing.",
                "objectives": "Reduce dependency on imported battery-grade raw materials.",
                "expected_impact": "",
                "keywords": "critical raw materials; batteries; processing",
            },
        )

        self.assertIn("battery-grade materials", explanation)
        self.assertNotIn("dependency imported battery", explanation)


if __name__ == "__main__":
    unittest.main()
