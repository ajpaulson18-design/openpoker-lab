"""Authenticate one historical rank-helper transition after foundation repair.

Only `_five_rank` and `independent_rank` provenance is preserved. The complete
preflop replay validator changed its acceptance and chance-normalization laws;
this bridge does not claim those laws equivalent. Historical consumers may use
this only when their sole dependency is the independently unchanged rank pair.
"""
import ast
import hashlib
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
PREFLOP_SOURCE = ROOT / "scripts/preflop_validation.py"
ARCHIVED_PREFLOP_SOURCE = ROOT / "tests/fixtures/preflop_validation_before_foundation.py.txt"
OLD_PREFLOP_LF_SHA256 = "c4abe50a3f3ff814910ad2eaf653e6e2b29f7c31b28e6618f1718283794cfaa8"
CURRENT_PREFLOP_LF_SHA256 = "f9e81b318b78b3e4d9af43095d1a99bf6a0e1c5604d27dd0ba3e4ac02116f06f"
RANK_FUNCTIONS = ("_five_rank", "independent_rank")
RIVER_AUDIT_SOURCE = ROOT / "scripts/audit_river_rational_certificate.py"
ARCHIVED_RIVER_AUDIT = ROOT / "tests/fixtures/audit_river_rational_certificate_before_foundation.py.txt"
ARCHIVED_RAISED_REFERENCE = ROOT / "tests/fixtures/full_deck_raised_reference.py.before_foundation.txt"
ARCHIVED_RAISED_AUDIT = ROOT / "tests/fixtures/audit_full_deck_raised_exact.py.before_foundation.txt"
ARCHIVED_RAISED_AUDIT_TEST = ROOT / "tests/fixtures/test_full_deck_raised_exact.py.before_foundation.txt"
BRIDGE_INPUTS = (Path(__file__).resolve(), ROOT / "scripts/historical_turn_sources.py",
                 ARCHIVED_PREFLOP_SOURCE, ARCHIVED_RIVER_AUDIT,
                 ARCHIVED_RAISED_REFERENCE, ARCHIVED_RAISED_AUDIT, ARCHIVED_RAISED_AUDIT_TEST)

# Each legacy verifier keeps its historical inventory; these archives are
# guarded as additional current operation inputs.
TURN_VERIFIER_NAMES = (
    "scripts/turn_blocker_profiles.py",
    "scripts/turn_weighted_profiles.py",
    "scripts/verify_turn_sequence.py",
    "scripts/verify_turn_blocker_sequence.py",
    "scripts/verify_turn_weighted_sequence.py",
    "scripts/verify_turn_suit_equivariance.py",
)
TURN_VERIFIER_ARCHIVES = tuple(ROOT / "tests/fixtures" / (Path(name).name + ".before_foundation.txt")
                               for name in TURN_VERIFIER_NAMES)
BRIDGE_INPUTS = BRIDGE_INPUTS + TURN_VERIFIER_ARCHIVES
TURN_CONTEXT_INPUTS = (
    "pokerlab/probability_guard.py",
    "tests/fixtures/postflop_solver_before_foundation.py.txt",
    "tests/fixtures/benchmark_full_deck_raised_turn_before_foundation.py.txt",
    "tests/fixtures/benchmark_turn_tail_before_foundation.py.txt",
    "tests/fixtures/audit_turn_tail_exact_before_foundation.py.txt",
    "tests/fixtures/build_raised_turn_witness_before_foundation.py.txt",
    "tests/fixtures/test_benchmark_turn_tail_before_foundation.py.txt",
    "tests/fixtures/test_turn_tail_artifacts_before_foundation.py.txt",
    "tests/fixtures/test_build_raised_turn_witness_before_foundation.py.txt",
)
BRIDGE_INPUTS = BRIDGE_INPUTS + tuple(ROOT / name for name in TURN_CONTEXT_INPUTS)


