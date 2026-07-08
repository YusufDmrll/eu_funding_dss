import csv
import tempfile
import unittest
from pathlib import Path

from core.partner_directory import (
    PARTNER_DIRECTORY_COLUMNS,
    build_partner_directory_suggestions,
    detect_partner_themes,
    score_partner_record,
)


class PartnerDirectoryTests(unittest.TestCase):
    def test_detect_partner_themes_from_project_and_call_text(self) -> None:
        themes = detect_partner_themes(
            "Green harbour shore power",
            "Port terminal operators need renewable storage at berth.",
        )

        self.assertIn("port energy / green harbour", themes)
        self.assertIn("green energy / hydrogen", themes)

    def test_missing_directory_returns_search_profile_without_matches(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing_path = Path(tmp) / "partner_directory.csv"
            suggestions = build_partner_directory_suggestions(
                result={
                    "call_title": "Green harbour energy infrastructure",
                    "description": "Port shore power and renewable storage.",
                },
                project_inputs={"project_desc": "A shore power project for port operators."},
                partner_roles=[
                    {"label": "Port authority or terminal operator"},
                    {"label": "Grid, energy, or shore-power infrastructure partner"},
                ],
                directory_path=missing_path,
            )

        self.assertEqual(suggestions["status"], "not_configured")
        self.assertEqual(suggestions["matches"], [])
        self.assertIn("Port authority or terminal operator", suggestions["search_profile"]["roles"])

    def test_directory_returns_relevant_partner_match(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "partner_directory.csv"
            with path.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=PARTNER_DIRECTORY_COLUMNS, delimiter=";")
                writer.writeheader()
                writer.writerow(
                    {
                        "organization_name": "North Sea Port Authority",
                        "country": "Netherlands",
                        "organization_type": "Port authority",
                        "sector": "Ports and energy infrastructure",
                        "roles": "Port authority or terminal operator; Operational pilot site",
                        "themes": "port energy / green harbour; green energy / hydrogen",
                        "website": "https://example.eu",
                        "notes": "Example checked partner profile.",
                        "verified_status": "verified",
                        "last_checked_utc": "2026-07-07T00:00:00Z",
                    }
                )

            suggestions = build_partner_directory_suggestions(
                result={
                    "call_title": "Green harbour energy infrastructure",
                    "description": "Port shore power and berth electrification.",
                },
                project_inputs={
                    "project_desc": "A shore power project for port operators.",
                    "user_country": "Netherlands",
                },
                partner_roles=[{"label": "Port authority or terminal operator"}],
                directory_path=path,
            )

        self.assertEqual(suggestions["status"], "matched")
        self.assertEqual(suggestions["matches"][0]["organization_name"], "North Sea Port Authority")
        self.assertGreaterEqual(suggestions["matches"][0]["score"], 8)

    def test_score_partner_record_requires_role_or_theme_signal(self) -> None:
        scored = score_partner_record(
            {
                "organization_name": "Unrelated Cultural Institute",
                "roles": "Museum operator",
                "themes": "cultural heritage",
                "country": "Netherlands",
            },
            requested_roles=["Security, cybersecurity, or resilience specialist"],
            requested_themes=["security / resilience"],
            user_country="Netherlands",
        )

        self.assertLess(scored["score"], 8)


if __name__ == "__main__":
    unittest.main()
