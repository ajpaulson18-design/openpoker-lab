import itertools,unittest
from unittest.mock import patch
from scripts.four_street_validation import build_model
from pokerlab.exact_storage_census import census_exact_selected_storage
from tests.test_four_street_certificate import _case
from tests.test_selected_operator_solver import request

SUITS='cdhs'; DECK=tuple(r+s for r in '23456789TJQKA' for s in SUITS); ORDER={c:i for i,c in enumerate(DECK)}
def card(c,m):return c[0]+m[c[1]]
def hand(h,m):return tuple(sorted(card(c,m) for c in h))
def board(b,m):return tuple(sorted((card(c,m) for c in b[:3]),key=ORDER.__getitem__))+tuple(card(c,m) for c in b[3:])
def hist(h,m):
 out=[]
 for token in h:
  if token.startswith('flop@'):out.append('flop@'+''.join(sorted((card(token[i:i+2],m) for i in (5,7,9)),key=ORDER.__getitem__)))
  elif token.startswith('turn@'):out.append('turn@'+card(token[5:],m))
  elif token.startswith('river@'):out.append('river@'+card(token[6:],m))
  else:out.append(token)
 return tuple(out)

class LiteralOracle(unittest.TestCase):
 def verify(self,case):
  model=build_model(case)
  ranges=[]
  for text in (case['sb_range'],case['bb_range']):
   side={}
   for token in text.split(','):
    h,w=(token.split(':')+['1'])[:2];side[tuple(sorted((h[:2],h[2:])))] = float(w)
   ranges.append(side)
  boards=set(tuple(raw[i:i+2] for i in range(0,10,2)) for raw in case['runouts'])
  group=[]
  for perm in itertools.permutations(SUITS):
   m=dict(zip(SUITS,perm))
   if all({hand(h,m):w for h,w in side.items()}==side for side in ranges) and {board(b,m) for b in boards}==boards:group.append((perm,m))
  keys=model.expected_infos
  orbits=set()
  for player,h,history in keys:
   pair=(h[:2],h[2:])
   orbits.add(min((player,hand(pair,m),hist(history,m)) for _,m in group))
  with patch('pokerlab.exact_selected_kernel.rank_hand',side_effect=AssertionError('rank')),patch('pokerlab.exact_selected_kernel.ExactSelectedRunoutKernel.pair_probability_exact',side_effect=AssertionError('pair')),patch('pokerlab.exact_selected_solver.train_packed',side_effect=AssertionError('train')):
   got=census_exact_selected_storage(request(case))
  self.assertEqual(got['information_rows'],len(keys));self.assertEqual(got['action_slots'],sum(len(n.actions) for n in keys.values()))
  self.assertEqual(got['history_token_entries'],sum(len(k[2]) for k in keys))
  self.assertEqual(got['suit_symmetry']['supported_row_orbits'],len(orbits))
  self.assertEqual(set(got['suit_symmetry']['permutations']),{''.join(x) for x,_ in group})
 def test_symmetric(self):
  case=_case(sb='AcAh:1,AdAh:1',bb='KcKh:1,KdKh:1',stacks=[2,2]);case['runouts']=['2c3c4h5s6h','2d3d4h5s6h'];self.verify(case)
 def test_asymmetric_blockers(self):
  case=_case(sb='AcAh:.7,AdAh:.3,2cAh:.2,2dAh:.4',bb='KcKh:.4,KdKh:.6,3cKh:.8,3dKh:.2',stacks=[2,2]);case['runouts']=['2c3c4h5s6h','2d3d4h5s6h'];self.verify(case)
if __name__=='__main__':unittest.main(verbosity=2)
