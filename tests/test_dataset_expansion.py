import unittest
from datetime import date

from scripts.expand_dataset_from_eu_api import (
    CSV_COLUMNS,
    calculate_theme_score,
    deduplicate_records,
    filter_active_records,
    normalize_api_result,
)


class DatasetExpansionTests(unittest.TestCase):
    def test_theme_scoring_is_transparent_and_theme_specific(self) -> None:
        result = calculate_theme_score(
            {
                "call_title": "Shore power and renewable energy for European ports",
                "topic_title": "",
                "description": "Reduce shipping emissions through berth electrification and port energy storage.",
                "objectives": "",
                "expected_impact": "",
                "keywords": "",
            }
        )

        self.assertGreaterEqual(result["theme_score"], 5)
        self.assertIn("maritime_port_logistics", result["matched_themes"])
        self.assertIn("hydrogen_green_energy", result["matched_themes"])
        self.assertIn("shore power", result["matched_terms"]["hydrogen_green_energy"])

    def test_deadline_filter_excludes_expired_and_invalid_records(self) -> None:
        active, skipped = filter_active_records(
            [
                {"call_id": "ACTIVE", "deadline_utc": "2027-03-01T00:00:00Z"},
                {"call_id": "EXPIRED", "deadline_utc": "2026-01-01T00:00:00Z"},
                {"call_id": "INVALID", "deadline_utc": "6"},
            ],
            today=date(2026, 6, 12),
        )

        self.assertEqual([record["call_id"] for record in active], ["ACTIVE"])
        self.assertEqual(skipped["expired"], 1)
        self.assertEqual(skipped["invalid_deadline"], 1)

    def test_deduplication_keeps_the_more_complete_record(self) -> None:
        sparse = {"call_id": "HORIZON-TEST-01", "description": "Short description", "source_url": ""}
        complete = {
            "call_id": "HORIZON-TEST-01",
            "description": "A detailed project scope " * 20,
            "objectives": "Clear objectives " * 10,
            "expected_impact": "Expected impact " * 10,
            "source_url": "https://example.eu/call",
            "call_title": "Test call",
            "deadline_utc": "2027-01-01T00:00:00Z",
        }

        records, duplicate_count = deduplicate_records([sparse, complete])

        self.assertEqual(duplicate_count, 1)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["source_url"], "https://example.eu/call")

    def test_schema_normalization_leaves_uncertain_fields_empty(self) -> None:
        api_result = {
            "summary": "Circular battery materials pilot",
            "metadata": {
                "identifier": ["HORIZON-CL5-2027-TEST-01"],
                "title": ["Circular battery materials pilot"],
                "descriptionByte": [
                    "<p class='topicdescriptionkind'>Expected Outcome:</p>"
                    "<p>More resilient European battery material supply chains.</p>"
                    "<p class='topicdescriptionkind'>Scope:</p>"
                    "<p>Develop and validate recycling and refining processes for battery materials.</p>"
                ],
                "typesOfAction": ["HORIZON Research and Innovation Actions"],
                "deadlineDate": ["2027-04-20T17:00:00.000+0000"],
                "url": [
                    "https://ec.europa.eu/info/funding-tenders/opportunities/portal/"
                    "screen/opportunities/topic-details/HORIZON-CL5-2027-TEST-01"
                ],
            },
        }

        record = normalize_api_result(
            api_result,
            checked_at="2026-06-12T12:00:00Z",
            today=date(2026, 6, 12),
        )

        self.assertEqual(list(record.keys()), CSV_COLUMNS)
        self.assertEqual(record["program"], "Horizon Europe")
        self.assertEqual(record["pillar"], "Pillar II")
        self.assertEqual(record["cluster"], "Cluster 5")
        self.assertEqual(record["action_type"], "RIA")
        self.assertIn("recycling and refining", record["description"])
        self.assertIn("resilient European", record["expected_impact"])
        for field in (
            "trl_min",
            "trl_max",
            "eligible_countries",
            "eligible_org_types",
            "consortium_required",
            "min_partners",
        ):
            self.assertEqual(record[field], "")


if __name__ == "__main__":
    unittest.main()
