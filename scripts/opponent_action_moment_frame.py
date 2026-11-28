"""Stdlib-only bounded decoding of conditional moment and transcript frames."""
from fractions import Fraction
import struct

Q=1<<52
DR=1<<625
DA=1<<364


def need(value,message):
    if not value:raise ValueError(message)


class Reader:
    def __init__(self,raw,limit):
        need(type(raw) is bytes and len(raw)<=limit,'moment bounded immutable frame')
        self.raw=raw;self.offset=0
    def take(self,size):
        need(0<=size<=len(self.raw)-self.offset,'moment truncated frame')
        result=self.raw[self.offset:self.offset+size];self.offset+=size;return result
    def magic(self,expected):need(self.take(8)==expected,'moment frame magic')
    def words(self,count):return struct.unpack('<'+'Q'*count,self.take(8*count))
    def integer(self,size,signed=False):return int.from_bytes(self.take(size),'little',signed=signed)
    def end(self):need(self.offset==len(self.raw),'moment trailing frame bytes')


def descriptor(reader,previous):
    actor,holding,ordinal,source,k=reader.words(5);key=(actor,holding,ordinal)
    need(actor in (0,1) and holding==0 and 0<=ordinal<1<<64 and source<388 and 2<=k<=4 and
         (previous is None or previous<key),'moment ordered unique descriptor')
    return key,source,k


