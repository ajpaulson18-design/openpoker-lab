"""Read-only mechanical extraction audit; baseline source is parsed, never run."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import subprocess


def need(value, message):
    if not value:
        raise ValueError(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args])


def function(tree, name):
    matches = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name]
    need(len(matches) == 1, "expected exactly one function: " + name)
    return matches[0]


def boundary(body, name):
    matches = [index for index, node in enumerate(body) if isinstance(node, ast.Assign)
               and any(isinstance(target, ast.Name) and target.id == name for target in node.targets)]
    need(len(matches) == 1, "expected one extraction boundary: " + name)
    return matches[0]


def dumps(nodes):
    return [ast.dump(node, include_attributes=False) for node in nodes]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--baseline", default="96e9fb1")
    args = parser.parse_args()
    repo, receipt = args.repo.resolve(), args.receipt.resolve()
    need(not receipt.exists() and repo not in receipt.parents, "receipt must be new and outside repository")
    path = repo / "pokerlab/exact_selected_solver.py"
    raw = path.read_bytes()
    status_before = git(repo, "status", "--porcelain=v1", "--untracked-files=all")
    baseline_commit = git(repo, "rev-parse", args.baseline + "^{commit}").decode().strip()
    baseline_raw = git(repo, "show", baseline_commit + ":pokerlab/exact_selected_solver.py")
    old, new = ast.parse(baseline_raw), ast.parse(raw)
    original = function(old, "solve_four_street_exact_selected")
    prepared = function(new, "_prepare_exact_selected")
    solve = function(new, "solve_four_street_exact_selected")
    old_cut, new_cut = boundary(original.body, "pair_rows"), boundary(solve.body, "pair_rows")
    need(isinstance(original.body[0], ast.Expr) and isinstance(prepared.body[0], ast.Expr), "missing function docstring")
    need(isinstance(prepared.body[-1], ast.Return), "preparation must end with returned context")
    setup, tail = original.body[1:old_cut], original.body[old_cut:]
    setup_equal = dumps(setup) == dumps(prepared.body[1:-1])
    tail_equal = dumps(tail) == dumps(solve.body[new_cut:])
    signatures_equal = (ast.dump(original.args, include_attributes=False) ==
                        ast.dump(prepared.args, include_attributes=False) ==
                        ast.dump(solve.args, include_attributes=False))
    need(len(setup) == 32 and setup_equal, "original 32 preparation statements changed")
    need(len(tail) == 34 and tail_equal, "original 34 post-preparation solve statements changed")
    need(signatures_equal, "extracted or public signature changed")
    need(path.read_bytes() == raw, "solver source changed during audit")
    need(git(repo, "status", "--porcelain=v1", "--untracked-files=all") == status_before,
         "repository status changed during audit")
    result = {
        "outcome": "passed", "baseline_commit": baseline_commit,
        "baseline_solver_sha256": digest(baseline_raw), "current_raw_solver_sha256": digest(raw),
        "solver_path": str(path), "preparation_statement_count": len(setup),
        "post_preparation_statement_count": len(tail), "preparation_ast_identical": setup_equal,
        "post_preparation_ast_identical": tail_equal, "signature_equivalence": signatures_equal,
        "repository_status_unchanged": True, "solver_raw_bytes_unchanged": True,
        "repository_code_executed": False, "repository_files_edited": False,
        "audit_helper_sha256": digest(Path(__file__).read_bytes()),
        "scope": "Mechanical AST equality ignores docstrings, source locations and formatting. Baseline git blob is parsed as data; no solver or repository code is imported/executed. Object lifetimes were separately reviewed by inspection."
    }
    receipt.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"outcome": "passed", "receipt_sha256": digest(receipt.read_bytes()), **result}))


if __name__ == "__main__":
    main()
