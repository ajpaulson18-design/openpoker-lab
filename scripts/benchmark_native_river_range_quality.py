"""Four-call fixed-budget native river quality batch."""
from __future__ import annotations
import argparse, hashlib, json, math, os, platform, subprocess, sys, traceback, uuid
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "docs" / "native-river-range-quality-protocol.md"
CASE_MANIFEST = ROOT / "benchmarks" / "native-river-range-quality-v1.json"
CONTROL_REPORT_SHA256 = "a731d45d9356158eb2711ebf734616c05b174abb236c85406f0e65b87b8c6444"
CONTROL_CLAIM_SHA256 = "7661066e157f285d49a52c8a6b25a14b3eed97cc6b313a7a38220c1f91e64172"
CONTROL_STATUS_SHA256 = "831599649628f7068489821f041c7f9a6c1c56db14a6a7e4b7d93fe3cf258961"
CONTROL_HELPER_SHA256 = "a4155547d39b49c65a7fcb3b22a0ee5ce751de17a6183026ee713f62f88203b6"
CASE_MANIFEST_LF_SHA256 = "49f8b00bd8ef43f8328b4fd4b485a98f9bc7ec991d2a68bfc0adf73d1ac2575f"
CONTROL_DIRNAME = "native-river-controls-v1-attempt-20261023"
METRICS = ("value_oop", "value_ip", "oop_best_response_value", "ip_best_response_value", "oop_best_response_gain", "ip_best_response_gain", "nash_conv", "exploitability")


def _sha(data): return hashlib.sha256(data).hexdigest()
def _lf(data): return data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
def _json_bytes(value): return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")
def _pretty(value): return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")
def _exclusive(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())
def _atomic(path, value):
    raw = _pretty(value); tmp = path.with_name(path.name + ".tmp")
    with tmp.open("xb") as stream: stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    os.replace(tmp, path)
def _inside(path, parent):
    try: path.relative_to(parent); return True
    except ValueError: return False


def authenticate_control_corpus(control_root):
    """Authenticate the retained, completed 16-policy corpus before study claim."""
    control_root = Path(control_root).resolve()
    report_path = control_root / "report.json"
    raw = report_path.read_bytes()
    if _sha(raw) != CONTROL_REPORT_SHA256:
        raise RuntimeError("Retained native-river-controls-v1 report digest mismatch")
    report = json.loads(raw.decode("utf-8"))
    claim_raw=(control_root/"claim.json").read_bytes(); status_raw=(control_root/"status.json").read_bytes()
    if _sha(claim_raw)!=CONTROL_CLAIM_SHA256 or _sha(status_raw)!=CONTROL_STATUS_SHA256: raise RuntimeError("Retained control claim/status digest mismatch")
    claim = json.loads(claim_raw.decode("utf-8")); status = json.loads(status_raw.decode("utf-8"))
    if report.get("schema") != "compiled-river-conformance-report-v1" or report.get("status") != "completed":
        raise RuntimeError("Retained control report is not completed")
    if not claim.get("claim_id") or not (claim["claim_id"] == report.get("claim_id") == status.get("claim_id")):
        raise RuntimeError("Retained control report/claim/status identity mismatch")
    if status.get("status") != "completed" or status.get("retry_permitted") is not False:
        raise RuntimeError("Retained control status is not completed/no-retry")
    if claim.get("retry_permitted") is not False:
        raise RuntimeError("Retained control claim does not forbid retry")
    receipts = []
    for profile in report.get("profiles", []):
        for backend in ("python_policy", "native_policy"):
            receipt = profile.get(backend)
            if not isinstance(receipt, dict): raise RuntimeError("Control policy receipt is missing")
            path = control_root / receipt["file"]
            policy = path.read_bytes()
            if len(policy) != receipt.get("bytes") or _sha(policy) != receipt.get("sha256"):
                raise RuntimeError("Retained control policy hash/size mismatch")
            receipts.append({"file": receipt["file"], "bytes": len(policy), "sha256": _sha(policy)})
    if len(receipts) != 16:
        raise RuntimeError(f"Expected all sixteen retained policies, found {len(receipts)}")
    return {"root":str(control_root),"report_sha256":_sha(raw),"claim_sha256":_sha(claim_raw),"status_sha256":_sha(status_raw),"claim_id":claim["claim_id"],"status":status["status"],"policy_count":len(receipts),"policies":receipts}


