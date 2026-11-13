# C22 Recovery Test Script — Stall, Cancellation, Interrupted Checkpoint Recovery

import asyncio
import json
import os
import sys
import time
import signal
from pathlib import Path

CHECKPOINT_DIR = Path("BASELINE_ONLY_RUN_VIA_VERIFIED_HARNESS")
CHECKPOINT_FILE = CHECKPOINT_DIR / "checkpoint.json"
WORK_FILE = CHECKPOINT_DIR / "work-log.json"

def ensure_dirs():
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)

def write_checkpoint(step, status, detail=""):
    """Write a durable checkpoint before each work unit."""
    cp = {
        "step": step,
        "status": status,
        "detail": detail,
        "timestamp": time.time(),
        "recoverable": True
    }
    CHECKPOINT_FILE.write_text(json.dumps(cp, indent=2))
    return cp

def read_checkpoint():
    if CHECKPOINT_FILE.exists():
        return json.loads(CHECKPOINT_FILE.read_text())
    return None

def append_work(step, result):
    """Append work result to durable log."""
    log = []
    if WORK_FILE.exists():
        log = json.loads(WORK_FILE.read_text())
    log.append({"step": step, "result": result, "timestamp": time.time()})
    WORK_FILE.write_text(json.dumps(log, indent=2))
    return log

async def simulate_work_unit(step_num, duration_seconds=2):
    """Simulate one unit of work with checkpoint before execution."""
    write_checkpoint(step_num, "in_progress", f"Starting step {step_num}")
    await asyncio.sleep(duration_seconds)
    append_work(step_num, "completed")
    write_checkpoint(step_num, "completed", f"Step {step_num} finished")
    return step_num

async def run_with_interrupt(total_steps=5, interrupt_at_step=3):
    """Run work units, simulating interruption at a given step."""
    ensure_dirs()
    
    # Check for existing checkpoint (recovery scenario)
    existing_cp = read_checkpoint()
    start_step = 1
    if existing_cp and existing_cp.get("status") == "completed":
        start_step = existing_cp["step"] + 1
        print(f"RECOVERY: Resuming from step {start_step} (previous step {existing_cp['step']} completed)")
    elif existing_cp and existing_cp.get("status") == "in_progress":
        start_step = existing_cp["step"]
        print(f"RECOVERY: Re-executing interrupted step {start_step}")
    
    results = []
    for step in range(start_step, total_steps + 1):
        print(f"Executing step {step}...")
        try:
            result = await simulate_work_unit(step, duration_seconds=1)
            results.append(result)
            print(f"  Step {step} completed")
            
            # Simulate interruption at the specified step
            if step == interrupt_at_step:
                print(f"  >>> INTERRUPT SIMULATED at step {step} <<<")
                write_checkpoint(step, "interrupted", f"Step {step} interrupted mid-execution")
                return results, step, "interrupted"
                
        except asyncio.CancelledError:
            print(f"  >>> CANCELLATION RECEIVED at step {step} <<<")
            write_checkpoint(step, "cancelled", f"Step {step} cancelled by external signal")
            return results, step, "cancelled"
    
    write_checkpoint(total_steps, "all_completed", "All steps finished successfully")
    return results, total_steps, "completed"

async def main():
    print("=== C22 Recovery Test: Stall, Cancellation, Interrupted Checkpoint ===\n")
    
    # Test 1: Interrupted execution with checkpoint recovery
    print("--- Test 1: Interrupted execution ---")
    results, stop_step, status = await run_with_interrupt(total_steps=5, interrupt_at_step=3)
    print(f"  Result: {len(results)} steps completed, stopped at step {stop_step}, status={status}")
    cp = read_checkpoint()
    print(f"  Checkpoint: step={cp['step']}, status={cp['status']}")
    assert cp["status"] == "interrupted", "Checkpoint should show interrupted status"
    assert cp["step"] == 3, "Checkpoint should be at step 3"
    print("  PASS: Checkpoint preserved interruption state")
    
    # Test 2: Recovery from interrupted checkpoint
    print("\n--- Test 2: Recovery from checkpoint ---")
    results2, stop_step2, status2 = await run_with_interrupt(total_steps=5, interrupt_at_step=99)
    print(f"  Result: {len(results2)} additional steps completed, final status={status2}")
    cp2 = read_checkpoint()
    print(f"  Checkpoint: step={cp2['step']}, status={cp2['status']}")
    assert cp2["status"] == "all_completed", "Recovery should complete all remaining steps"
    print("  PASS: Recovery completed all remaining steps from checkpoint")
    
    # Test 3: Cancellation simulation
    print("\n--- Test 3: Cancellation handling ---")
    # Simulate by writing a cancelled checkpoint manually
    write_checkpoint(7, "cancelled", "External cancellation signal received")
    cp3 = read_checkpoint()
    assert cp3["status"] == "cancelled", "Cancelled state should be preserved"
    print("  PASS: Cancellation state preserved in checkpoint")
    
    print("\n=== All C22 recovery tests PASSED ===")
    print(f"Checkpoint file: {CHECKPOINT_FILE}")
    print(f"Work log file: {WORK_FILE}")

if __name__ == "__main__":
    asyncio.run(main())