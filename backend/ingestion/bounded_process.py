"""Bound both child pipes and deadline through process exit. No parser imports."""
import os,selectors,subprocess,time


def run_child(command, *, wall_seconds=10, pipe_cap=65536):
    start=time.monotonic();deadline=start+wall_seconds
    out={'stdout':bytearray(),'stderr':bytearray()};reason=None;rc=None
    # Parser children receive a minimal environment, never hosting/DB/auth/model secrets.
    child_env={k:os.environ[k] for k in ('PATH','LANG','LC_ALL','TZ','TMPDIR') if k in os.environ}
    child_env['PYTHONNOUSERSITE']='1'
    process=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=child_env)
    selector=None
    try:
        selector=selectors.DefaultSelector()
        selector.register(process.stdout,selectors.EVENT_READ,'stdout')
        selector.register(process.stderr,selectors.EVENT_READ,'stderr')
        while selector.get_map() or process.poll() is None:
            remaining=deadline-time.monotonic()
            if remaining<=0:
                reason='wall_timeout';break
            for key,_ in selector.select(timeout=min(0.05,remaining)):
                data=os.read(key.fileobj.fileno(),4096)
                if not data:
                    selector.unregister(key.fileobj);continue
                field=key.data
                if len(out[field])+len(data)>pipe_cap:
                    reason=field+'_cap';break
                out[field].extend(data)
            if reason:break
            if not selector.get_map() and process.poll() is None:
                time.sleep(min(0.01,max(0,deadline-time.monotonic())))
        if reason and process.poll() is None:process.kill()
        remaining=max(0,deadline-time.monotonic())
        try:rc=process.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            reason=reason or 'wall_timeout'
            process.kill();rc=process.wait()
    except BaseException:
        if process.poll() is None:process.kill()
        process.wait()
        raise
    finally:
        if process.poll() is None:
            process.kill();process.wait()
        if selector is not None:selector.close()
        process.stdout.close();process.stderr.close()
    meta={'exit_code':rc,'kill_reason':reason,'reaped':process.poll() is not None,
          'duration_seconds':round(time.monotonic()-start,3),'stdout_bytes':len(out['stdout']),
          'stderr_bytes':len(out['stderr']),'each_pipe_cap':pipe_cap,'wall_seconds':wall_seconds}
    return meta,{k:bytes(v) for k,v in out.items()}
