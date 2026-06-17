import unittest

from core.guidance import MAX_GUIDANCE_ITEMS, build_next_step_guidance


class GuidanceTests(unittest.TestCase):
    def test_guidance_is_limited_to_two_items_and_prioritized(self) -> None:
        guidance = build_next_step_guidance(
            {
                "eligibility_status": "Partially Eligible",
                "eligibility_warnings": ["Organisation type appears probably eligible."],
                "eligibility_reasons": [],
                "data_quality_flags": ["Country eligibility details are missing or incomplete."],
                "match_confidence_label": "Needs Review",
                "consortium_required": 1,
                "min_partners": 3,
                "deadline_utc": "2026-09-14T15:00:00Z",
                "strategic_success_components": {"trl_alignment": 75.0},
            },
            user_trl=4,
            has_consortium=False,
            partner_count=2,
        )

        self.assertLessEqual(len(guidance), MAX_GUIDANCE_ITEMS)
        self.assertIn("consortium", guidance[0].lower())
        self.assertTrue(
            any("deadline" in item.lower() or "work programme" in item.lower() for item in guidance)
        )

    def test_guidance_uses_cautious_trl_message_when_needed(self) -> None:
        guidance = build_next_step_guidance(
            {
                "eligibility_status": "Eligible",
                "eligibility_warnings": [],
                "eligibility_reasons": [],
                "data_quality_flags": [],
                "match_confidence_label": "Reliable",
                "consortium_required": 0,
                "min_partners": 1,
                "deadline_utc": None,
                "strategic_success_components": {"trl_alignment": 75.0},
            },
            user_trl=3,
            has_consortium=True,
            partner_count=3,
        )

        self.assertTrue(any("trl" in item.lower() for item in guidance))

    def test_guidance_avoids_generic_deadline_message_when_not_needed(self) -> None:
        guidance = build_next_step_guidance(
            {
                "eligibility_status": "Eligible",
                "eligibility_warnings": [],
                "eligibility_reasons": [],
                "data_quality_flags": [],
                "match_confidence_label": "Reliable",
                "consortium_required": 0,
                "min_partners": 1,
                "deadline_utc": "2030-12-01T15:00:00Z",
                "strategic_success_components": {"trl_alignment": 100.0},
            },
            user_trl=5,
            has_consortium=True,
            partner_count=3,
        )

        self.assertEqual(
            guidance,
            ["Review the official call page, expected impact, and current listed deadline before shortlisting."],
        )

    def test_green_energy_guidance_precedes_raw_material_language(self) -> None:
        guidance = build_next_step_guidance(
            {
                "call_title": "Efficient energy input from renewable sources in process industries",
                "description": (
                    "Renewable electricity, energy efficiency, storage readiness, and industrial "
                    "decarbonisation for process industries and advanced materials production."
                ),
                "eligibility_status": "Eligible",
                "eligibility_warnings": [],
                "eligibility_reasons": [],
                "data_quality_flags": [],
                "match_confidence_label": "Reliable",
                "consortium_required": 0,
                "deadline_utc": "2030-12-01T15:00:00Z",
                "strategic_success_components": {"trl_alignment": 100.0},
            },
            user_trl=None,
            has_consortium=False,
            partner_count=None,
        )

        text = " ".join(guidance).lower()
        self.assertIn("energy", text)
        self.assertNotIn("recycling", text)
        self.assertNotIn("substitution", text)

    def test_wind_energy_guidance_does_not_fall_into_security_language(self) -> None:
        guidance = build_next_step_guidance(
            {
                "call_title": "Innovative technologies and solutions to improve wind energy systems",
                "description": (
                    "Wind energy systems, clean technologies, climate action, grid integration, "
                    "storage readiness, emissions reduction, and operational resilience."
                ),
                "eligibility_status": "Eligible",
                "eligibility_warnings": [],
                "eligibility_reasons": [],
                "data_quality_flags": [],
                "match_confidence_label": "Reliable",
                "consortium_required": 0,
                "deadline_utc": "2030-12-01T15:00:00Z",
                "strategic_success_components": {"trl_alignment": 100.0},
            },
            user_trl=None,
            has_consortium=False,
            partner_count=None,
        )

        text = " ".join(guidance).lower()
        self.assertIn("energy", text)
        self.assertNotIn("critical-infrastructure protection", text)

    def test_security_guidance_precedes_port_or_infrastructure_noise(self) -> None:
        guidance = build_next_step_guidance(
            {
                "call_title": "Enhancing physical protection of critical infrastructures",
                "description": (
                    "Security, critical infrastructure protection, threat detection, emergency "
                    "preparedness, and operational resilience."
                ),
                "eligibility_status": "Eligible",
                "eligibility_warnings": [],
                "eligibility_reasons": [],
                "data_quality_flags": [],
                "match_confidence_label": "Reliable",
                "consortium_required": 0,
                "deadline_utc": "2030-12-01T15:00:00Z",
                "strategic_success_components": {"trl_alignment": 100.0},
            },
            user_trl=None,
            has_consortium=False,
            partner_count=None,
        )

        text = " ".join(guidance).lower()
        self.assertIn("security", text)
        self.assertNotIn("recycling", text)
        self.assertNotIn("port infrastructure", text)


if __name__ == "__main__":
    unittest.main()
