"""Exact full-board heads-up preflop shove-or-fold finite game.

The small blind may fold or shove; the big blind may fold or call. There are
no limps, non-all-in raises, antes, rake or later-street decisions. Starting
stacks include posted blinds and must both exceed the big blind.
"""
from . import cfr
from .cfr_plus import train as train_cfrplus
from .preflop_tree import PreflopConfig
from .preflop_full_board_equity import (
    plan_preflop_equities, reweight_preflop_equities, FullBoardEquities, BOARDS_PER_PAIR,
)
from .river_tree import _Action, _Node, _Terminal, _terminal_value

MAX_MODELED_LOOP_ENTRIES = 500_000_000


def _options(config, iterations, algorithm, averaging_delay):
    if type(iterations) is not int or not 10 <= iterations <= 10_000:
        raise ValueError('Iterations must be an integer from 10 to 10,000')
    if algorithm not in ('vanilla','dcfr','cfrplus'):
        raise ValueError('Algorithm must be vanilla, dcfr or cfrplus')
    if type(averaging_delay) is not int or not 0 <= averaging_delay < iterations:
        raise ValueError('Averaging delay must be an integer in [0, iterations)')
    if averaging_delay and algorithm != 'cfrplus':
        raise ValueError('Positive averaging delay requires CFR+')
    if config is None:
        config = {}
    if not isinstance(config,dict):
        raise TypeError('Push/fold config must be a monetary mapping')
    if set(config)-{'small_blind','big_blind','starting_stack'}:
        raise ValueError('Push/fold config accepts only blinds and starting stacks')
    monetary=PreflopConfig(**config,raise_sizes=(),max_raises=0,include_all_in=True)
    if any(stack <= monetary.big_blind+1e-9 for stack in monetary.stacks):
        raise ValueError('Initial push/fold stacks must both exceed the big blind')
    return monetary


def _admit(prepared, iterations, algorithm):
    pairs=len(prepared.pairs)
    rows=3*pairs
    active=[{pair[p] for pair in prepared.pairs} for p in (0,1)]
    slots=2*sum(map(len,active))
    # Two decisions and three terminals; bound both complete player regret
    # passes, row rematching/updates and own-reach averaging per iteration.
    per_iteration=256+2048*rows+256*slots
    training=1024+64*rows+128*slots+iterations*per_iteration
    diagnostics=1024+512*rows+256*slots
    # Include repeated pair censuses through planning/build/table validation,
    # plus dictionary/range preparation. Ranking itself is capped separately.
    source=128+8*len(prepared.hands[0])*len(prepared.hands[1])+128*pairs+64*BOARDS_PER_PAIR*pairs
    total=training+diagnostics+source
    if total > MAX_MODELED_LOOP_ENTRIES:
        raise ValueError('Push/fold full-requested work exceeds 500,000,000 modeled loop entries')
    return {'budget_version':'preflop-push-fold-work-v1','requested_iterations':iterations,
            'compatible_pairs':pairs,'categorical_rows_upper_bound':rows,
            'information_action_slots':slots,'public_states':5,'algorithm':algorithm,
            'training_loop_entries_upper_bound':training,
            'diagnostic_loop_entries_upper_bound':diagnostics,
            'source_bookkeeping_loop_entries_upper_bound':source,
            'total_loop_entries_upper_bound':total,'total_loop_entry_limit':MAX_MODELED_LOOP_ENTRIES,
            'equity_preparation':dict(prepared.budget),
            'scope':'Conservative bookkeeping and generic-CFR/reference diagnostic loop entries for the fixed two-decision tree; source preparation is charged even when an immutable table is reused. Internal ranking instructions and caller progress callbacks are excluded; total rank calls have a separate pre-enumeration cap. Not bytecode, elapsed time, allocated bytes or RSS bounds.'}


def prepare_preflop_equities(sb_range,bb_range,*,progress=None):
    """Enumerate all full boards once; return an immutable reusable table."""
    return plan_preflop_equities(sb_range,bb_range).build(progress=progress)


def solve_preflop_push_fold(sb_range,bb_range,*,config=None,iterations=1000,
                            algorithm='cfrplus',averaging_delay=0,progress=None):
    """Prepare full-board equity and solve, admitting requested work first."""
    monetary=_options(config,iterations,algorithm,averaging_delay)
    plan=plan_preflop_equities(sb_range,bb_range)
    _admit(plan,iterations,algorithm)
    table=plan.build(progress=progress)
    return solve_prepared_push_fold(table,config={k:v for k,v in monetary.to_dict().items()
        if k in ('small_blind','big_blind','starting_stack')},iterations=iterations,
        algorithm=algorithm,averaging_delay=averaging_delay)


