import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from core.priority_enrichment import (
    detect_priority_themes,
    is_priority_enrichment_candidate,
    missing_metadata_fields,
    priority_enrichment_score,
    select_priority_enrichment_records,
)
from scripts.enrich_priority_call_metadata import run_priority_enrichment
from scripts.expand_dataset_from_eu_api import CSV_COLUMNS
from core.dataset_review import read_csv_records, write_csv_records


def _record(call_id: str, **overrides: str) -> dict[str, str]:
    record = {field: "" for field in CSV_COLUMNS}
    record.update(
        {
            "call_id": call_id,
            "program": "Horizon Europe",
            "pillar": "Pillar II",
            "cluster": "Cluster 5",
            "call_title": "Green harbour shore power and port energy systems",
            "topic_title": "Green harbour shore power and port energy systems",
            "description": (
                "Port authorities and terminal operators will deploy shore power, renewable energy, "
                "storage, and harbour infrastructure to reduce emissions."
            ),
            "objectives": "Demonstrate port energy integration.",
            "expected_impact": "Reduced emissions and improved harbour energy resilience.",
            "action_type": "IA",
            "deadline_utc": "2099-01-01",
            "source_url": f"https://example.test/{call_id}",
            "source_last_checked_utc": "2026-07-01T00:00:00Z",
        }
    )
    record.update(overrides)
    return record


class PriorityEnrichmentTests(unittest.TestCase):
    def test_detects_priority_themes(self) -> None:
        themes = detect_priority_themes(_record("PORT"))

        self.assertIn("port_energy_hydrogen", themes)
        self.assertIn("maritime_ports_logistics", themes)

    def test_candidate_requires_active_priority_record_with_missing_metadata(self) -> None:
        self.assertTrue(is_priority_enrichment_candidate(_record("ACTIVE"), today=date(2026, 7, 6)))
        self.assertFalse(
            is_priority_enrichment_candidate(
                _record("EXPIRED", deadline_utc="2020-01-01"),
                today=date(2026, 7, 6),
            )
        )
        self.assertFalse(
            is_priority_enrichment_candidate(
                _record(
                    "COMPLETE",
                    trl_min="4",
                    trl_max="7",
                    eligible_countries="EU Member States",
                    eligible_org_types="SMEs",
                    consortium_required="1",
                    min_partners="3",
                    budget_min_eur="1000000",
                    budget_max_eur="2000000",
                ),
                today=date(2026, 7, 6),
            )
        )

    def test_select_priority_records_orders_by_score(self) -> None:
        high = _record("HIGH", eligible_countries="", eligible_org_types="")
        low = _record("LOW", description="Short port energy text.", expected_impact="")
        off_theme = _record("OFF", call_title="Cultural education programme", description="School arts programme.")

        selected = select_priority_enrichment_records([off_theme, low, high], limit=2, today=date(2026, 7, 6))

        self.assertEqual(selected[0]["call_id"], "HIGH")
        self.assertGreater(priority_enrichment_score(high, today=date(2026, 7, 6)), 0)
        self.assertTrue(missing_metadata_fields(high))

    def test_priority_enrichment_script_writes_separate_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_path = root / "calls_seed_clean.csv"
            output_path = root / "priority_enriched.csv"
            log_path = root / "priority_enrichment_log.json"

            write_csv_records(input_path, [_record("PORT")])
            before = input_path.read_text(encoding="utf-8-sig")

            report = run_priority_enrichment(
                input_path=input_path,
                output_path=output_path,
                log_path=log_path,
                limit=10,
                skip_live_api=True,
            )

            self.assertEqual(input_path.read_text(encoding="utf-8-sig"), before)
            self.assertEqual(report["summary"]["priority_records_selected"], 1)
            self.assertFalse(report["main_dataset_modified"])
            self.assertFalse(report["sqlite_modified"])
            self.assertEqual(len(read_csv_records(output_path)), 1)

            loaded = json.loads(log_path.read_text(encoding="utf-8"))
            self.assertEqual(loaded["summary"]["priority_records_selected"], 1)


if __name__ == "__main__":
    unittest.main()
