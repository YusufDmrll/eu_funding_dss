import unittest

from scripts.enrich_eu_promotion_candidates import (
    extract_explicit_consortium,
    extract_explicit_eligibility,
    extract_explicit_trl,
)


class PromotionEnrichmentHelperTests(unittest.TestCase):
    def test_extracts_explicit_trl_range(self):
        result = extract_explicit_trl("Activities are expected to cover TRL 4-6 by the end of the project.")

        self.assertEqual(result["trl_min"], "4")
        self.assertEqual(result["trl_max"], "6")
        self.assertEqual(result["reason"], "explicit")

    def test_extracts_explicit_start_and_end_trl(self):
        result = extract_explicit_trl("Projects should start at TRL 5 and achieve TRL 7.")

        self.assertEqual(result["trl_min"], "5")
        self.assertEqual(result["trl_max"], "7")

    def test_start_value_takes_precedence_over_target_range_minimum(self):
        result = extract_explicit_trl("Activities start at TRL 6 and achieve TRL 7 to 8 by project end.")

        self.assertEqual(result["trl_min"], "6")
        self.assertEqual(result["trl_max"], "8")

    def test_start_range_and_end_value_use_outer_bounds(self):
        result = extract_explicit_trl("Activities start at TRL 6-7 and achieve TRL 8 by project end.")

        self.assertEqual(result["trl_min"], "6")
        self.assertEqual(result["trl_max"], "8")

    def test_conflicting_trl_ranges_are_ambiguous(self):
        result = extract_explicit_trl("One activity is TRL 3-5 while another is TRL 6-8.")

        self.assertEqual(result["trl_min"], "")
        self.assertEqual(result["trl_max"], "")
        self.assertEqual(result["reason"], "ambiguous")

    def test_extracts_explicit_minimum_consortium_size(self):
        result = extract_explicit_consortium(
            "Proposals must include at least three independent legal entities established in eligible countries."
        )

        self.assertEqual(result["consortium_required"], "1")
        self.assertEqual(result["min_partners"], "3")

    def test_consortium_encouragement_does_not_create_requirement(self):
        result = extract_explicit_consortium(
            "Participation of port authorities as partners in the consortium is strongly encouraged."
        )

        self.assertEqual(result["consortium_required"], "")
        self.assertEqual(result["min_partners"], "")

    def test_extracts_eligibility_only_from_explicit_target_statement(self):
        result = extract_explicit_eligibility(
            "This topic targets public local and regional authorities in EU Member States and Associated Countries."
        )

        self.assertEqual(result["eligible_org_types"], "public local and regional authorities")
        self.assertEqual(
            result["eligible_countries"],
            "EU Member States; Horizon Europe Associated Countries",
        )

    def test_ambiguous_eligibility_reference_does_not_create_values(self):
        result = extract_explicit_eligibility(
            "Applicants must comply with the eligibility conditions described in Annex B of the work programme."
        )

        self.assertEqual(result["eligible_countries"], "")
        self.assertEqual(result["eligible_org_types"], "")
        self.assertEqual(result["reason"], "not_found")


if __name__ == "__main__":
    unittest.main()
