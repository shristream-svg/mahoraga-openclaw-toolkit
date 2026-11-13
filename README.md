# MAHORAGA OpenClaw-adjacent utility toolkit

Private-review snapshot of a narrow set of locally developed, agent-assisted utilities. No public license grant or new copyright ownership claim is supplied. Review provenance and licensing before any public redistribution. This package does not include OpenClaw, upstream repository clones, private customer records, credentials, live agent configuration or a second assistant.

## Included

- `mahoraga_toolkit/ptt_capture.py`: explicit-invocation Windows PCM capture and independent WAV readback. Importing it never opens a device. Synthetic providers and a fake Windows driver test empty audio, cancellation, failures, cleanup and overwrite protection. Real microphone compatibility and Hinglish accuracy are unverified; no actual microphone was started by these tests.
- `mahoraga_toolkit/review_recovery.py`: a pure advisory recovery/Pause decision function with sixteen policy scenarios. It cannot resume a Goal or execute a task.
- `mahoraga_toolkit/file_tools.py`: exclusive hash-verified copy, exact CSV totals and local PDF info/merge/text commands. The original live memory-search command and home/workspace memory bindings were removed from this exported copy. It does not read a profile or chat database.
- `recovery_lab/`: reviewed real loopback HTTP timeout and owned-child process/crash fixtures. A five-unit idempotent file workflow is killed after its third durable effect but before its completion checkpoint, then independently reconciled. The old false-pass algorithm runs only in an isolated negative-control directory and must be rejected.

These fixtures establish the stated isolated behaviors. They do not establish real billing/printing/Vault integration, live provider outages, reboot recovery, continuous overnight operation, arbitrary external exactly-once effects or AGI capabilities.

## Requirements and tests

Core modules and tests use Python's standard library. The capture backend is Windows-specific, but synthetic tests do not access hardware. The optional file/PDF subset requires `pypdf`; `requirements-pdf.txt` records the version used for fresh verification. If it is absent, PDF tests report an explicit skip rather than a pass.

Run from this package directory with an existing Python 3.12 interpreter:

```text
python -m unittest discover -s tests -v
python recovery_lab/verified_recovery_test.py
```

The recovery lab creates fresh synthetic `recovery_lab/fixtures/run-*` directories. Those runtime files and receipts are ignored by Git. The harness never contacts a model provider, starts OpenClaw, changes a Goal, reads customer records or uses API keys. Do not run `old_recovery_snapshot.py` as a product: it deliberately preserves a broken algorithm for the verifier's negative control; its original personal directory was replaced by a harmless placeholder.

Example deterministic commands:

```text
python -m mahoraga_toolkit.file_tools copy-verified input.bin copy.bin
python -m mahoraga_toolkit.file_tools csv-total synthetic.csv amount total.json
python -m mahoraga_toolkit.file_tools pdf-merge combined.pdf first.pdf second.pdf
```

Outputs refuse overwrites. Keep private inputs and generated audio/documents outside the repository. Real microphone capture requires an explicit caller invocation; the package installs no listener, wake word, service, scheduler or startup task.

`PROVENANCE.json` records component-relative origins, source hashes and export-only changes without personal machine paths. The live workspace was not modified. No Git commit, remote configuration or push is performed by this package.

Windows capture design references: [Microsoft recording lifecycle](https://learn.microsoft.com/en-us/windows/win32/multimedia/managing-waveform-audio-recording) and [audio data buffers](https://learn.microsoft.com/en-us/windows/win32/multimedia/audio-data-blocks). These are references, not a claim that this code is Microsoft software or that a hardware pilot passed.
