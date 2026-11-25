"""Versioned typed-TLS observer frame, retaining the independent v1 census."""
import json
from tests.virtual_joint_cycle_reference import require
from tests.virtual_joint_arithmetic_cycle_reference import decode as original_decode


def decode(raw,offset,*,synthetic=False,sequence=None):
    prefix=b'JOINT_ARITHMETIC_LIGHT_CYCLES '
    require(type(raw) is bytes and len(raw)<=8192 and raw.startswith(prefix) and raw.endswith(b'\n'),'light cycle frame boundary')
    def pairs(items):
        result={}
        for key,value in items:
            require(key not in result,'duplicate light cycle key');result[key]=value
        return result
    value=json.loads(raw[len(prefix):],object_pairs_hook=pairs)
    require(type(value) is dict and type(value.get('version')) is int and value['version']==2 and
            value.get('observer_mode')=='typed-tls-inline-v1','light cycle explicit version/mode')
    normalized=dict(value);normalized['version']=1;del normalized['observer_mode']
    report=original_decode(b'JOINT_ARITHMETIC_CYCLES '+json.dumps(normalized).encode()+b'\n',offset,synthetic=synthetic,sequence=sequence)
    report['raw']=value
    report['scope']='Typed-TLS observer; same independent numeric-rule sample census. Unsampled calls omit virtual dispatch/OS thread queries. Empirical helper estimates require its own overhead gate; no pure-op or quality claim.'
    return report