def _lf(raw):
    return raw.replace(b"\r\n", b"\n")


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _rank_asts(raw):
    tree = ast.parse(raw.decode("utf-8"))
    functions = {node.name: node for node in tree.body
                 if isinstance(node, ast.FunctionDef) and node.name in RANK_FUNCTIONS}
    if set(functions) != set(RANK_FUNCTIONS):
        raise ValueError("Historical rank helper definitions are incomplete")
    # Both helpers depend on these two imported global bindings. Preserve their
    # exact import declarations as well as the function bodies.
    imports = {}
    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                binding = alias.asname or alias.name
                if binding in ("Counter", "combinations"):
                    if binding in imports:
                        raise ValueError("Duplicate rank dependency binding")
                    imports[binding] = ast.dump(node, include_attributes=False)
        elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(target, ast.Name) and target.id in ("Counter", "combinations", *RANK_FUNCTIONS) for target in targets):
                raise ValueError("Rank dependency is rebound")
    if set(imports) != {"Counter", "combinations"}:
        raise ValueError("Rank dependency imports are incomplete")
    return {**{name: ast.dump(functions[name], include_attributes=False)
               for name in RANK_FUNCTIONS}, **imports}


def authenticate_preflop_rank_transition():
    """Authenticate both exact files and unchanged rank-only function ASTs.

    Archived Python is parsed as inert source and is never imported/executed.
    The returned receipt is provenance for rank-only historical replay, not a
    new strategy-quality certificate or whole-validator equivalence statement.
    """
    require_committed_bridge()
    old = _lf(ARCHIVED_PREFLOP_SOURCE.read_bytes())
    current = _lf(PREFLOP_SOURCE.read_bytes())
    if _sha(old) != OLD_PREFLOP_LF_SHA256:
        raise ValueError("Archived preflop source differs from its immutable identity")
    if _sha(current) != CURRENT_PREFLOP_LF_SHA256:
        raise ValueError("Current preflop source differs from the reviewed foundation transition")
    original_asts, current_asts = _rank_asts(old), _rank_asts(current)
    if original_asts != current_asts:
        raise ValueError("Historical rank-helper ASTs differ")
    return {
        "scope": "rank-functions-only; not chance normalization or policy validation",
        "archived_lf_sha256": OLD_PREFLOP_LF_SHA256,
        "current_lf_sha256": CURRENT_PREFLOP_LF_SHA256,
        "preserved_function_ast_sha256": {
            name: _sha(value.encode("utf-8")) for name, value in original_asts.items()
        },
    }


def historical_preflop_rank_source_matches(path, historical_digest):
    """Accept only this exact old-to-current rank-only provenance transition."""
    if Path(path).resolve() != PREFLOP_SOURCE.resolve():
        return False
    try:
        authenticate_preflop_rank_transition()
    except (ValueError, OSError, SyntaxError, UnicodeError):
        return False
    old = _lf(ARCHIVED_PREFLOP_SOURCE.read_bytes())
    return historical_digest in {_sha(old), _sha(old.replace(b"\n", b"\r\n"))}


# This separate transition authenticates the historical audit implementation,
# while permitting only the reviewed provenance/operation-guard edits. It
# makes no claim that the new program is byte-identical to the historical one.
OLD_RIVER_AUDIT_LF_SHA256 = "6af6da2995f08a2a2ddcce6a6f66d366951df09aa2f004fe6bd02eb8f5bc940f"
CURRENT_RIVER_AUDIT_LF_SHA256 = "3ddbf81a806f3ed49976c24e5092e9ffbb2f1089af1f3c89be870da31f2616ee"


def _river_unchanged_ast(raw):
    tree = ast.parse(raw.decode("utf-8"))
    changed = {"_check_historical_model_sources", "_source_fingerprints", "_validate_saved_provenance"}
    nodes = [node for node in tree.body
             if not (isinstance(node, ast.FunctionDef) and node.name in changed)
             and not (isinstance(node, ast.ImportFrom) and node.module == "scripts.historical_foundation_sources")]
    return ast.dump(ast.Module(body=nodes, type_ignores=[]), include_attributes=False)


