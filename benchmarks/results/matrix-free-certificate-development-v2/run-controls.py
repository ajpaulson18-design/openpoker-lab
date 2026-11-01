"""Preserve both development-control modes and their actual source pins."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

work = Path(__file__).resolve().parent
repo = work / "matrix-free-certificate-repo"
out = work / "matrix-free-certificate-development-controls-v2"
out.mkdir(exist_ok=False)
modules = ("tests.test_exact_selected_matrix_free_certificate",
           "tests.test_matrix_free_selected_payoffs",
           "tests.test_matrix_free_four_street_rules",
           "tests.test_matrix_free_certificate_serialization",
           "tests.test_benchmark_matrix_free_certificate")
paths = sorted(repo.glob("scripts/*matrix_free*.py")) + sorted(repo.glob("tests/test*matrix_free*.py"))
def pins(): return {path.relative_to(repo).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
before = pins()
results = []
for name, flags in (("normal", []), ("optimized", ["-O"])):
    command = [sys.executable, "-B", *flags, "-m", "unittest", *modules, "-v"]
    with (out / (name + ".stdout.log")).open("xb") as stdout, (out / (name + ".stderr.log")).open("xb") as stderr:
        result = subprocess.run(command, cwd=repo, stdout=stdout, stderr=stderr)
    results.append({"mode": name, "command": command, "returncode": result.returncode})
    (out / (name + "-status.json")).write_text(json.dumps(results[-1], indent=2) + "\n")
    if result.returncode: break
after = pins()
receipt = {"source_before": before, "source_after": after, "results": results, "source_stable": before == after}
(out / "receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
print(json.dumps({"out": str(out), "results": results, "source_stable": before == after}), flush=True)
raise SystemExit(0 if before == after and len(results) == 2 and all(row["returncode"] == 0 for row in results) else 1)

