"""Exact historical turn-proof source transitions for the flop-only CFR+ admission.

Saved artifacts retain their original generation fingerprints. Only the seven
reviewed byte identities below may differ during historical replay. New
measurements and operation guards keep actual current file hashes. This does
not attest that historical source and current source are byte-identical.
"""

TRANSITIONS = {'pokerlab/postflop_solver.py': ('a9d54a39a558ef1e72dea0b84f2b1df83bd4d36bf21820f2fb8f01cb1764f085',
                                 '85b63897a9a4ae14dfa45053f2c2aa05a83549f6f75ee1dc205e0dba8c367808'),
 'scripts/audit_turn_tail_exact.py': ('721dd285b18af62b5de96a08ca2b27926dfd95a1f788f479c972258ae1dec5ba',
                                      '952737851f2264866ad59cdd0af27d3a90d1000d6ce59ebc84e791e37371a9ab'),
 'scripts/benchmark_full_deck_raised_turn.py': ('3d061307b4ebdff1e8ac718df73ae0c8155f52ecebec5757a9fb7bbef9f53b52',
                                                '25a60602e3fd24f2709d7a157560abf895317eaf481a7888035763313b1eeea9'),
 'scripts/benchmark_turn_tail.py': ('f19ce0b47d40d6b0610c38316d4e8ffd179e548b68f27e38425a39381fd0b273',
                                    'cb6e0bf638ce1b338fbe6a27ff09a0389b535190b7a2bbb022f6350f6982c052'),
 'scripts/build_raised_turn_witness.py': ('efdcfffb5910c484e99a2998123108d958fbffcb219b6e61f52c16dd4f9958b1',
                                          'd5d7c588745015fce097798f10a3c7a42e70049f4fd49a4880d09e2744cbcd05'),
 'tests/test_benchmark_turn_tail.py': ('1775f01a115a3f44f728a25f0aaf6b0709dc4b29ea329ad089665a74291d7517',
                                       '65cb0619ff4982e070fa8cdd35b55b1dd3464117e57a4d63b3ff847a11025544'),
 'tests/test_turn_tail_artifacts.py': ('024de18b698e153f5622f4627d7de4b817037333e776cc249dec18c0bcc1885a',
                                       '42b453a254e04214828d650dfd8092d74e4f68464bdf1f6b894691fbeb717754')}


from pathlib import Path
import ast
import hashlib
from scripts.historical_foundation_sources import BRIDGE_INPUTS, RAISED_TRANSITIONS, TURN_VERIFIER_TRANSITIONS, historical_foundation_source_matches


ROOT = Path(__file__).resolve().parents[1]
POSTFLOP_FOUNDATION_SHA256 = "75d15ac3945f38ee827a8cf887cc3a5755ae51ae177014dc0f266725d8586ca1"
GUARD_SHA256 = "1c250ebddf2f000c97e47001237ec50b0a6506583ca8e0df2cdea5de0a2b3a03"
POSTFLOP_ARCHIVE = "tests/fixtures/postflop_solver_before_foundation.py.txt"
FOUNDATION_TRANSITIONS = {
    "pokerlab/postflop_solver.py": POSTFLOP_FOUNDATION_SHA256,
    "scripts/benchmark_full_deck_raised_turn.py": "8bace93997409e1c81bb8fdfcb26f99ceda9fee3066b3d59fdf8e024442edcdd",
    "scripts/benchmark_turn_tail.py": "6c20525fd25504c06ce30a1866cd59b0c184d0b1106110ef182584d82bd1725f",
    "scripts/audit_turn_tail_exact.py": "4a3afd0e632bb6f9f69e89368b85e388677339c368f90bf10e7fad05f2a1fa1c",
    "scripts/build_raised_turn_witness.py": "1963bb3b93aa28ce8308ca781e91dd070d68da6ab3c180b16a86cdb5cf02bfb7",
    "tests/test_benchmark_turn_tail.py": "da94d4ee3cce775855e7441c72438d59d9dc3f53db410333b71c484d062b8a2f",
    "tests/test_turn_tail_artifacts.py": "9bb73ab8e10b5b51e943d767b5faec80d6df70917c40cf9fa514b1331b5412b4",
    "tests/test_build_raised_turn_witness.py": "10a58c21019ace5db28c5690feb190689940d28241062c4be89ab42215f0d471",
}
PRE_FOUNDATION_TESTS = {
    "tests/test_build_raised_turn_witness.py": ("b310ed3ec3834c75185a3be67c179fbbe86cc7a620b5c5349b36287506d6f36a",),
}
WRAPPER_CHANGES = {
    "scripts/benchmark_full_deck_raised_turn.py": ("fingerprints", "_validate_fingerprint_map"),
    "scripts/benchmark_turn_tail.py": ("fingerprints", "_check_report_envelope"),
    "scripts/audit_turn_tail_exact.py": ("fingerprints",),
    "scripts/build_raised_turn_witness.py": ("_source_files",),
    "tests/test_benchmark_turn_tail.py": (),
    "tests/test_turn_tail_artifacts.py": (),
    "tests/test_build_raised_turn_witness.py": (),
}
WRAPPER_ARCHIVES = tuple("tests/fixtures/" + Path(name).stem + "_before_foundation.py.txt"
                         for name in WRAPPER_CHANGES)