def historical_river_audit_source_matches(path, historical_digest):
    if Path(path).resolve() != RIVER_AUDIT_SOURCE.resolve():
        return False
    try:
        require_committed_bridge()
        old = _lf(ARCHIVED_RIVER_AUDIT.read_bytes())
        current = _lf(RIVER_AUDIT_SOURCE.read_bytes())
        return (_sha(old) == OLD_RIVER_AUDIT_LF_SHA256 and
                _sha(current) == CURRENT_RIVER_AUDIT_LF_SHA256 and
                historical_digest in {_sha(old), _sha(old.replace(b"\n", b"\r\n"))} and
                _river_unchanged_ast(old) == _river_unchanged_ast(current))
    except (ValueError, OSError, SyntaxError, UnicodeError):
        return False


# Full-deck raised replay: the pinned files changed only their provenance
# checks and operation-input guards. All mathematical code is AST-compared.
RAISED_TRANSITIONS = {
    "tests/test_full_deck_raised_exact.py": (ARCHIVED_RAISED_AUDIT_TEST, "c3402ad1343a2757d8c222020aadbccb0fab938a21679f6b8267b18891983494", "f8a603547f9c24a473ebd5a600659d7bd2f9c69e8b0f76539ecf078e0cadea97"),
    "scripts/full_deck_raised_reference.py": (ARCHIVED_RAISED_REFERENCE, "c0028a879aaf42a3b9c7c06819315a4c4a5547d37c4df5637da550187f85d704", "5df023c04f9e6cd03166206fb5045bc73137c93c9f926a9b9469a5cd4b242728"),
    "scripts/audit_full_deck_raised_exact.py": (ARCHIVED_RAISED_AUDIT, "897813f28f71ca91d9994ca1fa82cd5cad6dad928fcb67515d65260e88ce40ac", "6a392d9a3a0cf37f1bc16ef2bc10f0004a7e27c5d38af92765c99e230d6cfda2"),
}


def require_committed_bridge():
    """Return a raw bridge snapshot only after binding every input to HEAD."""
    try:
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                              check=True, capture_output=True, text=True).stdout.strip()
        names = sorted({path.relative_to(ROOT).as_posix() for path in BRIDGE_INPUTS})
        requests = "".join(f"{head}:{name}\n" for name in names).encode("utf-8")
        committed = subprocess.run(["git", "cat-file", "--batch"], cwd=ROOT,
                                   input=requests, check=True, capture_output=True).stdout
    except (OSError, subprocess.CalledProcessError) as error:
        raise ValueError("Cannot authenticate committed bridge source closure") from error
    offset = 0
    snapshot = {}
    for name in names:
        end = committed.find(b"\n", offset)
        header = committed[offset:end].split() if end >= 0 else []
        if len(header) != 3 or header[1] != b"blob" or not header[2].isdigit():
            raise ValueError(f"Bridge source is not committed at HEAD: {name}")
        size = int(header[2])
        start = end + 1
        stop = start + size
        if stop >= len(committed) or committed[stop:stop + 1] != b"\n":
            raise ValueError("Malformed committed bridge source response")
        working = (ROOT / name).read_bytes()
        if _lf(committed[start:stop]) != _lf(working):
            raise ValueError(f"Committed bridge source differs from working bytes: {name}")
        snapshot[name] = _sha(working)
        offset = stop + 1
    if offset != len(committed):
        raise ValueError("Unexpected committed bridge source response")
    try:
        final_head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                    check=True, capture_output=True, text=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as error:
        raise ValueError("Cannot recheck committed bridge HEAD") from error
    if final_head != head:
        raise ValueError("Git HEAD changed while authenticating bridge source closure")
    return {"__git_head__": head, **snapshot}


