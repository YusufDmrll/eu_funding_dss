import unittest
from datetime import date

from scripts.review_eu_expansion_candidates import (
    review_record,
    select_promotion_candidates,
    title_similarity,
)


def _record(**overrides):
    base = {
        "call_id": "HORIZON-TEST-01",
        "call_title": "Green and resilient port energy infrastructure",
        "topic_title": "Green and resilient port energy infrastructure",
        "description": "Port authorities will validate shore power, renewable energy, and resilient electricity infrastructure. " * 8,
        "objectives": "Deploy and validate clean port infrastructure with shipping and logistics partners. " * 4,
        "expected_impact": "Lower emissions, stronger port resilience, and cleaner maritime logistics. " * 4,
        "action_type": "IA",
        "deadline_utc": "2027-04-20T17:00:00Z",
        "source_url": "https://ec.europa.eu/example",
    }
    base.update(overrides)
    return base


class PromotionReviewTests(unittest.TestCase):
    def test_core_theme_record_scores_higher_than_broad_ai_only_record(self) -> None:
        core = review_record(
            _record(),
            {
                "theme_score": 14,
                "matched_themes": ["maritime_port_logistics", "hydrogen_green_energy"],
            },
            [],
            today=date(2026, 6, 12),
        )
        broad = review_record(
            _record(
                call_id="HORIZON-TEST-02",
                call_title="Frontier AI collaboration research",
                topic_title="Frontier AI collaboration research",
                description="Research on artificial intelligence methods and collaborative AI systems. " * 8,
                objectives="Develop new artificial intelligence techniques. " * 4,
                expected_impact="Improved research capability for general artificial intelligence. " * 4,
            ),
            {"theme_score": 5, "matched_themes": ["digital_infrastructure_ai"]},
            [],
            today=date(2026, 6, 12),
        )

        self.assertGreater(core["promotion_readiness_score"], broad["promotion_readiness_score"])
        self.assertIn("Only broad AI/digital", " ".join(broad["hold_reasons"]))

    def test_near_duplicate_curated_title_is_penalised(self) -> None:
        candidate = review_record(
            _record(),
            {"theme_score": 12, "matched_themes": ["maritime_port_logistics"]},
            [{"call_id": "CURATED-01", "call_title": "Green and resilient port energy infrastructure"}],
            today=date(2026, 6, 12),
        )

        self.assertLess(candidate["score_components"]["duplicate_safety"], 8)
        self.assertIn("very similar", " ".join(candidate["hold_reasons"]))

    def test_off_theme_title_is_penalised_even_with_broad_supply_chain_terms(self) -> None:
        candidate = review_record(
            _record(
                call_title="AI advice for farmers and resilient agricultural supply chains",
                topic_title="AI advice for farmers and resilient agricultural supply chains",
                description="Artificial intelligence will support farmers and agricultural supply chains. " * 8,
            ),
            {
                "theme_score": 10,
                "matched_themes": [
                    "digital_infrastructure_ai",
                    "security_resilience_infrastructure",
                    "transport_mobility_supply_chain",
                ],
            },
            [],
            today=date(2026, 6, 12),
        )

        self.assertIn("off-theme domain", " ".join(candidate["hold_reasons"]))
        self.assertLess(candidate["promotion_readiness_score"], 65)

    def test_scope_only_priority_terms_do_not_make_generic_ai_title_strong(self) -> None:
        candidate = review_record(
            _record(
                call_title="Deep reasoning and planning for cognitive AI systems",
                topic_title="Deep reasoning and planning for cognitive AI systems",
                description=(
                    "Artificial intelligence research may later support transport, resilient systems, "
                    "and industrial supply chains. " * 8
                ),
            ),
            {
                "theme_score": 12,
                "matched_themes": [
                    "digital_infrastructure_ai",
                    "security_resilience_infrastructure",
                    "transport_mobility_supply_chain",
                ],
            },
            [],
            today=date(2026, 6, 12),
        )

        self.assertIn("broad scope text", " ".join(candidate["hold_reasons"]))

    def test_selection_respects_quality_threshold_and_limit(self) -> None:
        reviewed = [
            {"call_id": "A", "promotion_readiness_score": 90, "theme_score_from_expansion": 10, "days_until_deadline": 100},
            {"call_id": "B", "promotion_readiness_score": 70, "theme_score_from_expansion": 8, "days_until_deadline": 80},
            {"call_id": "C", "promotion_readiness_score": 50, "theme_score_from_expansion": 12, "days_until_deadline": 70},
        ]

        selected, held = select_promotion_candidates(reviewed, limit=1, minimum_score=65)

        self.assertEqual([item["call_id"] for item in selected], ["A"])
        self.assertEqual({item["call_id"] for item in held}, {"B", "C"})

    def test_title_similarity_detects_close_titles(self) -> None:
        self.assertGreater(
            title_similarity(
                "Green and resilient port energy infrastructure",
                "Resilient green port energy infrastructure",
            ),
            0.75,
        )


if __name__ == "__main__":
    unittest.main()