# New operation guards capture these actual files; historical records remain
# unchanged. Only these introduced context entries may be absent historically.
OPERATION_INPUTS = tuple(dict.fromkeys((
    "scripts/historical_turn_sources.py", "scripts/historical_foundation_sources.py",
    "tests/fixtures/preflop_validation_before_foundation.py.txt",
    POSTFLOP_ARCHIVE, "pokerlab/probability_guard.py",
) + WRAPPER_ARCHIVES + tuple(path.relative_to(ROOT).as_posix() for path in BRIDGE_INPUTS)))


def _lf(path):
    return (ROOT / path).read_bytes().replace(b"\r\n", b"\n")


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def authenticate_postflop_transition():
    """Prove the admitted normal-mass path changed only by checked identities.

    The archive is inert source. This does not equate old underflow behavior
    with the new rejection, nor authorize new training from historical pins.
    """
    old, current = _lf(POSTFLOP_ARCHIVE), _lf("pokerlab/postflop_solver.py")
    if (_sha(old) != TRANSITIONS["pokerlab/postflop_solver.py"][1]
            or _sha(current) != POSTFLOP_FOUNDATION_SHA256
            or _sha(_lf("pokerlab/probability_guard.py")) != GUARD_SHA256):
        raise ValueError("Postflop foundation transition or probability guard differs")

    class RemoveGuards(ast.NodeTransformer):
        def visit_ImportFrom(self, node):
            if node.module == "probability_guard":
                return None
            return node

        def visit_Call(self, node):
            self.generic_visit(node)
            if isinstance(node.func, ast.Name) and node.func.id == "normal_positive_mass":
                if len(node.args) != 1 or node.keywords:
                    raise ValueError("Malformed postflop guard")
                return node.args[0]
            return node

    old_ast = ast.dump(ast.parse(old), include_attributes=False)
    new_ast = ast.dump(RemoveGuards().visit(ast.parse(current)), include_attributes=False)
    if old_ast != new_ast:
        raise ValueError("Postflop arithmetic or control flow differs beyond the reviewed guards")
    return {"scope": "normal-supported-mass identity; underflow now rejects",
            "archived_lf_sha256": _sha(old), "current_lf_sha256": _sha(current),
            "probability_guard_lf_sha256": GUARD_SHA256}


