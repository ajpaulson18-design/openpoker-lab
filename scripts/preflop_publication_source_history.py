"""Sealed CI/publication-helper transitions; calculation source never qualifies.

Original measured helper bytes remain archived. The later versions only permit
an authenticated historical CI workflow and this exact helper transition.
"""
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRANSITIONS = {
    ".github/workflows/native-fixed-street.yml": (
        "f707f54e8f0644bdddf12cf1de00826ef4bcf505dc11919749ae83c838dc6d66",
        "da2f20cda4e62d8edc70f9f81983c83e904ca14971ceced08e895fad5a1ee039",
        "benchmarks/sources/preflop-publication-context-v1/native-fixed-street.yml.txt"),
    "scripts/verify_preflop_jj_kk_basis_publication.py": (
        "56dd358774d3e49fdf5c54213dd706cc9b7135abbdec12f8181b18ffade0215f",
        "689d5c55e090973d684c0d683e51060eefcab6fae63a462eb957403dea2547ef",
        "benchmarks/sources/preflop-publication-context-v1/verify_preflop_jj_kk_basis_publication.py.txt"),
    "scripts/verify_preflop_three_rank_transport_publication.py": (
        "7d5b74a502022b98a34c7b9a47744743b6ac49547fe962a9d1158ce7a5d8dc7b",
        "0f0b5a37bf3058352f65df35402ee742fa2ef50760dce348bead5be930fa124b",
        "benchmarks/sources/preflop-publication-context-v1/verify_preflop_three_rank_transport_publication.py.txt"),
}


def authenticate_transition(relative, historical_lf, current_lf):
    """Return an exact archive-backed receipt, or None for an unlisted source."""
    row = TRANSITIONS.get(relative)
    if row is None:
        return None
    old, new, archive = row
    if historical_lf != old or current_lf != new:
        raise ValueError("Unrecognized publication-helper source transition: " + relative)
    path = ROOT / archive
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 100_000:
        raise ValueError("Missing or oversized publication-helper source archive")
    with path.open("rb") as stream:
        raw = stream.read(100_001)
    if len(raw) > 100_000 or hashlib.sha256(raw).hexdigest() != old:
        raise ValueError("Publication-helper source archive differs")
    if b"\r" in raw:
        raise ValueError("Publication-helper archive must contain the original LF bytes")
    return {"historical_lf_sha256": old, "current_lf_sha256": new, "archive": archive}
