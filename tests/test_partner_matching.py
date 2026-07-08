import unittest

from core.partner_matching import build_partner_guidance, infer_partner_role_cards, infer_partner_types


class PartnerMatchingTests(unittest.TestCase):
    def test_port_energy_project_suggests_operational_and_energy_partners(self) -> None:
        result = {
            "call_title": "Green harbour energy infrastructure",
            "description": "Port authorities, terminals, shore power, and berth electrification pilots.",
        }
        project_inputs = {
            "project_desc": "A shore power project for port terminal operators and harbour infrastructure."
        }

        partners = infer_partner_types(result, project_inputs)

        self.assertIn("Port authority or terminal operator", partners)
        self.assertIn("Grid, energy, or shore-power infrastructure partner", partners)
        guidance = build_partner_guidance(result, project_inputs)
        self.assertEqual(
            [role["label"] for role in guidance["primary_roles"]],
            [
                "Port authority or terminal operator",
                "Grid, energy, or shore-power infrastructure partner",
            ],
        )

    def test_critical_materials_project_suggests_value_chain_partners(self) -> None:
        result = {
            "call_title": "Critical raw materials recycling",
            "description": "Recover rare earth and battery materials from industrial waste.",
        }

        guidance = build_partner_guidance(result)

        self.assertIn("Recycling or materials processor", guidance["partner_types"])
        self.assertIn("Battery, manufacturing, or industrial value-chain partner", guidance["partner_types"])
        self.assertIn("Confirm consortium", guidance["caution"])
        self.assertIn("Start outreach", guidance["outreach_focus"])
        self.assertEqual(len(guidance["primary_roles"]), 2)
        self.assertIn("feedstock", guidance["validation_focus"])
        self.assertIn("Recycling or materials processor", guidance["outreach_rationale"])
        self.assertIn("confirm", guidance["outreach_rationale"].lower())
        self.assertTrue(guidance["directory_suggestions"]["search_profile"]["roles"])

    def test_required_consortium_raises_partner_priority_without_inventing_roles(self) -> None:
        guidance = build_partner_guidance(
            {
                "call_title": "Innovation action",
                "description": "Demonstration project.",
                "consortium_required": 1,
            },
            {"has_consortium": False},
        )

        self.assertEqual(guidance["priority"], "high")
        self.assertIn("consortium", guidance["summary"].lower())

    def test_security_project_uses_security_roles_without_port_or_recycling_leakage(self) -> None:
        roles = infer_partner_role_cards(
            {
                "call_title": "Critical infrastructure resilience and security innovation",
                "description": "Cybersecurity, emergency preparedness, risk assessment, and protected assets.",
            }
        )
        labels = [role["label"] for role in roles]

        self.assertIn("Critical-infrastructure operator", labels)
        self.assertIn("Security, cybersecurity, or resilience specialist", labels)
        self.assertNotIn("Port authority or terminal operator", labels)
        self.assertNotIn("Recycling or materials processor", labels)


if __name__ == "__main__":
    unittest.main()
