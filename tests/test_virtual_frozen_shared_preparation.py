import unittest
from unittest.mock import patch
from scripts.matrix_free_certificate_budget import Budget
from tests.virtual_betting_template_reference import build_reference_template,literal_reference_census
from tests.virtual_frozen_update_reference import _template_case
from tests.virtual_frozen_value_reference import prepare_expected_update_reference

class SharedPreparationTests(unittest.TestCase):
    def test_shared_budget_survives_both_builds_without_reset(self):
        owner=Budget({'work':150_000_000,'entries':1_000_000,'integer_bits':4096,'created_bits':1_000_000_000})
        template=build_reference_template(_template_case(),rule_budget=owner)
        first=owner.work
        literal=literal_reference_census(_template_case(),rule_budget=owner)
        self.assertGreater(owner.work,first)
        self.assertEqual(template.receipt['rule_budget']['work'],first)
        self.assertEqual(literal['rule_budget']['work'],owner.work)
        self.assertEqual(template.receipt['nodes'],388)
        self.assertEqual(literal['logical_occurrences'],1105)
    def test_tiny_parent_rejects_instead_of_getting_a_fresh_default(self):
        for builder in (build_reference_template,literal_reference_census):
            owner=Budget({'work':1})
            with self.subTest(builder=builder.__name__):
                with self.assertRaises(ValueError):builder(_template_case(),rule_budget=owner)
                self.assertLessEqual(owner.work,1)
    def test_complete_qfree_setup_admitted_before_any_build(self):
        with patch('tests.virtual_frozen_value_reference.build_frozen_update_census',side_effect=AssertionError('unadmitted setup entered')):
            with self.assertRaisesRegex(ValueError,'complete setup work'):
                prepare_expected_update_reference({'work':199_999_999})

if __name__ == '__main__':unittest.main()
