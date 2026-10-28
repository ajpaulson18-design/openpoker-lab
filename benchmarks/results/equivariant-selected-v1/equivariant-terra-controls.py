import gc,unittest,weakref
from unittest.mock import patch
from tests.test_equivariant_packed_cfr import _request,_train
from pokerlab.equivariant_packed_cfr import _sorted_chance_sum
from pokerlab.exact_selected_solver import _prepare_exact_selected,_OnePrefixMarginals
from pokerlab.equivariant_packed_cfr import train_equivariant_packed
from pokerlab.shared_public_topology import DecisionVertex
from pokerlab.exact_selected_solver import _tokens,_revealed_board
from array import array as actual_array

class Terra(unittest.TestCase):
 def test_arrays_release_gc_disabled_success_and_failure(self):
  for fail in (False,True):
   refs=[]
   class Tracked(actual_array):
    def __mul__(self,n):
     value=super().__mul__(n);refs.append(weakref.ref(value));return value
   def factory(*a,**kw):
    return Tracked(*a,**kw)
   old=gc.isenabled();gc.disable()
   try:
    with patch('pokerlab.equivariant_packed_cfr.array',side_effect=factory):
     if fail:
      with patch('pokerlab.equivariant_packed_cfr._sorted_chance_sum',side_effect=ValueError('injected')):
       with self.assertRaisesRegex(ValueError,'injected'): _train(_request())
     else:
      policy,receipt,kernel,infos=_train(_request());kernel.clear_rank_cache()
    self.assertTrue(refs);self.assertTrue(all(x() is None for x in refs))
   finally:
    if old:gc.enable()
 def test_private_hand_suit_orbits_and_zero_reach(self):
  from tests.test_equivariant_selected_solver import symmetric_case,mapped_row_key
  from tests.test_selected_operator_solver import request
  from pokerlab.exact_selected_solver import solve_four_street_exact_selected
  result=solve_four_street_exact_selected(request(symmetric_case()),pair_diagnostics='compact',training_reduction='suit-equivariant')
  rows={(r['player'],r['hand'],tuple(r['history'])):r for r in result['strategy']}
  zero=0
  for key,row in rows.items():
   partner=rows[mapped_row_key(row)]
   self.assertEqual([a['probability'].hex() for a in row['actions']],[a['probability'].hex() for a in partner['actions']])
   reach=1.0
   for i,token in enumerate(row['history']):
    prior=rows.get((row['player'],row['hand'],tuple(row['history'][:i])))
    if prior:
     for a in prior['actions']:
      if a['history_key']==token:reach*=a['probability']
   zero+=reach==0.0
  self.assertGreater(zero,0)
 def test_foreign_view_rejects(self):
  a=_prepare_exact_selected(_request(),pair_diagnostics='compact');b=_prepare_exact_selected(_request(),pair_diagnostics='compact')
  with self.assertRaises(ValueError):train_equivariant_packed(b.view.root,{},10,operator=a.adapter,marginals=_OnePrefixMarginals(a.adapter),shared_view=b.view)
 def test_signed_zero_subnormal_sort_order(self):
  s=float.fromhex('0x0.0000000000001p-1022');v=[[s,-0.],[-s,0.],[0.,-0.]]
  for seq in (v,list(reversed(v)),[v[1],v[0],v[2]]):
   x=_sorted_chance_sum(seq,2);self.assertEqual(tuple(a.hex() for a in x),('0x0.0p+0','0x0.0p+0'))
 def test_mutated_adapter_view_snapshot_rejects(self):
  a=_prepare_exact_selected(_request(),pair_diagnostics='compact');a.view._terminals=tuple(list(a.view._terminals))
  terminal=next(x for x in a.view._terminals if x is not None)
  with self.assertRaises(ValueError):a.adapter.values(terminal,[1.0]*a.kernel.hand_counts[1],0,())
if __name__=='__main__':unittest.main(verbosity=2)
