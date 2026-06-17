import unittest

from core.reporting import (
    _active_results,
    _build_plain_text_pdf,
    _build_primary_caution,
    _build_shortlist_count_text,
    _format_review_status,
    build_decision_support_pdf,
)
from core.source_urls import canonical_official_topic_url, official_source_label


class ReportingTests(unittest.TestCase):
    def test_battery_operation_call_does_not_receive_refining_caution(self):
        result = {
            "topic_title": "Enhanced electric operation and battery durability for waterborne transport",
            "description": "Improve battery operation and lifetime for electric vessels.",
            "objectives": "Demonstrate durable onboard battery systems.",
            "expected_impact": "Lower-emission waterborne transport.",
        }

        caution = _build_primary_caution(result)

        self.assertNotIn("materials upgrading or refining", caution or "")

    def test_port_side_guardrail_uses_ship_side_caution(self):
        result = {
            "topic_title": "Enhanced electric operation and battery durability for waterborne transport",
            "description": "Improve battery operation and lifetime for electric vessels at berth.",
            "theme_coherence": {"guardrails": ["port_side_scope_mismatch"]},
        }

        caution = _build_primary_caution(result)

        self.assertEqual(
            caution,
            "Check whether the ship-side scope is relevant enough for this port-side project.",
        )

    def test_pdf_only_keeps_active_recommended_calls(self) -> None:
        active = {"call_id": "ACTIVE", "deadline_utc": "2099-01-01"}
        expired = {"call_id": "EXPIRED", "deadline_utc": "2020-01-01"}
        unknown = {"call_id": "UNKNOWN", "deadline_utc": ""}

        filtered = _active_results([active, expired, unknown])

        self.assertEqual([result["call_id"] for result in filtered], ["ACTIVE"])

    def test_pdf_review_status_uses_input_quality_guardrail(self) -> None:
        result = {
            "similarity_score": 0.70,
            "match_confidence_label": "Reliable",
        }

        broad_status = _format_review_status(
            result,
            {
                "project_desc": "A broad innovation collaboration platform for regional partners.",
                "input_quality": {"quality_level": "broad"},
                "retrieval_mode": "semantic",
            },
        )
        detailed_status = _format_review_status(
            result,
            {
                "project_desc": "A detailed critical-material recovery and recycling process.",
                "input_quality": {"quality_level": "detailed"},
                "retrieval_mode": "semantic",
            },
        )

        self.assertEqual(broad_status, "Worth reviewing")
        self.assertEqual(detailed_status, "Strong match")

    def test_pdf_report_generation_returns_pdf_bytes(self) -> None:
        pdf_bytes = build_decision_support_pdf(
            project_inputs={
                "project_title": "Circular Materials Pilot",
                "project_desc": "A concise pilot for sustainable material reuse.",
                "user_country": "Turkey",
                "user_org_type": "SME",
                "user_trl": 5,
                "has_consortium": False,
                "partner_count": 1,
            },
            results=[
                {
                    "call_id": "HE-TEST-001",
                    "call_title": (
                        "Circular Manufacturing Test Call With A Deliberately Long Title To Verify "
                        "That The PDF Table Wraps Safely Without Overlapping Adjacent Columns"
                    ),
                    "similarity_score": 0.8123,
                    "program": "Horizon Europe",
                    "cluster": "Cluster 4",
                    "deadline_utc": "2099-10-01",
                    "deadline_status": "open_or_upcoming",
                    "eligibility_status": "Partially Eligible",
                    "match_confidence_label": "Reliable",
                    "match_explanation": (
                        "This match shows direct overlap with the call title and keywords, "
                        "including terms such as circular, manufacturing, and materials."
                    ),
                    "next_step_guidance": [
                        "Validate country, organisation, and call metadata against the official call text.",
                        "Review the official work programme and confirm the current deadline before investing further effort.",
                    ],
                    "strategic_success_index": 83.45,
                    "trl_min": 4,
                    "trl_max": 6,
                    "strategic_success_components": {"trl_alignment": 100.0},
                    "source_url": "https://example.com/funding/call/HE-TEST-001",
                }
            ],
        )

        self.assertTrue(pdf_bytes.startswith(b"%PDF"))
        self.assertGreater(len(pdf_bytes), 500)

    def test_plain_text_pdf_avoids_prototype_wording_and_formats_sme(self) -> None:
        pdf_bytes = _build_plain_text_pdf(
            project_inputs={
                "project_title": "",
                "project_desc": "Battery recycling project for European manufacturing supply chains.",
                "user_country": "Netherlands",
                "user_org_type": "sme",
                "user_trl": "",
                "has_consortium": False,
                "retrieval_mode": "semantic",
                "input_quality": {"quality_level": "detailed"},
            },
            results=[
                {
                    "call_id": "HORIZON-CL5-2027-02-D2-05",
                    "call_title": "Battery recycling topic",
                    "similarity_score": 0.71,
                    "strategic_success_index": 78,
                    "deadline_utc": "2099-01-01",
                    "deadline_status": "open_or_upcoming",
                    "eligibility_status": "Partially Eligible",
                    "match_confidence_label": "Reliable",
                    "match_explanation": "Relevant because it links battery-material recovery with recycling.",
                    "theme_coherence": {
                        "coherence_level": "strong",
                        "shared_themes": ["critical_materials_circularity"],
                        "guardrails": [],
                    },
                    "source_url": (
                        "https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/"
                        "opportunities/calls-for-proposals?keywords=HORIZON-CL5-2027-02-D2-05"
                    ),
                }
            ],
        )
        text = pdf_bytes.decode("latin-1", errors="ignore")

        self.assertNotIn("Project Title: N/A", text)
        self.assertNotIn("Project Title: Not provided", text)
        self.assertIn("Organisation Type: SME", text)
        self.assertNotIn("pilot dataset", text.lower())
        self.assertNotIn("screening indicator", text.lower())
        self.assertIn("HORIZON-CL5-2027-02-D2-05", text)
        self.assertIn("/topic-details/HORIZON-CL5-2027-02-D2-05", text)

    def test_shortlist_summary_does_not_oversell_mixed_statuses(self) -> None:
        results = [
            {"similarity_score": 0.72, "match_confidence_label": "Reliable"},
            {"similarity_score": 0.30, "match_confidence_label": "Reliable"},
            {"similarity_score": 0.03, "match_confidence_label": "Weak Match"},
        ]
        text = _build_shortlist_count_text(
            results,
            {
                "project_desc": "A detailed port energy project.",
                "input_quality": {"quality_level": "detailed"},
                "retrieval_mode": "semantic",
            },
        )

        self.assertIn("current options found", text)
        self.assertIn("needing more detail", text)
        self.assertNotIn("strong option", text.lower())
        self.assertNotIn("calls are currently worth reviewing", text)

    def test_canonical_official_topic_url_uses_topic_details_page(self) -> None:
        url = canonical_official_topic_url(
            "HORIZON-MISS-2027-03-OCEAN-03",
            "https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/opportunities/calls-for-proposals?keywords=HORIZON-MISS-2027-03-OCEAN-03",
        )

        self.assertEqual(
            url,
            "https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/opportunities/topic-details/HORIZON-MISS-2027-03-OCEAN-03",
        )
        self.assertEqual(
            official_source_label("HORIZON-MISS-2027-03-OCEAN-03"),
            "Open official topic page (HORIZON-MISS-2027-03-OCEAN-03)",
        )


if __name__ == "__main__":
    unittest.main()