def authenticate_wrapper_transition(name):
    """Bind exact reviewed provenance-only wrapper edits, preserving math AST."""
    archived = "tests/fixtures/" + Path(name).stem + "_before_foundation.py.txt"
    old, current = _lf(archived), _lf(name)
    old_pin = TRANSITIONS[name][1] if name in TRANSITIONS else PRE_FOUNDATION_TESTS[name][0]
    if (_sha(old) != old_pin
            or _sha(current) != FOUNDATION_TRANSITIONS[name]):
        raise ValueError("Turn wrapper differs from reviewed provenance transition")
    def unchanged(raw):
        tree = ast.parse(raw)
        if name.startswith("tests/"):
            class NormalizeSourceFixtures(ast.NodeTransformer):
                def visit_BinOp(self, node):
                    self.generic_visit(node)
                    if ast.unparse(node.right) == 'set(witness.OPERATION_INPUTS)':
                        return node.left
                    return node

                def visit_Assign(self, node):
                    target = ast.unparse(node.targets[0]) if len(node.targets) == 1 else ""
                    if target in ("current_pins", "source_map", "cls.sources"):
                        node.value = ast.Constant(value="reviewed-current-source-fixture")
                    return self.generic_visit(node)

                def visit_Expr(self, node):
                    if (isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Attribute)
                            and ast.unparse(node.value.func) in ("source_map.update", "cls.sources.update")):
                        return None
                    return self.generic_visit(node)
            tree = NormalizeSourceFixtures().visit(tree)
        tree.body = [node for node in tree.body if not (
            isinstance(node, ast.FunctionDef) and node.name in WRAPPER_CHANGES[name])
            and not (isinstance(node, ast.ImportFrom)
                     and node.module == "scripts.historical_turn_sources")]
        return ast.dump(tree, include_attributes=False)
    if unchanged(old) != unchanged(current):
        raise ValueError("Turn mathematical code differs beyond provenance functions")
    return {"scope": "reviewed provenance-only functions; all other AST unchanged",
            "archived_lf_sha256": _sha(old), "current_lf_sha256": _sha(current)}


def compatible_source(name, historical, current):
    if name == "scripts/audit_river_rational_certificate.py" or name in RAISED_TRANSITIONS or name in TURN_VERIFIER_TRANSITIONS:
        return current == _sha(_lf(name)) and historical_foundation_source_matches(ROOT / name, historical)
    if name == "scripts/preflop_validation.py":
        from scripts.historical_foundation_sources import (
            CURRENT_PREFLOP_LF_SHA256, authenticate_preflop_rank_transition,
            historical_preflop_rank_source_matches)
        if current == CURRENT_PREFLOP_LF_SHA256:
            if historical == current:
                authenticate_preflop_rank_transition()
                return True
            return historical_preflop_rank_source_matches(ROOT / name, historical)
        # An unreviewed equal digest is not a historical rank transition.
        return historical == current == "c4abe50a3f3ff814910ad2eaf653e6e2b29f7c31b28e6618f1718283794cfaa8"
    endpoints = TRANSITIONS.get(name, PRE_FOUNDATION_TESTS.get(name))
    extension = FOUNDATION_TRANSITIONS.get(name)
    if endpoints is None and extension is None:
        if name == "pokerlab/probability_guard.py":
            return historical == current == GUARD_SHA256
        return historical == current
    chain = tuple(endpoints or ()) + ((extension,) if extension else ())
    if historical not in chain or current not in chain:
        return False
    if chain.index(historical) > chain.index(current):
        return False
    if name == "pokerlab/postflop_solver.py" and current == POSTFLOP_FOUNDATION_SHA256:
        authenticate_postflop_transition()
    if name in WRAPPER_CHANGES and current == extension:
        authenticate_wrapper_transition(name)
    return True


def validate_current_context(current):
    """Bind newly introduced source dependencies when running the new path."""
    if (current.get("pokerlab/postflop_solver.py") != POSTFLOP_FOUNDATION_SHA256
            and current.get("scripts/preflop_validation.py") !=
            "f9e81b318b78b3e4d9af43095d1a99bf6a0e1c5604d27dd0ba3e4ac02116f06f"):
        return
    if any(current.get(name) != _sha(_lf(name)) for name in OPERATION_INPUTS):
        raise ValueError("Current source differs from reviewed foundation dependencies")
    authenticate_postflop_transition()


def compatible_source_maps(historical, current):
    if type(historical) is not dict or type(current) is not dict:
        return False
    try:
        validate_current_context(current)
    except (ValueError, OSError, SyntaxError):
        return False
    extras = set(current) - set(historical)
    if set(historical) - set(current) or extras - set(OPERATION_INPUTS):
        return False
    if extras:
        # Authenticate actual introduced dependencies, not caller-re-signed maps.
        if not all(current[name] == _sha(_lf(name)) for name in extras):
            return False
        authenticate_postflop_transition()
    return all(compatible_source(name, digest, current[name])
               for name, digest in historical.items())
