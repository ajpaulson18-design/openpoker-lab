"""Independent structural dyadic carriers; no native Store or training adapter."""
from fractions import Fraction

Q = 1 << 52


def need(value, message):
    if not value:
        raise ValueError(message)


def depths(graph, root=0):
    """Maximum remaining own decisions, including the current own decision.

    A terminal payoff is an integer multiple of 1/2. A selected opponent
    edge and a reveal introduce no policy denominator; an own Q52 mixture
    introduces at most one. Sharing this structural bound never shares rows.
    """
    need(type(graph) is tuple and 0 < len(graph) <= 388 and
         type(root) is int and 0 <= root < len(graph), 'row depth graph domain')
    edges = 0
    for item in graph:
        need(type(item) is tuple and len(item) == 3, 'row depth node shape')
        phase, actor, children = item
        need(type(phase) is str and type(actor) is int and type(children) is tuple and
             all(type(c) is int and 0 <= c < len(graph) for c in children), 'row depth edge domain')
        need((phase == 'decision' and actor in (0, 1) and 2 <= len(children) <= 4) or
             (phase == 'reveal' and actor == -1 and len(children) == 1) or
             (phase in ('fold', 'showdown') and actor == -1 and not children), 'row depth phase contract')
        edges += len(children)
    need(edges <= 410, 'row depth edge ceiling')
    active = set(); result = {}; path_depth = {}

    def visit(source):
        need(source not in active, 'row depth cycle')
        if source in result:
            return result[source]
        active.add(source)
        phase, actor, children = graph[source]
        suffixes = tuple(visit(c) for c in children)
        value = tuple((phase == 'decision' and actor == p) +
                      max((v[p] for v in suffixes), default=0) for p in (0, 1))
        path_depth[source] = 1 + max((path_depth[c] for c in children), default=0)
        need(max(value) <= 7 and path_depth[source] <= 64, 'row depth fixed template ceiling')
        active.remove(source); result[source] = value
        return value

    visit(root)
    need(len(result) == len(graph), 'row depth unreachable node')
    return tuple(result[s] for s in range(len(graph)))


def convert(rr, aa, power):
    """Losslessly convert canonical retained R625/A364 to row Rpower/A52."""
    need(type(power) is int and power in range(53, 366, 52) and
         type(rr) is tuple and type(aa) is tuple and 2 <= len(rr) <= 4 and len(rr) == len(aa) and
         all(type(x) is int and abs(x).bit_length() <= 631 for x in rr) and
         all(type(x) is int and 0 <= x and x.bit_length() <= 366 for x in aa), 'row carrier domain')
    shift = 625 - power
    need(all(x % (1 << shift) == 0 for x in rr) and all(x % (1 << 312) == 0 for x in aa),
         'row carrier exact structural divisibility')
    r = tuple(x // (1 << shift) for x in rr); a = tuple(x >> 312 for x in aa)
    need(tuple(x << shift for x in r) == rr and tuple(x << 312 for x in a) == aa,
         'row carrier exact roundtrip')
    return r, a


def matching(rr):
    """Fraction quotients/remainders and deterministic Q52 tie order."""
    total = sum(max(0, x) for x in rr)
    values = [Fraction(max(0, x) * Q, total) for x in rr] if total else [Fraction(Q, len(rr))] * len(rr)
    units = [v.numerator // v.denominator for v in values]
    for i in sorted(range(len(rr)), key=lambda i: (-(values[i] - units[i]), i))[:Q-sum(units)]:
        units[i] += 1
    return tuple(units)
