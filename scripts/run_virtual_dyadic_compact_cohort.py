"""Frozen compact numerical transport study using the independent legacy replay."""
from pathlib import Path
import hashlib
import struct
import shutil
import time
import traceback

from scripts import run_virtual_dyadic_training_cohort as cohort
from scripts.virtual_dyadic_compact_wire import compact_size, expand_compact, compact_segments
from tests.virtual_dyadic_sweep_capture import sweep_stream_contract

ROOT=cohort.ROOT
BASELINE="benchmarks/results/native-dyadic-indexed-cache-ten-card-accepted-v1"


FACTORED_COUNTS={"from_values":1_447_016,"scales":1_329_176,"additions":1_420_012,
                 "subtractions":562_132,"mixes":238_392,"expansions":8}
FACTORED_WORK=64*sum(value for key,value in FACTORED_COUNTS.items() if key!="mixes")+320*FACTORED_COUNTS["mixes"]


def verify_factored_execution(record,admission):
    packed_fields={"packed_additions","packed_subtractions","packed_clipped",
                   "packed_target_words_read","packed_target_words_written"}
    metrics={"implicit_zero_bits","maximum_coefficient_bits","maximum_shift"}
    cohort.require(type(record) is dict and record.keys()==
                   set(FACTORED_COUNTS)|packed_fields|metrics|{"work"} and
                   all(type(value) is int and value>=0 for value in record.values()),
                   "factored execution receipt schema differs")
    image_words=admission["page_image_words"]
    sweeps_read=1 if admission.get("initial_packed_stage") else 2
    cohort.require(all(record[key]==value for key,value in FACTORED_COUNTS.items()) and
                   record["work"]==admission["factored_metadata_work"]==FACTORED_WORK and
                   record["packed_target_words_read"]==sweeps_read*image_words and
                   record["packed_target_words_written"]==2*image_words and
                   0<record["packed_additions"]+record["packed_subtractions"]<=4*281_066 and
                   record["packed_clipped"]<=record["packed_subtractions"] and
                   0<record["implicit_zero_bits"]<=sum(FACTORED_COUNTS.values())*704 and
                   0<record["maximum_shift"]<=644 and 0<record["maximum_coefficient_bits"]<=645,
                   "factored execution count or scale differs")
    return record


CHECKED_HISTORY_DECISIONS=114_774
CHECKED_HISTORY_ACTUAL=62_890_960
VISIT_HISTORY_ACTUAL=34_741_384


def checked_history_baseline(record,*,history_visit=False):
    """Validate the new ledger, then recover the legacy shape/capacity record."""
    cohort.require(type(record) is dict and record.get("checked_history") is True and
                   record.get("history_decisions_per_walk")==CHECKED_HISTORY_DECISIONS,
                   "checked History profile census differs")
    cohort.require((record.get("history_visit") is True) if history_visit else
                   ("history_visit" not in record),"History visit profile differs")
    expected=VISIT_HISTORY_ACTUAL if history_visit else CHECKED_HISTORY_ACTUAL
    delta=99_754_616-expected
    components=record.get("component_work")
    cohort.require(type(components) is dict and components.get("history")==expected,
                   "checked History work census differs")
    legacy=dict(record,component_work=dict(components,history=99_754_616))
    legacy.pop("history_visit",None)
    legacy.pop("checked_history")
    legacy.pop("history_decisions_per_walk")
    for key in ("planned_total_work","compact_composed_work","factored_composed_work","parent_allowance"):
        cohort.require(type(legacy.get(key)) is int,"checked History work field differs")
        legacy[key]+=(-delta if key=="parent_allowance" else delta)
    return legacy_admission(legacy,factored=True)


def equal_quantizer_baseline(record):
    """Check both mixed-phase comparison reserves without assuming any hits."""
    cohort.require(type(record) is dict,"equal quantizer admission requires a record")
    extra=16*119_196+48*281_066
    terms=record.get("quantizer_terms")
    components=record.get("component_work")
    cohort.require(record.get("equal_quantizer") is True and type(terms) is list and
                   len(terms)==3 and all(type(n) is int for n in terms) and
                   type(components) is dict and components.get("quantizer")==sum(terms),
                   "equal quantizer reservation differs")
    normalized=dict(record,quantizer_terms=[terms[0],terms[1]-extra,terms[2]-extra],
                    component_work=dict(components,quantizer=sum(terms)-2*extra))
    normalized.pop("equal_quantizer")
    for field in ("planned_total_work","compact_composed_work","factored_composed_work","parent_allowance"):
        cohort.require(type(normalized.get(field)) is int,"equal quantizer admission field differs")
        normalized[field]+=(2*extra if field=="parent_allowance" else -2*extra)
    return checked_history_baseline(normalized,history_visit=True)


