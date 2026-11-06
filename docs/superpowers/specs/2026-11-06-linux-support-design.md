# Linux support for the Baidu Netdisk MCP setup

## Intent and chosen approach

Make this setup usable on the owner's Linux host and on headless Linux installations while preserving Windows behavior. The owner selected permission-restricted private credential files rather than a desktop keyring. A keyring-only approach would introduce a desktop dependency; retaining PowerShell/DPAPI would not make the Windows authorization portable.

This is a Linux port of the existing official MCP launchers and upload protection, not a new cloud synchronization client. No automatic backup, persisted multipart resume or cloud-file reorganization is included.

## Architecture and configuration

Add Python-based platform settings/authorization helpers shared by the Python uploader and Node remote launcher. Retain the Windows helpers and the existing Windows settings format. Select the Linux backend explicitly from installation settings; do not infer a backend from token contents or fall back from failed DPAPI decryption to plaintext.

A Linux installer accepts explicit CODE/DATA/CONFIG roots or a supplied workspace TOML using `tomllib` on Python 3.12+. Prefer explicit command options, then environment roots, then explicitly supplied TOML. Runtime dependencies go under `DATA_ROOT/baidu-netdisk-mcp/runtime/linux`, separate from preserved historical Windows dependencies. Launchers and private settings belong under `CONFIG_ROOT/deployments/baidu-netdisk-mcp`; credentials belong there too, outside all source/worktree directories. Use a stable deployed launcher path when registering MCPs. No compatibility symlinks or references to temporary worktrees.

Download the official uploader at the existing pinned upstream revision and retain the pinned bridge package unless verification proves a compatibility change necessary. Verify an existing checkout before reusing it and never rewrite upstream files. Use Linux `.venv/bin/python` and executable lookup without npm.cmd, Windows creation flags or PowerShell assumptions. Installation is rerunnable without replacing credentials or unrelated configuration. Refuse source-contained or symlinked credential paths and existing runtime/configuration belonging to another installation. Support dependency-only/preparation mode without registering MCPs.

## Credentials and refresh

Linux authorization uses a versioned JSON document with access token, optional refresh token, saved UTC time and positive bounded lifetime. Separate application credentials contain matching AppKey/SecretKey when automatic refresh is desired. These files are plaintext protected by filesystem access, not encrypted or interchangeable with DPAPI files. Directory mode is 0700; credential and private settings files are 0600. On read, require the current owner and reject group/other permission bits, symlinks, malformed data and missing or invalid expiration. Validate parent path permissions through the private deployment root. Do not chmod imported historical files silently.

Provide a hidden interactive credential-entry command; secrets never appear in command-line arguments, shell history, logs or generated registration commands. Fresh Linux authorization is required unless an already designated Linux credential exists. Do not attempt to decrypt old Windows files or search unrelated credential stores. An example documents fields without real values.

Reuse the expiry semantics (refresh within seven days, fail closed at expiry), a shared bounded cross-process refresh lock, atomic same-directory replacement, fsync and restrictive modes. Re-read under lock so two MCPs do not rotate concurrently. Preserve a private pending refreshed credential if final publication fails, block further refresh pending explicit recovery and do not overwrite it. Unknown/expired credentials cannot start either MCP. Missing refresh material can use a currently valid access token with a sanitized warning; it must stop at expiry. Never reuse a token after an authorization change fails validation.

The Node remote relay continues waiting for active requests before reconnecting, without replaying writes. It checks authorization through a platform-neutral helper, observes revision changes and prevents new requests after expiration even between scheduled checks. The local provider reloads under its existing lease lock, checks expiration on every lease and never exposes credential-bearing exceptions. Preserve exact-token and URL/Bearer redaction. No credential in child-process arguments: pass helper results over captured pipes, with generic failure diagnostics.

## Existing behavior and documentation

Keep the default no-overwrite upload policy, explicit overwrite setting, conflict protection and unchanged official uploader source. Preserve existing Windows registration and refresh semantics with regression tests. Add concise English default README and Linux setup instructions, keep corresponding zh-CN reader documentation and visible reciprocal language links. Preserve current setup-guide links for Windows users; document the Linux backend's plaintext-at-rest permission model, authorization procedure, expiry, recovery, installation/registration and how to disable the MCPs.

## Verification and deployment

Run existing Python and Node suites as a baseline. Add Linux tests for root precedence/TOML, private path rejection, file ownership/modes/symlinks, atomic save, hidden input, valid/expiring/expired/malformed authorization, missing/mismatched app credentials, concurrent refresh and pending recovery. Use synthetic tokens and a local fake OAuth transport; assert errors/logs never disclose them. Test launchers with fake helpers/bridge to cover startup failure, rotation, active-write preservation and expired-request rejection. Test install preparation in isolated temporary roots and verify deployed commands do not reference a worktree or Windows executables.

Prepare and review code in a separate PR, run applicable checks against the current target, then merge and clean up under standing authorization. The repository's no-public-publication instruction is satisfied by a final reviewable PR/contents approval if publication to a new public surface is proposed; ordinary development PR integration follows the owner's standing instructions. Installation on the actual host uses the selected canonical roots and preserves historical data. Only after runtime paths and tests pass should MCP registrations change. Actual credential entry requires a user handoff; first authenticated validation is read-only initialization and root listing. Upload/download/share/delete integration tests need explicit test scope and synthetic fixtures, not preexisting cloud files. Do not claim authenticated usability until those read-only checks pass.

## Builder decisions

The implementer chooses helper module names and CLI subcommands, using the existing relay and authorization provider where feasible. Keep dependencies minimal; stdlib Python supports file credentials/locks/OAuth. Avoid a new daemon or keyring dependency. Deployment may remain staged pending credentials; report exactly what is installed, registered, authenticated and unverified.

## Exploration baseline (2026-11-06)

Base `a13e659`: Python unittest discovery: 30 tests, 11 passed and 19 Windows-dependent skips on Linux. Node protocol test file passed. No Linux credential backend exists yet, and no authenticated Linux MCP test has run. The canonical Linux deployment directory is absent. Historical runtime/test data is retained and has not been modified. Builder review found no important unresolved design questions.