def solve_prepared_push_fold(equities,*,config=None,iterations=1000,
                             algorithm='cfrplus',averaging_delay=0):
    """Solve with structurally validated trusted counts, without re-enumerating boards."""
    monetary=_options(config,iterations,algorithm,averaging_delay)
    if not isinstance(equities,FullBoardEquities):
        raise TypeError('equities must be a FullBoardEquities table with trusted counts')
    equities.validate()
    budget=_admit(equities,iterations,algorithm)
    sb,bb=monetary.small_blind,monetary.big_blind
    stack_sb,stack_bb=monetary.stacks
    matched=min(stack_sb,stack_bb)
    shove=_Action('all_in',round(stack_sb-sb,9),stack_sb,stack_sb-bb+1e-9>=bb)
    call=_Action('call',round(matched-bb,9),matched)
    response=_Node((shove.token,),1,(_Action('fold'),call),
        (_Terminal('fold',(stack_sb,bb),0),_Terminal('showdown',(stack_sb,matched))))
    root=_Node((),0,(_Action('fold'),shove),(_Terminal('fold',(sb,bb),1),response))
    active=[sorted({pair[p] for pair in equities.pairs}) for p in (0,1)]
    infos={(0,i,()):2 for i in active[0]}
    infos.update({(1,j,response.history):2 for j in active[1]})
    def key(node,world):
        return node.player,world[node.player],node.history
    def payoff(node,world):
        return _terminal_value(node,world[3],0.0)
    if algorithm=='cfrplus':
        averages=train_cfrplus(root,equities.worlds,infos,iterations,
            terminal_value=payoff,node_key=key,delay=averaging_delay)
    else:
        averages=cfr.train(root,equities.worlds,infos,iterations,algorithm,
                           terminal_value=payoff,node_key=key)
    value=cfr.evaluate(root,equities.worlds,averages,payoff,key)
    br0=cfr.best_response(0,root,equities.worlds,averages,payoff,key)
    br1=cfr.best_response(1,root,equities.worlds,averages,payoff,key)
    gap=max(0.0,br0+br1)
    rows=[]
    for player,hand,history in sorted(infos):
        node=root if player==0 else response
        rows.append({'player':'sb' if player==0 else 'bb',
                     'hand':''.join(equities.hands[player][hand]),'street':'preflop',
                     'revealed_board':[],'history':list(history),
                     'actions':[{'name':a.name,'amount':a.amount,'raise_to':a.raise_to,
                                 'history_key':a.token,'probability':probability}
                                for a,probability in zip(node.actions,averages[(player,hand,history)])]})
    counts=[]
    for pair,count in zip(equities.pairs,equities.counts):
        i,j,prior=pair;wins,ties,losses=count
        counts.append({'sb_hand':''.join(equities.hands[0][i]),'bb_hand':''.join(equities.hands[1][j]),
                       'wins':wins,'ties':ties,'losses':losses,'boards':BOARDS_PER_PAIR,
                       'pair_probability':float(prior)})
    return {'solver_version':'preflop-push-fold-v1','strategy_schema':'preflop-strategy-v1',
            'algorithm':algorithm,'iterations':iterations,'averaging_delay':averaging_delay,
            'config':{k:v for k,v in monetary.to_dict().items() if k in ('small_blind','big_blind','starting_stack')},
            'runout_mode':'full-deck-unordered-final-boards',
            'compatible_pairs':len(equities.pairs),'physical_boards':BOARDS_PER_PAIR*len(equities.pairs),
            'training_world_rows':len(equities.worlds),'info_sets':len(infos),
            'work_budget':budget,'pair_equities':counts,'strategy':rows,
            'value_sb':value,'value_bb':-value,'sb_best_response_value':br0,
            'bb_best_response_value':br1,'nash_conv':gap,'exploitability':gap/2,
            'sb_best_response_gain':max(0.0,br0-value),'bb_best_response_gain':max(0.0,br1+value),
            'scope':'Exact full-board equity for a finite heads-up preflop SB fold/shove and BB fold/call action model. Whole-hand net chip transfers including blinds and unmatched refunds. Both starting stacks exceed the big blind. No limps, non-all-in raises, later-street betting, antes, rake or multiway equilibrium.'}