def ratio(saved,scale):
    need(type(saved) is dict and set(saved)=={'numerator','denominator'} and
         type(saved['numerator']) is int and type(saved['denominator']) is int and
         0<saved['denominator'] and max(abs(saved['numerator']).bit_length(),saved['denominator'].bit_length())<=2688,
         'moment bounded reported fraction')
    n,d=saved['numerator'],saved['denominator'];need(scale%d==0,'moment reported carrier')
    return n*(scale//d)


def parse(wire,side,report):
    """Check all coordinates before current numerical references are imported.

    This decoder checks necessary invariants, not the stochastic law. Fresh
    independent moment/transcript reconstruction must still match every byte.
    """
    reader=Reader(wire,2_135_476);reader.magic(b'OPLOAM01');header=reader.words(21)
    index=report['case'];hands=report['hands'];board=report['board']
    need(header[:5]==(1,index,52,1,1) and 0<=index<3 and 0<=header[5]<34_246_080 and
         header[6:10]==tuple(hands[0]+hands[1]) and header[10:15]==tuple(board) and
         len(set(header[6:15]))==9 and max(header[6:15])<52 and tuple(sorted(board[:3]))==tuple(board[:3]) and
         header[15:]==(report['showdown_sign']+1,4,434,1039,625,364),'moment physical/header domain')
    tables=[];last_work=last_bits=0
    for table_index in range(4):
        begin=reader.offset;reader.magic(b'OPLOMT01');h=reader.words(10);policy,scheme=divmod(table_index,2)
        need(h[:8]==(1,policy,scheme,434,1039,441872,1105,1105) and
             last_work<=h[8]<=16_000_000 and last_bits<=h[9]<=1_000_000_000,'moment table census/accounting')
        last_work,last_bits=h[8:];roots=[]
        for _target in (0,1):
            mean=reader.integer(88,True);second=reader.integer(168)
            need(abs(mean)<=8*DR and second>=mean*mean and (scheme==0 or second<=64*DR*DR),'moment root variance/bound')
            roots.append((mean,second))
        need(roots[0][0]==-roots[1][0],'moment expected zero-sum roots')
        rows={};previous=None;slots=0;stats=[0,0,0,0]
        for _ in range(434):
            key,source,k=descriptor(reader,previous);previous=key;units=[];rs=[];aa=[]
            for _a in range(k):
                u=reader.words(1)[0];r=reader.integer(88,True);r2=reader.integer(168)
                a=reader.integer(48);a2=reader.integer(96)
                need(u<=Q and abs(r)<=16*DR and a<=DA and r2>=r*r and a2>=a*a and
                     (scheme==0 or (r2<=256*DR*DR and a2<=DA*DA)),'moment coordinate variance/bound')
                units.append(u);rs.append(r);aa.append(a)
                stats[0]+=r2-r*r;stats[1]+=a2-a*a;stats[2]+=r*r;stats[3]+=a*a
            need(sum(units)==Q and sum(u*r for u,r in zip(units,rs))==0 and
                 all(a*Q==sum(aa)*u for a,u in zip(aa,units)),'moment mean grid/center/average ratio')
            rows[key]=(source,tuple(units),tuple(rs),tuple(aa));slots+=k
        need(slots==1039 and reader.offset-begin==441872,'moment complete table layout')
        saved=report['tables'][table_index]
        need((saved['profile'],saved['scheme'],saved['rows'],saved['slots'])==
             (('uniform','visible-hash')[policy],('uniform-target-average','policy-role-average')[scheme],434,1039) and
             stats==[ratio(saved[name],scale) for name,scale in
                (('regret_variance_sum',DR*DR),('average_variance_sum',DA*DA),
                 ('regret_mean_square_sum',DR*DR),('average_mean_square_sum',DA*DA))],
             'moment every raw coordinate accounts to reported statistics')
        if scheme:need(rows==tables[-1][0] and tuple(x[0] for x in roots)==tuple(x[0] for x in tables[-1][1]),
                       'moment scheme first-moment identity')
        tables.append((rows,roots))
    reader.magic(b'OPLOMF01');footer=reader.words(5);reader.end()
    need(footer[0]>=last_work and footer[2]>=last_bits and footer[4]==4 and
         dict(zip(('work','entries','created_bits','integer_bits'),footer[:4]))==report['moment_resource_accounting'] and
         all(0<v<=cap for v,cap in zip(footer[:4],(16_000_000,500_000,1_000_000_000,4096))),
         'moment final resource receipt')
    reader=Reader(side,1_048_576);reader.magic(b'OPLOAW01')
    need(reader.words(4)==(1,index,4,len(side)),'moment witness header')
    for table_index in range(4):
        begin=reader.offset;reader.magic(b'OPLOWT01');h=reader.words(11);policy,scheme=divmod(table_index,2)
        need(h[:4]==(1,policy,scheme,policy) and 0<h[4]<=204 and h[5]<=816 and
             h[6]+h[7]<=204 and 0<h[9]<=367 and 0<h[10]<=367,'moment witness structural bounds')
        for _ in (0,1):
            root=reader.integer(88,True)
            if scheme:need(abs(root)<=8*DR and root%(1<<260)==0,'moment compact witness root')
        rows={};previous=None;slots=0;authority=tables[table_index][0]
        for _ in range(h[4]):
            key,source,k=descriptor(reader,previous);previous=key;units=[];rs=[];aa=[]
            need(key in authority and source==authority[key][0] and k==len(authority[key][1]),'moment witness source binding')
            for _a in range(k):
                u=reader.words(1)[0];r=reader.integer(88,True);a=reader.integer(48)
                if scheme:need(abs(r)<=16*DR and a<=DA and r%(1<<260)==0 and a%(1<<312)==0,'moment compact witness R/A')
                units.append(u);rs.append(r);aa.append(a)
            need(tuple(units)==authority[key][1] and sum(u*r for u,r in zip(units,rs))==0 and
                 all(a*Q==sum(aa)*u for a,u in zip(aa,units)),'moment witness policy/center/average ratio')
            rows[key]=(tuple(units),tuple(rs),tuple(aa));slots+=k
        need(slots==h[5],'moment witness slot census');chosen=set()
        for target,count in enumerate(h[6:8]):
            for _ in range(count):
                t,actor,holding,ordinal,selected,n,d=reader.words(7);key=(actor,holding,ordinal)
                need(t==target and actor==1-target and key in rows and (target,key) not in chosen and
                     selected<len(rows[key][0]) and 0<n<=d<=Q,'moment witness supported unique proposal')
                q=Fraction(1,len(rows[key][0])) if scheme==0 else Fraction(rows[key][0][selected],Q)
                need(q>0 and (n,d)==(q.numerator,q.denominator),'moment witness proposal factor')
                chosen.add((target,key))
        if scheme:
            for key,(units,_r,aa) in rows.items():
                expected=tuple(u*(DA//Q) for u in units) if (1-key[0],key) in chosen else (0,)*len(units)
                need(aa==expected,'moment witness opposite-role average')
        need(reader.offset-begin==h[8],'moment witness complete chunk')
        saved=report['witnesses'][table_index]
        need((saved['profile'],saved['scheme'],saved['choice'],saved['observed_rows'],saved['slots'],saved['visits'],
              saved['proposal_factors'],saved['probability_materialized'],saved['role_compact_denominators_verified'])==
             (policy,('uniform-target-average','policy-role-average')[scheme],('first','last')[policy],h[4],h[5],list(h[9:]),
              h[6]+h[7],False,bool(scheme)),'moment witness reported census')
    reader.end()
    return {'tables':4,'rows_per_table':434,'slots_per_table':1039,'first_moment_coordinates':8312,
            'marginal_second_coordinates':8312,'supported_transcript_witnesses':4}
