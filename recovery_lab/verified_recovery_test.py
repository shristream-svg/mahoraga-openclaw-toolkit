"""Actual isolated HTTP/process/crash fixtures; never controls OpenClaw/real apps.
Run with existing Python3.12. Workers write only within this script's fixtures/.
"""
import argparse,ast,collections,hashlib,http.server,json,os,queue,shutil,socket,subprocess,sys,tempfile,threading,time,traceback,urllib.request,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parent
FIXTURES=ROOT/'fixtures'
TOTAL=5

def digest(data):return hashlib.sha256(data).hexdigest()
def durable_json(path,data):
    temp=path.with_name(path.name+f'.pending-{os.getpid()}')
    with temp.open('x',encoding='utf-8') as f:json.dump(data,f);f.flush();os.fsync(f.fileno())
    os.replace(temp,path)
def append(path,data):
    with path.open('a',encoding='utf-8') as f:f.write(json.dumps(data)+'\n');f.flush();os.fsync(f.fileno())
def payload(root,i):return f"synthetic-c22:{(root/'fixture-id.txt').read_text().strip()}:unit:{i}\n".encode()
def read_log(path):return [json.loads(line) for line in path.read_text().splitlines() if line.strip()] if path.exists() else []
def assert_exact_units(units):
    if units!=list(range(1,TOTAL+1)):raise AssertionError('Duplicate, missing or out-of-order unit effects')
def validate_unit_index(step):
    if type(step) is not int or not 1<=step<=TOTAL:raise AssertionError('Checkpoint exceeds configured units')
def validate_checkpoint(cp):
    validate_unit_index(cp['step'])
    if cp['total']!=TOTAL or cp['status'] not in ('in_progress','completed','done'):raise AssertionError('Invalid checkpoint state')
    if type(cp['completedThrough']) is not int or not 0<=cp['completedThrough']<=TOTAL:raise AssertionError('Invalid completed-through checkpoint')
    if cp['status']=='done' and (cp['step']!=TOTAL or cp['completedThrough']!=TOTAL):raise AssertionError('Incomplete done checkpoint')

def effect_worker(root,pause_after_effect=False):
    completed_hint=0
    if (root/'checkpoint.json').exists():
        checkpoint=json.loads((root/'checkpoint.json').read_text());validate_checkpoint(checkpoint)
        completed_hint=checkpoint['completedThrough']
    records=read_log(root/'effects.jsonl')
    counts=collections.Counter(r['unit'] for r in records)
    if any(n!=1 for n in counts.values()):raise AssertionError('Duplicate receipt before resume')
    skipped=[]
    # A completed checkpoint is a hint, not authority to ignore target readback.
    # Verify acknowledged units without restarting them or moving the cursor back.
    for i in range(1,completed_hint+1):
        file=root/f'unit-{i}.bin';expected=payload(root,i)
        previous=next((r for r in records if r['unit']==i),None)
        if not file.exists() or file.read_bytes()!=expected or not previous or previous['sha256']!=digest(expected):
            raise AssertionError('Completed checkpoint cannot be reconciled; refusing replay')
        skipped.append(i)
    for i in range(completed_hint+1,TOTAL+1):
        file=root/f'unit-{i}.bin';expected=payload(root,i);sha=digest(expected)
        durable_json(root/'checkpoint.json',{'step':i,'completedThrough':i-1,'status':'in_progress','total':TOTAL})
        if file.exists():
            if file.read_bytes()!=expected:raise AssertionError('Existing effect hash mismatch; refusing overwrite/replay')
            skipped.append(i);disposition='reconciled'
        else:
            with file.open('xb') as f:f.write(expected);f.flush();os.fsync(f.fileno())
            disposition='created'
        previous=next((r for r in records if r['unit']==i),None)
        if previous:
            if previous['sha256']!=sha:raise AssertionError('Receipt hash mismatch')
        else:
            record={'unit':i,'sha256':sha,'disposition':disposition}
            append(root/'effects.jsonl',record);records.append(record)
        if pause_after_effect and i==3:
            print(json.dumps({'event':'effect3-before-checkpoint','pid':os.getpid()}),flush=True)
            # Bounded even if the parent dies; no later effects during this pause.
            time.sleep(30)
            raise RuntimeError('Test parent did not terminate the owned worker')
        durable_json(root/'checkpoint.json',{'step':i,'completedThrough':i,'status':'completed','total':TOTAL})
    durable_json(root/'checkpoint.json',{'step':TOTAL,'completedThrough':TOTAL,'status':'done','total':TOTAL})
    print(json.dumps({'event':'finished','skippedExisting':skipped}),flush=True)