class ProductionRuntime:
    """Bindings to the frozen checkout and existing no-training/replay helpers."""
    def __init__(self, source_root, build_directory):
        self.root = Path(source_root).resolve(); self.build = Path(build_directory).resolve()
        sys.path.insert(0, str(self.root)) if str(self.root) not in sys.path else None
        if Path(__file__).resolve()!=self.root/"scripts"/"benchmark_native_river_range_quality.py": raise RuntimeError("production runner must resolve from its pinned checkout path")
        from scripts import benchmark_river_heldout_quality as baseline
        from scripts import preflop_validation as ranks
        from scripts import turn_rational_certificate as exact
        from scripts import turn_river_validation as rules
        from pokerlab import native_river_solver as native
        from pokerlab import native_fixed_street as fixed
        from pokerlab import postflop_solver as post
        from pokerlab import public_cfr as public
        from pokerlab import turn_tail_adapter as turn
        from pokerlab import river_tail_adapter as river
        from pokerlab import river_config as rc
        self.baseline, self.ranks, self.exact, self.rules = baseline, ranks, exact, rules
        self.native, self.fixed, self.post, self.public, self.turn, self.river = native, fixed, post, public, turn, river
        self.river_config = rc.RiverConfig

    def source_snapshot(self, expected_head):
        from scripts import benchmark_river_heldout_quality as baseline
        from pathlib import Path
        from scripts import turn_river_validation
        # Reuse the reviewed auth used by the retained conformance runner.
        from importlib.util import spec_from_file_location, module_from_spec
        helper_path = self.root / "benchmarks" / "results" / "native-river-controls-v1" / "validate_compiled_river.py"
        if _sha(helper_path.read_bytes())!=CONTROL_HELPER_SHA256: raise RuntimeError("pinned retained control helper hash mismatch")
        spec = spec_from_file_location("_retained_native_river_controls", helper_path)
        helper = module_from_spec(spec); spec.loader.exec_module(helper)
        state = helper._source_snapshot(self.root, baseline)
        if state.get("head") != expected_head or state.get("status") != "clean":
            raise RuntimeError("Checkout HEAD/clean source pin differs")
        external = {}
        for path in (Path(__file__).resolve(), PROTOCOL, CASE_MANIFEST):
            raw = path.read_bytes(); external[str(path)] = {"bytes":len(raw),"raw_sha256":_sha(raw),"normalized_lf_sha256":_sha(_lf(raw))}
        # Add the reusable 8x8 census helper to the committed source pin explicitly.
        rel="scripts/river_heldout_preflight.py"; target=self.root/rel
        committed_helper=subprocess.check_output(["git","-C",str(self.root),"show",f"{expected_head}:{rel}"],stderr=subprocess.STDOUT)
        helper_raw=target.read_bytes()
        if _lf(helper_raw)!=_lf(committed_helper): raise RuntimeError("independent census helper differs from expected committed source")
        state.setdefault("files",{})[rel]={"bytes":len(helper_raw),"raw_sha256":_sha(helper_raw),"normalized_lf_sha256":_sha(_lf(helper_raw)),"git_blob":subprocess.check_output(["git","-C",str(self.root),"rev-parse",f"{expected_head}:{rel}"],text=True).strip()}
        state["study_source_files"] = external
        # When installed in the checkout, bind these new files to the expected committed Git blobs too.
        committed = {}
        for rel in ("scripts/benchmark_native_river_range_quality.py", "docs/native-river-range-quality-protocol.md", "benchmarks/native-river-range-quality-v1.json"):
            target=self.root/rel
            if not target.is_file(): raise RuntimeError("required new source is absent from checkout: "+rel)
            blob_raw=subprocess.check_output(["git","-C",str(self.root),"show",f"{expected_head}:{rel}"],stderr=subprocess.STDOUT)
            raw=target.read_bytes()
            if _lf(raw)!=_lf(blob_raw): raise RuntimeError("new source differs from committed expected Git blob: "+rel)
            blob=subprocess.check_output(["git","-C",str(self.root),"rev-parse",f"{expected_head}:{rel}"],text=True,stderr=subprocess.STDOUT).strip()
            committed[rel]={"git_blob":blob,"raw_sha256":_sha(raw),"normalized_lf_sha256":_sha(_lf(raw))}
        state["new_source_git_pins"] = committed
        return state

    def build_snapshot(self):
        from importlib.util import spec_from_file_location, module_from_spec
        helper_path = self.root / "benchmarks" / "results" / "native-river-controls-v1" / "validate_compiled_river.py"
        if _sha(helper_path.read_bytes())!=CONTROL_HELPER_SHA256: raise RuntimeError("pinned retained control helper hash mismatch")
        spec = spec_from_file_location("_retained_native_river_build", helper_path)
        helper = module_from_spec(spec); spec.loader.exec_module(helper)
        return helper._build_snapshot(self.build, self.root)

    def preflight(self, case, iterations):
        """Mirror every production and native full-request admission without backend lookup."""
        cards = self.native.cards
        board = cards(case["board"]); cfg = self.native._config(case["config"], "config")
        hands, worlds, selected, pair_count = self.native._enumerate_worlds(board, case["oop"], case["ip"], iterations=iterations)
        if selected: raise ValueError("river case unexpectedly contains future runouts")
        allocation = {}; root, nodes, chance_nodes, visited, _ = self.native._build_postflop_tree(board, cfg, worlds=worlds, allocation_counts=allocation)
        if chance_nodes: raise ValueError("river public tree contains chance nodes")
        if len(worlds)*visited*iterations*3 > self.river.MAX_WORLD_NODE_WORK: raise ValueError("historical river world-node admission rejected")
        legal = self.native._prefix_hand_index(worlds)
        slots = sum(len(node.actions)*len(legal.get((player,()),())) for (player,_),node in nodes.items())
        if slots > self.turn.MAX_INFO_ACTION_SLOTS: raise ValueError("historical info-action slot admission rejected")
        dense = max(map(len,hands))*allocation["total"]*(3*iterations+3)
        if dense > self.turn.MAX_DENSE_HAND_STATE_PASS_WORK: raise ValueError("historical dense work admission rejected")
        infos = {}
        for (player,history),node in nodes.items():
            for idx in sorted(legal.get((player,()),())): infos[(player,idx,history)] = len(node.actions)
        _, hand_counts = self.public._validate_inputs(worlds,infos,iterations,"cfrplus",cfg.pot,self.native._Chance)
        edges,_ = self.public._aggregate_prefixes(worlds,hand_counts); prefix=sum(len(row) for row in edges.values())
        if prefix > self.public.MAX_PREFIX_EDGES: raise ValueError("historical prefix edge admission rejected")
        # Independent numeric-model world and traversal admissions are separate from production guards.
        from scripts import turn_river_validation as independent_rules
        iboard=independent_rules.cards(case["board"],5); icfg=independent_rules._config(case["config"],"config")
        iworlds,iselected=independent_rules._worlds(iboard,(independent_rules.expand_range(case["oop"],iboard),independent_rules.expand_range(case["ip"],iboard)),None)
        if len(iworlds)>independent_rules.MAX_WORLD_COUNT: raise ValueError("independent MAX_WORLD_COUNT admission rejected")
        iroot=independent_rules._public_tree(iboard,icfg,icfg,iselected,iworlds); inodes=independent_rules._collect_nodes(iroot)
        if len(inodes)*len(iworlds)*4>independent_rules.MAX_ORACLE_WORK: raise ValueError("independent modeled numeric replay admission rejected")
        # Independent rules census adapted from the pinned held-out helper primitives
        # (whose published CASES-specific wrapper assumes 4x4 ranges).
        from scripts import river_heldout_preflight as preflight
        production_census_root, _ = preflight._build_tree(self.river_config.from_dict(case["config"]))
        independent_census_root = independent_rules._public_tree(iboard,icfg,icfg,iselected,iworlds)
        prod_sig=preflight._tree_signature(production_census_root,independent=False,pot=icfg.pot)
        indep_sig=preflight._tree_signature(independent_census_root,independent=True,pot=icfg.pot)
        native_sig=preflight._tree_signature(root,independent=False,pot=cfg.pot)
        if prod_sig != indep_sig or native_sig != indep_sig: raise AssertionError("independent census found a production/native public tree/utility mismatch")
        counts=preflight._walk(independent_census_root,independent=True)
        uniform,uniform_policies,census_nodes=preflight._uniform_production_artifact(case,iboard,production_census_root,iworlds,self.river_config.from_dict(case["config"]))
        replay=independent_rules.replay_policy(uniform,case["oop"],case["ip"],board=iboard,config=self.river_config.from_dict(case["config"]))
        uniform.update({m:replay[m] for m in ("value_oop","value_ip","oop_best_response_value","ip_best_response_value","oop_best_response_gain","ip_best_response_gain","nash_conv","exploitability")})
        independent_rules.compare_result(uniform,replay,tolerance=1e-9)
        exact_smokes={}
        for mode in ("scan","partition"):
            result=self.exact.evaluate_exact(independent_census_root,iworlds,uniform_policies,icfg.pot,result=uniform,chance_grouping=mode,max_work=self.exact.MAX_EXACT_WORK,max_depth=self.exact.MAX_EXACT_DEPTH,max_bits=self.exact.MAX_FRACTION_BITS)
            exact_smokes[mode]={"work":result["work"],"depth":result["tree_depth"],"fraction_bits":result["maximum_fraction_bits"],"nash_conv":str(result["metrics"]["nash_conv"])}
        if exact_smokes["scan"]["nash_conv"]!=exact_smokes["partition"]["nash_conv"]: raise AssertionError("adapted full-range exact scan/partition disagreement")
        # Independently validate every enumerated native physical pair, normalized joint mass and showdown sign.
        independent_by_pair={(tuple(w["hands"][0]),tuple(w["hands"][1])):w for w in iworlds}
        if len(independent_by_pair)!=len(iworlds): raise AssertionError("independent worlds contain duplicate physical pairs")
        if len(worlds)!=len(independent_by_pair): raise AssertionError("production and independent enumerators differ in world count")
        mass_error=0.0
        production_pairs=set()
        for wi in worlds:
            h0,h1,mass,sign=wi[:4]; pair=(tuple(hands[0][h0]),tuple(hands[1][h1])); iw=independent_by_pair.get(pair)
            if pair in production_pairs: raise AssertionError("production worlds contain duplicate physical pairs")
            production_pairs.add(pair)
            if iw is None: raise AssertionError("production world pair absent from independent enumerator")
            err=abs(float(iw["weight"])-float(mass)); mass_error=max(mass_error,err)
            if err>1e-15: raise AssertionError("production normalized world mass differs from independent physical law")
            r0=self.ranks.independent_rank(iboard+pair[0]); r1=self.ranks.independent_rank(iboard+pair[1]); isign=(r0>r1)-(r0<r1)
            if sign!=isign or sign!=iw["sign"]: raise AssertionError("production rank sign differs from independent rank evaluator")
        if production_pairs!=set(independent_by_pair): raise AssertionError("production and independent physical pair sets differ")
        physical_rank_census={"world_pairs":len(worlds),"mass_max_abs_difference":mass_error,"ties":sum(1 for w in worlds if w[3]==0),"rank_signs":{"loss":sum(w[3]<0 for w in worlds),"tie":sum(w[3]==0 for w in worlds),"win":sum(w[3]>0 for w in worlds)}}
        adapted_census={"independent_tree_decisions":counts[0],"independent_tree_terminals":counts[1],"independent_tree_action_slots":counts[2],"max_depth":counts[3],"production_tree_signature_matches":True,"native_postflop_tree_signature_matches":True,"uniform_numeric_replay_metrics":{m:float(replay[m]) for m in METRICS},"uniform_exact_smokes":exact_smokes,"production_physical_world_crosscheck":physical_rank_census,"independent_rank_census":self._rank_census(iboard,case,iworlds)}
        native_world_rows=[(w[0],w[1],w[2],w[2]*w[3]) for w in worlds]
        native_active=self.fixed._worlds(native_world_rows,reduction="public-batched")
        native_nodes=list(self.fixed._walk(root,cfg.pot)); max_native_depth=0; max_native_actions=0; pending=[(root,0)]
        while pending:
            node,depth=pending.pop(); max_native_depth=max(max_native_depth,depth)
            if hasattr(node,"actions"): max_native_actions=max(max_native_actions,len(node.actions)); pending.extend((child,depth+1) for child in node.children)
        if len(nodes)>self.post._MAX_PUBLIC_NODES: raise ValueError("historical public-node admission rejected")
        native_admit = self.fixed.admit_native_shape(allocation["total"],len(worlds),slots,iterations,"cfrplus",reduction="public-batched",hand_counts=tuple(len({w[p] for w in worlds}) for p in (0,1)))
        return {"case_id":case["id"],"iterations":iterations,"candidate_hand_pair_iterations":len(hands[0])*len(hands[1])*iterations,"world_iterations":len(worlds)*iterations,"world_node_work":len(worlds)*visited*iterations*3,"dense_hand_state_pass_work":dense,"worlds":len(worlds),"compatible_pairs":pair_count,"public_states":allocation["total"],"public_nodes":len(nodes),"terminal_nodes":allocation.get("terminal"),"information_sets":len(infos),"chance_nodes":chance_nodes,"world_traversal_nodes":visited,"tree_actions":sum(len(node.actions) for node in nodes.values()),"native_tree_nodes":len(native_nodes),"native_tree_max_depth":max_native_depth,"native_tree_max_actions":max_native_actions,"native_active_hand_counts":[len(native_active[0]),len(native_active[1])],"information_action_slots":slots,"prefix_hand_edges":prefix,"independent_world_count":len(iworlds),"independent_max_world_count":independent_rules.MAX_WORLD_COUNT,"independent_numeric_modeled_work":len(inodes)*len(iworlds)*4,"independent_numeric_modeled_work_limit":independent_rules.MAX_ORACLE_WORK,"adapted_independent_census":adapted_census,"native_shape_admission":native_admit,"trainer_or_build_lookup_called":False}

    def call(self, case, backend, iterations):
        cfg = self.river_config.from_dict(case["config"])
        if backend == "python-materialized-D0":
            from pokerlab import river_tail_adapter
            return river_tail_adapter.solve_river_tail(case["board"],case["oop"],case["ip"],cfg,iterations=iterations,discard=0)
        return self.native.solve_native_river(case["board"],case["oop"],case["ip"],cfg,iterations=iterations,build_directory=self.build)

    def audit(self, result, case, limits):
        # Reuse the existing audited T=10,000 independent pipeline unchanged.
        # It performs physical numeric replay, all eight metric checks, row/count
        # validation, both exact groupings, and reports exact-cap rejection.
        from contextlib import nullcontext
        from importlib.util import spec_from_file_location, module_from_spec
        helper_path = self.root / "benchmarks" / "results" / "native-river-controls-v1" / "validate_compiled_river.py"
        if _sha(helper_path.read_bytes())!=CONTROL_HELPER_SHA256: raise RuntimeError("pinned retained control helper hash mismatch")
        spec = spec_from_file_location("_native_river_audit_tripwire", helper_path)
        helper = module_from_spec(spec); spec.loader.exec_module(helper)
        with helper._production_helpers_forbidden() as blocked:
            base = self.baseline._audit_policy(result, case)
        if blocked: raise RuntimeError("Independent replay reached a production solver/model helper")
        exact = base["exact"]
        groups = exact.get("chance_groupings", {})
        if exact.get("status") == "admitted":
            if set(groups) != {"scan", "partition"} or any(groups[k].get("status") != "admitted" for k in groups):
                raise ValueError("exact oracle did not admit both scan and partition")
            target = exact.get("target_met")
        elif exact.get("status") == "admission-rejected":
            target = None
        else:
            raise ValueError("exact oracle returned an unknown status")
        board = self.rules.cards(case["board"], 5)
        ranges = (self.rules.expand_range(case["oop"], board), self.rules.expand_range(case["ip"], board))
        worlds, _ = self.rules._worlds(board, ranges, None)
        rank = self._rank_census(board, case, worlds)
        return {"numeric_metrics":base["metrics"], "numeric_differences":base["float_replay_differences"],
                "world_count":base["worlds"], "compatible_pairs":base["compatible_pairs"],
                "information_sets":base["information_sets"], "public_decision_nodes":base["public_decision_nodes"],
                "rank_census":rank, "action_rows":result["strategy"], "exact_audit":exact,
                "exact_audits":groups, "quality_gate":target, "blocked_production_helper_calls":[]}

    def _rank_census(self, board, case, worlds):
        rules=self.rules; ranges=(rules.expand_range(case["oop"],board),rules.expand_range(case["ip"],board)); vals=[]
        for side in ranges: vals.append({"".join(hand):self.ranks.independent_rank(board+hand) for hand in side})
        ties=[]
        for world in worlds:
            h0,h1=world["hands"]
            if vals[0]["".join(h0)]==vals[1]["".join(h1)]: ties.append(["".join(h0),"".join(h1)])
        return {"categories":sorted({rank[0] for side in vals for rank in side.values()}),"compatible_exact_rank_tie_worlds":len(ties),"tie_pairs":ties,"per_hand_category":[{k:v[0] for k,v in side.items()} for side in vals]}


