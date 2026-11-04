import copy,unittest
from tests.virtual_frozen_study_admission import census_study_admission
from tests.virtual_frozen_value_reference import prepare_expected_update_reference
from tests.virtual_frozen_whole_study import compose_study_admission,LIMITS

class WholeStudyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.census=census_study_admission()
        cls.expected=prepare_expected_update_reference()
    def test_complete_composition_and_separate_gates(self):
        receipt=compose_study_admission(self.census,self.expected)
        self.assertEqual(receipt['native_eval_requests'],5040)
        self.assertEqual(receipt['native_admit_requests'],2)
        self.assertFalse(receipt['ready_for_producer'])
        self.assertEqual(receipt['active_law_owners'],1)
        self.assertEqual(receipt['uses']['artifact_bytes'],sum(receipt['file_families'].values()))
        for name,value in receipt['uses'].items():self.assertLessEqual(value,LIMITS[name])
    def test_every_whole_resource_family_is_reduce_only(self):
        receipt=compose_study_admission(self.census,self.expected)
        for name,value in receipt['uses'].items():
            with self.subTest(family=name):
                with self.assertRaisesRegex(ValueError,'admission exceeded'):
                    compose_study_admission(self.census,self.expected,limits={name:value-1})
        with self.assertRaises(ValueError):compose_study_admission(self.census,self.expected,limits={'native_work':LIMITS['native_work']+1})
    def test_partial_census_cannot_be_composed_as_complete(self):
        partial=copy.deepcopy(self.census)
        partial['laws']['uniform']['calls']=2519
        with self.assertRaisesRegex(ValueError,'complete two-law'):compose_study_admission(partial,self.expected)

if __name__ == '__main__':unittest.main()