def child_main(mode,root):
    root=root.resolve()
    if not root.is_relative_to(FIXTURES.resolve()) or not root.is_dir():raise SystemExit('Refusing worker path outside owned fixtures')
    if mode in ('effect-pause','effect-resume'):effect_worker(root,mode=='effect-pause')
    elif mode=='heartbeat':
        print(json.dumps({'event':'heartbeat-ready','pid':os.getpid()}),flush=True)
        deadline=time.monotonic()+30;n=0
        while time.monotonic()<deadline:
            n+=1;append(root/'heartbeat.jsonl',{'tick':n});time.sleep(.025)
    elif mode=='negative-old':
        source=(ROOT/'old_recovery_snapshot.py').read_text(encoding='utf-8-sig')
        tree=ast.parse(source);changed=0
        for node in tree.body:
            if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='CHECKPOINT_DIR' for t in node.targets):
                node.value=ast.Call(func=ast.Name(id='Path',ctx=ast.Load()),args=[ast.Constant(str(root))],keywords=[]);changed+=1
        if changed!=1 or 'write_checkpoint(7' not in source:raise AssertionError('Unexpected old baseline; review before executing')
        exec(compile(ast.fix_missing_locations(tree),str(ROOT/'old_recovery_snapshot.py'),'exec'),{'__name__':'__main__','__file__':str(ROOT/'old_recovery_snapshot.py')})

def spawn(mode,root):
    return subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'--worker',mode,'--root',str(root)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8',cwd=str(ROOT),creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
def wait_line(child,seconds=5):
    lines=queue.Queue()
    def reader():
        try:lines.put(child.stdout.readline())
        except Exception as e:lines.put(e)
    threading.Thread(target=reader,daemon=True).start()
    result=lines.get(timeout=seconds)
    if not isinstance(result,str) or not result.strip():raise AssertionError('Owned child did not reach expected event')
    return json.loads(result)
def stop_owned(child,kill=False):
    if child.poll() is None:
        (child.kill if kill else child.terminate)()
    child.wait(timeout=5)
def fixture(parent,name):
    p=parent/name;p.mkdir();(p/'fixture-id.txt').write_text(uuid.uuid4().hex);return p
def check_effects(root):
    units=sorted(int(p.stem.split('-')[1]) for p in root.glob('unit-*.bin'))
    if units!=list(range(1,TOTAL+1)):raise AssertionError('Wrong completed effect set')
    receipts=read_log(root/'effects.jsonl')
    assert_exact_units([r['unit'] for r in receipts])
    for i in units:
        expected=payload(root,i)
        if (root/f'unit-{i}.bin').read_bytes()!=expected:raise AssertionError('Independent content mismatch')
        if next(r for r in receipts if r['unit']==i)['sha256']!=digest(expected):raise AssertionError('Independent hash mismatch')
    cp=json.loads((root/'checkpoint.json').read_text());validate_checkpoint(cp)
    if cp['status']!='done':raise AssertionError('Not completed')
    return {'units':units,'effectLogCounts':dict(collections.Counter(r['unit'] for r in receipts)),'checkpoint':cp,'hashes':{str(i):digest((root/f'unit-{i}.bin').read_bytes()) for i in units}}