def _validate_return(result, case, backend, iterations):
    if not isinstance(result,dict): raise ValueError("solver did not return an object")
    required=("algorithm","solver_version","strategy_schema","board","config","iterations","requested_iterations","discard","source_iteration_window","averaged_sweeps","average_weight_sum","requested_average_passes","requested_regret_passes","requested_total_traversal_passes","average_schedule","update_schedule","value_oop","value_ip","oop_best_response_value","ip_best_response_value","oop_best_response_gain","ip_best_response_gain","nash_conv","exploitability","strategy","worlds","worlds_materialized","deals","compatible_pairs","info_sets","public_nodes","public_states","terminal_nodes","chance_nodes","world_traversal_nodes","tree_actions","training_calls","resource_usage")
    missing=[name for name in required if name not in result]
    if missing: raise ValueError("solver return omitted required metadata: "+", ".join(missing))
    if type(iterations) is not int or type(result["iterations"]) is not int or type(result["requested_iterations"]) is not int or type(result["discard"]) is not int or type(result["averaged_sweeps"]) is not int or type(result["average_weight_sum"]) is not int or type(result["requested_average_passes"]) is not int or type(result["requested_regret_passes"]) is not int or type(result["requested_total_traversal_passes"]) is not int or type(result["source_iteration_window"]) is not list or len(result["source_iteration_window"])!=2 or any(type(v) is not int for v in result["source_iteration_window"]): raise ValueError("CFR+ schedule metadata must use exact integer types")
    if result["algorithm"]!="cfrplus" or result["iterations"]!=iterations or result["requested_iterations"]!=iterations or result["discard"]!=0 or result["source_iteration_window"]!=[1,iterations] or result["averaged_sweeps"]!=iterations or result["average_weight_sum"]!=iterations*(iterations+1)//2 or result["requested_average_passes"]!=iterations or result["requested_regret_passes"]!=2*iterations or result["requested_total_traversal_passes"]!=3*iterations: raise ValueError("solver returned falsified CFR+ T/window/weight/pass metadata")
    if result["worlds_materialized"]!=result["worlds"] or result["compatible_pairs"]!=result["deals"]: raise ValueError("returned physical world/pair counts disagree")
    if result["strategy_schema"]!="postflop-strategy-v1" or result["board"]!=[case["board"][i:i+2] for i in range(0,len(case["board"]),2)] or _json_bytes(result["config"])!=_json_bytes(case["config"]): raise ValueError("solver result case identity/schema mismatch")
    for name in ("worlds","worlds_materialized","deals","compatible_pairs","info_sets","public_nodes","public_states","terminal_nodes","chance_nodes","world_traversal_nodes","tree_actions","training_calls"):
        if type(result[name]) is not int or result[name]<0: raise ValueError("solver count metadata must be exact nonnegative integers: "+name)
    if result["training_calls"]!=1: raise ValueError("training call count must be exactly one")
    if backend=="native":
        if result["solver_version"]!="research-native-river-cfrplus-v1" or not isinstance(result.get("native_training"),dict): raise ValueError("native solver version/build receipt missing")
        if result.get("execution_backend")!="native-fixed-street-public-batched-river" or result.get("average_schedule")!="native-linear-completed-sweep-own-reach": raise ValueError("unexpected native execution/averaging version")
    else:
        if result["solver_version"]!="research-river-tail-adapter-v1" or result.get("average_schedule")!="direct-original-linear-sweep-weight-own-reach-tail": raise ValueError("unexpected Python materialized solver/averaging version")
    if result.get("update_schedule")!="alternating-oop-then-ip": raise ValueError("unexpected CFR+ update schedule")
    for metric in METRICS:
        v=result.get(metric)
        if isinstance(v,bool) or not isinstance(v,(float,int)) or not math.isfinite(float(v)): raise ValueError("invalid metric metadata: "+metric)
    if not isinstance(result["strategy"],list) or not result["strategy"] or not isinstance(result["resource_usage"],dict): raise ValueError("full strategy rows/resource provenance missing")
    return result


