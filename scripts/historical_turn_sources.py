"""Exact historical turn-proof source transitions for the flop-only CFR+ admission.

Saved artifacts retain their original generation fingerprints. Only the five
reviewed byte identities below may differ during historical replay. New
measurements and operation guards keep actual current file hashes. This does
not attest that historical source and current source are byte-identical.
"""

TRANSITIONS = {'pokerlab/postflop_solver.py': ('a9d54a39a558ef1e72dea0b84f2b1df83bd4d36bf21820f2fb8f01cb1764f085',
                                 'e0af827215f4731ac249345f067d8d18d9721ddcf43f563c15991eefa9c37b6f'),
 'scripts/audit_turn_tail_exact.py': ('721dd285b18af62b5de96a08ca2b27926dfd95a1f788f479c972258ae1dec5ba',
                                      '952737851f2264866ad59cdd0af27d3a90d1000d6ce59ebc84e791e37371a9ab'),
 'scripts/benchmark_full_deck_raised_turn.py': ('3d061307b4ebdff1e8ac718df73ae0c8155f52ecebec5757a9fb7bbef9f53b52',
                                                '25a60602e3fd24f2709d7a157560abf895317eaf481a7888035763313b1eeea9'),
 'scripts/benchmark_turn_tail.py': ('f19ce0b47d40d6b0610c38316d4e8ffd179e548b68f27e38425a39381fd0b273',
                                    'cb6e0bf638ce1b338fbe6a27ff09a0389b535190b7a2bbb022f6350f6982c052'),
 'scripts/build_raised_turn_witness.py': ('efdcfffb5910c484e99a2998123108d958fbffcb219b6e61f52c16dd4f9958b1',
                                          'd5d7c588745015fce097798f10a3c7a42e70049f4fd49a4880d09e2744cbcd05')}


def compatible_source(name, historical, current):
    endpoints = TRANSITIONS.get(name)
    if endpoints is None:
        return historical == current
    old, new = endpoints
    return (historical, current) in ((old, old), (old, new), (new, new))


def compatible_source_maps(historical, current):
    return (type(historical) is dict and type(current) is dict
            and set(historical) == set(current)
            and all(compatible_source(name, digest, current[name])
                    for name, digest in historical.items()))
