# C22 reviewed isolated recovery fixtures

Run with the existing Python 3.12 interpreter: `python verified_recovery_test.py`.
Standard library only. Every run creates a fresh `fixtures/run-*` directory and
keeps its receipts/readbacks for review. There are no provider keys, model calls,
Gateway/Goal mutations, native restarts or customer records in the test harness.

What executes:

- A real ephemeral loopback HTTP server accepts a request and deliberately stalls.
  The actual urllib client must time out within a measured bound. This is a
  transport stand-in, not a real model outage.
- An owned child writes heartbeats. The parent actually terminates and joins that
  exact process, then checks that its durable heartbeat bytes stop changing.
- Another owned child creates three deterministic effects and receipts, then
  blocks after effect3 is fsynced but before its completion checkpoint. The parent
  checks the exact crash window and actually kills/joins the child. Resume checks
  completed1–2, reconciles existing3, creates4–5, and independently verifies five
  contents/hashes, exactly-one audit entries, prior mtimes/sizes and checkpoint5.
- Duplicate receipts and checkpoint7 are deliberately injected and must fail the
  verifier. The reviewed old script is also executed against a rewritten fresh
  fixture root: it prints allPASS while producing duplicate effects1–3 and
  checkpoint7; the independent invariants reject that negative control.
- The existing16 advisory user-Pause/provenance cases execute against source
  copies in that run's fresh policy directory. These are policy fixtures, not a
  live operator-Pause event replay or actual OpenClaw resume.

Exactly-once scope is these deterministic exclusive-create files under one owned
worker/controller. Arbitrary external operations, partial writes before the
chosen crash window, concurrent recovery controllers, real provider outages,
Gateway restart/reboot and overnight operation are not established. This does
not complete all of P6 or promote any native recovery controller.

The economical local review route was unavailable; one NVIDIA Lightning request
returned a640-token review. Its incorrect suggestion that step3 artifacts should
be absent was rejected. The actual test requires durable step3 before killing.
No model draft code was executed. `latest-result.json` and the selected run's
result.json contain the actual assertion outcomes and source hashes.

The source bundle includes the same trusted harness/policy plus the old negative
control with its hardcoded native-workspace directory replaced by a harmless
relative placeholder. The harness still rewrites that placeholder to its unique
fixture before running the old algorithm. SOURCE-MANIFEST.json records this
packaging-only path change and the original audited hash.
