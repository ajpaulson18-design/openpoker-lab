"""Verify an entire retained frozen-update study without numerical producers."""
from pathlib import Path
import argparse
import json
import time
import traceback
from tests.virtual_frozen_source_guard import capture_source, verify_source, require_source_bootstrap
from tests.virtual_frozen_saved_review import authenticate_saved_study, replay_saved_numeric, replay_plan, unlinked_path
from tests.virtual_frozen_run_control import RunClaim
from tests.virtual_frozen_saved_mutations import native_witnesses


def review(study, operator, frozen_repo, head, output):
    repo = Path(__file__).resolve().parents[1]
    require_source_bootstrap(repo)
    study, operator, frozen_repo = map(unlinked_path, (study, operator, frozen_repo))
    output = Path(output).resolve()
    if any(output.is_relative_to(p) for p in (repo, study, operator, frozen_repo)):
        raise ValueError('saved review output must be separate from sources and original evidence')
    verifier_source = capture_source(repo)
    require_source_bootstrap(repo, verifier_source)
    claim = RunClaim(output, verifier_source['head'])
    started = time.perf_counter()
    def save(name, value, cap=1 << 20):
        raw = (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()
        if len(raw) > cap:
            raise ValueError('saved review receipt byte bound')
        with (output / name).open('xb') as destination:
            destination.write(raw)
    try:
        save('resource-plan.json', replay_plan())
        save('verifier-source.json', verifier_source, 16 << 20)
        provenance = authenticate_saved_study(study, operator, frozen_repo, head)
        save('provenance.json', provenance)
        witnesses = native_witnesses(study, output / 'mutations')
        save('native-mutation-witnesses.json', witnesses)
        if not witnesses['all_detected']:
            raise ValueError('real native corruption witness missing or undetected; see saved receipt')
        count = 0
        with (output / 'progress.jsonl').open('xb') as destination:
            def progress(record):
                nonlocal count
                raw = (json.dumps(record, sort_keys=True) + '\n').encode()
                if len(raw) > 512 or count >= 5040:
                    raise ValueError('saved review progress bound')
                destination.write(raw)
                destination.flush()
                count += 1
            result = replay_saved_numeric(study, provenance, progress=progress,
                                         witness_directory=output / 'mutations')
        result['duration_seconds'] = time.perf_counter() - started
        result['verifier_head'] = verifier_source['head']
        result['outer_verifier_exit_and_final_bootstrap'] = 'required separately'
        result['native_mutation_witnesses'] = witnesses
        result['verifier_source_final'] = verify_source(repo, verifier_source)
        require_source_bootstrap(repo, verifier_source)
        save('result.json', result)
        if not result['q_free_mutation_witness']['detected']:
            raise ValueError('q-free corruption witness undetected; see saved result')
        claim.finish('complete', {'saved_calls': count, 'result': 'result.json',
                                 'acceptance': 'numeric replay and four witnesses pass; outer verifier exit/final bootstrap still required'})
        return result
    except BaseException as error:
        claim.finish('failed', {'first_error': type(error).__name__ + ': ' + str(error)[:2048],
                               'traceback': traceback.format_exc()[-16384:]})
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('study', 'operator', 'frozen-repo', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--expected-head', required=True)
    args = parser.parse_args()
    print(json.dumps(review(args.study, args.operator, args.frozen_repo,
                            args.expected_head, args.output), sort_keys=True))


if __name__ == '__main__':
    main()
