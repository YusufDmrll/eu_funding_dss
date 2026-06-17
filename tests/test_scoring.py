import unittest

from core.scoring import (
    MIN_DISPLAY_SIMILARITY_SCORE,
    MIN_RELIABLE_SIMILARITY_SCORE,
    calculate_strategic_success_index,
    determine_client_review_status,
    determine_match_confidence_label,
    eligibility_status_to_score,
    format_client_confidence_label,
    similarity_to_score,
    trl_alignment_score,
)


class StrategicScoringTests(unittest.TestCase):
    def test_similarity_score_is_scaled_to_100(self) -> None:
        self.assertEqual(similarity_to_score(0.82), 82.0)

    def test_eligibility_status_mapping_is_transparent(self) -> None:
        self.assertEqual(eligibility_status_to_score("Eligible"), 100.0)
        self.assertEqual(eligibility_status_to_score("Partially Eligible"), 70.0)
        self.assertEqual(eligibility_status_to_score("Not Eligible"), 30.0)

    def test_trl_alignment_is_full_when_inside_range(self) -> None:
        self.assertEqual(trl_alignment_score(5, 4, 6), 100.0)

    def test_trl_alignment_drops_by_distance_when_outside_range(self) -> None:
        self.assertEqual(trl_alignment_score(3, 4, 6), 75.0)
        self.assertEqual(trl_alignment_score(8, 4, 6), 50.0)

    def test_match_confidence_labels_are_simple_and_explainable(self) -> None:
        self.assertEqual(MIN_DISPLAY_SIMILARITY_SCORE, 0.08)
        self.assertEqual(MIN_RELIABLE_SIMILARITY_SCORE, 0.14)
        self.assertEqual(determine_match_confidence_label(0.14), "Reliable")
        self.assertEqual(determine_match_confidence_label(0.10), "Needs Review")
        self.assertEqual(determine_match_confidence_label(0.04), "Weak Match")

    def test_client_confidence_labels_are_cautious(self) -> None:
        self.assertEqual(format_client_confidence_label("Reliable"), "Strong match")
        self.assertEqual(format_client_confidence_label("Needs Review"), "Worth reviewing")
        self.assertEqual(format_client_confidence_label("Weak Match"), "Needs more detail")

    def test_vague_input_cannot_produce_strong_match(self) -> None:
        status = determine_client_review_status(
            0.72,
            input_quality={"quality_level": "broad"},
            retrieval_mode="semantic",
            internal_confidence_label="Reliable",
        )

        self.assertEqual(status, "Worth reviewing")

    def test_low_similarity_cannot_produce_strong_match(self) -> None:
        status = determine_client_review_status(
            0.12,
            input_quality={"quality_level": "detailed"},
            retrieval_mode="semantic",
            internal_confidence_label="Needs Review",
        )

        self.assertEqual(status, "Worth reviewing")

    def test_good_semantic_similarity_can_produce_strong_match(self) -> None:
        status = determine_client_review_status(
            0.62,
            input_quality={"quality_level": "detailed"},
            retrieval_mode="semantic",
            internal_confidence_label="Reliable",
        )

        self.assertEqual(status, "Strong match")

    def test_borderline_semantic_similarity_is_not_strong_match(self) -> None:
        status = determine_client_review_status(
            0.52,
            input_quality={"quality_level": "detailed"},
            retrieval_mode="semantic",
            internal_confidence_label="Reliable",
        )

        self.assertEqual(status, "Worth reviewing")

    def test_partial_theme_coherence_cannot_produce_strong_match(self) -> None:
        status = determine_client_review_status(
            0.70,
            input_quality={"quality_level": "detailed"},
            retrieval_mode="semantic",
            internal_confidence_label="Reliable",
            theme_coherence={
                "coherence_level": "partial",
                "shared_themes": ["port_energy_hydrogen"],
                "guardrails": ["partial_theme_overlap"],
                "max_client_status": "Worth reviewing",
            },
        )

        self.assertEqual(status, "Worth reviewing")

    def test_log_style_input_cannot_produce_strong_match(self) -> None:
        status = determine_client_review_status(
            0.72,
            input_quality={
                "quality_level": "detailed",
                "project_intent_level": "non_project",
                "is_likely_non_project": True,
            },
            retrieval_mode="semantic",
            internal_confidence_label="Reliable",
        )

        self.assertEqual(status, "Needs more detail")

    def test_theme_guardrail_caps_strong_match(self) -> None:
        status = determine_client_review_status(
            0.72,
            input_quality={"quality_level": "detailed"},
            retrieval_mode="semantic",
            internal_confidence_label="Reliable",
            theme_coherence={"max_client_status": "Worth reviewing"},
        )

        self.assertEqual(status, "Worth reviewing")

    def test_strategic_success_index_combines_all_components(self) -> None:
        result = calculate_strategic_success_index(
            similarity_score=0.80,
            eligibility_status="Eligible",
            user_trl=5,
            trl_min=4,
            trl_max=6,
        )

        self.assertEqual(result["strategic_success_index"], 90.0)
        self.assertEqual(
            result["strategic_success_components"],
            {
                "similarity": 80.0,
                "eligibility": 100.0,
                "trl_alignment": 100.0,
            },
        )
        self.assertEqual(result["match_confidence_label"], "Reliable")


if __name__ == "__main__":
    unittest.main()
