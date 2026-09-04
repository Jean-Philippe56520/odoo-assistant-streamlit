import unittest
from unittest.mock import patch

from odoo_import.duplicate_service import (
    classify_lead_candidates,
    find_lead_candidates,
    normalize_city_name,
    normalize_company_name,
    normalize_phone_for_match,
)


class DuplicateServiceTests(unittest.TestCase):
    def test_french_phone_formats_are_equivalent(self):
        expected = "0612345678"
        for value in (
            "06 12 34 56 78",
            "06.12.34.56.78",
            "06-12-34-56-78",
            "+33 6 12 34 56 78",
            "0033 6 12 34 56 78",
        ):
            self.assertEqual(normalize_phone_for_match(value), expected)

    def test_company_normalization_is_strict_but_ignores_legal_forms(self):
        self.assertEqual(normalize_company_name("SARL DUPONT INDUSTRIE"), "dupont industrie")
        self.assertEqual(normalize_company_name("Dupont Industrie SAS"), "dupont industrie")
        self.assertNotEqual(
            normalize_company_name("Dupont Services"),
            normalize_company_name("Dupont Industrie"),
        )
        self.assertEqual(normalize_city_name("Saint-Brieuc"), "saint brieuc")

    def test_cross_phone_mobile_and_multiple_candidates(self):
        data = {
            "partner_name": "Dupont Industrie SAS",
            "city": "Lorient",
            "email_from": "contact@dupont.fr",
            "phone": "06 12 34 56 78",
            "mobile": "",
        }
        rows = [
            {
                "id": 10,
                "partner_name": "Autre",
                "city": "Vannes",
                "email_from": "",
                "phone": "",
                "mobile": "+33 6 12 34 56 78",
            },
            {
                "id": 11,
                "partner_name": "Dupont Industrie SARL",
                "city": "LORIENT",
                "email_from": "CONTACT@DUPONT.FR",
                "phone": "",
                "mobile": "",
            },
            {
                "id": 12,
                "partner_name": "Dupont Services",
                "city": "Lorient",
                "email_from": "",
                "phone": "",
                "mobile": "",
            },
        ]

        candidates = classify_lead_candidates(data, rows)

        self.assertEqual([candidate.lead_id for candidate in candidates], [11, 10])
        self.assertEqual(candidates[0].match_level, "strong")
        self.assertIn("email", candidates[0].reasons)
        self.assertIn("company_city", candidates[0].reasons)
        self.assertEqual(candidates[1].reasons, ("phone",))

    def test_company_city_only_is_secondary(self):
        data = {"partner_name": "SARL Atelier Martin", "city": "Auray"}
        rows = [
            {"id": 20, "partner_name": "Atelier Martin SAS", "city": "AURAY"},
            {"id": 21, "partner_name": "Atelier Maritime", "city": "Auray"},
        ]

        candidates = classify_lead_candidates(data, rows)

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].lead_id, 20)
        self.assertEqual(candidates[0].match_level, "company_city")

    def test_short_company_name_does_not_trigger_secondary_match(self):
        data = {"partner_name": "ABM", "city": "Lorient"}
        rows = [{"id": 30, "partner_name": "ABM SAS", "city": "Lorient"}]
        self.assertEqual(classify_lead_candidates(data, rows), [])

    @patch("odoo_import.duplicate_service.execute_kw")
    def test_odoo_queries_are_targeted_and_limited(self, execute_kw):
        execute_kw.return_value = []

        find_lead_candidates(
            7,
            {
                "partner_name": "Dupont Industrie",
                "city": "Lorient",
                "email_from": "x@example.com",
                "phone": "06 12 34 56 78",
                "mobile": "",
            },
        )

        self.assertGreaterEqual(execute_kw.call_count, 1)
        for call in execute_kw.call_args_list:
            args, kwargs = call
            self.assertEqual(args[2], "search_read")
            self.assertTrue(kwargs["args"][0])
            self.assertLessEqual(kwargs["kwargs"]["limit"], 30)


if __name__ == "__main__":
    unittest.main()
