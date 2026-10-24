"""Exact physical-world equivalence controls for staged rank/card primitives."""
from fractions import Fraction
from unittest.mock import patch
import unittest
from scripts import river_ranked_certificate as q
from scripts import turn_river_validation as rules

class ExactRankedLawTests(unittest.TestCase):
    def check_game(self,board,oop,ip):
        law=q.ExactRankedRiverLaw(board,oop,ip)
        ranges=(rules.expand_range(oop,law.board),rules.expand_range(ip,law.board))
        worlds,_=rules._worlds(law.board,ranges,None)
        self.assertEqual(sum(law.marginals[0]),1);self.assertEqual(sum(law.marginals[1]),1)
        for p in (0,1):
            for i,h in enumerate(law.hands[p]):
                self.assertEqual(law.marginals[p][i],sum((w["weight"] for w in worlds if w["hands"][p]==h),Fraction()))
            reach=tuple(Fraction(i+1,len(law.hands[1-p])+1) for i in range(len(law.hands[1-p])))
            ri=dict(zip(law.hands[1-p],reach))
            for kind,winner in (("showdown",None),("fold",0),("fold",1)):
                node=rules._Terminal(kind,(11.2,29.1),winner) if kind=="fold" else rules._Terminal(kind,(11.2,29.1))
                actual=law.terminal_vector(node,p,reach,17.3)
                for i,h in enumerate(law.hands[p]):
                    expected=Fraction()
                    for world in worlds:
                        if world["hands"][p]!=h:continue
                        value=rules._terminal_payoff(node,{**world,"pot":17.3})
                        payoff=Fraction.from_float(float(value))*(1 if p==0 else -1)
                        expected+=world["weight"]*ri[world["hands"][1-p]]*payoff
                    self.assertEqual(actual[i],expected,(p,h,kind,winner))
        self.assertLessEqual(law.budget.work,100000)
        self.assertTrue(law.budget.counters["static_rank_sort_comparisons_upper_bound"])

    def test_weighted_blockers_ties_and_identical_holdings(self):
        self.check_game("AhKdQcJs2d","AsTc:1,3c4c:0.25,9c9d:0.75,5c6c:0.5","AsKh:0.5,QhTh:0.75,8c8d:0.25,3c4c:1")

    def test_dead_hands_exact_cancellation_and_unequal_refunds(self):
        self.check_game("2c3d4h5s9c","AsAh:1,KcKd:0.25","AsKc:1,AhKd:1,KcKd:1e-10")

    def test_royal_flush_zero_showdown_known_anchor(self):
        law=q.ExactRankedRiverLaw("AcKcQcJcTc","AsAh:1,3d4d:.25","QhTh:.5,8c8d:.25")
        for p in (0,1):
            self.assertEqual(law.terminal_vector(rules._Terminal("showdown",(7.3,12.9)),p,(Fraction(1),Fraction(1)),43.7),(Fraction(),Fraction()))

    def test_no_production_rank_or_payoff_helper_used(self):
        with patch("pokerlab.cards.rank_hand",side_effect=AssertionError("production rank")), patch("pokerlab.ranked_river.rank_hand",side_effect=AssertionError("ranked alias")):
            self.check_game("2c7d9hJs5s","AcKc:1,AsAh:.5,KsKh:1","AcAd:1,KcKd:.75,AcKc:.25")

    def test_malformed_terminal_metadata_is_rejected(self):
        law=q.ExactRankedRiverLaw("AcKdQcJs2d","AsAh","KcKh")
        for node in (rules._Terminal("fold",(0.,0.),True),rules._Terminal("showdown",(-1.,0.)),rules._Terminal("showdown",(float("nan"),0.)),rules._Terminal("showdown",(True,0.))):
            with self.assertRaises(ValueError):law.terminal_vector(node,0,(Fraction(1),),100.)

    def test_exact_caches_are_local_and_reach_keys_are_immutable(self):
        a=q.ExactRankedRiverLaw("AcKdQcJs2d","AsAh,3c4c","KcKh,5c6c")
        b=q.ExactRankedRiverLaw("AcKdQcJs2d","AsAh,3c4c","KcKh,5c6c")
        node=rules._Terminal("showdown",(0.,0.));reach=[Fraction(1),Fraction(1)]
        first=a.terminal_vector(node,0,reach,100.)
        a.terminal_vector(node,0,reach,100.)
        self.assertGreater(a.budget.counters["terminal_vector_cache_hits"],0)
        reach[0]=Fraction()
        changed=a.terminal_vector(node,0,reach,100.)
        self.assertNotEqual(first,changed)
        self.assertEqual(first,b.terminal_vector(node,0,(Fraction(1),Fraction(1)),100.))
        self.assertIsNot(a._index_cache,b._index_cache)
        self.assertIsNot(a._terminal_cache,b._terminal_cache)

    def test_limits_and_invalid_reach_fail(self):
        with self.assertRaisesRegex(ValueError,"work limit"):
            q.ExactRankedRiverLaw("AcKdQcJs2d","AsAh","KcKh",max_work=1)
        with self.assertRaises(ValueError):q.ExactRankedRiverLaw("AcKdQcJs2d","AsAh:1e-300","KcKh",max_bits=64)
        law=q.ExactRankedRiverLaw("AcKdQcJs2d","AsAh","KcKh")
        for reach in ((Fraction(2),),(1.0,),()):
            with self.assertRaises(ValueError):law.terminal_vector(rules._Terminal("showdown",(0.,0.)),0,reach,100.)


class RankedCertificateProfileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import json
        from pathlib import Path
        from tests.test_native_river_controls_saved import _load_runner,EXPECTED_REPORT_SHA256,_sha
        cls.artifact=Path(__file__).resolve().parents[1]/"benchmarks/results/native-river-controls-v1"
        cls.helper=_load_runner()
        raw=(cls.artifact/"report.json").read_bytes()
        if _sha(raw)!=EXPECTED_REPORT_SHA256:raise AssertionError("Retained physical certificate report digest differs")
        cls.report=json.loads(raw)
        cls.cases={c["id"]:c for c in (*cls.helper.BASE_CASES,cls.helper.FRESH_CASE,cls.helper.CHECK_ONLY)}

    def test_every_retained_policy_matches_both_physical_exact_groupings(self):
        import json
        maximum=0
        for profile in self.report["profiles"]:
            case=self.cases[profile["scenario"]]
            for backend in ("native","python"):
                policy=json.loads((self.artifact/profile[backend+"_policy"]["file"]).read_text(encoding="utf-8"))
                with self.subTest(case=case["id"],T=profile["iterations"],backend=backend),self.helper._production_helpers_forbidden() as blocked:
                    with patch.object(rules,"_worlds",side_effect=AssertionError("physical worlds materialized")):
                        actual=q.evaluate_ranked_certificate(policy,case["oop"],case["ip"],board=case["board"],config=case["config"])
                    stored=profile[backend+"_audit"]["exact_audit"]
                    for mode in ("scan","partition"):
                        expected={k:Fraction(v) for k,v in stored["chance_groupings"][mode]["metrics_fraction"].items()}
                        self.assertEqual(actual["metrics"],expected)
                        self.assertEqual(actual["normalized_policy_rows"],stored["chance_groupings"][mode]["normalized_policy_rows"])
                        self.assertEqual(actual["normalization_ledger"],stored["chance_groupings"][mode]["normalization_ledger"])
                    self.assertEqual(actual["worlds_materialized"],0)
                    self.assertEqual(actual["metrics"]["nash_conv"],actual["upper_value_bound"]-actual["lower_value_bound"])
                    self.assertEqual(blocked,[])
                    maximum=max(maximum,actual["work"])
        self.assertLessEqual(maximum,100000)

    def test_malformed_complete_policy_rejects(self):
        import copy,json
        profile=self.report["profiles"][0];case=self.cases[profile["scenario"]]
        saved=json.loads((self.artifact/profile["python_policy"]["file"]).read_text(encoding="utf-8"))
        mutations=[lambda r:r["strategy"].pop(),lambda r:r["strategy"].append(copy.deepcopy(r["strategy"][0])),lambda r:r["strategy"][0]["actions"][0].update(probability=True),lambda r:r["strategy"][0]["actions"][0].update(amount=True),lambda r:r.update(info_sets=True),lambda r:r.update(board=[]),lambda r:r.update(river_config={}),lambda r:r.update(street_configs={}),lambda r:r.update(turn_config={}),lambda r:r.update(strategy_schema="river-strategy-v1"),lambda r:r.update(public_states=True)]
        for mutate in mutations:
            policy=copy.deepcopy(saved);mutate(policy)
            with self.assertRaises(ValueError):q.evaluate_ranked_certificate(policy,case["oop"],case["ip"],board=case["board"],config=case["config"])

    def test_hundred_hand_known_zero_uniform_control_and_old_capacity_rejection(self):
        from itertools import combinations
        from scripts import turn_rational_certificate as physical
        board=rules.cards("AcKcQcJcTc",5)
        deck=[c for c in rules.DECK if c not in board]
        pairs=list(combinations(deck,2))
        oop=",".join("".join(h) for h in pairs[:100]);ip=",".join("".join(h) for h in pairs[-100:])
        cfg=rules._config({"pot":17.3,"effective_stack":[1.1,1.1],"bet_sizes":[.5],"raise_sizes":[],"max_raises":0,"include_all_in":False},"config")
        ranges=(rules.expand_range(oop,board),rules.expand_range(ip,board))
        # Every seven-card hand contains the public royal flush. This known
        # zero-sign physical fixture avoids recomputing the same anchor rank
        # for every pair; ordinary rank correctness is covered above.
        pairs=[(h0,h1) for h0 in ranges[0] for h1 in ranges[1] if not set(h0)&set(h1)]
        worlds=[{"hands":pair,"board":board,"river":None,"weight":Fraction(1,len(pairs)),"sign":0} for pair in pairs]
        root=rules._public_tree(board,cfg,cfg,(),worlds);nodes=rules._collect_nodes(root)
        rows=[]
        for node in nodes:
            for hand in ranges[node.player]:
                if not any(w["hands"][node.player]==hand for w in worlds):continue
                rows.append({"player":"oop" if node.player==0 else "ip","hand":"".join(hand),"street":"river","board":list(board),"history":list(node.history),"actions":[{**a,"probability":1/len(node.actions)} for a in rules._row_actions(node)]})
        policy={"strategy_schema":"postflop-strategy-v1","board":list(board),"config":cfg.to_dict(),"runouts":[],"reachable_runouts":[],"runout_mode":"none","info_sets":len(rows),"deals":len(worlds),"strategy":rows}
        with patch.object(rules,"_worlds",return_value=(worlds,())):
            numeric=rules.replay_policy(policy,oop,ip,board=board,config=cfg)
        with self.helper._production_helpers_forbidden(),patch.object(rules,"_worlds",side_effect=AssertionError("materialized worlds")):
            actual=q.evaluate_ranked_certificate(policy,oop,ip,board=board,config=cfg)
        self.assertEqual(actual["worlds_materialized"],0)
        self.assertGreater(actual["compatible_pairs"],8000)
        self.assertLessEqual(actual["lower_value_bound"],0)
        self.assertLessEqual(0,actual["upper_value_bound"])
        self.assertLessEqual(actual["work"],100000)
        self.assertGreater(actual["work_by_kind"]["terminal_vector_cache_hits"],0)
        for k,v in actual["metrics"].items():self.assertAlmostEqual(float(v),numeric[k],delta=1e-9)
        policies=rules._validate_policy(policy,root,nodes,worlds,board,(),True)
        with self.assertRaisesRegex(ValueError,"work limit"):
            physical.evaluate_exact(root,worlds,policies,cfg.pot,result=policy)

    def test_full_certificate_caps_fail_in_both_modes(self):
        import json
        profile=self.report["profiles"][0];case=self.cases[profile["scenario"]]
        saved=json.loads((self.artifact/profile["python_policy"]["file"]).read_text(encoding="utf-8"))
        for limits in ({"max_work":500},{"max_depth":1},{"max_bits":16},{"max_work":True},{"max_work":100001}):
            with self.subTest(limits=limits),self.assertRaises(ValueError):q.evaluate_ranked_certificate(saved,case["oop"],case["ip"],board=case["board"],config=case["config"],**limits)

if __name__=="__main__":unittest.main()