def _validate_native_receipt(result, build_snapshot, expected_admission):
    receipt=result.get("native_training")
    if not isinstance(receipt,dict) or not isinstance(receipt.get("build"),dict) or not isinstance(receipt.get("admission"),dict): raise ValueError("native result is missing build/admission receipt")
    if receipt.get("backend")!="native-fixed-street-v1" or receipt.get("reduction")!="public-batched": raise ValueError("native receipt backend/reduction identity differs")
    if type(receipt.get("native_world_rows")) is not int or receipt["native_world_rows"]!=expected_admission["world_rows"]: raise ValueError("native receipt world-row count differs from fresh admission")
    for key in ("input_sha256","output_sha256"):
        value=receipt.get(key)
        if not isinstance(value,str) or len(value)!=64 or any(ch not in "0123456789abcdef" for ch in value): raise ValueError("native receipt omitted a valid protocol payload hash: "+key)
    build=receipt["build"]; manifest=build_snapshot["manifest"]
    if _json_bytes(build)!=_json_bytes(manifest):
        raise ValueError("native receipt build identity or JSON types differ")
    if build_snapshot.get("manifest_sha256") is None or _json_bytes(receipt["admission"])!=_json_bytes(expected_admission): raise ValueError("native receipt does not match pinned build or fresh full-request admission")
    admission=receipt["admission"]
    for key in ("requested_iterations","algorithm","reduction","total_loop_entries_upper_bound","total_loop_entry_limit","native_heap_bytes_upper_bound","native_heap_byte_limit","wire_bytes_upper_bound","wire_byte_limit"):
        if key not in admission: raise ValueError("native receipt omitted admission field "+key)
    if admission["requested_iterations"]!=result["iterations"] or admission["algorithm"]!="cfrplus" or admission["reduction"]!="public-batched": raise ValueError("native receipt request/admission identity differs")


