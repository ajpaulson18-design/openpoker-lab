"""Exclusive evidence directories and bounded child observation; no auto-retry."""
from pathlib import Path
import hashlib,json,subprocess,threading,time,os


def _json_exclusive(path,value,cap=65536):
    raw=(json.dumps(value,sort_keys=True,indent=2)+'\n').encode('utf-8')
    if len(raw)>cap:raise ValueError('control receipt byte bound')
    with path.open('xb') as output:output.write(raw)


class RunClaim:
    """An existing output directory always blocks acquisition, even after failure."""
    def __init__(self,directory,head):
        if type(head) is not str or len(head) not in (40,64) or any(c not in '0123456789abcdef' for c in head):
            raise ValueError('claim needs a committed source identity')
        self.directory=Path(directory)
        self.directory.mkdir(parents=True,exist_ok=False)
        _json_exclusive(self.directory/'claim.json',{'version':'virtual-frozen-run-claim-v1','head':head,'controller_pid':os.getpid(),'claim_epoch_seconds':time.time(),'scope':'single immutable attempt; no automatic retry; PID metadata is not proof of liveness'})
        self._closed=False
    def finish(self,status,receipt):
        if self._closed:raise ValueError('run claim already consumed')
        self._closed=True
        if status not in ('complete','failed'):raise ValueError('invalid terminal claim status')
        _json_exclusive(self.directory/'terminal.json',{'status':status,'receipt':receipt})


def run_bounded_child(command,request,directory,*,stdout_limit,stderr_limit=65536,timeout=300):
    """Save request first; stream bounded logs, observe actual exit, never retry.

    This is process observation only. Success does not validate a response,
    authenticate code, or imply numerical acceptance.
    """
    if (type(command) is not list or not 1<=len(command)<=64 or
            any(type(a) is not str or not a or len(a)>4096 for a in command)):
        raise ValueError('bounded child command')
    if type(request) is not bytes or len(request)>1025:raise ValueError('bounded child request')
    if (type(stdout_limit) is not int or not 0<stdout_limit<=2135476 or
            type(stderr_limit) is not int or not 0<stderr_limit<=65536 or
            type(timeout) not in (int,float) or not 0<timeout<=300):
        raise ValueError('reduce-only child bounds')
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=False)
    with (directory/'request.bin').open('xb') as output:output.write(request)
    stdout=(directory/'stdout.bin').open('xb');stderr=(directory/'stderr.bin').open('xb')
    records=[{'observed_bytes':0,'saved_bytes':0,'sha256':hashlib.sha256()},
             {'observed_bytes':0,'saved_bytes':0,'sha256':hashlib.sha256()}]
    failures=[];process=None;started=time.perf_counter();returncode=None;timed_out=False
    def stop():
        if process is not None and process.poll() is None:
            try:process.kill()
            except ProcessLookupError:pass
    def drain(pipe,output,index,limit):
        try:
            while True:
                chunk=pipe.read(65536)
                if not chunk:break
                record=records[index];record['observed_bytes']+=len(chunk)
                kept=chunk[:max(0,limit-record['saved_bytes'])]
                output.write(kept);record['sha256'].update(kept);record['saved_bytes']+=len(kept)
                if len(kept)!=len(chunk):
                    failures.append('stdout_limit' if index==0 else 'stderr_limit');stop();break
        except BaseException as error:
            failures.append(type(error).__name__);stop()
        finally:
            pipe.close();output.close()
    with (directory/'request.bin').open('rb') as input_file:
        try:
            process=subprocess.Popen(command,stdin=input_file,stdout=subprocess.PIPE,stderr=subprocess.PIPE,shell=False)
        except BaseException as error:
            stdout.close();stderr.close();failures.append('launch_'+type(error).__name__)
        else:
            readers=[threading.Thread(target=drain,args=(process.stdout,stdout,0,stdout_limit)),
                     threading.Thread(target=drain,args=(process.stderr,stderr,1,stderr_limit))]
            for reader in readers:reader.start()
            try:returncode=process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out=True;stop();returncode=process.wait()
            finally:
                if process.poll() is None:stop();returncode=process.wait()
                for reader in readers:reader.join()
    for record in records:record['sha256']=record['sha256'].hexdigest()
    status=('launch_error' if process is None else 'timeout' if timed_out else
            'stream_failure' if failures else 'exited')
    receipt={'version':'bounded-child-observation-v1','status':status,'returncode':returncode,
             'actual_exit_observed':process is not None and process.poll() is not None,
             'duration_seconds':time.perf_counter()-started,'streams':records,'failures':failures,
             'request_sha256':hashlib.sha256(request).hexdigest(),'automatic_retries':0}
    _json_exclusive(directory/'process.json',receipt)
    return receipt
