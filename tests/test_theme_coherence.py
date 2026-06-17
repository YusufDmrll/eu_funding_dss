import unittest

from core.theme_coherence import assess_theme_coherence, build_coherence_explanation


def call_record(title: str, description: str = "", keywords: str = "") -> dict:
    return {
        "call_title": title,
        "topic_title": title,
        "description": description,
        "objectives": description,
        "expected_impact": "",
        "keywords": keywords,
    }


class ThemeCoherenceTests(unittest.TestCase):
    def test_generic_ai_only_is_capped_at_needs_more_detail(self) -> None:
        result = assess_theme_coherence(
            "We want to build an innovative AI platform using data to improve services.",
            call_record("AI foundation models for energy systems", "Artificial intelligence and data sharing."),
        )

        self.assertIn("generic_digital_only", result["guardrails"])
        self.assertEqual(result["max_client_status"], "Needs more detail")

    def test_industrial_ai_is_reviewable_but_not_strong(self) -> None:
        result = assess_theme_coherence(
            "We are developing an AI tool for industrial manufacturing planning and factory automation.",
            call_record("Factory automation using artificial intelligence", "Industrial production planning."),
        )

        self.assertIn("generic_digital_only", result["guardrails"])
        self.assertEqual(result["max_client_status"], "Worth reviewing")

    def test_sme_support_does_not_strongly_match_sector_technology(self) -> None:
        result = assess_theme_coherence(
            "We are creating a support programme for clean-tech SMEs needing investment readiness and pilot customers.",
            call_record("Advanced photovoltaic production equipment", "Industrial solar manufacturing technology."),
        )

        self.assertIn("sme_support_scope_mismatch", result["guardrails"])
        self.assertEqual(result["max_client_status"], "Needs more detail")

    def test_freight_project_detects_passenger_transport_drift(self) -> None:
        result = assess_theme_coherence(
            "A maritime freight logistics platform for cargo terminals and supply chains.",
            call_record("Resilient multimodal passenger transport hubs", "Public transport and passenger mobility."),
        )

        self.assertIn("passenger_transport_drift", result["guardrails"])
        self.assertEqual(result["max_client_status"], "Needs more detail")

    def test_hydrogen_project_detects_ccus_drift(self) -> None:
        result = assess_theme_coherence(
            "Green hydrogen production and storage infrastructure for an industrial port.",
            call_record("Delivery of industrial CCUS clusters", "Carbon capture infrastructure and storage."),
        )

        self.assertIn("hydrogen_scope_drift", result["guardrails"])
        self.assertEqual(result["max_client_status"], "Needs more detail")
        self.assertIn("explicit hydrogen relevance is not clear", build_coherence_explanation(result))

    def test_explicit_hydrogen_call_is_not_marked_as_drift(self) -> None:
        result = assess_theme_coherence(
            "Green hydrogen production and storage infrastructure for an industrial port.",
            call_record("Hydrogen infrastructure for industrial clusters", "Hydrogen production and storage."),
        )

        self.assertNotIn("hydrogen_scope_drift", result["guardrails"])

    def test_port_side_project_caps_ship_side_only_call(self) -> None:
        result = assess_theme_coherence(
            "A shore power and berth energy system for port authorities and terminal operators.",
            call_record(
                "Onboard renewable energy solutions for ships",
                "Full-scale ship propulsion demonstration to reduce fuel consumption of ships.",
            ),
        )

        self.assertIn("port_side_scope_mismatch", result["guardrails"])
        self.assertEqual(result["max_client_status"], "Worth reviewing")
        self.assertIn("ship-side", build_coherence_explanation(result))

    def test_direct_harbour_call_is_not_marked_as_port_scope_mismatch(self) -> None:
        result = assess_theme_coherence(
            "A shore power and berth energy system for port authorities and terminal operators.",
            call_record(
                "Green and resilient harbours",
                "Deploy port infrastructure solutions with port authorities in operational port areas.",
            ),
        )

        self.assertNotIn("port_side_scope_mismatch", result["guardrails"])


if __name__ == "__main__":
    unittest.main()