def _validate_admission(item):
    caps={"candidate_hand_pair_iterations":3000000,"world_iterations":3000000,"world_node_work":30000000,"dense_hand_state_pass_work":30000000,"public_states":250000,"public_nodes":10000,"information_action_slots":1000000,"prefix_hand_edges":250000,"worlds":384,"independent_world_count":200000,"independent_numeric_modeled_work":8000000}
    for key,cap in caps.items():
        value=item.get(key)
        if type(value) is not int or value<0 or value>cap: raise ValueError("fresh full-request admission missing/over cap: "+key)
    if item.get("iterations")!=10000 or item.get("case_id") not in ("river-weighted-8x8-blocker-tie-short-refund","river-paired-8x8-short-refund-zero-tie") or item.get("backend_cell") not in ("python-materialized-D0","native"): raise ValueError("admission receipt identity/T is invalid")
    for key in ("compatible_pairs","information_sets","terminal_nodes","native_tree_nodes","native_tree_max_depth","native_tree_max_actions","independent_numeric_modeled_work_limit","chance_nodes","world_traversal_nodes","tree_actions"):
        if type(item.get(key)) is not int or item[key]<0: raise ValueError("fresh admission count missing/invalid: "+key)
    if item.get("native_active_hand_counts") != [8,8]: raise ValueError("fresh admission active hand counts are not the frozen 8x8 ranges")
    native=item.get("native_shape_admission")
    if not isinstance(native,dict) or native.get("requested_iterations")!=10000 or native.get("algorithm")!="cfrplus" or native.get("reduction")!="public-batched": raise ValueError("native shape admission is absent or for another request")
    for key,cap in (("total_loop_entries_upper_bound",500000000),("native_heap_bytes_upper_bound",67108864),("wire_bytes_upper_bound",8388608)):
        value=native.get(key)
        if type(value) is not int or not 0<=value<=cap: raise ValueError("native full-request shape exceeds/misses fixed envelope: "+key)
    if native.get("public_states")!=item["public_states"] or native.get("world_rows")!=item["worlds"] or native.get("information_action_slots")!=item["information_action_slots"]: raise ValueError("native shape receipt differs from fresh public/world/action counts")
    if native.get("total_loop_entry_limit")!=500000000 or native.get("native_heap_byte_limit")!=67108864 or native.get("wire_byte_limit")!=8388608: raise ValueError("native fixed envelope limits changed")
    if item["native_tree_max_depth"]>32 or item["native_tree_max_actions"]>12: raise ValueError("native structural tree admission exceeds fixed limits")
    if item.get("native_active_hand_counts")!=[8,8] or native.get("active_hand_counts")!=[8,8]: raise ValueError("native shape receipt does not contain the frozen 8x8 active ranges")
    if item.get("trainer_or_build_lookup_called") is not False: raise ValueError("preflight unexpectedly invoked trainer/build lookup")
    return item