def reuse_snapshot_baseline(record):
    cohort.require(type(record) is dict and record.get("reuse_snapshot") is True and
                   record.get("row_directory_page_limit")==7456 and
                   record.get("row_directory_read_call_limit")==8*119_196 and
                   record.get("policy_spill_read_call_limit")==2*119_196 and
                   record.get("factored_composed_entries")==374_708 and
                   record.get("factored_composed_payload_bits")==20_958_080,
                   "snapshot reuse I/O or storage reservation differs")
    normalized=dict(record,row_directory_page_limit=7656,row_directory_read_call_limit=10*119_196,
                    policy_spill_read_call_limit=3*119_196,factored_composed_entries=372_660,
                    factored_composed_payload_bits=20_827_008)
    normalized.pop("reuse_snapshot")
    legacy=equal_quantizer_baseline(normalized)
    return dict(legacy,row_directory_page_limit=record["row_directory_page_limit"],
                row_directory_read_call_limit=record["row_directory_read_call_limit"],
                policy_spill_read_call_limit=record["policy_spill_read_call_limit"])


def zero_policy_bootstrap_baseline(record):
    rows, slots = 119_196, 281_066
    removed_quantizer = 320*rows+48*slots
    added_state, removed_route = 32*rows, 16*rows
    saved_work = removed_quantizer+removed_route-added_state
    cohort.require(type(record) is dict and record.get("zero_policy_bootstrap") is True and
                   record.get("page_request_limit")==10*rows and
                   record.get("quantizer_terms", [])[:1]==[0],
                   "initial uniform policy profile or request census differs")
    components = record["component_work"]
    parent = record["parent_work"]
    normalized = dict(record, page_request_limit=11*rows,
                      paging_work=record["paging_work"]+removed_route,
                      quantizer_terms=[removed_quantizer,*record["quantizer_terms"][1:]],
                      component_work=dict(components,state=components["state"]-added_state,
                                          quantizer=components["quantizer"]+removed_quantizer,
                                          parent=components["parent"]+removed_route),
                      parent_work=dict(parent,route=parent["route"]+removed_route),
                      parent_allowance=record["parent_allowance"]-removed_quantizer+added_state)
    normalized.pop("zero_policy_bootstrap")
    for field in ("planned_total_work","compact_composed_work","factored_composed_work"):
        normalized[field] += saved_work
    legacy = reuse_snapshot_baseline(normalized)
    return dict(legacy, page_request_limit=record["page_request_limit"])


def first_regret_bound_baseline(record):
    from scripts.project_virtual_dyadic_eleven import forecast
    prior_terms=[0,171_485_216,241_149_832]
    expected=forecast(10,644,12,1,first_regret_bound=True)
    components=record.get("component_work")
    cohort.require(record.get("first_regret_bound") is True and record.get("quantizer_terms")==expected and
                   type(components) is dict and components.get("quantizer")==sum(expected),
                   "first-sweep regret support or packed-width forecast differs")
    restored=sum(prior_terms)-sum(expected)
    normalized=dict(record,quantizer_terms=prior_terms,component_work=dict(components,quantizer=sum(prior_terms)),
                    parent_allowance=record["parent_allowance"]-restored)
    normalized.pop("first_regret_bound")
    for field in ("planned_total_work","compact_composed_work","factored_composed_work"):
        normalized[field]+=restored
    return zero_policy_bootstrap_baseline(normalized)


def initial_packed_stage_baseline(record):
    rows=119_196
    route_work=32*rows
    cohort.require(record.get("initial_packed_stage") is True and record.get("page_request_limit")==8*rows,
                   "initial packed stage request census differs")
    components=record["component_work"]
    parent=record["parent_work"]
    normalized=dict(record,page_request_limit=10*rows,paging_work=record["paging_work"]+route_work,
                    component_work=dict(components,parent=components["parent"]+route_work),
                    parent_work=dict(parent,route=parent["route"]+route_work))
    normalized.pop("initial_packed_stage")
    for field in ("planned_total_work","compact_composed_work","factored_composed_work"):
        normalized[field]+=route_work
    legacy=first_regret_bound_baseline(normalized)
    return dict(legacy,page_request_limit=record["page_request_limit"])


