# Linux MCP Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Install and run both official Baidu MCP routes on headless Linux with permission-restricted private credentials.
**Architecture:** Explicit Linux settings/credential backend reused by existing launchers; pinned upstream and bridge in a separate Linux runtime. Preserve Windows backend.
**Tech Stack:** Python 3.12 stdlib, Node, unittest/node:test, optional official MCP environment.
**Spec:** `docs/superpowers/specs/2026-11-06-linux-support-design.md`

## Global Constraints

- Credential directories 0700, files 0600, private paths outside source; plaintext-at-rest explicitly documented.
- No DPAPI migration/decryption, cloud writes, or user credential values in command arguments/logs.
- Preserve Windows helpers, upload conflict protection, pinned upstream source and no request replay.
- Actual authentication requires user handoff after implementation/preparation.

## Review Focus

- Bad owner/modes/symlink/expiry must prevent token use (Task 1).
- Two launchers refreshing concurrently must not rotate twice or lose pending credentials (Task 1).
- Expired token must stop new calls even during backoff (Task 2).
- Installer must preserve unknown/historical files and avoid worktree paths (Task 3).
- Errors and both streams must hide tokens and credential URLs (Task 1/2).

### Task 1: Linux settings, credentials and refresh

**Files:** Create `scripts/linux_config.py`, `linux_authorization.py`, `credential-helper.py`, `tests/test_linux_authorization.py`.
**Interfaces:** `load_settings(path)`, `read_private_json(path, root)`, `save_private_json`, `ensure_authorization(settings, force=False)`, helper CLI settings/ensure/token/save with captured output and hidden entry.
- [ ] Write unittest cases for permissions, path containment, expiry, ownership, atomic saves, fake refresh transport, pending recovery and roots.
- [ ] Run new tests: expect missing-module failure.
- [ ] Implement Linux backend with flock, bounded HTTPS refresh and restrictive atomic persistence.
- [ ] Run unittest discovery: expect new tests pass and existing behavior preserved; commit.

### Task 2: Cross-platform launcher integration

**Files:** Modify `scripts/start-local.py`, `authorization.py`, `start-remote.mjs`, `remote-worker.mjs`; create `scripts/platform-config.mjs`, tests for helpers/providers and remote expiry.
**Interfaces:** settings choose Linux helper explicitly; helper commands never put secrets in argv. Existing Windows commands unchanged.
- [ ] Write tests for Linux provider lease/reload/expiry and Node fake-helper selection/failed authorization.
- [ ] Run tests: expect backend selection failure.
- [ ] Add backend dispatch, expiry-aware leases and request gating; preserve relay and overwrite policy.
- [ ] Run Python and Node suites plus syntax checks: expect pass; commit.

### Task 3: Installer, docs and staged host deployment

**Files:** Create `scripts/install-linux.py`, `tests/test_linux_install.py`, `docs/setup-linux.md`, `.zh-CN.md`, English README with zh-CN counterpart.
**Interfaces:** Installer explicit roots/env/TOML precedence, prepare-only and skip-registration modes, pinned source verification, stable deployed commands, no credential replacement.
- [ ] Write temp-root tests for repeated preparation, source/symlink rejection and stable launch settings.
- [ ] Run tests: expect missing installer failure.
- [ ] Implement installer and synchronized docs; run full suites and syntax checks.
- [ ] Independently review branch and fix important findings; push PR, honor checks, merge under standing authorization and verify merged code.
- [ ] Prepare canonical host deployment without credentials; register only after dependency/launcher checks. If credentials are absent, hand off hidden authorization entry and clearly report authenticated checks pending.