def _validate_manifest(manifest):
    ids=("river-weighted-8x8-blocker-tie-short-refund","river-paired-8x8-short-refund-zero-tie")
    calls=[(ids[0],"python-materialized-D0"),(ids[0],"native"),(ids[1],"python-materialized-D0"),(ids[1],"native")]
    if manifest.get("iterations")!=10000 or [c.get("id") for c in manifest.get("cases",[])]!=list(ids): raise ValueError("case/iteration manifest differs from frozen design")
    if [(c.get("case"),c.get("backend")) for c in manifest.get("calls",[])]!=calls: raise ValueError("call grid differs from exact four-call order")
    if manifest.get("target_nash_conv")!="1/1000" or manifest.get("policy_probability_tolerance")!=1e-9 or manifest.get("metric_tolerance")!=1e-8: raise ValueError("target/parity contract differs from frozen design")
    if manifest.get("exact_limits")!={"work":100000,"depth":64,"fraction_bits":65536}: raise ValueError("exact audit limits differ from frozen design")
    if manifest.get("independent_numeric_limits")!={"MAX_WORLD_COUNT":200000,"MAX_ORACLE_WORK":8000000,"exact_work":100000,"exact_depth":64,"exact_fraction_bits":65536}: raise ValueError("independent numeric caps differ from pinned source")


def _policy_parity(native, python, audit_n, audit_p, tol_policy, tol_metric):
    def index(result):
        rows={}
        for row in result["strategy"]:
            k=(row["player"],row["hand"],tuple(row["history"]))
            if k in rows: raise ValueError("duplicate information-set row")
            rows[k]=row
        return rows
    ni,pi=index(native),index(python)
    if set(ni)!=set(pi): return {"status":"failed","reason":"information-set coverage differs","max_probability_delta":None,"metric_deltas":None}
    maximum=0.0
    for key in ni:
        na,pa=ni[key]["actions"],pi[key]["actions"]
        if len(na)!=len(pa): return {"status":"failed","reason":"action cardinality differs","max_probability_delta":None,"metric_deltas":None}
        for a,b in zip(na,pa):
            if any(a.get(f)!=b.get(f) for f in ("name","amount","raise_to","history_key")): return {"status":"failed","reason":"action metadata differs","max_probability_delta":None,"metric_deltas":None}
            maximum=max(maximum,abs(float(a["probability"])-float(b["probability"])))
    deltas={m:float(audit_n["numeric_metrics"][m])-float(audit_p["numeric_metrics"][m]) for m in METRICS}
    failed=maximum>tol_policy or any(abs(v)>tol_metric for v in deltas.values())
    return {"status":"failed" if failed else "passed","max_probability_delta":maximum,"metric_deltas":deltas,"policy_tolerance":tol_policy,"metric_tolerance":tol_metric}


