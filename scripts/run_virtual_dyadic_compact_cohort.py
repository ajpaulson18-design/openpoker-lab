"""Frozen compact numerical transport study using the independent legacy replay."""
from pathlib import Path
import shutil
import time
import traceback

from scripts import run_virtual_dyadic_training_cohort as cohort
from scripts.virtual_dyadic_compact_wire import compact_size, expand_compact
from tests.virtual_dyadic_sweep_capture import sweep_stream_contract

ROOT=cohort.ROOT
BASELINE="benchmarks/results/native-dyadic-indexed-cache-ten-card-accepted-v1"


def legacy_admission(record):
    cohort.require(type(record) is dict and record.get("compact_wire") is True and
                   record.get("complement_division") is True,
                   "explicit compact complement admission required")
    cohort.require(record.get("output_bytes")==compact_size() and
                   record.get("sweep_stream")==sweep_stream_contract(compact_wire=True),
                   "compact transport equation differs")
    legacy={key:value for key,value in record.items() if key!="compact_wire"}
    legacy["output_bytes"]=cohort.TEN_CARD_SPLIT_BYTES
    legacy["sweep_stream"]=sweep_stream_contract()
    cohort.validate_admission(legacy,ten_complement=True)
    return legacy


def run_compact(output,expected_head,*,train=False):
    cohort.require(type(train) is bool,"compact training selector must be boolean")
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

        folder,_=observed("ADMIT_TEN_COMPACT_WIRE")
        admission=cohort.exact_json((folder/"stdout.bin").read_bytes())
        legacy=legacy_admission(admission)
        cohort.save(output/"admission.json",admission)
        result={"head":expected_head,"admission":admission,"legacy_admission":legacy,
                "training_invocations":0,"quality_gate":None,
                "scope":"fixed indexed complement ten-card T2 compact transport"}
        if train:
            stage=cohort.stage_schedule(ten_card=True,virtual_zero=True,batch_rows=True)
            trace=cohort.rank_trace()
            cohort.require((stage["logical_read_calls"]+stage["direct_write_calls"],
                            stage["physical_read_words"],stage["written_words"])==
                           (admission["page_request_limit"],admission["page_read_word_limit"],
                            admission["page_write_word_limit"]),"compact pager schedule differs")
            entered=1
            folder,process=observed("TRAIN_TEN_COMPACT_WIRE")
            compact=folder/"stdout.bin"
            compact_digest=cohort.sha(compact)
            cohort.require(compact.stat().st_size==admission["output_bytes"] and
                           process["streams"][0]["sha256"]==compact_digest,"compact native bytes differ")
            paging=cohort.verify_paging(output/"page-images",legacy,stage)
            images=[{"name":name,**paging["images"][name]} for name in cohort.SPLIT_IMAGE_NAMES]
            capture=cohort.verify_sweep_capture(process,admission,images,compact_digest)
            expanded=folder/"expanded.bin"
            with compact.open("rb") as reader,expanded.open("x+b") as writer:
                expansion=expand_compact(reader,writer,source_size=admission["output_bytes"])
            digest=cohort.sha(expanded)
            cohort.require(expanded.stat().st_size==cohort.TEN_CARD_SPLIT_BYTES,
                           "expanded legacy extent differs")
            quantizer=cohort.verify_division_receipt(output/"page-images",legacy)
            policy=cohort.verify_policy_spill(output/"page-images",expanded,legacy)
            directory=cohort.verify_row_directory(output/"page-images-rows",expanded,legacy)

            prior=cohort.exact_json((ROOT/BASELINE/"manifest.json").read_bytes())
            for name in ("manifest.json","verification.zip"):
                cohort.require(cohort.sha(ROOT/BASELINE/name)==source["files"][BASELINE+"/"+name]["raw_sha256"],
                               "compact baseline source identity differs")
            cohort.require(capture["frames"]==prior["sweep_capture"]["frames"] and
                           digest==prior["sweep_capture"]["retained_sha256"],
                           "compact expansion or checkpoint digests differ from accepted indexed evidence")
            bootstrap=ROOT/"scripts/run_virtual_frozen_source_only.py"
            receipt_path=output/"saved-review-bootstrap.json"
            args=["--saved",str(expanded),"--sha256",digest,"--paired","--rank-sets","--ten-card",
                  "--count-policy-divisions","--phase-payload","--row-batched","--indexed-cache",
                  "--complement-divisions","--sweep-checkpoint-digest",
                  *(frame["sha256"] for frame in capture["frames"])]
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
                          compact_sweep_capture=capture,expansion=expansion,saved_only_replay=replay,
                          saved_review_compiled_sources=compiled)
            result["rank_index"]=cohort.verify_rank_index(output/"page-images",legacy,replay,trace)
            result["comparison"]=cohort.compare_ten_card_complement(source,result,expanded,replay)
            cohort.require(quantizer==cohort.verify_division_receipt(output/"page-images",legacy) and
                           paging==cohort.verify_paging(output/"page-images",legacy,stage) and
                           policy==cohort.verify_policy_spill(output/"page-images",expanded,legacy) and
                           directory==cohort.verify_row_directory(output/"page-images-rows",expanded,legacy) and
                           cohort.sha(compact)==compact_digest and cohort.sha(expanded)==digest,
                           "compact study input changed after replay")
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
