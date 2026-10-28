import unittest
from unittest.mock import patch
from pokerlab.suit_quotient_plan import SuitQuotientPlan
from pokerlab.suit_public_automorphism import verify_public_suit_automorphisms
from pokerlab.exact_selected_solver import _prepare_exact_selected
from tests.test_equivariant_selected_solver import symmetric_case
from tests.test_selected_operator_solver import request

def prep(t=10):
 return _prepare_exact_selected(request(symmetric_case(),iterations=t),pair_diagnostics='compact',exact_arithmetic='dyadic',training_reduction='suit-equivariant')
class Review(unittest.TestCase):
 def test_suit_maps_are_immutable(self):
  x=prep();p=SuitQuotientPlan(x,10)
  with self.assertRaises(TypeError):p._maps[0]['c']='d'
 def test_plan_binds_admitted_iterations(self):
  x=prep(100)
  with self.assertRaises(ValueError):SuitQuotientPlan(x,10)
 def test_public_graph_work_rejects_before_validation_when_budget_one(self):
  x=prep()
  with patch('pokerlab.suit_public_automorphism._number',side_effect=AssertionError('validation before work admission')):
   with self.assertRaises(ValueError):verify_public_suit_automorphisms(x.topology,('cdhs',),max_additional_work=1)
if __name__=='__main__':unittest.main(verbosity=2)