def run_with_runtime(runtime, manifest, output, expected_head, build_path, control_auth):
    """Strict one-shot lifecycle with injectable dependencies for no-training tests."""
    _validate_manifest(manifest)
    output=Path(output).resolve(); root=Path(runtime.root).resolve(); build=Path(build_path).resolve()
    if _inside(output,root) or _inside(output,build): raise ValueError("output must be outside checkout and build")
    if output.exists(): raise FileExistsError(output)
    before_source=runtime.source_snapshot(expected_head); before_build=runtime.build_snapshot()
    case_by_id={c["id"]:c for c in manifest["cases"]}; admissions=[]
    for cell in manifest["calls"]:
        item=runtime.preflight(case_by_id[cell["case"]],manifest["iterations"]); item["backend_cell"]=cell["backend"]
        if item.get("case_id")!=cell["case"] or item.get("iterations")!=manifest["iterations"]: raise ValueError("fresh admission identity differs from call cell")
        admissions.append(_validate_admission(item))
    if len(admissions)!=4: raise ValueError("all four backend/case full-request admissions are required before claim")
    claim_id=uuid.uuid4().hex; saved=[]; profiles=[]; active=None; created=False
    claim={"schema":"native-river-range-quality-claim-v1","claim_id":claim_id,"output":str(output),"source":before_source,"build":before_build,"control_authentication":control_auth,"manifest":manifest,"preflight_admissions":admissions,"target_nash_conv":manifest["target_nash_conv"],"created_utc":datetime.now(timezone.utc).isoformat(),"retry_permitted":False}
    status={"claim_id":claim_id,"status":"starting","phase":"claim","saved_policies":[],"completed_audits":[],"retry_permitted":False}
    def guards(label):
        _same(before_source,runtime.source_snapshot(expected_head),"source "+label)
        _same(before_build,runtime.build_snapshot(),"build "+label)
        if control_auth.get("root"):
            _same(control_auth,authenticate_control_corpus(control_auth["root"]),"retained controls "+label)
    def verify_policy(receipt):
        raw=(output/receipt["file"]).read_bytes()
        if len(raw)!=receipt["bytes"] or _sha(raw)!=receipt["sha256"]: raise RuntimeError("saved raw policy receipt changed")
        loaded=json.loads(raw.decode("utf-8"))
        if _json_bytes(loaded)!=raw: raise RuntimeError("saved raw policy is not canonical UTF-8 JSON")
        return raw,loaded
    try:
        output.mkdir(parents=True,exist_ok=False); created=True
        _exclusive(output/"claim.json",_pretty(claim)); (output/"policies").mkdir()
        status["status"]="running"; _atomic(output/"status.json",status)
        # Persist all four raw returns first. No policy metadata or quality audit is a gate here.
        for index,cell in enumerate(manifest["calls"]):
            active={**cell,"index":index,"iterations":manifest["iterations"]}; case=case_by_id[cell["case"]]
            guards("before call")
            result=runtime.call(case,cell["backend"],manifest["iterations"])
            raw=_json_bytes(result)
            filename=f"{case['id']}-{cell['backend']}-T{manifest['iterations']}.json"; path=output/"policies"/filename
            _exclusive(path,raw); loaded=path.read_bytes()
            receipt={"file":"policies/"+filename,"bytes":len(raw),"sha256":_sha(raw),"case":case["id"],"backend":cell["backend"],"iterations":manifest["iterations"]}
            saved.append(receipt)
            if loaded!=raw or _sha(loaded)!=receipt["sha256"]: raise RuntimeError("raw policy failed immediate save/reload")
            status.update({"phase":"training","active_call":active,"saved_policies":saved.copy()}); _atomic(output/"status.json",status)
            guards("after call")
        if len(saved)!=4: raise RuntimeError("four raw policies were not persisted")
        # Validate all four files before any metadata, replay, exact audit, or parity work.
        for receipt in saved: verify_policy(receipt)
        status.update({"phase":"independent-audits","active_call":None}); _atomic(output/"status.json",status)
        audits={}
        preflight_by_cell={(a["case_id"],a["backend_cell"]):a for a in admissions}
        for receipt in saved:
            guards("before audit")
            raw,result=verify_policy(receipt); case=case_by_id[receipt["case"]]
            try:
                _validate_return(result,case,receipt["backend"],manifest["iterations"])
                admission=preflight_by_cell[(receipt["case"],receipt["backend"])]
                count_map={"worlds":"worlds","worlds_materialized":"worlds","deals":"compatible_pairs","compatible_pairs":"compatible_pairs","info_sets":"information_sets","public_nodes":"public_nodes","public_states":"public_states","terminal_nodes":"terminal_nodes","chance_nodes":"chance_nodes","world_traversal_nodes":"world_traversal_nodes","tree_actions":"tree_actions"}
                for field,expected in count_map.items():
                    if result[field]!=admission.get(expected): raise ValueError("returned count differs from fresh full-request admission: "+field)
                if receipt["backend"]=="native": _validate_native_receipt(result,before_build,admission["native_shape_admission"])
                audit=runtime.audit(result,case,manifest["exact_limits"])
                audit["replay_status"]="valid"
                audit["numeric_target_met"]=(float(audit["numeric_metrics"]["nash_conv"])<=float(Fraction(1,1000)))
                exact=audit.get("exact_audit",{})
                audit["exact_target_met"]=(exact.get("target_met") if exact.get("status")=="admitted" else None)
            except Exception as exc:
                audit={"replay_status":"invalid","quality_gate":None,"numeric_target_met":None,"exact_target_met":None,"failure_type":type(exc).__name__,"failure":str(exc),"traceback":traceback.format_exc()}
            audits[(receipt["case"],receipt["backend"])]=audit
            profiles.append({**receipt,"independent_audit":audit,"numeric_target_met":audit.get("numeric_target_met"),"exact_target_met":audit.get("exact_target_met")})
            status["completed_audits"].append({"case":receipt["case"],"backend":receipt["backend"],"replay_status":audit["replay_status"]}); _atomic(output/"status.json",status)
            guards("after audit")
        guards("before parity")
        parity=[]
        for case in manifest["cases"]:
            n=audits[(case["id"],"native")]; p=audits[(case["id"],"python-materialized-D0")]
            native_receipt=next(x for x in saved if x["case"]==case["id"] and x["backend"]=="native")
            python_receipt=next(x for x in saved if x["case"]==case["id"] and x["backend"]=="python-materialized-D0")
            _,nr=verify_policy(native_receipt); _,pr=verify_policy(python_receipt)
            if n.get("replay_status")!="valid" or p.get("replay_status")!="valid": check={"status":"unknown","reason":"one or both independent numeric replays invalid"}
            else: check=_policy_parity(nr,pr,n,p,manifest["policy_probability_tolerance"],manifest["metric_tolerance"])
            parity.append({"case":case["id"],**check})
        guards("after parity")
        # Final receipt audit catches mutation after an otherwise successful policy audit.
        for receipt in saved: verify_policy(receipt)
        for profile in profiles:
            exact=profile["independent_audit"].get("exact_audit",{})
            profile["quality_gate"]=(exact.get("target_met") if exact.get("status")=="admitted" else None)
        invalid=any(p["independent_audit"].get("replay_status")!="valid" for p in profiles)
        report={"schema":"native-river-range-quality-report-v1","status":"completed-with-audit-errors" if invalid else "completed","claim_id":claim_id,"source":before_source,"build":before_build,"control_authentication":control_auth,"preflight_admissions":admissions,"profiles":profiles,"parity":parity,"scope":"Two fixed weighted 8x8 river games at T=10000; independent physical replay; no speed claim.","completed_utc":datetime.now(timezone.utc).isoformat()}
        _exclusive(output/"report.json",_pretty(report)); status.update({"status":report["status"],"phase":"done","parity":parity,"retry_permitted":False}); _atomic(output/"status.json",status); return report
    except BaseException as exc:
        failure={"schema":"native-river-range-quality-failure-v1","claim_id":claim_id,"status":"failed","failure_type":type(exc).__name__,"failure":str(exc),"traceback":traceback.format_exc(),"active_call":active,"saved_policies":saved,"retry_permitted":False}
        if created:
            try: _exclusive(output/"failure.json",_pretty(failure))
            except BaseException: pass
            try: status.update({"status":"failed","phase":"failed","failure_type":type(exc).__name__,"failure":str(exc),"saved_policies":saved,"retry_permitted":False}); _atomic(output/"status.json",status)
            except BaseException: pass
        raise