def bounded_stage_width_baseline(record):
    from scripts.project_virtual_dyadic_eleven import stage_arithmetic
    rows, slots = 119_196, 281_066
    arithmetic = sum(stage_arithmetic(10,644))
    cohort.require(record.get("bounded_stage_width") is True and record.get("stage_arithmetic_work")==arithmetic,
                   "row-specific staging arithmetic census differs")
    restored=2*(16*slots+8*rows)*11-arithmetic
    components=record["component_work"]
    normalized=dict(record,component_work=dict(components,state=components["state"]+restored),
                    parent_allowance=record["parent_allowance"]-restored)
    normalized.pop("bounded_stage_width")
    normalized.pop("stage_arithmetic_work")
    for field in ("planned_total_work","compact_composed_work","factored_composed_work"):
        normalized[field]+=restored
    return first_regret_bound_baseline(normalized)


def packed_policy_baseline(record):
    """Remove only the separately admitted fixed-stride row scans."""
    rows, slots = 119_196, 281_066
    extra=32*rows+4*(2_962_722+2*slots)
    cohort.require(record.get("packed_policy") is True and
                   record.get("packed_policy_scan_work")==extra and
                   record.get("page_image_words")==2_962_722 and
                   record.get("component_work",{}).get("quantizer")==317_853_256+extra,
                   "packed policy scan admission differs")
    normalized=dict(record,component_work=dict(record["component_work"],
        quantizer=record["component_work"]["quantizer"]-extra),
        parent_allowance=record["parent_allowance"]+extra)
    normalized.pop("packed_policy")
    normalized.pop("packed_policy_scan_work")
    for field in ("planned_total_work","compact_composed_work","factored_composed_work"):
        normalized[field]-=extra
    return normalized