def stalled_http_test():
    accepted=threading.Event();release=threading.Event()
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):accepted.set();release.wait(2)
        def log_message(self,*args):pass
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler);server.daemon_threads=True
    thread=threading.Thread(target=lambda:server.serve_forever(poll_interval=.01),daemon=True);thread.start()
    start=time.monotonic();timed_out=False
    try:
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(f'http://127.0.0.1:{server.server_port}/stalled-model-fixture',timeout=.2):pass
        except (TimeoutError,socket.timeout):timed_out=True
        elapsed=time.monotonic()-start
        assert accepted.is_set() and timed_out and .12<=elapsed<1.5,(accepted.is_set(),timed_out,elapsed)
        return {'passed':True,'requestAccepted':True,'clientTimedOut':True,'configuredTimeoutSeconds':.2,'elapsedSeconds':round(elapsed,4),'scope':'actual localhost HTTP request stall, not a real model/provider outage'}
    finally:release.set();server.shutdown();server.server_close();thread.join(timeout=2)

def cancel_child_test(root):
    child=spawn('heartbeat',root)
    try:
        event=wait_line(child);assert event['event']=='heartbeat-ready' and event['pid']==child.pid
        end=time.monotonic()+3
        while not (root/'heartbeat.jsonl').exists() and time.monotonic()<end:time.sleep(.01)
        assert (root/'heartbeat.jsonl').exists()
        stop_owned(child);assert child.returncode!=0
        before=(root/'heartbeat.jsonl').read_bytes();assert read_log(root/'heartbeat.jsonl')
        time.sleep(.12);assert (root/'heartbeat.jsonl').read_bytes()==before
        return {'passed':True,'ownedPid':child.pid,'exitCode':child.returncode,'actualTerminateCalled':True,'workTicksBeforeStop':len(read_log(root/'heartbeat.jsonl')),'noPostExitWrites':True}
    finally:stop_owned(child,kill=True)

def crash_resume_test(root):
    child=spawn('effect-pause',root)
    try:
        event=wait_line(child);assert event['event']=='effect3-before-checkpoint' and event['pid']==child.pid
        cp=json.loads((root/'checkpoint.json').read_text());assert cp=={'step':3,'completedThrough':2,'status':'in_progress','total':5}
        assert [r['unit'] for r in read_log(root/'effects.jsonl')]==[1,2,3]
        before={i:{'hash':digest((root/f'unit-{i}.bin').read_bytes()),'mtime':(root/f'unit-{i}.bin').stat().st_mtime_ns,'size':(root/f'unit-{i}.bin').stat().st_size} for i in (1,2,3)}
        assert (root/'unit-3.bin').read_bytes()==payload(root,3)
        stop_owned(child,kill=True);assert child.returncode!=0
        assert json.loads((root/'checkpoint.json').read_text())==cp
    finally:stop_owned(child,kill=True)
    resumed=spawn('effect-resume',root)
    try:
        stdout,stderr=resumed.communicate(timeout=8)
        assert resumed.returncode==0,(stdout,stderr)
        report=json.loads(stdout.strip());assert report['skippedExisting']==[1,2,3]
    finally:stop_owned(resumed,kill=True)
    independent=check_effects(root)
    for i,state in before.items():
        f=root/f'unit-{i}.bin';assert {'hash':digest(f.read_bytes()),'mtime':f.stat().st_mtime_ns,'size':f.stat().st_size}==state
    # A duplicate receipt and out-of-range checkpoint must be rejected, not called complete.
    oldlog=(root/'effects.jsonl').read_bytes();append(root/'effects.jsonl',read_log(root/'effects.jsonl')[0])
    try:check_effects(root)
    except AssertionError:duplicate_rejected=True
    else:raise AssertionError('Duplicate-effect negative control falsely passed')
    (root/'effects.jsonl').write_bytes(oldlog)
    try:validate_checkpoint({'step':7,'completedThrough':7,'total':5,'status':'done'})
    except AssertionError:out_of_range_rejected=True
    else:raise AssertionError('Checkpoint7 negative control falsely passed')
    return {'passed':True,'killedOwnedPid':child.pid,'killedExitCode':child.returncode,'crashWindow':cp,'effect3DurableBeforeCheckpoint':True,'resumeSkippedExisting':[1,2,3],'preexistingHashesSizesAndMtimesPreserved':True,'duplicateReceiptRejected':duplicate_rejected,'checkpoint7Rejected':out_of_range_rejected,**independent}

