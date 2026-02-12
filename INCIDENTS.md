# INCIDENTS

## Incident Log

- 2026-02-11: No production reliability incidents or regressions were observed during this cycle.
  - Validation scope: local quality gate (`make check`) and CLI smoke runs for recursive nested ZIP sanitization and allowlist-by-detected-type behavior.
  - Prevention rules reaffirmed:
    - Treat content-type detection and allowlist behavior as one contract; enforce with mismatch regression tests.
    - Keep recursive nested archive processing bounded by explicit depth and aggregate-byte limits.

- 2026-02-09: No production reliability incidents or regressions were observed during this cycle.
  - Validation scope: local quality gate (`make check`) and CLI smoke runs for ZIP normal mode, strict dry-run mode, and nested-archive copy policy.
  - Prevention rules reaffirmed:
    - Keep ZIP guardrail checks before decompression whenever possible.
    - Maintain deterministic warning/report ordering to reduce CI noise and aid triage.
    - Require regression tests for every new safety control and CLI policy flag.

### 2026-02-12T20:01:25Z | Codex execution failure
- Date: 2026-02-12T20:01:25Z
- Trigger: Codex execution failure
- Impact: Repo session did not complete cleanly
- Root Cause: codex exec returned a non-zero status
- Fix: Captured failure logs and kept repository in a recoverable state
- Prevention Rule: Re-run with same pass context and inspect pass log before retrying
- Evidence: pass_log=logs/20260212-101456-file-sanitizer-cycle-2.log
- Commit: pending
- Confidence: medium

### 2026-02-12T20:04:54Z | Codex execution failure
- Date: 2026-02-12T20:04:54Z
- Trigger: Codex execution failure
- Impact: Repo session did not complete cleanly
- Root Cause: codex exec returned a non-zero status
- Fix: Captured failure logs and kept repository in a recoverable state
- Prevention Rule: Re-run with same pass context and inspect pass log before retrying
- Evidence: pass_log=logs/20260212-101456-file-sanitizer-cycle-3.log
- Commit: pending
- Confidence: medium

### 2026-02-12T20:08:23Z | Codex execution failure
- Date: 2026-02-12T20:08:23Z
- Trigger: Codex execution failure
- Impact: Repo session did not complete cleanly
- Root Cause: codex exec returned a non-zero status
- Fix: Captured failure logs and kept repository in a recoverable state
- Prevention Rule: Re-run with same pass context and inspect pass log before retrying
- Evidence: pass_log=logs/20260212-101456-file-sanitizer-cycle-4.log
- Commit: pending
- Confidence: medium

### 2026-02-12T20:11:50Z | Codex execution failure
- Date: 2026-02-12T20:11:50Z
- Trigger: Codex execution failure
- Impact: Repo session did not complete cleanly
- Root Cause: codex exec returned a non-zero status
- Fix: Captured failure logs and kept repository in a recoverable state
- Prevention Rule: Re-run with same pass context and inspect pass log before retrying
- Evidence: pass_log=logs/20260212-101456-file-sanitizer-cycle-5.log
- Commit: pending
- Confidence: medium

### 2026-02-12T20:15:20Z | Codex execution failure
- Date: 2026-02-12T20:15:20Z
- Trigger: Codex execution failure
- Impact: Repo session did not complete cleanly
- Root Cause: codex exec returned a non-zero status
- Fix: Captured failure logs and kept repository in a recoverable state
- Prevention Rule: Re-run with same pass context and inspect pass log before retrying
- Evidence: pass_log=logs/20260212-101456-file-sanitizer-cycle-6.log
- Commit: pending
- Confidence: medium

### 2026-02-12T20:18:49Z | Codex execution failure
- Date: 2026-02-12T20:18:49Z
- Trigger: Codex execution failure
- Impact: Repo session did not complete cleanly
- Root Cause: codex exec returned a non-zero status
- Fix: Captured failure logs and kept repository in a recoverable state
- Prevention Rule: Re-run with same pass context and inspect pass log before retrying
- Evidence: pass_log=logs/20260212-101456-file-sanitizer-cycle-7.log
- Commit: pending
- Confidence: medium

### 2026-02-12T20:22:16Z | Codex execution failure
- Date: 2026-02-12T20:22:16Z
- Trigger: Codex execution failure
- Impact: Repo session did not complete cleanly
- Root Cause: codex exec returned a non-zero status
- Fix: Captured failure logs and kept repository in a recoverable state
- Prevention Rule: Re-run with same pass context and inspect pass log before retrying
- Evidence: pass_log=logs/20260212-101456-file-sanitizer-cycle-8.log
- Commit: pending
- Confidence: medium

### 2026-02-12T20:25:46Z | Codex execution failure
- Date: 2026-02-12T20:25:46Z
- Trigger: Codex execution failure
- Impact: Repo session did not complete cleanly
- Root Cause: codex exec returned a non-zero status
- Fix: Captured failure logs and kept repository in a recoverable state
- Prevention Rule: Re-run with same pass context and inspect pass log before retrying
- Evidence: pass_log=logs/20260212-101456-file-sanitizer-cycle-9.log
- Commit: pending
- Confidence: medium

### 2026-02-12T20:29:24Z | Codex execution failure
- Date: 2026-02-12T20:29:24Z
- Trigger: Codex execution failure
- Impact: Repo session did not complete cleanly
- Root Cause: codex exec returned a non-zero status
- Fix: Captured failure logs and kept repository in a recoverable state
- Prevention Rule: Re-run with same pass context and inspect pass log before retrying
- Evidence: pass_log=logs/20260212-101456-file-sanitizer-cycle-10.log
- Commit: pending
- Confidence: medium