def legacy_admission(record,*,factored=False):
    cohort.require(type(factored) is bool and type(record) is dict,"invalid factored admission selector")
    cohort.require("checked_history" not in record and "history_visit" not in record and "equal_quantizer" not in record and "reuse_snapshot" not in record and "zero_policy_bootstrap" not in record and "first_regret_bound" not in record and "initial_packed_stage" not in record,
                   "unexpected extended training profile")
    if factored:
        cohort.require(record.get("factored_execution") is True and
                       record.get("factored_metadata_work")==FACTORED_WORK==380_819_456 and
                       record.get("factored_composed_work")==record.get("compact_composed_work",0)+FACTORED_WORK<=2_150_000_000 and
                       record.get("factored_composed_entries")==record.get("compact_composed_entries",0)+8192<=2_000_000 and
                       record.get("factored_composed_payload_bits")==record.get("compact_composed_payload_bits",0)+524288<=1_200_000_000,
                       "factored composed resource ledger differs")
        removed={"factored_execution","factored_metadata_work","factored_composed_work",
                 "factored_composed_entries","factored_composed_payload_bits"}
        earlier={key:value for key,value in record.items() if key not in removed}
        return legacy_admission(earlier)
    cohort.require("factored_execution" not in record,"unexpected factored execution profile")
    cohort.require(type(record) is dict and record.get("compact_wire") is True and
                   record.get("complement_division") is True,
                   "explicit compact complement admission required")
    cohort.require(record.get("output_bytes")==compact_size() and
                   record.get("sweep_stream")==sweep_stream_contract(compact_wire=True),
                   "compact transport equation differs")
    rows,slots=119_196,281_066
    encoding=208*rows+64*slots+16*((rows+7)//8)
    cohort.require(record.get("compact_encoding_work")==encoding==43_019_392 and
                   record.get("compact_composed_work")==record["planned_total_work"]+
                       record["sweep_stream"]["copy_work"]+encoding<=2_150_000_000 and
                   record.get("compact_composed_entries")==record["entries"]+4100+32<=2_000_000 and
                   record.get("compact_composed_payload_bits")==record["payload_bits"]+262400+2048<=1_200_000_000,
                   "compact composed resource ledger differs")
    removed={"compact_wire","compact_encoding_work","compact_composed_work",
             "compact_composed_entries","compact_composed_payload_bits"}
    legacy={key:value for key,value in record.items() if key not in removed}
    legacy["output_bytes"]=cohort.TEN_CARD_SPLIT_BYTES
    legacy["sweep_stream"]=sweep_stream_contract()
    cohort.validate_admission(legacy,ten_complement=True)
    return legacy


def reconstruct_wire(compact,pages,images,capture):
    digest=hashlib.sha256()
    size=0

    def add(stream,length):
        nonlocal size
        remaining=length
        while remaining:
            block=stream.read(min(65536,remaining))
            cohort.require(block,"compact wire reconstruction truncated")
            digest.update(block)
            size+=len(block)
            remaining-=len(block)

    with compact.open("rb") as stream:
        epoch=0
        for name,length in compact_segments():
            add(stream,length)
            if name in ("sweep1_roots","sweep2_policy_roots"):
                image=images[epoch]
                epoch+=1
                header=struct.pack("<8sQQQ",b"OPLCPG01",epoch,epoch%2,image["bytes"])
                digest.update(header)
                size+=len(header)
                path=pages/image["name"]
                cohort.require(cohort.sha(path)==image["sha256"],"wire reconstruction image identity differs")
                with path.open("rb") as source:
                    add(source,image["bytes"])
                    cohort.require(not source.read(1),"wire reconstruction image has trailing bytes")
        cohort.require(not stream.read(1),"compact wire reconstruction has trailing numerical bytes")
    cohort.require(size==capture["contract"]["wire_bytes"] and
                   digest.hexdigest()==capture["wire_sha256"],"independent compact wire hash differs")
    return {"bytes":size,"sha256":digest.hexdigest(),"status":"independent_exact_reconstruction"}


def run_compact(output,expected_head,*,train=False,factored=False,checked_history=False,history_visit=False,equal_quantizer=False,reuse_snapshot=False,zero_policy_bootstrap=False,first_regret_bound=False,initial_packed_stage=False,bounded_stage_width=False,pair_complement=False,bounded_division=False,packed_policy=False):
    cohort.require(type(train) is bool and type(factored) is bool,"compact training selectors must be boolean")
    cohort.require(type(checked_history) is bool and (not checked_history or factored),
                   "checked History requires factored training")
    cohort.require(type(history_visit) is bool and (not history_visit or checked_history),
                   "History visit requires checked History training")
    cohort.require(type(equal_quantizer) is bool and (not equal_quantizer or history_visit),
                   "equal quantizer requires the visit profile")
    cohort.require(type(reuse_snapshot) is bool and (not reuse_snapshot or equal_quantizer),
                   "snapshot reuse requires equal quantizer profile")
    cohort.require(type(zero_policy_bootstrap) is bool and (not zero_policy_bootstrap or reuse_snapshot),
                   "initial policy bootstrap requires the owned row snapshot")
    cohort.require(type(first_regret_bound) is bool and (not first_regret_bound or zero_policy_bootstrap),
                   "first regret support bound requires the zero bootstrap profile")
    cohort.require(type(initial_packed_stage) is bool and (not initial_packed_stage or first_regret_bound),
                   "initial packed staging requires the owned two-sweep zero image")
    cohort.require(type(bounded_stage_width) is bool and
                   (not bounded_stage_width or first_regret_bound and not initial_packed_stage),
                   "bounded staging arithmetic requires the preceding owned-row profile")
    cohort.require(type(pair_complement) is bool and (not pair_complement or bounded_stage_width),
                   "two-positive complement requires bounded factored staging")
    cohort.require(type(bounded_division) is bool and (not bounded_division or pair_complement),
                   "bounded policy division requires pair complement")
    cohort.require(type(packed_policy) is bool and (not packed_policy or bounded_division),
                   "packed policy requires the bounded division profile")
    suffix=("TEN_PACKED_POLICY" if packed_policy else "TEN_BOUNDED_DIVISION" if bounded_division else "TEN_PAIR_COMPLEMENT" if pair_complement else "TEN_BOUNDED_STAGE_WIDTH" if bounded_stage_width else "TEN_INITIAL_PACKED_STAGE" if initial_packed_stage else "TEN_FIRST_REGRET_BOUND" if first_regret_bound else "TEN_ZERO_POLICY_BOOTSTRAP" if zero_policy_bootstrap else "TEN_REUSE_SNAPSHOT" if reuse_snapshot else "TEN_EQUAL_QUANTIZER" if equal_quantizer else "TEN_HISTORY_VISIT" if history_visit
            else "TEN_CHECKED_HISTORY" if checked_history
            else "TEN_FACTORED" if factored else "TEN_COMPACT_WIRE")
    history_work=VISIT_HISTORY_ACTUAL if history_visit else CHECKED_HISTORY_ACTUAL
    cohort.require(cohort.require_source_bootstrap(ROOT)["interpreter"]["optimize"]==0,
                   "compact cohort requires normal source-only execution")
    cohort.require(cohort._git(ROOT,["rev-parse","HEAD"]).decode().strip()==expected_head,
                   "compact cohort committed source differs")
    output=Path(output).absolute()
    cohort.unlinked_path(output.parent)
    cohort.require(not output.is_relative_to(ROOT) and
                   shutil.disk_usage(output.parent).free>=cohort.ARTIFACT_ALLOWANCE,
                   "compact external evidence admission")
    claim=cohort.RunClaim(output,expected_head)
    entered=0
    started=time.perf_counter()
    try:
        source=cohort.capture_source(ROOT,snapshot_directory=output/"source")
        cohort.require(source["head"]==expected_head,"compact source capture differs")
        cohort.require_source_bootstrap(ROOT,source)
        cohort.save(output/"source.json",source)
        cohort.save(output/"fixed-proof-gate.json",cohort.require_frozen_gate(source))
        build_dir=output/"build"
        build=cohort.build(build_dir,target=cohort.TARGET)
        build_path=build_dir/"native-exact-build-manifest.json"
        build_hash=cohort.sha(build_path)
        executable=Path(build["executable"])

        def observed(mode):
            cohort.require(cohort.sha(build_path)==build_hash,"compact native build manifest drift")
            cohort.bind_build(build,source,cohort.TARGET,output/"source",build_dir)
            folder=output/mode.lower()
            command=[str(executable)]
            if mode.startswith("TRAIN"):
                scratch=output/"page-images"
                cohort.require(not scratch.exists() and str(scratch).isascii(),
                               "compact fresh native scratch required")
                command.append(str(scratch))
            process=cohort.run_bounded_dyadic_probe(command,mode,folder)
            cohort.save(folder/"binary-identity.json",{
                "before_sha256":build["executable_sha256"],"after_sha256":cohort.sha(executable),
                "build_manifest_sha256":cohort.sha(build_path)})
            cohort.require_exit(process,folder)
            cohort.require(cohort.sha(build_path)==build_hash,"compact native build manifest changed")
            cohort.bind_build(build,source,cohort.TARGET,output/"source",build_dir)
            return folder,process

        folder,_=observed("ADMIT_"+suffix)
        admission=cohort.exact_json((folder/"stdout.bin").read_bytes())
        if bounded_stage_width:
            cohort.require(admission.get("packed_policy",False) is packed_policy,
                           "packed policy selection differs")
            normalized=packed_policy_baseline(admission) if packed_policy else dict(admission)
            cohort.require(admission.get("pair_complement",False) is pair_complement,
                           "two-positive complement selection differs")
            normalized.pop("pair_complement",None)
            cohort.require(admission.get("bounded_division",False) is bounded_division,
                           "bounded policy division selection differs")
            normalized.pop("bounded_division",None)
            legacy=bounded_stage_width_baseline(normalized)
        elif initial_packed_stage:
            legacy=initial_packed_stage_baseline(admission)
        elif first_regret_bound:
            legacy=first_regret_bound_baseline(admission)
        elif zero_policy_bootstrap:
            legacy=zero_policy_bootstrap_baseline(admission)
        elif reuse_snapshot:
            legacy=reuse_snapshot_baseline(admission)
        elif equal_quantizer:
            legacy=equal_quantizer_baseline(admission)
        elif checked_history:
            legacy=checked_history_baseline(admission,history_visit=history_visit)
        else:
            legacy=legacy_admission(admission,factored=factored)
        cohort.save(output/"admission.json",admission)
        result={"head":expected_head,"admission":admission,"legacy_admission":legacy,
                "training_invocations":0,"quality_gate":None,
                "scope":"fixed indexed complement ten-card T2 with "+("factored execution" if factored else "compact transport")}
        if train:
            stage=cohort.stage_schedule(ten_card=True,virtual_zero=True,batch_rows=True,
                                        zero_policy_bootstrap=zero_policy_bootstrap,initial_packed_stage=initial_packed_stage)
            trace=cohort.rank_trace()
            cohort.require((stage["logical_read_calls"]+stage["direct_write_calls"],
                            stage["physical_read_words"],stage["written_words"])==
                           (admission["page_request_limit"],admission["page_read_word_limit"],
                            admission["page_write_word_limit"]),"compact pager schedule differs")
            entered=1
            folder,process=observed("TRAIN_"+suffix)
            compact=folder/"stdout.bin"
            compact_digest=cohort.sha(compact)
            cohort.require(compact.stat().st_size==admission["output_bytes"] and
                           process["streams"][0]["sha256"]==compact_digest,"compact native bytes differ")
            paging=cohort.verify_paging(output/"page-images",legacy,stage)
            images=[{"name":name,**paging["images"][name]} for name in cohort.SPLIT_IMAGE_NAMES]
            capture=cohort.verify_sweep_capture(process,admission,images,compact_digest)
            wire_reconstruction=reconstruct_wire(compact,output/"page-images",images,capture)
            encoding=cohort.exact_json((output/"compact-wire.json").read_bytes())
            cohort.require(encoding=={"compact_encoding_work":admission["compact_encoding_work"]},
                           "native compact encoder work differs")
            if factored:
                result["factored_execution"]=verify_factored_execution(
                    cohort.exact_json((output/"factored-execution.json").read_bytes()),admission)
            expanded=folder/"expanded.bin"
            with compact.open("rb") as reader,expanded.open("x+b") as writer:
                expansion=expand_compact(reader,writer,source_size=admission["output_bytes"])
            digest=cohort.sha(expanded)
            cohort.require(expanded.stat().st_size==cohort.TEN_CARD_SPLIT_BYTES,
                           "expanded legacy extent differs")
            quantizer=cohort.verify_division_receipt(output/"page-images",legacy)
            policy=cohort.verify_policy_spill(output/"page-images",expanded,legacy,reuse_snapshot=reuse_snapshot)
            directory=cohort.verify_row_directory(output/"page-images-rows",expanded,legacy,reuse_snapshot=reuse_snapshot)

            prior=cohort.exact_json((ROOT/BASELINE/"manifest.json").read_bytes())
            for name in ("manifest.json","verification.zip"):
                cohort.require(cohort.sha(ROOT/BASELINE/name)==source["files"][BASELINE+"/"+name]["raw_sha256"],
                               "compact baseline source identity differs")
            cohort.require(capture["frames"]==prior["sweep_capture"]["frames"] and
                           (checked_history or digest==prior["sweep_capture"]["retained_sha256"]),
                           "compact expansion or checkpoint digests differ from accepted indexed evidence")
            bootstrap=ROOT/"scripts/run_virtual_frozen_source_only.py"
            receipt_path=output/"saved-review-bootstrap.json"
            args=["--saved",str(expanded),"--sha256",digest,"--paired","--rank-sets","--ten-card",
                  "--count-policy-divisions","--phase-payload","--row-batched","--indexed-cache",
                  "--complement-divisions","--sweep-checkpoint-digest",
                  *(frame["sha256"] for frame in capture["frames"])]
            if equal_quantizer: args.append("--equal-quantizer")
            if zero_policy_bootstrap: args.append("--zero-policy-bootstrap")
            if first_regret_bound: args.append("--first-regret-bound")
            if pair_complement: args.append("--pair-complement")
            if packed_policy: args.append("--packed-policy")
            command=cohort.source_only_command(bootstrap,
                source["files"]["scripts/run_virtual_frozen_source_only.py"]["raw_sha256"],
                "scripts.verify_virtual_dyadic_training",receipt_path,args)
            cohort.save(output/"saved-review-command.json",command)
            review=cohort.run_bounded_child(command,b"",output/"saved-review",stdout_limit=65536)
            cohort.require_exit(review,output/"saved-review")
            compiled=cohort.check_verifier_bootstrap(receipt_path,source)
            replay=cohort.exact_json((output/"saved-review/stdout.bin").read_bytes())
            cohort.require(replay["status"]=="saved_two_sweep_exact_replay_pass" and
                           replay["saved_output_sha256"]==digest and replay["native_producer_calls"]==0,
                           "compact expanded saved-only replay differs")
            result.update(training_invocations=1,paging=paging,quantizer=quantizer,policy_spill=policy,
                          row_directory=directory,sweep_capture=prior["sweep_capture"],
                          compact_sweep_capture=capture,compact_encoding_receipt=encoding,
                          wire_reconstruction=wire_reconstruction,expansion=expansion,saved_only_replay=replay,
                          saved_review_compiled_sources=compiled)
            result["rank_index"]=cohort.verify_rank_index(output/"page-images",legacy,replay,trace)
            if checked_history:
                cohort.require(replay["work_plan"]["history"]==replay["work_actual"]["history"]==
                               admission["component_work"]["history"]==history_work,
                               "checked History realization differs")
            receipt_path_equal=output/"equal-quantizer.json"
            if equal_quantizer:
                equal_receipt=cohort.exact_json(receipt_path_equal.read_bytes())
                cohort.require(type(equal_receipt) is dict and len(equal_receipt)==2 and
                               all(type(value) is int and value>0 for value in equal_receipt.values()) and
                               equal_receipt=={key:replay["equal_quantizer"][key] for key in
                                               ("equal_rows","equal_divisions_avoided")} and
                               replay["work_plan"]["quantizer"]==admission["component_work"]["quantizer"],
                               "independent equal quantizer receipt differs")
                result["equal_quantizer"]=equal_receipt
            if packed_policy:
                packed_receipt=cohort.exact_json((output/"packed-policy.json").read_bytes())
                cohort.require(type(packed_receipt) is dict and
                               packed_receipt==replay.get("packed_policy") and
                               all(type(v) is int and v>=0 for v in packed_receipt.values()) and
                               packed_receipt.get("rows")==2*admission["rows"] and
                               packed_receipt.get("scan_work")==admission["packed_policy_scan_work"] and
                               packed_receipt.get("words_scanned")==admission["page_image_words"],
                               "independent packed policy classification or scan differs")
                result["packed_policy"]=packed_receipt
            result["comparison"]=cohort.compare_ten_card_complement(source,result,expanded,replay,
                checked_history_work=history_work if checked_history else None,
                equal_quantizer_plan=admission["component_work"]["quantizer"] if equal_quantizer else None,
                reuse_snapshot=reuse_snapshot,zero_policy_bootstrap=zero_policy_bootstrap,
                first_regret_bound=first_regret_bound,initial_packed_stage=initial_packed_stage,
                stage_state_work=admission['component_work']['state'] if bounded_stage_width else None)
            cohort.require(quantizer==cohort.verify_division_receipt(output/"page-images",legacy) and
                           paging==cohort.verify_paging(output/"page-images",legacy,stage) and
                           policy==cohort.verify_policy_spill(output/"page-images",expanded,legacy,reuse_snapshot=reuse_snapshot) and
                           directory==cohort.verify_row_directory(output/"page-images-rows",expanded,legacy,reuse_snapshot=reuse_snapshot) and
                           cohort.sha(compact)==compact_digest and cohort.sha(expanded)==digest and
                           encoding==cohort.exact_json((output/"compact-wire.json").read_bytes()),
                           "compact study input changed after replay")
            if factored:
                cohort.require(result["factored_execution"]==verify_factored_execution(
                    cohort.exact_json((output/"factored-execution.json").read_bytes()),admission),
                    "factored execution receipt changed after replay")
            if equal_quantizer:
                cohort.require(result["equal_quantizer"]==cohort.exact_json(receipt_path_equal.read_bytes()),
                               "equal quantizer receipt changed after replay")
            result["host_retained_bytes"]={"compact":compact.stat().st_size,
                                          "expanded_for_verification":expanded.stat().st_size}
        result["source_final"]=cohort.verify_source(ROOT,source)
        cohort.scan_project_caches(ROOT)
        cohort.require_source_bootstrap(ROOT,source)
        cohort.bind_build(build,source,cohort.TARGET,output/"source",build_dir)
        cohort.require(sum(p.stat().st_size for p in output.rglob("*") if p.is_file())<=
                       cohort.ARTIFACT_ALLOWANCE-(1<<20),"compact actual artifact allowance exceeded")
        result["duration_seconds"]=time.perf_counter()-started
        cohort.save(output/"result.json",result)
        claim.finish("complete",{"result":"result.json","training_invocations":entered,
                                "outer_exit_and_final_bootstrap":"required separately"})
        return result
    except BaseException as error:
        claim.finish("failed",{"first_error":type(error).__name__+": "+str(error)[:2048],
                              "training_invocations_entered":entered,
                              "traceback":traceback.format_exc()[-16384:]})
        raise