def operation_fingerprints(source_paths):
    """Bind introduced dependencies to HEAD and retain raw operation hashes.

    Historical inventories remain unchanged. Stable pre-existing helper edits
    reject before reconstruction; raw hashes and HEAD also detect operation drift.
    """
    snapshot = require_committed_bridge()
    return {**snapshot, **{str(path).replace("\\", "/"): _sha((ROOT / path).read_bytes())
                          for path in source_paths}}


def _raised_test_ast(raw, *, archive):
    tree = ast.parse(raw.decode("utf-8"))
    if archive:
        class ReplaceSyntheticMaps(ast.NodeTransformer):
            def visit_Assign(self, node):
                if (len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
                        and node.targets[0].id == "source_map" and isinstance(node.value, ast.Dict)
                        and ast.literal_eval(node.value) in ({"source": "pinned"}, {"test-source": "stable"})):
                    node.value = ast.parse("audit.fingerprints()", mode="eval").body
                return self.generic_visit(node)
        tree = ReplaceSyntheticMaps().visit(tree)
    return ast.dump(tree, include_attributes=False)


def _raised_unchanged_ast(raw):
    tree = ast.parse(raw.decode("utf-8"))
    nodes = [node for node in tree.body
             if not (isinstance(node, ast.FunctionDef) and node.name == "verify_saved_artifact")
             and not (isinstance(node, ast.ImportFrom) and node.module == "scripts.historical_foundation_sources")]
    return ast.dump(ast.Module(body=nodes, type_ignores=[]), include_attributes=False)


def compatible_historical_reference_sources(historical, current, expected_paths):
    """Authenticate exact source sets and only the explicitly reviewed transitions."""
    if (not isinstance(historical, dict) or not isinstance(current, dict) or
            set(historical) != set(expected_paths) or set(current) != set(expected_paths)):
        return False
    try:
        require_committed_bridge()
        for name in expected_paths:
            old_digest, current_digest = historical[name], current[name]
            if name == "scripts/preflop_validation.py":
                authenticate_preflop_rank_transition()
                if current_digest != CURRENT_PREFLOP_LF_SHA256 or old_digest not in (
                        OLD_PREFLOP_LF_SHA256, CURRENT_PREFLOP_LF_SHA256):
                    return False
            elif name in TURN_VERIFIER_TRANSITIONS:
                if current_digest != TURN_VERIFIER_TRANSITIONS[name][1] or not _turn_verifier_matches(ROOT / name, old_digest):
                    return False
            elif name in RAISED_TRANSITIONS:
                archive, old_pin, current_pin = RAISED_TRANSITIONS[name]
                old_bytes, current_bytes = _lf(archive.read_bytes()), _lf((ROOT / name).read_bytes())
                if (_sha(old_bytes) != old_pin or _sha(current_bytes) != current_pin or
                        current_digest != current_pin or old_digest not in (old_pin, current_pin) or
                        ((_raised_test_ast(old_bytes, archive=True) != _raised_test_ast(current_bytes, archive=False))
                         if name == "tests/test_full_deck_raised_exact.py" else
                         (_raised_unchanged_ast(old_bytes) != _raised_unchanged_ast(current_bytes)))):
                    return False
            elif old_digest != current_digest:
                return False
        return True
    except (ValueError, OSError, SyntaxError, UnicodeError):
        return False