def _same(expected, observed, label):
    if expected!=observed: raise RuntimeError(label+" changed during batch")


def run(source_root, build_directory, control_root, output, expected_head):
    control=authenticate_control_corpus(control_root)
    manifest_raw=CASE_MANIFEST.read_bytes()
    manifest_lf=_lf(manifest_raw)
    if _sha(manifest_lf)!=CASE_MANIFEST_LF_SHA256: raise RuntimeError("frozen case manifest LF digest changed")
    manifest=json.loads(manifest_lf.decode("utf-8"))
    runtime=ProductionRuntime(source_root,build_directory)
    _validate_manifest(manifest)
    from scripts import turn_river_validation as independent_rules
    from scripts import turn_rational_certificate as exact_rules
    if manifest["independent_numeric_limits"]["MAX_WORLD_COUNT"]!=independent_rules.MAX_WORLD_COUNT or manifest["independent_numeric_limits"]["MAX_ORACLE_WORK"]!=independent_rules.MAX_ORACLE_WORK or manifest["exact_limits"]!={"work":exact_rules.MAX_EXACT_WORK,"depth":exact_rules.MAX_EXACT_DEPTH,"fraction_bits":exact_rules.MAX_FRACTION_BITS}: raise RuntimeError("source-derived independent audit caps changed")
    return run_with_runtime(runtime,manifest,output,expected_head,build_directory,control)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root",required=True,type=Path); parser.add_argument("--build-dir",required=True,type=Path); parser.add_argument("--control-root",required=True,type=Path); parser.add_argument("--output",required=True,type=Path); parser.add_argument("--expected-source-head",required=True)
    args=parser.parse_args(argv); report=run(args.source_root,args.build_dir,args.control_root,args.output,args.expected_source_head)
    print(json.dumps({"status":report["status"],"policies":len(report["profiles"]),"output":str(args.output.resolve())},sort_keys=True)); return 0
if __name__=="__main__": raise SystemExit(main())
