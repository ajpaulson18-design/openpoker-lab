"""Independent literal-world replay for the first PROOF9 finite-grid trainer.

The production path must not store these worlds. This bounded oracle deliberately
uses one world at a time for CFR and groups worlds by visible information for BR.
No native routing, prepared chance, payoff, state, or rank helper is an oracle.
"""
from dataclasses import dataclass
from fractions import Fraction
from itertools import combinations, permutations

from scripts.preflop_validation import independent_rank
from tests.full_deck_public_chance_reference import PROOF9, card_name
from tests.test_native_dyadic_policy import allocation
from tests.virtual_betting_template_reference import build_reference_template
from tests.virtual_frozen_update_reference import _template_case, scaled_proof9_ranges
from tests.virtual_frozen_value_reference import _reveal_token

Q = 1 << 52
D = 580 << 625
ROWS = 24_420
SLOTS = 58_164
OCCURRENCES = 1_105


def require(value, message):
    if not value:
        raise ValueError(message)


@dataclass(frozen=True)
class World:
    holdings: tuple
    board: tuple
    mass: Fraction
    sign: int


class Fixture:
    def __init__(self, *, ten_card=False):
        self.deck = tuple(sorted((*PROOF9, 0))) if ten_card else PROOF9
        require(len(set(self.deck)) == (10 if ten_card else 9), 'reference deck geometry')
        self.denominator = (3480 << 625) if ten_card else D
        self.value_bits = 644 if ten_card else 642
        self.row_count = 119_196 if ten_card else ROWS
        self.slot_count = 281_066 if ten_card else SLOTS
        self.runouts = 120 if ten_card else 20
        self.template = build_reference_template(_template_case())
        self.nodes = self.template.nodes
        require(len(self.nodes) == 388, 'reference shared state geometry')
        # Symbolic paths are transport keys. Numerical replay below keys on the
        # actual action/reveal token tuple and original holding, independently.
        self.paths = [(self.template.root, None, None, 0, None)]
        for position, (node_id, _, _, street, _) in enumerate(self.paths):
            node = self.nodes[node_id]
            require(node.street == street, 'reference literal street')
            for edge_number, edge in enumerate(node.edges):
                require(len(self.paths) < OCCURRENCES, 'reference literal path cap')
                next_street = node.state.board_length if node.phase == 'reveal' else street
                self.paths.append((edge.child, position, edge.token, next_street, edge_number))
        require(len(self.paths) == OCCURRENCES, 'reference literal occurrence census')
        self.stakes = {}
        for node_id, node in enumerate(self.nodes):
            if node.phase in ('fold', 'showdown'):
                self.stakes[node_id] = min(Fraction.from_float(float(x)) for x in node.state.state.committed)
        ranges = scaled_proof9_ranges()
        raw = [(i,j,h0,h1,w0*w1) for i,(h0,w0) in enumerate(ranges[0])
               for j,(h1,w1) in enumerate(ranges[1]) if set(h0).isdisjoint(h1)]
        normalizer = sum(x[-1] for x in raw)
        worlds = []
        for i,j,h0,h1,w in raw:
            left = tuple(c for c in self.deck if c not in (*h0,*h1))
            for flop in combinations(left,3):
                for turn,river in permutations(tuple(c for c in left if c not in flop),2):
                    board = (*flop,turn,river)
                    rank = [independent_rank(tuple(card_name(c) for c in (*hand,*board)))
                            for hand in (h0,h1)]
                    worlds.append(World((i,j),board,w/(self.runouts*normalizer),(rank[0]>rank[1])-(rank[0]<rank[1])))
        require(len(worlds)==3*self.runouts and sum(w.mass for w in worlds)==1 and {w.sign for w in worlds}=={-1,0,1},
                'reference literal physical support')
        self.worlds = tuple(worlds)
        self.menus = {}
        for world in self.worlds:
            self._register(self.template.root,(),world)
        require(len(self.menus)==self.row_count and sum(map(len,self.menus.values()))==self.slot_count,'reference exact row/slot census')

    def _register(self, node_id, history, world):
        node = self.nodes[node_id]
        if node.phase == 'reveal':
            token = _reveal_token(world.board,node.state.board_length)
            self._register(node.edges[0].child,(*history,token),world)
        elif node.phase == 'decision':
            actor=node.state.player
            key=actor,world.holdings[actor],history
            actions=tuple(e.token for e in node.edges)
            require(self.menus.setdefault(key,actions)==actions,'reference row legal-order drift')
            for edge in node.edges:self._register(edge.child,(*history,edge.token),world)

    def compact_key(self, value, actor, holding):
        require(type(value) is int and 0 <= value < 1<<64,'compact key scalar')
        occurrence,length=value>>33,(value>>30)&7
        require(occurrence<len(self.paths) and length in (0,3,4,5),'compact key path/prefix')
        require(value & (((1<<30)-1) ^ ((1<<(6*length))-1))==0,'compact key unused card bits')
        board=tuple((value>>(6*i))&63 for i in range(length))
        require(len(set(board))==length and set(board)<=set(self.deck) and (length<3 or tuple(sorted(board[:3]))==board[:3]),
                'compact key physical grammar')
        _,_,_,street,_=self.paths[occurrence]
        require(street==length,'compact key visible street')
        tokens=[]
        while occurrence:
            _,parent,token,visible,_=self.paths[occurrence]
            tokens.append(token if token is not None else _reveal_token(board,visible))
            occurrence=parent
        key=actor,holding,tuple(reversed(tokens))
        require(key in self.menus,'compact key has no physical decision row')
        return key

    def ordered_rows(self):
        """Independent positive-prior preorder, using literal joint support."""
        def visit(i,h,worlds):
            node=self.nodes[i]
            if node.phase=='reveal':
                size=node.state.board_length
                groups={}
                for w in worlds:groups.setdefault(w.board[:size],[]).append(w)
                for prefix,group in sorted(groups.items()):
                    yield from visit(node.edges[0].child,(*h,_reveal_token(prefix,size)),group)
            elif node.phase=='decision':
                actor=node.state.player
                for hold in sorted({w.holdings[actor] for w in worlds}):
                    yield actor,hold,h
                for edge in node.edges:yield from visit(edge.child,(*h,edge.token),worlds)
        return visit(self.template.root,(),self.worlds)

    def terminal_completion_counts(self):
        """Unseen completions in all-in payoff queries, never decision rows."""
        streets=(0,3,4,5)
        positive={k:len({w.board[:k] for w in self.worlds}) for k in streets}
        candidates={0:len(self.deck)*(len(self.deck)-1)*(len(self.deck)-2)//6,3:len(self.deck)-3,4:len(self.deck)-4}
        ranked=hidden=0
        for node_id,_,_,street,_ in self.paths:
            if self.nodes[node_id].phase=='showdown':
                ranked+=positive[5]
                hidden+=sum(positive[k]*candidates[k] for k in streets[:-1] if k>=street)
        return ranked,hidden

    def terminal(self, node_id, world):
        node=self.nodes[node_id]
        sign=world.sign if node.phase=='showdown' else (1 if node.state.winner==0 else -1)
        return self.stakes[node_id]*sign

    def grid(self, raw=None, *, average=False):
        return {key:tuple(allocation((0,)*len(menu) if raw is None else raw[key],average)[0])
                for key,menu in self.menus.items()}

    def _probabilities(self, policy):
        require(policy.keys()==self.menus.keys(),'saved grid row inventory')
        result={}
        for key,units in policy.items():
            require(len(units)==len(self.menus[key]) and all(type(u) is int and 0<=u<=Q for u in units) and sum(units)==Q,
                    'saved grid row partition')
            result[key]=tuple(Fraction(u,Q) for u in units)
        return result

    def sweep(self, policy, previous_regrets=None, previous_average=None, *, root_holding_values=False):
        """Literal-world full CFR+ update on one supplied frozen current grid."""
        require((previous_regrets is None)==(previous_average is None),'incomplete prior sweep')
        p=self._probabilities(policy)
        delta={key:[Fraction(0)]*len(menu) for key,menu in self.menus.items()}
        averages={key:[Fraction(0)]*len(menu) for key,menu in self.menus.items()}
        def visit(i,h,w,r0,r1):
            node=self.nodes[i]
            if node.phase in ('fold','showdown'):return self.terminal(i,w)
            if node.phase=='reveal':
                return visit(node.edges[0].child,(*h,_reveal_token(w.board,node.state.board_length)),w,r0,r1)
            actor=node.state.player
            key=actor,w.holdings[actor],h
            probabilities=p[key]
            values=[]
            for edge,q in zip(node.edges,probabilities):
                values.append(visit(edge.child,(*h,edge.token),w,r0*q if actor==0 else r0,r1*q if actor==1 else r1))
            mixed=sum(q*v for q,v in zip(probabilities,values))
            own,opposite=(r0,r1) if actor==0 else (r1,r0)
            signed_other=w.mass*opposite*(1 if actor==0 else -1)
            own_mass=w.mass*own
            for a,q in enumerate(probabilities):
                delta[key][a]+=signed_other*(values[a]-mixed)
                averages[key][a]+=own_mass*q
            return mixed
        root_values=[Fraction(0)]*4
        for w in self.worlds:
            value=w.mass*visit(self.template.root,(),w,Fraction(1),Fraction(1))
            root_values[w.holdings[0]]+=value
            root_values[2+w.holdings[1]]-=value
        def numerator(x):
            q,r=divmod(x.numerator*self.denominator,x.denominator)
            require(r==0 and abs(q).bit_length()<=self.value_bits,'reference numerator outside admitted fixed grid')
            return q
        regrets={};raw_average={}
        for k,menu in self.menus.items():
            old_r=(0,)*len(menu) if previous_regrets is None else previous_regrets[k]
            old_a=(0,)*len(menu) if previous_average is None else previous_average[k]
            regrets[k]=tuple(max(0,r+numerator(v)) for r,v in zip(old_r,delta[k]))
            raw_average[k]=tuple(a+numerator(v) for a,v in zip(old_a,averages[k]))
        return regrets,raw_average,tuple(root_values) if root_holding_values else sum(root_values[:2])

    def quality(self, saved_grid):
        """Best response chooses once per visible history and own holding."""
        p=self._probabilities(saved_grid)
        def profile(i,h,w):
            node=self.nodes[i]
            if node.phase in ('fold','showdown'):return self.terminal(i,w)
            if node.phase=='reveal':
                return profile(node.edges[0].child,(*h,_reveal_token(w.board,node.state.board_length)),w)
            actor=node.state.player
            return sum(q*profile(edge.child,(*h,edge.token),w)
                       for q,edge in zip(p[actor,w.holdings[actor],h],node.edges) if q)
        sb=sum(w.mass*profile(self.template.root,(),w) for w in self.worlds)
        def response(i,h,group,target):
            if not group:return Fraction(0)
            node=self.nodes[i]
            if node.phase in ('fold','showdown'):
                return sum(m*self.terminal(i,w)*(1 if target==0 else -1) for w,m in group)
            if node.phase=='reveal':
                groups={}
                for w,m in group:groups.setdefault(_reveal_token(w.board,node.state.board_length),[]).append((w,m))
                return sum(response(node.edges[0].child,(*h,token),g,target) for token,g in groups.items())
            actor=node.state.player
            if actor==target:
                # World masses are UNNORMALIZED. Maximize after summing all
                # indistinguishable worlds, even where saved own reach is zero.
                return max(response(edge.child,(*h,edge.token),group,target) for edge in node.edges)
            result=Fraction(0)
            for a,edge in enumerate(node.edges):
                other=[(w,m*q) for w,m in group if (q:=p[actor,w.holdings[actor],h][a])]
                result+=response(edge.child,(*h,edge.token),other,target)
            return result
        br=tuple(sum(response(self.template.root,(),[(w,w.mass) for w in self.worlds if w.holdings[t]==hand],t)
                     for hand in (0,1)) for t in (0,1))
        gains=br[0]-sb,br[1]+sb
        require(min(gains)>=0,'negative exact best-response gain')
        return {'profile_sb':sb,'profile_bb':-sb,'best_responses':br,'gains':gains,'exploitability':sum(gains)/2}
