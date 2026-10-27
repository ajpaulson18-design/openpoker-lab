import json
from pathlib import Path
import sys
import tracemalloc
from unittest.mock import patch

sys.path.insert(0, str(Path.cwd()))
from scripts.benchmark_selected_operator import _request
from pokerlab import selected_operator_solver as solver, packed_operator_cfr as packed

mode = sys.argv[1]
case = json.loads(Path('benchmarks/four-street-integration-v1.json').read_text())['case']
request = _request(case, 10)
events = []

def monitor(label, function):
    def observed(*args, **kwargs):
        before = tracemalloc.get_traced_memory()
        result = function(*args, **kwargs)
        current, peak = tracemalloc.get_traced_memory()
        events.append({'phase': label, 'before': before, 'after': [current, peak]})
        return result
    return observed

with patch.object(solver, '_prepare', monitor('prepare', solver._prepare)), \
     patch.object(solver.reference, '_positive_pot_training_view', monitor('tree-view', solver.reference._positive_pot_training_view)), \
     patch.object(packed, 'layout_census', monitor('layout-census', packed.layout_census)), \
     patch.object(packed, 'train_packed', monitor('packed-training', packed.train_packed)), \
     patch.object(solver, '_train_prepared', monitor('row-training', solver._train_prepared)), \
     patch.object(solver, '_normalize_policies', monitor('policy-normalization', solver._normalize_policies)), \
     patch.object(solver, '_evaluate_prepared', monitor('diagnostics', solver._evaluate_prepared)):
    tracemalloc.start()
    result = solver.solve_four_street_operator(request, rank_cache_boards=64, strategy_storage=mode)
    events.append({'phase': 'complete', 'after': tracemalloc.get_traced_memory()})
    tracemalloc.stop()
print(json.dumps({'mode': mode, 'events': events}, indent=2))
