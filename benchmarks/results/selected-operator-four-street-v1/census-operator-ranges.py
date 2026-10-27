import hashlib
import itertools
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path.cwd()))
from pokerlab.cards import DECK
from pokerlab.selected_operator_solver import census_four_street_operator
from scripts.benchmark_selected_operator import _request, _identity

source = _identity()
if source['status']:
    raise ValueError('Clean source required')
case = json.loads(Path('benchmarks/four-street-integration-v1.json').read_text())['case']
# Disjoint private-card pools isolate support-size growth from blocker effects.
# The original weighted/blocker benchmark remains the correctness control.
sb = list(itertools.combinations(DECK[:12], 2))
bb = list(itertools.combinations(DECK[12:24], 2))
boards = [''.join(DECK[24:27] + (DECK[27+i], DECK[34+i])) for i in range(6)]
rows = []
for size in (1, 2, 4, 8, 16, 32, 64):
    changed = dict(case, sb_range=','.join(''.join(h) for h in sb[:size]),
                   bb_range=','.join(''.join(h) for h in bb[:size]), runouts=boards)
    try:
        census = census_four_street_operator(_request(changed, 10))
        rows.append({'hands_per_seat': size, 'admitted': True, 'census': census})
    except ValueError as exc:
        rows.append({'hands_per_seat': size, 'admitted': False, 'reason': str(exc)})
if _identity() != source:
    raise ValueError('Source changed')
out = Path('../range-census-v1.json')
with out.open('x') as stream:
    json.dump({'source_commit': source['commit'], 'source_clean': True,
               'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               'boards': boards, 'rows': rows,
               'scope': 'Rank-free storage/work census only; no training, policy or convergence result.'},
              stream, indent=2)
print(json.dumps(rows))
