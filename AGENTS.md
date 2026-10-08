# Baidu Netdisk Setup

This repository contains Windows setup helpers and documentation for the official Baidu Netdisk MCP. It is an independent project.

- Keep credentials, private configuration, downloaded SDKs, generated inventories and test artifacts outside this repository.
- Resolve machine roots from an explicitly supplied workspace TOML or command parameters. Do not put personal absolute paths in shared scripts.
- Official upstream code is downloaded at a pinned revision; do not vendor or edit it.
- Never log OAuth tokens, cookies or credential-bearing URLs. Decrypt Windows DPAPI credentials only inside the launching process.
- Local uploads must require explicit overwrite authorization and document their conflict behavior. Tests may only delete fixtures created by that test after identity checks.
- Public docs must distinguish direct API tests from installed MCP tests and anonymous downloads from independently authenticated recipients.
- Validate scripts with syntax checks, unit tests and explicitly authorized integration tests. No public publication until the owner approves the prepared contents.
