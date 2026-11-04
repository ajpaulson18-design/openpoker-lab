"""Strict bounded parser for one PROOF9 native response; no process execution.

The total byte cap is checked before ASCII decoding and splitlines. Parsing then
holds the bounded raw input, decoded text, line list and result simultaneously;
this is not a process RSS or allocation bound.
"""
import re

MAX_BYTES = 16384 + 256*868 + 868*15*(64+16) + 128*2078 + (2*2078+2*868+1)*(384//4+4)
DECK = (16, 17, 24, 32, 33, 35, 37, 43, 48)
HANDS = {0: {(43,48), (32,43)}, 1: {(24,37), (16,32)}}
DEFAULT_LIMITS = (500000000, 2000000, 65536, 1 << 30)
_DEC = re.compile(r'(?:0|[1-9][0-9]*)\Z')
_HEX = re.compile(r'(?:0|-?[1-9a-f][0-9a-f]*)\Z')
_TOKEN = re.compile(r'[!-~]{1,64}\Z')

class ProtocolError(ValueError):
    pass

def _uint(s, maximum=(1 << 64)-1):
    if len(s)>20 or not _DEC.fullmatch(s):
        raise ProtocolError('invalid decimal')
    n=int(s)
    if n>maximum: raise ProtocolError('decimal exceeds bound')
    return n

def _integer(s):
    if len(s.lstrip('-'))>96 or not _HEX.fullmatch(s):
        raise ProtocolError('invalid hexadecimal integer')
    return -int(s[1:],16) if s.startswith('-') else int(s,16)

def request(mode, proposal, board, limits=DEFAULT_LIMITS):
    if mode not in ('ADMIT','EVAL') or proposal not in ('UNIFORM','RIVER_WEIGHTED'):
        raise ProtocolError('invalid request selector')
    if type(board) not in (tuple,list) or len(board)!=5 or any(type(x) is not int or x not in DECK for x in board) or len(set(board))!=5 or not board[0]<board[1]<board[2]:
        raise ProtocolError('invalid board')
    if type(limits) not in (tuple,list) or len(limits)!=4 or any(type(x) is not int or not 0<x<=cap for x,cap in zip(limits,DEFAULT_LIMITS)):
        raise ProtocolError('invalid limits')
    return ('FROZEN_UPDATE_V1 '+mode+' '+proposal+' '+' '.join(map(str,board))+' '+' '.join(map(str,limits))+'\n').encode('ascii')

def parse(raw, *, mode=None, proposal=None, board=None):
    if type(raw) is not bytes or len(raw)>MAX_BYTES: raise ProtocolError('response byte bound')
    if any(byte != 10 and not 32 <= byte <= 126 for byte in raw): raise ProtocolError('nonprintable response')
    try: text=raw.decode('ascii')
    except UnicodeDecodeError as e: raise ProtocolError('non-ASCII response') from e
    if not text.endswith('\n') or '\r' in text: raise ProtocolError('invalid newline framing')
    lines=text.splitlines(); pos=0
    def line():
        nonlocal pos
        if pos>=len(lines): raise ProtocolError('truncated response')
        s=lines[pos];pos+=1
        if not s or s.strip()!=s or '  ' in s or '\t' in s: raise ProtocolError('invalid field spacing')
        return s.split(' ')
    def tagged(name,count):
        x=line()
        if len(x)!=count+1 or x[0]!=name: raise ProtocolError('invalid '+name+' framing')
        return x[1:]
    first=line()
    if first==['FROZEN_UPDATE_ERROR_V1']:
        reason=line()
        if len(reason)<2 or reason[0]!='reason' or len(' '.join(reason[1:]))>256: raise ProtocolError('invalid error')
        if line()!=['end'] or pos!=len(lines): raise ProtocolError('trailing error')
        return {'error':' '.join(reason[1:])}
    if first!=['FROZEN_UPDATE_RESULT_V1']: raise ProtocolError('invalid version')
    gotmode=tagged('mode',1)[0]; status=tagged('status',1)[0]
    if gotmode not in ('ADMIT','EVAL') or status not in (('ADMITTED','REJECTED') if gotmode=='ADMIT' else ('COMPLETE',)) or (mode is not None and gotmode!=mode): raise ProtocolError('invalid mode/status')
    if tagged('scope',1)!=['PROOF9_FULL_V1']: raise ProtocolError('invalid scope')
    gotproposal=tagged('proposal',1)[0]
    if gotproposal not in ('UNIFORM','RIVER_WEIGHTED') or (proposal is not None and proposal!=gotproposal): raise ProtocolError('invalid proposal')
    gotboard=tuple(_uint(x,51) for x in tagged('board',5))
    request(gotmode,gotproposal,gotboard)
    if board is not None and tuple(board)!=gotboard: raise ProtocolError('board mismatch')
    probe=tuple(_uint(x) for x in tagged('probe',5))
    if not 1<=probe[0]<=1024 or probe[1]!=MAX_BYTES or probe[2]!=16384+16*probe[0]+16*MAX_BYTES or probe[3]!=512 or not 181<=probe[4]<=384: raise ProtocolError('invalid probe transport')
    forecast=tuple(_uint(x) for x in tagged('forecast',17))
    if forecast[0] not in (0,1) or (gotmode=='ADMIT' and (status=='ADMITTED')!=bool(forecast[0])) or (gotmode=='EVAL' and forecast[0]!=1): raise ProtocolError('forecast status mismatch')
    if forecast[5]>forecast[4] or forecast[6]>868 or forecast[7]>2078 or forecast[11]>384: raise ProtocolError('forecast geometry')
    setup=tuple(_uint(x) for x in tagged('setup',5)); calls=tuple(_uint(x) for x in tagged('calls',4))
    if forecast[1]>500000000 or forecast[12]>(1<<30) or forecast[13]>2000000 or setup[0]>500000000 or setup[1]>2000000 or setup[2]>2000000 or setup[3]>384 or setup[4]>(1<<30): raise ProtocolError('resource limit')
    if gotmode=='ADMIT' and any(calls): raise ProtocolError('admit performed callbacks')
    actual=(); den=None
    if gotmode=='EVAL':
        actual=tuple(_uint(x) for x in tagged('actual',4));den=_integer(tagged('regret_denominator',1)[0])
        if actual[0]>forecast[2] or actual[1]>forecast[3] or actual[2]>forecast[4]-forecast[5] or actual[3]>forecast[5]: raise ProtocolError('actual work exceeds forecast')
        if den<=0: raise ProtocolError('nonpositive regret denominator')
    count=_uint(tagged('rows',1)[0],868)
    if (gotmode=='ADMIT' and count) or count>forecast[6]: raise ProtocolError('invalid row count')
    rows=[];seen=set();slots=0
    for idx in range(count):
        fields=tagged('row',6); rid,actor,first,second,depth,n=(_uint(x) for x in fields)
        if rid!=idx or actor not in HANDS or (first,second) not in HANDS[actor] or depth>15 or not 1<=n<=4: raise ProtocolError('invalid row')
        history=[]
        for _ in range(depth):
            token=tagged('token',1)[0]
            if not _TOKEN.fullmatch(token): raise ProtocolError('invalid history token')
            history.append(token)
        key=(actor,first,second,tuple(history))
        if key in seen: raise ProtocolError('duplicate row key')
        seen.add(key)
        avgden,mass=(_integer(x) for x in tagged('average',2))
        if avgden<=0 or mass<0: raise ProtocolError('invalid average')
        actions=[];weighted=0;avgsum=0;policy=0
        for a in range(n):
            item=tagged('action',5)
            if _uint(item[0])!=a: raise ProtocolError('action order')
            exp=-1 if item[1]=='-1' else _uint(item[1],19)
            token=item[2]
            if not _TOKEN.fullmatch(token) or token in [x[1] for x in actions]: raise ProtocolError('invalid action token')
            regret,average=_integer(item[3]),_integer(item[4])
            if average<0 or (exp<0 and average!=0) or (exp>=0 and average*(1<<exp)!=mass): raise ProtocolError('invalid action average')
            weight=0 if exp<0 else 1 << (19-exp)
            policy+=weight;weighted+=weight*regret;avgsum+=average
            actions.append((exp,token,regret,average))
        if policy!=1<<19 or weighted!=0 or avgsum!=mass: raise ProtocolError('row invariant')
        if line()!=['endrow']: raise ProtocolError('missing endrow')
        slots+=n
        if slots>forecast[7]: raise ProtocolError('action slots exceed forecast')
        rows.append({'key':key,'average_denominator':avgden,'average_mass':mass,'actions':actions})
    if line()!=['end'] or pos!=len(lines): raise ProtocolError('trailing response')
    return {'mode':gotmode,'status':status,'proposal':gotproposal,'board':gotboard,'probe':probe,'forecast':forecast,'setup':setup,'calls':calls,'actual':actual,'regret_denominator':den,'rows':rows}