def historical_foundation_source_matches(path, historical_digest):
    """Match only authenticated, explicitly reviewed foundation transitions."""
    try:
        require_committed_bridge()
        resolved = Path(path).resolve()
        if resolved == PREFLOP_SOURCE.resolve():
            authenticate_preflop_rank_transition()
            return historical_digest in (_line_ending_hashes(ARCHIVED_PREFLOP_SOURCE.read_bytes()) |
                                         _line_ending_hashes(PREFLOP_SOURCE.read_bytes()))
        if resolved == RIVER_AUDIT_SOURCE.resolve():
            return (historical_river_audit_source_matches(path, OLD_RIVER_AUDIT_LF_SHA256) and
                    historical_digest in (_line_ending_hashes(ARCHIVED_RIVER_AUDIT.read_bytes()) |
                                          _line_ending_hashes(RIVER_AUDIT_SOURCE.read_bytes())))
        for name, (archive, old_pin, current_pin) in RAISED_TRANSITIONS.items():
            if resolved == (ROOT / name).resolve():
                return (compatible_historical_reference_sources({name: old_pin}, {name: current_pin}, (name,)) and
                        historical_digest in (_line_ending_hashes(archive.read_bytes()) |
                                              _line_ending_hashes((ROOT / name).read_bytes())))
        return (_turn_verifier_matches(path, historical_digest) or
                _synthetic_test_matches(path, historical_digest))
    except (ValueError, OSError, SyntaxError, UnicodeError):
        return False


# Exact old and new source identities; AST differences are confined to the
# explicitly named provenance/operation-guard functions and the bridge import.
TURN_VERIFIER_TRANSITIONS = {
    "scripts/turn_blocker_profiles.py": ("42798c5153841991b8c8c775f863dab97acbec96b2df6c0afba9e6ce37a7907c", "b2f80637acaaf8c6a8fae3a18342ba8bde7cbb032333f1b3118e0e2b898fcebf", ('inputs', 'source_pins')),
    "scripts/turn_weighted_profiles.py": ("7716c5032cce3f499abdb8b30bdc8457f9c0070b0dd7f010c2c495e77c3e650e", "d4e752666deb31d70bc277883554231bab2ad49a7b18bbf1a409fa84bf3b7974", ('inputs', 'source_pins')),
    "scripts/verify_turn_sequence.py": ("4d9aef7ec85ff6d5491ec172c0e73eb96d8af56db3881efb88491e466364b79d", "53293d819de49d39a47dc07dad36dc9d13e7053ab2346bd34a754f9d2e98d75b", ('_inputs', '_provenance')),
    "scripts/verify_turn_blocker_sequence.py": ("2cb229d6a4aba97dca363196ee387d57272aebcb1be2c3a8aa44f5b700256428", "e5f813d11b45571b237a25ee0607a039cb304ae6aa12858e04c804327dab9302", ('_inputs', '_provenance')),
    "scripts/verify_turn_weighted_sequence.py": ("ee4b2785e151e8768b42a017341b58cfe7e4554a7c0e2ed51c4b6420c34983ed", "acc78e6b7de650fc1976c043eaa84791f37a28b537c7be07f70bab0d6e5dee38", ('_inputs', '_provenance')),
    "scripts/verify_turn_suit_equivariance.py": ("75e4dd31ab18817a6032e60cfdbec53916ab553d60f472cac179df769ed5f13e", "6a8c4685b116fb2ccd3410e5bff775f039dfbaea12da6e4c65e2cb7c503526b2", ('source_inputs', 'verify_source_pins')),
}


