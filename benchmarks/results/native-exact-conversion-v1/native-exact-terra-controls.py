import argparse,hashlib,json,math,random,struct,subprocess
from fractions import Fraction
from pathlib import Path

def need(condition,message):
 if not condition:raise ValueError(message)
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--repo',type=Path,required=True);parser.add_argument('--build-dir',type=Path,required=True);parser.add_argument('--output-dir',type=Path);args=parser.parse_args()
 repo=args.repo.resolve(strict=True);build=args.build_dir.resolve(strict=True);out=None
 if args.output_dir is not None:
  out=args.output_dir.resolve();need(out!=repo and repo not in out.parents and out!=build and build not in out.parents and not out.exists(),'output directory must be new and external');out.mkdir(parents=True)
 manifest_path=build/'native-exact-build-manifest.json';manifest_raw=manifest_path.read_bytes();manifest=json.loads(manifest_raw);exe=build/'native-exact-binary64-probe.exe'
 expected_sources={'native/exact_binary64_probe.cpp','native/exact_binary64.hpp','scripts/build_native_exact_four_street.py','third_party/boost-multiprecision-1.92.0/manifest.json','third_party/boost-multiprecision-1.92.0/LICENSE_1_0.txt','third_party/boost-multiprecision-1.92.0/headers.zip'}
 need(manifest.get('contract')=='native-exact-build-v1' and manifest.get('target')=='converter','invalid build manifest contract')
 need(set(manifest['source_sha256'])==expected_sources,'source manifest keyset mismatch')
 source_before={name:digest(repo/name) for name in expected_sources};need(source_before==manifest['source_sha256'],'candidate/build source bytes differ')
 need(manifest['dependency_archive_sha256']=='33c422ab3ebfa9e86c62f41f372ec2b9c2cefa303f1885391aa4d8250ef2f831' and source_before['third_party/boost-multiprecision-1.92.0/headers.zip']==manifest['dependency_archive_sha256'],'dependency archive pin mismatch')
 need(manifest['dependency_manifest_sha256']=='4d6f33341887e35a0c29e9dc5da2a326d546427940c2b16b485db0c61b042555' and source_before['third_party/boost-multiprecision-1.92.0/manifest.json']==manifest['dependency_manifest_sha256'],'dependency manifest pin mismatch')
 need(source_before['third_party/boost-multiprecision-1.92.0/LICENSE_1_0.txt']=='c9bff75738922193e67fa726fa225535870d2aa1059f91452c411736284ad566' and manifest['license']=='BSL-1.0','dependency license pin mismatch')
 exe_before=digest(exe);need(manifest['executable_sha256']==exe_before,'binary hash differs')
 if out:(out/'build-manifest.json').write_bytes(manifest_raw)
 rng=random.Random(328142);cases=[]
 def put(n,d):
  if n.bit_length()<=65536 and d.bit_length()<=65536:cases.append((n,d))
 def midpoint(a,b):return (Fraction.from_float(a)+Fraction.from_float(b))/2
 small=float.fromhex('0x1p-1022');maxf=float.fromhex('0x1.fffffffffffffp+1023')
 for x in (midpoint(math.nextafter(small,0),small),Fraction.from_float(maxf)+Fraction(2)**970):
  for offset in (-1,0,1):
   y=x+Fraction(offset,2**1200) if x < 1 else x+offset
   for sign in (-1,1):put(sign*y.numerator,y.denominator)
 for i in range(900):
  e=rng.randint(-1022,1023);raw=(rng.getrandbits(52)|(1<<52));base=math.ldexp(raw,e-52);nextv=math.nextafter(base,math.inf)
  if not math.isfinite(nextv):continue
  mid=midpoint(base,nextv)
  for k in (-1,0,1):
   perturb=Fraction(1,2**min(5000,max(1200,mid.denominator.bit_length()+25)));y=mid+k*perturb
   for sign in (-1,1):put(sign*y.numerator,y.denominator)
 for i in range(400):
  bits=rng.choice([1,53,1024,4096,16000,65535,65536]);shift=rng.randint(-1024,1024);n=(1<<(bits-1))|rng.getrandbits(min(bits-1,64));d=(1<<(bits-1))|rng.getrandbits(min(bits-1,64))
  if shift>=0:n<<=shift
  else:d<<=-shift
  put(n,d);put(-n,d)
 need(len(cases)==5966,'deterministic case inventory drift')
 def record(n,d):return ('-' if n<0 else '')+format(abs(n),'x')+' '+format(d,'x')
 payload='OPENPOKER_EXACT_BINARY64_V1\n'+'\n'.join(record(n,d) for n,d in cases)+'\n'
 if out:(out/'probe-input.txt').write_bytes(payload.encode('ascii'))
 try:r=subprocess.run([str(exe)],input=payload.encode('ascii'),capture_output=True,timeout=120)
 except subprocess.TimeoutExpired as exc:
  if out:
   (out/'probe-stdout.txt').write_bytes(exc.stdout or b'');(out/'probe-stderr.txt').write_bytes(exc.stderr or b'');(out/'probe-status.json').write_text(json.dumps({'status':'timeout','seconds':120})+'\n',encoding='utf-8')
  raise
 if out:
  (out/'probe-stdout.txt').write_bytes(r.stdout);(out/'probe-stderr.txt').write_bytes(r.stderr);(out/'probe-status.json').write_text(json.dumps({'returncode':r.returncode})+'\n',encoding='utf-8')
 need(r.returncode==0,'probe failed: '+repr((r.returncode,r.stderr[:1000],r.stdout[-1000:])))
 lines=r.stdout.decode('ascii').splitlines();need(bool(lines) and lines[0]=='READY\tOPENPOKER_EXACT_BINARY64_V1','protocol mismatch');lines=lines[1:];need(len(lines)==len(cases),'response count mismatch')
 for i,((n,d),line) in enumerate(zip(cases,lines)):
  try:
   f=float(Fraction(n,d));expected='rounded_below_normal' if f==0. or abs(f)<small else None
  except OverflowError:expected='rounded_overflow';f=None
  fields=line.split('\t')
  if expected:need(fields==['ERR',expected],'wrong error at case '+str(i)+': '+line)
  else:
   bits=struct.unpack('>Q',struct.pack('>d',f))[0];need(len(fields)==5 and fields[0]=='OK' and int(fields[1],16)==bits,'wrong rounding at case '+str(i)+': '+line)
   need(0<int(fields[2])<=65536 and 0<int(fields[3])<=65589,'invalid width receipt at case '+str(i))
 source_after={name:digest(repo/name) for name in expected_sources};need(source_after==source_before and digest(exe)==exe_before and manifest_path.read_bytes()==manifest_raw,'source, manifest or binary changed during review')
 receipt={'status':'passed','cases':len(cases),'seed':328142,'exe_sha256':exe_before,'manifest_sha256':hashlib.sha256(manifest_raw).hexdigest(),'source_sha256':source_before,'source_and_binary_unchanged':True,'scope':'independent Python Fraction rounding oracle; native converter only'}
 if out:
  receipt['saved_sha256']={name:digest(out/name) for name in ('build-manifest.json','probe-input.txt','probe-stdout.txt','probe-stderr.txt','probe-status.json')}
  (out/'receipt.json').write_text(json.dumps(receipt,sort_keys=True,indent=2)+'\n',encoding='utf-8')
 print(json.dumps(receipt,sort_keys=True))
if __name__=='__main__':main()
