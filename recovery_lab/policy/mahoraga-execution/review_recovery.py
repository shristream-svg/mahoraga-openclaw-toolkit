"""Pure advisory recovery gate. No execution, state mutation, network or resume."""
def review(c):
    if c.get('goal_status') == 'complete':
        return 'idle-complete'
    pause = c.get('pause_at')
    resume = c.get('explicit_user_resume_at', 0)
    if c.get('goal_status') == 'paused' and not pause:
        return 'preserve-pause'
    if pause and (c.get('pause_actor') != 'machine' and resume <= pause):
        return 'preserve-pause'
    if c.get('goal_status') == 'active':
        return 'native-continuation-only'
    if c.get('goal_status') != 'paused':
        return 'wait-external-gate'
    if c.get('attempts', 0) >= 3:
        return 'recovery-budget-exhausted'
    if c.get('identical_attempts', 0) >= 2:
        return 'change-strategy-before-resume'
    if c.get('interruption') not in ('process_exit', 'transient_transport'):
        return 'diagnose-before-resume'
    required = ('scoped_operator_authority', 'same_goal', 'idle_builtin_local',
                'recoverable_history', 'effects_reconciled', 'runtime_healthy')
    if not all(c.get(k) is True for k in required):
        return 'reconcile-before-resume'
    if c.get('now', 0) < c.get('next_retry_at', 0):
        return 'wait-backoff'
    return 'native-operator-resume-eligible'

if __name__ == '__main__':
    import json, sys
    if len(sys.argv) != 2:
        raise SystemExit('Usage: python review_recovery.py checkpoint-input.json (advisory only)')
    with open(sys.argv[1], encoding='utf-8-sig') as f:
        print(json.dumps({'decision': review(json.load(f)), 'sideEffects': False}))