TURN_VERIFIER_TRANSITIONS.update({
    "scripts/river_blocker_profiles.py": ("1d6d1e462df3c1ed162ab1042e9dc9d7b928a94eb8a5f08819223fb097488e71", "e24611dcacdca2345efd16d65c225937207e9ca47bc8c5351ad9ea0a31e73de0", ('_sources',)),
    "scripts/benchmark_river_direct_tail.py": ("7362280470f9fa3aea575de981242e383e11dfa7acdba6669a820d2548bbf486", "4eeb90812297f41a5eb25bb144482ed59284f17ab8b395b6dc0dbeb9c161d9a0", ('_verify_bundle',)),
    "scripts/benchmark_river_direct_long_tail.py": ("cf79a69df6c3e71643a882359c074c7d825574d9b1b769ac9e6b377f182ca576", "1cbd4b4b69065edde3019308245c9a1cf6510e60e2d4f55c9b4f1b0d7da7514e", ('_validate_report_context', '_verify_bundle')),
    "scripts/benchmark_turn_direct_tail.py": ("17604a38e02911de28f2484fd9a4f278deb08a8544b4a89f74beecb51b021156", "0c955d193f754ecfc2a0e6509ebcf5df62b6985fbeb84705d32b34f59e0b99b5", ('_verify_payload',)),
    "scripts/benchmark_turn_three_hand_tail.py": ("62eb0eeebafb720f6f6a06ce855d119d9c52d882a6066b4f892c3e9157149aec", "c5fc79fc9f8ab70063d6ce9df69e2d4c5af9e6415920bce1a92e205077cfa903", ('_verify_bundle',)),
    "scripts/audit_raised_turn_full_physical.py": ("da2759d2653768cc877c2a6eb6a3ed934e884ea0498be9370282675902435522", "08b9cf6e43158177deeb887d52bf8a543d6fd40a5f80a73993bd5cfa8e866188", ('_preflight_saved_report', 'verify_report')),
})
BRIDGE_INPUTS = BRIDGE_INPUTS + tuple(
    ROOT / "tests/fixtures" / (Path(name).name + ".before_foundation.txt")
    for name in (('scripts/river_blocker_profiles.py', 'scripts/benchmark_river_direct_tail.py', 'scripts/benchmark_river_direct_long_tail.py', 'scripts/benchmark_turn_direct_tail.py', 'scripts/benchmark_turn_three_hand_tail.py', 'scripts/audit_raised_turn_full_physical.py')))


def _line_ending_hashes(raw):
    lf = _lf(raw)
    return {_sha(lf), _sha(lf.replace(b"\n", b"\r\n"))}


def _turn_verifier_unchanged_ast(raw, allowed):
    tree = ast.parse(raw.decode("utf-8"))
    tree.body = [node for node in tree.body
                 if not (isinstance(node, ast.FunctionDef) and node.name in allowed)
                 and not (isinstance(node, ast.ImportFrom) and
                          node.module == "scripts.historical_foundation_sources")]
    return ast.dump(tree, include_attributes=False)


def _turn_verifier_matches(path, digest):
    try:
        name = Path(path).resolve().relative_to(ROOT.resolve()).as_posix()
        old_pin, current_pin, allowed = TURN_VERIFIER_TRANSITIONS[name]
        archived = ROOT / "tests/fixtures" / (Path(name).name + ".before_foundation.txt")
        old = _lf(archived.read_bytes())
        current = _lf((ROOT / name).read_bytes())
        return (_sha(old) == old_pin and _sha(current) == current_pin and
                digest in (_line_ending_hashes(old) | _line_ending_hashes(current)) and
                _turn_verifier_unchanged_ast(old, allowed) == _turn_verifier_unchanged_ast(current, allowed))
    except (KeyError, ValueError, OSError, SyntaxError, UnicodeError):
        return False


# These exact changes patch only synthetic equality plumbing contexts. The
# normalized AST must reproduce the complete archived test file.
SYNTHETIC_TEST_TRANSITIONS = {
    "tests/test_benchmark_river_direct_tail.py": ("5eae3ab6511d76f35d3a95a1789f4e6ef1642142229853891aca6320a76abb71", "2656d22814fa63cdc143c5f667527c93aad424158b1f98b0567b83931cc0261f", 3),
    "tests/test_benchmark_river_direct_long_tail.py": ("9aa292830ba25d2d39f84bfec2737e8198c1774866c83e0338cd97d6f010bf75", "a2a4a0c9fe30c00504c2fe11f5d92907f04fc944b0afc8c1687194388db29b9a", 3),
    "tests/test_benchmark_turn_three_hand_tail.py": ("9bd0168502fa43ee7c09a1ed3a54c7599593626aa1d8888b00cd1ac637ec9eb8", "c9ae3f7307f50252735941e071b29ceda61a11228df94474a4201e7850cc1550", 2),
    "tests/test_benchmark_turn_three_hand_tail_adversarial.py": ("10372f01d917e8bd0654bb1f1dd598a9fb931557fb1a97582f0ba2f188f6199d", "375cbf5c15ac2ee01355a48e4e5ec38a5758cd03dd1f732d9ffc08009ab8dfc0", 4),
}
BRIDGE_INPUTS = BRIDGE_INPUTS + tuple(
    ROOT / "tests/fixtures" / (Path(name).name + ".before_synthetic_bridge.txt")
    for name in SYNTHETIC_TEST_TRANSITIONS)
