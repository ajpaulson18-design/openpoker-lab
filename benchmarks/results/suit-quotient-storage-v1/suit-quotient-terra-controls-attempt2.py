import gc,inspect,unittest,weakref
from array import array as array_type
from unittest.mock import patch
from pokerlab.exact_selected_solver import solve_four_street_exact_selected
from pokerlab.suit_quotient_plan import SuitQuotientPlan
from tests.test_equivariant_selected_solver import symmetric_case
from tests.test_selected_operator_solver import request
import pokerlab.suit_quotient_cfr as qmod

REQ=lambda:request(symmetric_case(),iterations=10)
def solve():return solve_four_street_exact_selected(REQ(),pair_diagnostics='compact',training_reduction='suit-equivariant',strategy_storage='suit-quotient')
def within(name):
 frame=inspect.currentframe().f_back
 while frame:
  if frame.f_code.co_name==name:return True
  frame=frame.f_back
 return False

class Controls(unittest.TestCase):
 def duplicate(self,phase):
  original=SuitQuotientPlan.locate;origadd=qmod._add;commits=[]
  def locate(plan,key):
   q,off,bit=original(plan,key)
   if within(phase) and plan.sizes[q]>1:return q,off,1
   return q,off,bit
  def add(a,b,label='CFR+ sum'):
   if label in ('CFR+ regret update','average-strategy accumulation'):commits.append(label)
   return origadd(a,b,label)
  with patch.object(SuitQuotientPlan,'locate',new=locate),patch.object(qmod,'_add',side_effect=add):
   with self.assertRaisesRegex(ValueError,'Duplicate Q member'):solve()
  if phase=='target_values':self.assertNotIn('CFR+ regret update',commits)
  else:self.assertNotIn('average-strategy accumulation',commits)
 def test_duplicate_responder_before_commit(self):self.duplicate('target_values')
 def test_duplicate_average_before_commit(self):self.duplicate('average')
 def test_member_regret_mismatch_before_commit(self):
  old=qmod._sub;add=qmod._add;count=[0];commits=[]
  def sub(a,b,label='CFR+ difference'):
   v=old(a,b,label)
   if label=='counterfactual regret increment':
    count[0]+=1
    if count[0]==1:return v+0.125
   return v
  def track(a,b,label='CFR+ sum'):
   if label=='CFR+ regret update':commits.append(label)
   return add(a,b,label)
  with patch.object(qmod,'_sub',side_effect=sub),patch.object(qmod,'_add',side_effect=track):
   with self.assertRaisesRegex(ValueError,'increments differ'):solve()
  self.assertEqual(commits,[])
 def test_no_reference_R_map_and_q_arrays_release_before_expansion(self):
  refs=[];original=SuitQuotientPlan.iter_rows;expanded=[]
  class Tracked(array_type):
   def __mul__(self,n):
    x=super().__mul__(n);refs.append(weakref.ref(x));return x
  def factory(*a,**kw):return Tracked(*a,**kw)
  def rows(plan):
   if within('train_suit_quotient') and not within('layout_census_suit_quotient'):
    expanded.append(True);self.assertTrue(refs);self.assertTrue(all(r() is None for r in refs))
   yield from original(plan)
  with patch.object(qmod,'array',side_effect=factory),patch.object(SuitQuotientPlan,'iter_rows',new=rows),patch('pokerlab.exact_selected_solver.layout_census_shared',side_effect=AssertionError('R layout')):
   result=solve()
  self.assertTrue(expanded);self.assertEqual(result['operator_census']['suit_quotient_storage']['retained_expanded_row_lookup_entries'],0)
 def test_average_member_mismatch_before_commit(self):
  mul=qmod._mul;add=qmod._add;count=[0];commits=[]
  def change(a,b,label='CFR+ product'):
   v=mul(a,b,label)
   if label=='iteration-weighted average':
    count[0]+=1
    if count[0]==1:return v+0.125
   return v
  def track(a,b,label='CFR+ sum'):
   if label=='average-strategy accumulation':commits.append(label)
   return add(a,b,label)
  with patch.object(qmod,'_mul',side_effect=change),patch.object(qmod,'_add',side_effect=track):
   with self.assertRaisesRegex(ValueError,'average contributions differ'):solve()
  self.assertEqual(commits,[])
 def omitted(self,phase):
  orig=SuitQuotientPlan.supported_hand_indices;add=qmod._add;omitted=[False];commits=[]
  def support(plan,prefix,player):
   vals=orig(plan,prefix,player)
   if within(phase) and not omitted[0] and vals:
    omitted[0]=True;return vals[1:]
   return vals
  def track(a,b,label='CFR+ sum'):
   if label in ('CFR+ regret update','average-strategy accumulation'):commits.append(label)
   return add(a,b,label)
  with patch.object(SuitQuotientPlan,'supported_hand_indices',new=support),patch.object(qmod,'_add',side_effect=track):
   with self.assertRaisesRegex(ValueError,'Incomplete Q member coverage'):solve()
  if phase=='target_values':self.assertNotIn('CFR+ regret update',commits)
  else:self.assertNotIn('average-strategy accumulation',commits)
 def test_omitted_responder_before_commit(self):self.omitted('target_values')
 def test_omitted_average_before_commit(self):self.omitted('average')
 def test_mismatched_menu_rejects(self):
  old=SuitQuotientPlan.locate
  def locate(plan,key):
   q,offset,bit=old(plan,key)
   if within('target_values'):
    for other,menu in enumerate(plan.menus):
     if menu!=plan.menus[q]:return other,plan.offsets[other],bit
   return q,offset,bit
  with patch.object(SuitQuotientPlan,'locate',new=locate):
   with self.assertRaisesRegex(ValueError,'ordered action menu'):solve()

if __name__=='__main__':unittest.main(verbosity=2)
