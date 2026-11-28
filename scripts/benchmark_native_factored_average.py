"""Source-frozen same-host complete-call average staging comparison."""
from argparse import ArgumentParser
from pathlib import Path
import hashlib
import json
import statistics
import struct
import subprocess
import time
from tests.test_native_exact_reach import authenticate

FOOTER=struct.Struct("<8s64Q")
TRAIN=b"DYADIC_T2_V1 TRAIN_TEN_BOUNDED_DIVISION\n"
REFERENCE_SHA="bc0496571953a80fd6b1a0f321ed903e11691c5ae5328ed532853ded264ffa49"
def run(ROOT, baseline, candidate, REFERENCE, OUT, census):
    ROOT, baseline, candidate, REFERENCE, OUT, census = (
        p.resolve() for p in (ROOT, baseline, candidate, REFERENCE, OUT, census))
    if OUT.is_relative_to(ROOT):
        raise ValueError("capture must remain external to frozen source")
    HEAD="299b4ec4ee011d63db9cf3b91fe2ab7e5e97e1d7"
    EXES={"baseline":(baseline,"virtual-dyadic-training-staged-pages"),
          "factored":(candidate,"virtual-dyadic-training-factored-average")}
    def need(ok,message):
        if not ok: raise ValueError(message)
    def sha(path):
        with path.open("rb") as f: return hashlib.file_digest(f,"sha256").hexdigest()
    def save(path,data):
        with path.open("x",encoding="utf8",newline="\n") as f:
            f.write(json.dumps(data,indent=2,sort_keys=True)+"\n")
    def identity():
        need(subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()==HEAD and
             not subprocess.check_output(["git","status","--porcelain"],cwd=ROOT),"frozen source drift")
        return {label:authenticate(exe,ROOT,target) for label,(exe,target) in EXES.items()}
    initial=identity()
    need(initial["baseline"][1]["source_sha256"]==initial["factored"][1]["source_sha256"],
         "targets used different source bytes")
    independent=json.loads((census).read_bytes())
    forecast=independent["forecast_average_build"]["10"]
    observed=independent["saved"]["total"]
    delta={5:-forecast["reduction"],11:-observed["reduction"],
           18:-forecast["reduction"],27:-observed["reduction"]}
    need(sha(REFERENCE/"stdout.bin")==REFERENCE_SHA,"reference wire drift")
    protocol=json.loads((ROOT/"benchmarks/results/native-dyadic-staged-pages-v1/protocol.json").read_bytes())
    sidecars=protocol["stable_sidecars"]
    sidecars["page-images/paging.json"]=sha(REFERENCE/"page-images/paging.json")
    need(all(sha(REFERENCE/name)==expected for name,expected in sidecars.items()),"reference owner artifact drift")
    OUT.mkdir()
    save(OUT/"protocol.json",{
     "source_head":HEAD,"reference_wire_sha256":REFERENCE_SHA,"operator_sha256":sha(Path(__file__)),
     "independent_census_sha256":sha(ROOT/"../dyaverage-factor-saved1.json"),
     "alternating_pairs":8,"warmup_pairs":1,"median_elapsed_ratio_max":0.96,
     "candidate_faster_pairs_min":6,"expected_footer_delta":delta,"stable_sidecars":sidecars,
     "scope":"one Windows host; two complete matched ten-card native calls per pair",
     "native_builds":{label:{k:identity[1][k] for k in
         ("target","source_sha256","compiler_sha256","executable_sha256")} for label,identity in initial.items()}
    })
    admissions={}
    for label,(exe,_) in EXES.items():
        p=subprocess.run([str(exe)],input=b"DYADIC_T2_V1 ADMIT_TEN_BOUNDED_DIVISION\n",
                         capture_output=True,timeout=30,check=True)
        need(not p.stderr,"admission stderr")
        admissions[label]=json.loads(p.stdout)
    need(admissions["baseline"]["scaled_average_build_work"]==forecast["before"] and
         admissions["factored"]["scaled_average_build_work"]==forecast["after"],
         "native forecast differs from independent bound")
    save(OUT/"admissions.json",admissions)
    def call(label,mode):
        case=OUT/label
        case.mkdir()
        wire=case/"stdout.bin"
        errors=case/"stderr.bin"
        stamp=time.perf_counter()
        with wire.open("xb") as stdout,errors.open("xb") as err:
            child=subprocess.Popen([str(EXES[mode][0]),str(case/"page-images")],
                stdin=subprocess.PIPE,stdout=stdout,stderr=err,cwd=ROOT,
                creationflags=subprocess.CREATE_NO_WINDOW)
            try:
                child.communicate(TRAIN,timeout=45)
            finally:
                if child.poll() is None:
                    child.kill()
                    child.wait(timeout=10)
        elapsed=time.perf_counter()-stamp
        record={"mode":mode,"elapsed_seconds":elapsed,"returncode":child.returncode,
                "actual_exit_observed":child.poll() is not None,"wire_bytes":wire.stat().st_size,
                "wire_sha256":sha(wire),"stderr_bytes":errors.stat().st_size}
        save(case/"process.json",record)
        need(child.returncode==0 and not errors.stat().st_size and wire.stat().st_size==50507464,
             "complete native process failed: "+label)
        if mode=="baseline":
            need(record["wire_sha256"]==REFERENCE_SHA,"baseline wire differs")
        else:
            with wire.open("rb") as actual,(REFERENCE/"stdout.bin").open("rb") as reference:
                left=wire.stat().st_size-FOOTER.size
                while left:
                    n=min(left,65536)
                    need(actual.read(n)==reference.read(n),"numerical output differs: "+label)
                    left-=n
                a=FOOTER.unpack(actual.read())
                b=FOOTER.unpack(reference.read())
                need(a[0]==b[0]==b"OPLDTP02","footer identity differs")
                differences={i:x-y for i,(x,y) in enumerate(zip(a[1:],b[1:],strict=True)) if x!=y}
                need(differences==delta,"independently predicted average charges differ: "+str(differences))
        need(all(sha(case/name)==expected for name,expected in sidecars.items()),
             "checkpoint, policy, directory or arithmetic receipt differs: "+label)
        record["numerical_and_owner_parity"]=True
        save(case/"verified.json",record)
        return record
    try:
        warmup={mode:call("warm-"+mode,mode) for mode in EXES}
        print(json.dumps({"warmup":{k:v["elapsed_seconds"] for k,v in warmup.items()}}),flush=True)
        pairs=[]
        for index in range(1,9):
            order=("baseline","factored") if index%2 else ("factored","baseline")
            results={mode:call(f"{index:02}-{mode}",mode) for mode in order}
            ratio=results["factored"]["elapsed_seconds"]/results["baseline"]["elapsed_seconds"]
            pairs.append({"pair":index,"order":order,"ratio":ratio,"observations":results})
            print(json.dumps({"pair":index,"ratio":ratio}),flush=True)
        need(identity()==initial,"final source or executable drift")
        ratios=[p["ratio"] for p in pairs]
        median=statistics.median(ratios)
        faster=sum(r<1 for r in ratios)
        terminal={"status":"complete","warmup":warmup,"pairs":pairs,"median_elapsed_ratio":median,
                  "faster_pairs":faster,"timing_gate_passed":median<=0.96 and faster>=6,
                  "complete_native_calls":18,"all_numerical_and_owner_parity":True,
                  "footer_delta":delta,"actual_average_work":observed,"forecast_average_work":forecast}
        save(OUT/"terminal.json",terminal)
        print(json.dumps({k:terminal[k] for k in ("median_elapsed_ratio","faster_pairs","timing_gate_passed")}),flush=True)
    except BaseException as error:
        save(OUT/"failure.json",{"error":str(error),"type":type(error).__name__,"automatic_retries":0})
        raise
    

if __name__ == "__main__":
    parser=ArgumentParser(description=__doc__)
    for name in ("source","baseline","candidate","reference","output","census"):
        parser.add_argument("--"+name,type=Path,required=True)
    args=parser.parse_args()
    run(*(getattr(args,key) for key in ("source","baseline","candidate","reference","output","census")))