_SYNTHETIC_PATCH_AST = ast.dump(ast.parse(
    'patch.object(runner, "compatible_exact_source_maps", side_effect=lambda saved, current, root: saved == current)',
    mode="eval").body, include_attributes=False)


def _synthetic_test_ast(raw, *, strip):
    tree = ast.parse(raw.decode("utf-8"))
    count = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.With):
            kept = []
            for item in node.items:
                matched = (item.optional_vars is None and
                           ast.dump(item.context_expr, include_attributes=False) == _SYNTHETIC_PATCH_AST)
                if matched and strip:
                    count += 1
                else:
                    kept.append(item)
            node.items = kept
    return ast.dump(tree, include_attributes=False), count


def _synthetic_test_matches(path, digest):
    try:
        name = Path(path).resolve().relative_to(ROOT.resolve()).as_posix()
        old_pin, current_pin, expected_count = SYNTHETIC_TEST_TRANSITIONS[name]
        archived = ROOT / "tests/fixtures" / (Path(name).name + ".before_synthetic_bridge.txt")
        old, current = _lf(archived.read_bytes()), _lf((ROOT / name).read_bytes())
        old_ast, old_count = _synthetic_test_ast(old, strip=True)
        current_ast, current_count = _synthetic_test_ast(current, strip=True)
        return (_sha(old) == old_pin and _sha(current) == current_pin and
                old_count == 0 and current_count == expected_count and old_ast == current_ast and
                digest in (_line_ending_hashes(old) | _line_ending_hashes(current)))
    except (KeyError, ValueError, OSError, SyntaxError, UnicodeError):
        return False


def foundation_source_accepts(path, historical_digest, direct_candidates):
    """Require reviewed transitions for protected sources; retain ordinary strict pins otherwise."""
    try:
        require_committed_bridge()
        name = Path(path).resolve().relative_to(ROOT.resolve()).as_posix()
        protected = (name in TURN_VERIFIER_TRANSITIONS or name in SYNTHETIC_TEST_TRANSITIONS or name in RAISED_TRANSITIONS or
                     name in ("scripts/preflop_validation.py", "scripts/audit_river_rational_certificate.py"))
        if protected:
            return historical_foundation_source_matches(path, historical_digest)
        return historical_digest in direct_candidates
    except (ValueError, OSError):
        return False


def compatible_exact_source_maps(historical, current, root=ROOT):
    """Keep historical map shape and accept only authenticated source transitions."""
    if type(historical) is not dict or type(current) is not dict or set(historical) != set(current):
        return False
    try:
        require_committed_bridge()
        for name, digest in historical.items():
            path = Path(root) / name
            candidate = current[name]
            if not foundation_source_accepts(path, digest, {candidate}):
                return False
            # Protected transitions must bind the current supplied hash to disk.
            if name in TURN_VERIFIER_TRANSITIONS or name in SYNTHETIC_TEST_TRANSITIONS or name in RAISED_TRANSITIONS or name in (
                    "scripts/preflop_validation.py", "scripts/audit_river_rational_certificate.py"):
                if candidate != _sha(_lf(path.read_bytes())):
                    return False
        return True
    except (OSError, ValueError):
        return False
