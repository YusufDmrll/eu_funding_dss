import unittest

from core.grant_assistant import (
    build_concept_note_starter,
    build_proposal_readiness_memo,
    llm_assistant_policy,
)


class GrantAssistantTests(unittest.TestCase):
    def test_concept_note_uses_theme_specific_angle(self) -> None:
        starter = build_concept_note_starter(
            {
                "call_title": "Battery-grade critical raw materials recycling",
                "description": "Circular battery materials, recycling, and raw materials processing.",
            },
            {
                "project_title": "Battery Materials Recovery",
                "project_desc": (
                    "We develop a process to recover battery materials from industrial waste, "
                    "reduce dependency, and support European manufacturing."
                ),
            },
        )

        self.assertEqual(starter["working_title"], "Battery Materials Recovery")
        self.assertIn("materials resilience", starter["call_fit_angle"])
        self.assertTrue(any("Value-chain case" in item for item in starter["proposal_outline"]))
        self.assertTrue(any("Feedstock" in item for item in starter["evidence_to_collect"]))
        self.assertTrue(starter["evidence_to_collect"])

    def test_missing_project_inputs_are_requested_without_blocking(self) -> None:
        starter = build_concept_note_starter(
            {"call_title": "Clean energy demonstration", "description": "Energy efficiency pilots."},
            {"project_desc": "Green platform."},
        )

        self.assertIn("target users or beneficiaries", starter["missing_information"])
        self.assertIn("current maturity or validation stage", starter["missing_information"])

    def test_port_energy_concept_note_focuses_on_port_deployment(self) -> None:
        starter = build_concept_note_starter(
            {
                "call_title": "Green harbour energy infrastructure",
                "description": "Shore power, port energy systems, berth electrification, and storage.",
            },
            {
                "project_desc": (
                    "We develop a shore power planning tool for port operators to reduce berth emissions "
                    "and integrate storage with renewable energy."
                )
            },
        )

        self.assertIn("port-side infrastructure", " ".join(starter["proposal_outline"]))
        self.assertTrue(any("berth" in item.lower() for item in starter["evidence_to_collect"]))
        self.assertIn("Start outreach", starter["outreach_focus"])

    def test_llm_policy_keeps_generation_disabled_until_security_is_ready(self) -> None:
        policy = llm_assistant_policy()

        self.assertEqual(policy["status"], "not_enabled")
        self.assertIn("API-key", policy["reason"])

    def test_proposal_readiness_memo_marks_well_described_project_as_structured_review_ready(self) -> None:
        memo = build_proposal_readiness_memo(
            {
                "call_title": "Green harbour energy infrastructure",
                "description": "Port energy systems, shore power, renewable integration, and demonstration.",
                "objectives": "Demonstrate port-side energy integration with operational users.",
                "expected_impact": "Reduced berth emissions and improved port energy resilience.",
                "source_url": "https://example.eu/topic",
                "trl_min": "5",
                "trl_max": "7",
                "eligible_countries": "EU Member States",
                "eligible_org_types": "SME; Large company; Research organisation",
                "consortium_required": "1",
                "budget_min_eur": "1000000",
                "similarity_score": 0.42,
                "strategic_success_index": 76,
            },
            {
                "project_desc": (
                    "The problem is high berth emissions and grid congestion in European ports. "
                    "We develop a shore power optimisation solution for port operators and energy providers, "
                    "with a pilot validation plan at TRL 6 to reduce emissions and improve resilience."
                )
            },
        )

        self.assertEqual(memo["readiness_level"], "Ready for structured review")
        self.assertTrue(memo["strongest_starting_points"])
        self.assertTrue(any("official" in action.lower() for action in memo["first_actions"]))
        self.assertTrue(any("port-side use case" in item.lower() for item in memo["preparation_focus"]))
        self.assertTrue(any("operator" in item.lower() for item in memo["preparation_focus"]))

    def test_proposal_readiness_memo_stays_cautious_when_metadata_and_project_detail_are_missing(self) -> None:
        memo = build_proposal_readiness_memo(
            {
                "call_title": "Clean energy innovation",
                "description": "Energy transition topic.",
                "similarity_score": 0.09,
                "strategic_success_index": 32,
            },
            {"project_desc": "Green platform."},
        )

        self.assertEqual(memo["readiness_level"], "Early concept - add detail before proposal work")
        self.assertTrue(memo["main_gaps"])
        self.assertTrue(memo["preparation_focus"])
        self.assertIn("official", memo["source_caution"].lower())


if __name__ == "__main__":
    unittest.main()
