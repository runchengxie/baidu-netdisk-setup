# Linux Original-Application Authorization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore a usable path to original-app automatic refresh on Linux while preserving experience access.
**Architecture:** Isolated private profile, hidden authorization-code exchange and pending recovery; alternate settings selected consistently across the existing launchers/checker.
**Tech Stack:** Python 3.12 stdlib, existing Node relay, unittest/node:test.
**Spec:** `docs/superpowers/specs/2026-11-06-linux-app-authorization-design.md`

## Global Constraints

- No DPAPI decryption, active default change, cloud writes or credentials in arguments/logs.
- Owner-only private files, existing refresh lock, bounded one-attempt HTTPS exchange.
- New authorization requires matching SecretKey and fresh code entered locally by the owner.

## Review Focus

- Missing refresh/scope and malformed code responses must never publish credentials (Task 1).
- Failed two-file publication must retain complete pending recovery (Task 1).
- Explicit replacement and pending state must not bypass shared locks (Task 1).
- Alternate settings must reach both workers/helpers without changing defaults (Task 2).
- CLI errors and OAuth responses must not reveal codes or secrets (Task 1/2).

### Task 1: Isolated profile and authorization-code exchange

**Files:** Create `scripts/linux_app_authorization.py`, `tests/test_linux_app_authorization.py`; modify `linux_authorization.py`, `credential-helper.py`, installer FILES.
**Interfaces:** `prepare_app_profile(settings, app_key)`, `authorization_url(app_key,state)`, `exchange_app_authorization(settings,secret,code,request=None,replace=False)`, `recover_app_authorization(settings,replace=False)`. CLI prepare-app/authorize-app/recover-app with hidden entry and non-secret profile selection.
- [ ] Write tests for isolation, exact request fields, response validation, one attempt, private pending publication/recovery and unchanged current files.
- [ ] Run new tests: expect missing module; implement minimal backend and CLI.
- [ ] Run new and existing unittest suites: expect pass; commit.

### Task 2: Selected-profile launchers and docs

**Files:** Modify `start-local.py`, `platform-config.mjs`, `check-mcp.py`; extend Node/Python fixture launcher tests; update English/zh-CN Linux docs and README scope.
**Interfaces:** non-secret `BAIDU_MCP_SETTINGS_FILE` selects one private profile end-to-end; default remains settings.json.
- [ ] Add fixture tests showing a candidate profile reaches the worker and different authorization without touching default files.
- [ ] Run tests: expect wrong default selection; implement selection propagation.
- [ ] Document code/OOB flow, pending recovery, actual verification limits and historical sharing distinction.
- [ ] Run full Python/Node suites, syntax and diff checks; independent review; fix important findings with reproductions.
- [ ] Push PR, validate current target, merge/verify/clean up under standing authorization; deploy stable source and prepare candidate profile. Retain private migration evidence; owner handoff for hidden credentials precedes live read/refresh verification.