def old_pattern_negative_test(root):
    child=spawn('negative-old',root)
    try:
        stdout,stderr=child.communicate(timeout=18);assert child.returncode==0,(stdout,stderr)
    finally:stop_owned(child,kill=True)
    (root/'old-stdout.txt').write_text(stdout);(root/'old-stderr.txt').write_text(stderr)
    work=json.loads((root/'work-log.json').read_text());counts=dict(collections.Counter(r['step'] for r in work));cp=json.loads((root/'checkpoint.json').read_text())
    assert counts=={1:2,2:2,3:2,4:1,5:1},counts
    assert cp['step']==7 and cp['status']=='cancelled'
    assert 'All C22 recovery tests PASSED' in stdout
    try:assert_exact_units([r['step'] for r in work])
    except AssertionError:duplicates_rejected=True
    else:raise AssertionError('Old duplicate work falsely accepted')
    try:validate_unit_index(cp['step'])
    except AssertionError:checkpoint_rejected=True
    else:raise AssertionError('Old checkpoint7 falsely accepted')
    return {'passed':True,'originalPrintedPass':True,'independentVerifierRejectedOriginal':duplicates_rejected and checkpoint_rejected,'observedDuplicateCounts':counts,'observedInvalidFinalCheckpoint':cp['step'],'scope':'reviewed old source executed only after its sole fixed checkpoint directory was rewritten to this fresh isolated fixture'}

def policy_test(run):
    policy=run/'policy';(policy/'mahoraga-execution').mkdir(parents=True)
    shutil.copyfile(ROOT/'policy/test_recovery.py',policy/'test_recovery.py')
    shutil.copyfile(ROOT/'policy/mahoraga-execution/review_recovery.py',policy/'mahoraga-execution/review_recovery.py')
    child=subprocess.run([sys.executable,str(policy/'test_recovery.py')],cwd=str(policy),capture_output=True,text=True,timeout=5,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    assert child.returncode==0,(child.stdout,child.stderr)
    result=json.loads((policy/'recovery-test-result.json').read_text());assert result['passed']==16
    return {'passed':True,'casesPassed':16,'cases':result['cases'],'scope':'pure advisory policy fixtures; no actual OpenClaw resume or user-pause event replay'}

def main():
    FIXTURES.mkdir(exist_ok=True);run=Path(tempfile.mkdtemp(prefix='run-',dir=FIXTURES));results={}
    report={'passed':False,'asOfUnix':time.time(),'fixture':str(run),'scope':'Isolated localhost transport, owned subprocess termination and idempotent synthetic-file recovery. NOT full OpenClaw/model outage, gateway restart, overnight reliability, arbitrary exactly-once business mutations or full P6 completion.','checks':results}
    try:
        results['stalledHttp']=stalled_http_test()
        results['actualChildCancellation']=cancel_child_test(fixture(run,'cancel'))
        results['killAfterEffectBeforeCheckpoint']=crash_resume_test(fixture(run,'crash-resume'))
        results['originalFalsePassNegativeControl']=old_pattern_negative_test(fixture(run,'old-negative'))
        results['userPausePolicy']=policy_test(run)
        report['passed']=True
    except Exception as e:report['error']=type(e).__name__+': '+str(e);report['traceback']=traceback.format_exc()
    report['sourceSha256']=digest(Path(__file__).read_bytes());report['oldSnapshotSha256']=digest((ROOT/'old_recovery_snapshot.py').read_bytes())
    durable_json(run/'result.json',report);durable_json(ROOT/'latest-result.json',report)
    print(json.dumps({'passed':report['passed'],'fixture':str(run),'checks':{k:v.get('passed') for k,v in results.items()},'error':report.get('error')}))
    raise SystemExit(0 if report['passed'] else 1)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--worker',choices=['effect-pause','effect-resume','heartbeat','negative-old']);p.add_argument('--root',type=Path);args=p.parse_args()
    if args.worker:child_main(args.worker,args.root)
    else:main()
