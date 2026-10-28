import gc,weakref
from array import array
from unittest.mock import patch
from tests.test_equivariant_packed_cfr import _request,_train
seen=[];calls=[];caught=None
class Tracked(array):
 def __mul__(self,n):
  result=super().__mul__(n);seen.append(weakref.ref(result));return result
 def __rmul__(self,n):return self.__mul__(n)
def factory(*args,**kwargs):
 calls.append(1)
 if len(calls)==5:raise MemoryError('controlled array allocation failure')
 return Tracked(*args,**kwargs)
gc.disable()
try:
 with patch('pokerlab.equivariant_packed_cfr.array',side_effect=factory):
  try:_train(_request())
  except MemoryError as e:caught=e
 print('factory_calls',len(calls),'numeric_arrays_created',len(seen),'numeric_arrays_alive_with_traceback',sum(ref() is not None for ref in seen),'error',repr(caught))
finally:gc.enable()
