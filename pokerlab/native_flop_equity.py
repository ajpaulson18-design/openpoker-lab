"""Explicit native cold preparation for bounded fixed-flop checkdown tables.

The default Python preparer is unchanged. Normal range/blocker/work admission
precedes every executable lookup; failures never trigger a Python fallback.
"""
from dataclasses import dataclass
import json
import subprocess
import tempfile

from .cards import DECK
from .flop_checkdown_worlds import (
    prepare_flop_worlds,UNORDERED_BOARDS_PER_PAIR,ORDERED_OUTCOMES_PER_PAIR,
)
from .flop_checkdown_equity import FlopCheckdownEquities
from . import native_preflop_equity as native

MAX_OUTPUT_BYTES=native.MAX_OUTPUT_BYTES
NATIVE_TIMEOUT_SECONDS=native.NATIVE_TIMEOUT_SECONDS


def _invoke(board_ids,rows,build_directory):
    executable,manifest=native._backend(build_directory)
    request=(f'{native.PROTOCOL} FLOP {len(rows)} '+ ' '.join(map(str,board_ids))+'\n'
             +''.join(' '.join(map(str,row))+'\n' for row in rows)).encode('ascii')
    if len(request)>MAX_OUTPUT_BYTES:raise ValueError('Native flop request exceeds byte limit.')
    with tempfile.TemporaryFile() as output,tempfile.TemporaryFile() as errors:
        completed=subprocess.run([str(executable)],input=request,stdout=output,stderr=errors,
                                 timeout=NATIVE_TIMEOUT_SECONDS,check=False)
        output.seek(0);payload=output.read(MAX_OUTPUT_BYTES+1)
        errors.seek(0);error=errors.read(4096)
    if completed.returncode:
        raise RuntimeError(f'Native flop preparation failed ({completed.returncode}): '
                           +error.decode('utf-8',errors='replace').strip())
    if len(payload)>MAX_OUTPUT_BYTES:raise ValueError('Native flop response exceeds byte limit.')
    after_executable,after_manifest=native._backend(build_directory)
    if executable!=after_executable or manifest!=after_manifest:
        raise RuntimeError('Native flop source, manifest or executable changed during execution.')
    try:
        result=json.loads(payload,object_pairs_hook=native._json_object,parse_constant=native._reject_constant)
    except (ValueError,UnicodeError,RecursionError) as exc:
        raise ValueError('Native flop response is not valid bounded JSON.') from exc
    return result,manifest


@dataclass(frozen=True,slots=True)
class NativeFlopPreparation:
    """Existing immutable table plus detached native preparation provenance."""
    equities:FlopCheckdownEquities
    _metadata_json:str

    @property
    def metadata(self):return json.loads(self._metadata_json)


def prepare_native_flop_checkdown_equities(board,oop_range,ip_range,*,build_directory):
    """Rank admitted complete future cards through an explicitly built helper."""
    plan=prepare_flop_worlds(board,oop_range,ip_range)
    ids={card:index for index,card in enumerate(DECK)}
    board_ids=[ids[card] for card in plan.board]
    rows=[tuple(ids[card] for card in plan.hands[0][i]+plan.hands[1][j]) for i,j,_ in plan.pairs]
    result,manifest=_invoke(board_ids,rows,build_directory)
    expected_keys={'schema_version','mode','board','pairs','counts','unordered_boards_per_pair',
                   'ordered_outcomes_per_pair','board_evaluations','rank_calls'}
    if type(result) is not dict or set(result)!=expected_keys:
        raise ValueError('Native flop count response has unexpected fields.')
    expected_numbers={'schema_version':1,'unordered_boards_per_pair':UNORDERED_BOARDS_PER_PAIR,
                      'ordered_outcomes_per_pair':ORDERED_OUTCOMES_PER_PAIR,
                      'board_evaluations':len(rows)*UNORDERED_BOARDS_PER_PAIR,
                      'rank_calls':2*len(rows)*UNORDERED_BOARDS_PER_PAIR}
    if result['mode']!='flop' or any(type(result[k]) is not int or result[k]!=v for k,v in expected_numbers.items()):
        raise ValueError('Native flop identity or physical work census changed.')
    if (type(result['board']) is not list or result['board']!=board_ids
            or any(type(card) is not int for card in result['board'])
            or type(result['pairs']) is not list or len(result['pairs'])!=len(rows)
            or any(type(row) is not list or row!=list(expected) or any(type(card) is not int for card in row)
                   for row,expected in zip(result['pairs'],rows))):
        raise ValueError('Native flop board or ordered private-pair echo changed.')
    counts=result['counts']
    if (type(counts) is not list or len(counts)!=len(rows)
            or any(type(row) is not list or len(row)!=3
                   or any(type(n) is not int or n<0 or n%2 for n in row)
                   or sum(row)!=ORDERED_OUTCOMES_PER_PAIR for row in counts)):
        raise ValueError('Native flop counts must cover every ordered outcome with even W/T/L totals.')
    table=FlopCheckdownEquities(tuple(plan.board),
                              tuple(tuple(tuple(hand) for hand in hands) for hands in plan.hands),
                              tuple((i,j,prior) for i,j,prior in plan.pairs),
                              tuple(tuple(row) for row in counts),tuple(plan.budget.items()))
    table.validate()
    metadata={'backend':'native-fixed-flop-counts-v1','build':manifest,
              'compatible_pairs':len(rows),'board_evaluations':result['board_evaluations'],
              'rank_calls':result['rank_calls'],'ordered_outcomes':len(rows)*ORDERED_OUTCOMES_PER_PAIR,
              'source_inclusive_admission':True,'response':result,
              'scope':'Exact fixed-flop future checkdown counts under existing limits. '
                      'Explicit source build; structural validation does not authenticate untrusted counts.'}
    return NativeFlopPreparation(table,json.dumps(metadata,sort_keys=True,allow_nan=False))
