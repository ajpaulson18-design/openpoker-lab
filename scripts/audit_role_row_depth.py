"""Source-frozen structural carrier audit of independently replayed native state."""
import argparse
from collections import Counter
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path
from scripts.run_opponent_action_study import ROOT, closure, git, need


def audit(output):
    output = Path(output).resolve()
    need(output.parent == ROOT.parent.resolve() and not output.exists(), 'row depth fresh external evidence')
    names = closure(('scripts/audit_role_row_depth.py', 'tests/role_row_depth_reference.py',
                     'tests/test_role_row_depth_reference.py', 'scripts/replay_compact_role_storage.py'))
    need(not git('status', '--porcelain', '--untracked-files=all', '--', *names), 'row depth committed complete source')
    head = git('rev-parse', 'HEAD').decode().strip()
    tree = {line.split('\t', 1)[1]: line.split('\t', 1)[0].split()[2] for line in git('ls-tree', '-r', head).decode().splitlines()}
    output.mkdir()
    for name, raw in names.items():
        path = output/'source'/name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw)
    (output/'source-identity.json').write_text(json.dumps({'head': head, 'raw_sha256': {n: sha256(b).hexdigest() for n, b in names.items()},
        'committed_blobs': {n: tree[n] for n in names}}, indent=2)+'\n')
    # Complete source/build/process authentication, followed by fresh full1326
    # literal/Fraction replay, precedes new structural interpretation.
    from scripts import replay_compact_role_storage as saved, joint_evidence_archive as archive, replay_joint_two_epoch_packet as helper
    replay = saved.replay()
    (output/'independent-state-replay.json').write_text(json.dumps(replay, indent=2)+'\n')
    _manifest, loaded, pins = archive.load(saved.PACKET, helper, pin=saved.PIN, version='compact-role-storage',
        labels=('observations', 'builds', 'objects'), packager='package_compact_role_storage1.py.txt')
    from scripts.matrix_free_certificate_budget import Budget
    from tests.virtual_betting_template_reference import build_reference_template
    from tests.virtual_frozen_update_reference import _template_case
    from tests.compact_role_storage_reference import unwrap
    from tests.role_row_depth_reference import depths, convert, matching
    source_budget = Budget({'work': 43000000, 'entries': 131072, 'created_bits': 1000000000, 'integer_bits': 4096})
    template = build_reference_template(_template_case(), rule_budget=source_budget); nodes = template.nodes
    graph = tuple((n.phase, n.state.player if n.phase == 'decision' else -1, tuple(e.child for e in n.edges)) for n in nodes)
    own = depths(graph, template.root)
    need(len(nodes) == 388 and sum(len(n.edges) for n in nodes) == 410 and own[template.root] == (6, 7), 'row depth fixed independent source')
    stakes = {i: min(Fraction.from_float(float(x)) for x in n.state.state.committed)
              for i, n in enumerate(nodes) if n.phase in ('fold', 'showdown')}
    need(all(abs(x) <= 8 and (2*x).denominator == 1 for x in stakes.values()), 'row depth half-unit whole-hand payoffs')
    paths = [template.root]
    for source in paths:
        paths.extend(e.child for e in nodes[source].edges)
        need(len(paths) <= 1105, 'row depth literal occurrence ceiling')
    need(len(paths) == 1105, 'row depth complete literal transport')
    # A separate, bounded post-replay audit; it admits no larger training,
    # reference walk, lifetime or I/O request. All original caps stay fixed.
    limits = {'snapshots': 24, 'retained_rows': 7344, 'raw_rows': 4896,
              'retained_slots': 29376, 'raw_slots': 19584, 'integer_bits': 704}
    meter = Budget({'work': 16000000, 'entries': 500000, 'created_bits': 1000000000, 'integer_bits': 4096})
    meter.entries(300000, 'bounded post-replay rows, descriptors and output')
    counts = Counter(); totals = Counter(); reports = []; row_images = []; seen = {}; histogram = Counter()
    fields = ('canonical_numeric_bits', 'global_compact_numeric_bits', 'row_compact_numeric_bits',
              'global_compact_used_limb_model', 'row_compact_used_limb_model', 'nonzero_regrets', 'removed_extra_regret_bits')

    def identity(metadata):
        actor, hand, ordinal, source, k = metadata
        need(paths[ordinal >> 33] == source and graph[source][0] == 'decision' and
             graph[source][1] == actor and len(graph[source][2]) == k, 'row depth complete history/source/menu binding')
        key = (actor, hand, ordinal)
        need(key not in seen or seen[key] == metadata, 'row depth immutable row source')
        seen[key] = metadata
        power = 1 + 52*own[source][actor]
        need(53 <= power <= 365, 'row depth own decision included')
        return key, power

    for profile in (0, 1):
        for label in ('same-world', 'boundaries', 'shared-flop-future', 'sb-loss', 'sb-win', 'shared-board-distinct-holding'):
            prefix = f'matrix/normal/profile-{profile}-{label}'; files = loaded['observations']
            protocol = helper.decode(files[prefix+'/protocol.json']); selectors = tuple(tuple(x) for x in protocol['selectors'])
            records, _normalized, storage, _admission = unwrap(files[prefix+'/compact/stdout.bin'], files[prefix+'/request.bin'],
                profile, selectors, protocol['rule'], 1)
            for epoch, record in enumerate(records, 1):
                metrics = storage['storage'][epoch-1]; limb_bits = metrics['limb_bits']; values = Counter()
                counts['snapshots'] += 1
                for row in record['raw']:
                    meter.charge('row_depth_raw', 1024); meter._reserve((704,)*96, 'row depth raw conversion')
                    _key, power = identity(row[:5]); rr, aa = row[7:9]
                    counts['raw_rows'] += 1; counts['raw_slots'] += len(rr)
                    r, a = convert(tuple(x << 260 for x in rr), tuple(x << 312 for x in aa), power)
                    need(tuple(x << (365-power) for x in r) == rr and a == aa, 'row depth raw exact global roundtrip')
                for key, (rr, aa, units) in record['snapshot'].items():
                    meter.charge('row_depth_retained', 1024); meter._reserve((704,)*96, 'row depth retained conversion and allocation')
                    bound_key, power = identity(seen[key]); need(bound_key == key, 'row depth retained original key')
                    counts['retained_rows'] += 1; counts['retained_slots'] += len(rr); histogram[power] += 1
                    r, a = convert(rr, aa, power); global_r = tuple(x >> 260 for x in rr)
                    need(matching(rr) == matching(r) == units, 'row depth independent exact Q52 matching policy')
                    positive = [x for x in global_r if x > 0]; small_positive = [x for x in r if x > 0]
                    effective = lambda xs: max((x.bit_length() for x in xs), default=0) - min(((x & -x).bit_length()-1 for x in xs), default=0)
                    need(effective(positive) == effective(small_positive), 'row depth unchanged normalized division width')
                    canonical_bits = sum(abs(x).bit_length() for x in (*rr, *aa))
                    global_bits = sum(abs(x).bit_length() for x in (*global_r, *a))
                    row_bits = sum(abs(x).bit_length() for x in (*r, *a)); nz = sum(x != 0 for x in rr)
                    need(global_bits-row_bits == (365-power)*nz, 'row depth exact additional padding identity')
                    values.update(dict(zip(fields, (canonical_bits, global_bits, row_bits,
                        sum(max(1, (abs(x).bit_length()+limb_bits-1)//limb_bits) for x in (*global_r, *a)),
                        sum(max(1, (abs(x).bit_length()+limb_bits-1)//limb_bits) for x in (*r, *a)), nz, (365-power)*nz))))
                    row_images.append({'case': f'profile-{profile}-{label}', 'epoch': epoch, 'identity': seen[key],
                        'regret_power': power, 'regrets': r, 'averages': a, 'unchanged_units': units})
                need(values['global_compact_used_limb_model'] == metrics['native_used_limbs'], 'row depth anchored global native used limbs')
                need(all(counts[k] <= v for k, v in limits.items() if k != 'integer_bits'), 'row depth fixed batch geometry')
                totals.update(values); reports.append({'case': f'profile-{profile}-{label}', 'epoch': epoch, 'limb_bits': limb_bits,
                    'rows': metrics['rows'], 'slots': metrics['slots'], **{f: values[f] for f in fields}})
    source_rows = Counter(m[3] for m in seen.values())
    result = {'status': 'role-row-structural-carrier-audited', 'source_head': head, 'source_files': len(names),
        'original_state_packet_pin': saved.PIN, 'original_replay_coordinates': replay['numeric_coordinates_per_representation'],
        'limits': limits, 'counts': dict(counts), 'post_audit_budget': meter.receipt(), 'independent_template_budget': source_budget.receipt(),
        'root_remaining_own_decisions': own[template.root], 'half_unit_terminals_checked': len(stakes),
        'regret_power_histogram_over_separate_snapshots': dict(sorted(histogram.items())),
        'distinct_rows_sharing_sources': sum(n for n in source_rows.values() if n > 1),
        'totals_over_separate_snapshots': {f: totals[f] for f in fields}, 'cases': reports,
        'native_calls': 0, 'archived_source_executed': False, 'native_row_carrier_implemented': False,
        'quality_gate': None, 'supported_native_epochs': 2,
        'scope': 'Structural dyadic induction and lossless saved T2 conversions. Full-history rows remain separate. Additional limb figures are exact used-limb models, not observed row-carrier capacity, total memory, runtime, longer-training admission or solved quality. Normalized Quantizer division widths are unchanged.'}
    (output/'row-carriers.json').write_text(json.dumps(row_images, indent=2)+'\n')
    (output/'structural-powers.json').write_text(json.dumps({'graph': graph, 'remaining_own_decisions': own}, indent=2)+'\n')
    need(git('rev-parse', 'HEAD').decode().strip() == head and all((ROOT/n).read_bytes() == b for n, b in names.items()), 'row depth raw source drift')
    need(archive.load(saved.PACKET, helper, pin=saved.PIN, version='compact-role-storage', labels=('observations', 'builds', 'objects'),
        packager='package_compact_role_storage1.py.txt')[2] == pins, 'row depth original state packet drift')
    (output/'result.json').write_text(json.dumps(result, indent=2)+'\n'); return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('output', type=Path)
    r = audit(p.parse_args().output)
    print(json.dumps({k: r[k] for k in ('status', 'source_head', 'source_files', 'counts', 'totals_over_separate_snapshots')}, indent=2))
