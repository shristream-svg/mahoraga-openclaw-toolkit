import importlib.util, json
from pathlib import Path
p=Path(__file__).parent/'mahoraga-execution/review_recovery.py'
s=importlib.util.spec_from_file_location('review_recovery',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
base=dict(goal_status='paused',pause_at=100,pause_actor='machine',attempts=0,interruption='process_exit',scoped_operator_authority=True,same_goal=True,idle_builtin_local=True,recoverable_history=True,effects_reconciled=True,runtime_healthy=True,now=200,next_retry_at=150)
cases=[
 ('eligible proven machine interruption',{},'native-operator-resume-eligible'),
 ('newer user stop wins',dict(pause_actor='user',explicit_user_resume_at=99),'preserve-pause'),
 ('unknown pause not resumed',dict(pause_actor=None),'preserve-pause'),
 ('missing pause provenance rejected',dict(pause_at=None,pause_actor=None),'preserve-pause'),
 ('new explicit user resume may revoke pause',dict(pause_actor='user',explicit_user_resume_at=101),'native-operator-resume-eligible'),
 ('ambiguous effect not replayed',dict(effects_reconciled=False),'reconcile-before-resume'),
 ('missing history not guessed',dict(recoverable_history=False),'reconcile-before-resume'),
 ('other goal not resumed',dict(same_goal=False),'reconcile-before-resume'),
 ('busy native run not duplicated',dict(idle_builtin_local=False),'reconcile-before-resume'),
 ('completed remains idle',dict(goal_status='complete'),'idle-complete'),
 ('active uses native continuation',dict(goal_status='active'),'native-continuation-only'),
 ('provider timing respected',dict(now=149),'wait-backoff'),
 ('bounded recovery attempts',dict(attempts=3),'recovery-budget-exhausted'),
 ('identical failures need a new strategy',dict(identical_attempts=2),'change-strategy-before-resume'),
 ('unknown failure diagnosed',dict(interruption='unknown'),'diagnose-before-resume'),
 ('budget limit not bypassed',dict(goal_status='budget_limited'),'wait-external-gate')]
for name,delta,expected in cases:
    got=m.review(base|delta);assert got==expected,(name,got,expected)
result={'passed':len(cases),'scope':'pure advisory decision logic only; not a live OpenClaw restart/overnight test','cases':[c[0] for c in cases]}
(Path(__file__).parent/'recovery-test-result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result))
