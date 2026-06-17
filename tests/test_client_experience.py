import unittest

from core.client_experience import (
    build_call_strategy,
    build_review_status_reason,
    build_theme_aware_caution,
    is_internal_mode,
    port_side_call_classification,
    prioritize_client_results,
)


class ClientExperienceTests(unittest.TestCase):
    def test_internal_mode_is_off_by_default_and_explicit_when_enabled(self) -> None:
        self.assertFalse(is_internal_mode({}))
        self.assertTrue(is_internal_mode({"EU_FUNDING_INTERNAL_MODE": "true"}))

    def test_port_side_project_promotes_direct_harbour_call(self) -> None:
        ship_side = {
            "call_id": "SHIP",
            "call_title": "Onboard renewable energy solutions for ships",
            "topic_title": "Onboard renewable energy solutions for ships",
            "description": "Improve ship propulsion and reduce fuel consumption of ships.",
        }
        harbour = {
            "call_id": "PORT",
            "call_title": "Green, circular and resilient harbours",
            "topic_title": "Green, circular and resilient harbours",
            "description": "Deploy systemic solutions in ports with port authorities.",
        }

        ordered = prioritize_client_results(
            [ship_side, harbour],
            "A shore power and berth energy project for port authorities and terminal operators.",
        )

        self.assertEqual(ordered[0]["call_id"], "PORT")
        self.assertEqual(port_side_call_classification(ship_side), "ship_side_adjacent")
        self.assertEqual(port_side_call_classification(harbour), "direct_port_side")

    def test_non_port_project_keeps_retrieval_order(self) -> None:
        results = [{"call_id": "A"}, {"call_id": "B"}]
        self.assertEqual(
            prioritize_client_results(results, "A rare earth recycling process."),
            results,
        )

    def test_status_reason_explains_ship_side_scope(self) -> None:
        reason = build_review_status_reason(
            {"theme_coherence": {"guardrails": ["port_side_scope_mismatch"]}},
            "Worth reviewing",
            input_quality={"quality_level": "detailed"},
        )
        self.assertIn("ship-side", reason)

    def test_strong_match_reason_uses_human_language(self) -> None:
        reason = build_review_status_reason(
            {
                "similarity_score": 0.66,
                "theme_coherence": {
                    "shared_themes": ["critical_materials_circularity"],
                    "guardrails": [],
                },
            },
            "Strong match",
            input_quality={"quality_level": "detailed"},
        )

        self.assertIn("direct critical materials", reason)
        self.assertNotIn("text relevance", reason.lower())
        self.assertNotIn("priority review", reason.lower())

    def test_call_strategy_is_cautious_when_metadata_is_missing(self) -> None:
        strategy = build_call_strategy(
            {
                "match_explanation": "Relevant to port energy.",
                "theme_coherence": {
                    "shared_themes": ["port_energy_hydrogen"],
                    "coherence_level": "strong",
                    "guardrails": [],
                },
                "data_quality_flags": [
                    "Country eligibility details are missing or incomplete.",
                    "Organisation type details are missing or incomplete.",
                ],
                "consortium_required": None,
                "strategic_success_components": {"trl_alignment": 50.0},
            },
            {
                "project_desc": (
                    "We are developing a shore power solution for port authorities that will reduce "
                    "emissions and improve European harbour resilience through an operational pilot."
                ),
                "user_trl": None,
                "has_consortium": False,
            },
        )

        self.assertTrue(any("eligibility" in item.lower() for item in strategy["clarifications"]))
        self.assertTrue(any("consortium" in item.lower() for item in strategy["next_steps"]))
        self.assertLessEqual(len(strategy["next_steps"]), 4)

    def test_green_energy_strategy_does_not_leak_recycling_language(self) -> None:
        result = {
            "call_title": "Clean technologies for climate action",
            "description": (
                "Industrial clean energy, renewable electricity, energy efficiency, storage readiness, "
                "and emissions reduction for manufacturing sites."
            ),
            "theme_coherence": {
                "shared_themes": ["port_energy_hydrogen"],
                "coherence_level": "strong",
                "guardrails": [],
            },
            "strategic_success_components": {"trl_alignment": 100.0},
            "consortium_required": 0,
        }
        project_inputs = {
            "project_desc": (
                "A green energy project for an industrial SME using renewable electricity, energy "
                "management, storage readiness, and industrial decarbonisation."
            ),
            "user_trl": None,
            "has_consortium": False,
        }

        strategy = build_call_strategy(result, project_inputs)
        caution = build_theme_aware_caution(result, project_inputs)
        combined = " ".join(strategy["next_steps"] + [caution or ""]).lower()

        self.assertIn("energy", combined)
        self.assertNotIn("recycling", combined)
        self.assertNotIn("recovery", combined)
        self.assertNotIn("substitution", combined)

    def test_wind_energy_strategy_uses_energy_language(self) -> None:
        result = {
            "call_title": "Innovative technologies and solutions to improve wind energy systems",
            "description": (
                "Wind energy systems, clean technologies, climate action, grid integration, "
                "storage readiness, and emissions reduction."
            ),
            "theme_coherence": {
                "shared_themes": ["sme_startup_ecosystem"],
                "coherence_level": "moderate",
                "guardrails": [],
            },
            "strategic_success_components": {"trl_alignment": 100.0},
            "consortium_required": 0,
        }
        project_inputs = {
            "project_desc": (
                "A green energy project for an industrial SME using renewable integration, "
                "storage readiness, energy efficiency, and industrial decarbonisation."
            ),
            "user_trl": None,
            "has_consortium": False,
        }

        strategy = build_call_strategy(result, project_inputs)
        combined = " ".join(strategy["next_steps"]).lower()

        self.assertIn("energy", combined)
        self.assertIn("decarbonisation", combined)
        self.assertNotIn("critical-infrastructure protection", combined)

    def test_security_strategy_does_not_leak_port_or_circularity_language(self) -> None:
        result = {
            "call_title": "Enhancing physical protection of critical infrastructures",
            "description": (
                "Critical infrastructure protection, cyber-physical security, threat detection, "
                "risk assessment, and operational resilience."
            ),
            "theme_coherence": {
                "shared_themes": ["security_resilience_infrastructure"],
                "coherence_level": "strong",
                "guardrails": [],
            },
            "strategic_success_components": {"trl_alignment": 100.0},
            "consortium_required": 0,
        }
        project_inputs = {
            "project_desc": (
                "A security innovation project for critical port and energy infrastructure focused "
                "on threat detection, cyber-physical risk, and emergency preparedness."
            ),
            "user_trl": None,
            "has_consortium": False,
        }

        strategy = build_call_strategy(result, project_inputs)
        caution = build_theme_aware_caution(result, project_inputs)
        combined = " ".join(strategy["next_steps"] + [caution or ""]).lower()

        self.assertIn("security", combined)
        self.assertNotIn("recycling", combined)
        self.assertNotIn("circular", combined)
        self.assertNotIn("shore", combined)

    def test_port_shore_power_strategy_can_use_port_language_when_supported(self) -> None:
        result = {
            "call_title": "Green, circular and resilient harbours",
            "description": (
                "Port authorities, harbour infrastructure, shore power, port energy systems, "
                "electrification, and emissions reduction."
            ),
            "theme_coherence": {
                "shared_themes": ["port_energy_hydrogen", "maritime_ports_logistics"],
                "coherence_level": "strong",
                "guardrails": [],
            },
            "strategic_success_components": {"trl_alignment": 100.0},
            "consortium_required": 0,
        }
        project_inputs = {
            "project_desc": (
                "A shore power and green harbour project for port authorities and terminal operators."
            ),
            "user_trl": None,
            "has_consortium": False,
        }

        strategy = build_call_strategy(result, project_inputs)
        caution = build_theme_aware_caution(result, project_inputs)
        combined = " ".join(strategy["next_steps"] + [caution or ""]).lower()

        self.assertTrue(any(term in combined for term in ("port", "harbour", "energy")))


if __name__ == "__main__":
    unittest.main()
