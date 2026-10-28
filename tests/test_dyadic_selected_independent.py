import itertools, math, random, unittest
from fractions import Fraction
from sys import float_info
from unittest.mock import patch
from pokerlab.exact_selected_kernel import ExactSelectedRunoutKernel
from pokerlab.exact_selected_float_adapter import ExactSelectedFloatAdapter
from pokerlab.exact_selected_solver import solve_four_street_exact_selected
from scripts.preflop_validation import independent_rank
from tests.test_selected_operator_solver import CASE, request

DECK = tuple(r+s for r in '23456789TJQKA' for s in 'cdhs')
BOARDS = ('2c3c4d7h8h','2c3c4d7h8s','2c3c4d8h7h','ThJhQhKhAh')
RNG = random.Random(77321)

def oracle(kernel, prefix, reach, player, kind, payoff):
    rows=[]
    for i,h0 in enumerate(kernel.hands[0]):
        for j,h1 in enumerate(kernel.hands[1]):
            if set(h0)&set(h1): continue
            for raw in BOARDS:
                b=tuple(raw[k:k+2] for k in range(0,10,2))
                if set(h0+h1)&set(b): continue
                mass=Fraction.from_float(float(kernel.weights[0][i])) * Fraction.from_float(float(kernel.weights[1][j]))
                r0,r1=independent_rank(h0+b),independent_rank(h1+b)
                rows.append((i,j,(''.join(b[:3]),b[3],b[4]),mass,(r0>r1)-(r0<r1)))
    z=sum((r[3] for r in rows),Fraction())
    selected=[r for r in rows if r[2][:len(prefix)]==prefix]
    margins=tuple(tuple(sum((r[3] for r in selected if r[p]==i),Fraction())/z for i in range(len(kernel.hands[p]))) for p in (0,1))
    values=[Fraction() for _ in kernel.hands[player]]
    for i,j,_,mass,sign in selected:
        values[(i,j)[player]] += mass*reach[(j,i)[player]]*payoff*(sign if kind=='showdown' else 1)*(1 if player==0 else -1)/z
    return margins, tuple(values)

class DyadicTerraControls(unittest.TestCase):
    def test_literal_randomized_physical_oracle(self):
        hands=[('As','Ad'),('Ks','Kd'),('Qs','Qd'),('Jh','Jc'),('7h','7d'),('2c','2d'),('9s','9d'),('Ts','Tc')]
        weights=[1.0,0.7,2.0**-1022,2.0**-1074,1e-200]
        prefixes=[(),('2c3c4d',),('2c3c4d','7h'),('2c3c4d','7h','8h'),('ThJhQh',),('5c6c7c',)]
        queries=0
        for _ in range(12):
            s=RNG.sample(hands,4); t=RNG.sample(hands,4)
            a={h:RNG.choice(weights) for h in s}; b={h:RNG.choice(weights) for h in t}
            try: k=ExactSelectedRunoutKernel(a,b,BOARDS,arithmetic='dyadic')
            except ValueError as e:
                if 'no positive compatible' in str(e): continue
                raise
            for prefix, player, kind in itertools.product(prefixes,(0,1),('fold','showdown')):
                reach=tuple(Fraction.from_float(RNG.choice([0.0,0.25,0.7,1.0,2.0**-1074])) for _ in k.hands[1-player])
                payoff=Fraction(-7,8) if kind=='fold' else Fraction(5,8)
                m,v=oracle(k,prefix,reach,player,kind,payoff)
                self.assertEqual(k.joint_marginals_exact(prefix),m)
                self.assertEqual(k.terminal_values_exact(prefix,kind=kind,payoff=payoff,player=player,opponent_reach=reach),v)
                queries+=1
        self.assertEqual(queries,288)

    def test_exact_tie_cancellation_and_zero_reach(self):
        k=ExactSelectedRunoutKernel('2c2d','3c3d',('ThJhQhKhAh',),arithmetic='dyadic')
        for player in (0,1):
            for reach in ((1.0,),(0.0,)):
                self.assertEqual(k.terminal_values_exact((),kind='showdown',payoff=1.0,player=player,opponent_reach=reach),(Fraction(0),))

    def test_win_loss_exact_cancellation(self):
        k=ExactSelectedRunoutKernel('AsAd','KsKd,QsQd',('2c3c4d7hKc',),arithmetic='dyadic')
        self.assertEqual(k.terminal_values_exact((),kind='showdown',payoff=1.0,player=0,opponent_reach=(1.0,1.0)),(Fraction(0),))

    def test_bit_growth_rejects_before_ranking(self):
        k=ExactSelectedRunoutKernel('AsAd','KsKd',('2c3c4d7h8h',),arithmetic='dyadic')
        before=k.statistics()['rank_calls']
        with patch('pokerlab.exact_selected_kernel.rank_hand',side_effect=AssertionError('rank entered')):
            with self.assertRaises(ValueError):
                k.terminal_values_exact((),kind='showdown',payoff=1.0,player=0,opponent_reach=(Fraction(1,2**65530),))
        self.assertEqual(k.statistics()['rank_calls'],before)

    def test_binary64_normal_boundary(self):
        k=ExactSelectedRunoutKernel('AsAd','KsKd',('2c3c4d7h8h',),arithmetic='dyadic')
        from pokerlab.shared_public_topology import compile_shared_public_topology
        from pokerlab.shared_topology_view import SharedPublicView
        from pokerlab.river_tree import _Terminal
        adapter=ExactSelectedFloatAdapter(k,SharedPublicView(compile_shared_public_topology(_Terminal('showdown',(1.,1.)))))
        threshold=Fraction.from_float(float_info.min)-Fraction(1,2**1075)
        self.assertEqual(adapter._convert(threshold),float_info.min)
        self.assertEqual(adapter._convert(-threshold),-float_info.min)
        for x in (threshold-Fraction(1,2**1100),-threshold+Fraction(1,2**1100),Fraction(1,2**2000),-Fraction(1,2**2000)):
            with self.assertRaises(ValueError): adapter._convert(x)
        self.assertEqual(adapter._convert(Fraction()),0.0)

    def test_bad_dyadic_fraction_before_ranking(self):
        k=ExactSelectedRunoutKernel('AsAd','KsKd',('2c3c4d7h8h',),arithmetic='dyadic')
        before=k.statistics()['rank_calls']
        with patch('pokerlab.exact_selected_kernel.rank_hand',side_effect=AssertionError('rank entered')):
            for reach,pay in (((Fraction(1,3),),Fraction(1)),((Fraction(1),),Fraction(1,3))):
                with self.assertRaises(ValueError): k.terminal_values_exact((),kind='showdown',payoff=pay,player=0,opponent_reach=reach)
        self.assertEqual(k.statistics()['rank_calls'],before)

    def test_integer_payload_rejects_before_train_or_rank(self):
        with patch('pokerlab.exact_selected_solver.MAX_DYADIC_INTEGER_PAYLOAD_BITS',1), patch('pokerlab.exact_selected_solver.train_packed',side_effect=AssertionError('training entered')), patch('pokerlab.exact_selected_kernel.rank_hand',side_effect=AssertionError('rank entered')):
            with self.assertRaisesRegex(ValueError,'payload'):
                solve_four_street_exact_selected(request(CASE,iterations=10),exact_arithmetic='dyadic',pair_diagnostics='compact')

if __name__=='__main__': unittest.main(verbosity=2)
