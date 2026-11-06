# Linux setup

[简体中文](setup-linux.zh-CN.md) · [Project](../README.md) · [Windows](../setup-guide.md)

Install the two official MCP routes using private Linux credential files. Python 3.12+, Node/npm, Git, uv and Codex CLI are required. No desktop keyring or PowerShell is needed. The installer pins official source revision `b3983d330fea79c7b72e6b7014803e1830148d2c` and `mcp-remote@0.14.3`; upstream files are not edited.

## Install or prepare

Resolve `CODE_ROOT`, `DATA_ROOT` and `CONFIG_ROOT` from your machine configuration. The installer accepts explicit `--code-root`, `--data-root`, `--config-root`, then corresponding environment variables, then an explicitly supplied TOML with a `[roots]` table and uppercase keys. It does not automatically discover private files.

```bash
python3 scripts/install-linux.py --workspace-config "$CONFIG_ROOT/shared/workspace.toml" \
  --prepare-only
python3 scripts/install-linux.py --workspace-config "$CONFIG_ROOT/shared/workspace.toml" \
  --skip-registration
```

Preparation copies launchers and private settings without downloading dependencies or registering MCPs. The second command downloads pinned dependencies without registration. Run without either flag to register both after reviewing the installation. Unknown deployments, symlinks, modified/wrong upstream revisions and incompatible roots stop installation; existing credentials and historical Windows runtime files are preserved.

Runtime dependencies are under `DATA_ROOT/baidu-netdisk-mcp/runtime/linux`; launchers and private settings are under `CONFIG_ROOT/deployments/baidu-netdisk-mcp`. Registration uses these stable deployed paths, never a task worktree. Linux `.venv/bin/python` is recorded in settings.

## Authorize privately

Linux credentials are **plaintext at rest**, protected by directory mode `0700` and file mode `0600`. Programs running as you and root can read them. Store this deployment on a filesystem that enforces Linux ownership/modes; do not silently reuse loose-permission migrated files. Both MCPs reject wrong ownership, group/other access, symlink paths, source-contained files, malformed expiry and expired tokens. Windows DPAPI credentials cannot be reused.

Obtain a fresh authorization through the current [official preparation instructions](https://github.com/baidu-netdisk/mcp#使用准备), confirm the application and requested permissions in your browser, and keep all token-bearing result URLs private. The experience route is temporary and may require manual renewal. For a token response obtained through an application you own, use its access token, optional refresh token and remaining validity seconds. No SecretKey belonging to somebody else's application is needed or recoverable through this project.

```bash
deployment="$CONFIG_ROOT/deployments/baidu-netdisk-mcp"
python3 "$deployment/credential-helper.py" save
```

At the hidden prompt, paste the complete fresh official authorization result URL, including its `#` fragment. Only the official `https://openapi.baidu.com/oauth/2.0/login_success` result is accepted. Alternatively enter an access token, then the optional refresh token and remaining validity seconds from the response. Existing credentials are preserved unless you explicitly add `--replace`. Do not paste credentials into chat, shell command arguments, environment setup scripts or public files. The internal `token` helper is only for captured launcher pipes; it refuses to print to a terminal.

For your own application, set the non-secret `appKey` in the private `settings.json` to match the authorization, then run `credential-helper.py save-secret` for hidden SecretKey entry. Application credentials and OAuth tokens use separate versioned files. Windows `.env` overrides are not used by this Linux backend; Linux values come from its private settings.

```bash
python3 "$deployment/credential-helper.py" ensure
```

This prints only sanitized expiry/refresh state. Automatic refresh is attempted within seven days of expiration when matching materials exist. The two MCPs serialize refresh with an OS-released file lock and reread the token under lock. Atomic private persistence retains a `.pending-refresh` file if final publication fails; preserve it and resolve the saved authorization before another refresh. Missing refresh materials can use a currently valid access token; expired or unknown credentials stop startup. Local upload checks credentials on each call and retains one token for that operation. Remote requests stop at expiration and reconnect after a token change without replaying writes; rotation waits for active requests. Cross-process in-flight operations are not guaranteed to survive a server-side token rotation.

## Registration and read-only verification

Once dependencies and authorization are ready, run the installer without `--skip-registration`, or register using the deployed settings:

```bash
node_path="$(command -v node)"
python_path="$DATA_ROOT/baidu-netdisk-mcp/runtime/linux/official-mcp/src/baidu-netdisk/.venv/bin/python"
codex mcp add baidu-netdisk -- "$node_path" "$deployment/start-remote.mjs"
codex mcp add baidu-netdisk-local-uploader -- "$python_path" "$deployment/start-local.py"
"$python_path" "$deployment/check-mcp.py"
```

The last command initializes both protocols, lists tool names and performs a remote root listing; it does not print cloud filenames or tokens and makes no cloud writes. Restart the Codex connection after updating launchers. Initialization alone does not prove valid authorization; require `rootListingErrno=0` too. Local upload end-to-end remains unverified until a separately scoped synthetic test is authorized.

To disable these routes, use `codex mcp remove baidu-netdisk` and `codex mcp remove baidu-netdisk-local-uploader`; this does not delete private credentials or cloud files. Do not remove an unrelated registration.

## Verification

```bash
python3 -m unittest discover -s tests
node --test tests/test_remote_session.mjs tests/test_platform_config.mjs
python3 -m compileall -q scripts
```

Linux tests use synthetic tokens and no cloud writes. Windows-only tests skip on Linux; run them on Windows before claiming that platform is reverified. Temporary permission tests need a filesystem enforcing POSIX modes and paths outside Git ancestors. The Linux change adds permission/expiry/refresh/provider/installer coverage, while preserving the existing request-rotation and upload-conflict tests. Historical Windows integration results remain in [verification.md](verification.md), not relabeled as Linux results. Host installation, registration, authenticated initialization and a successful root listing are distinct stages; report each separately.
