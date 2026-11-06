# Baidu Netdisk MCP setup

[简体中文](README.zh-CN.md)

Install and launch the [official Baidu Netdisk MCP](https://github.com/baidu-netdisk/mcp) from Codex on Windows or headless Linux. This project provides pinned installation helpers, private authorization management, token refresh and explicit upload-overwrite protection. It does not host the cloud service or modify the official uploader source.

- **Linux:** start with the [Linux setup guide](docs/setup-linux.md). Credentials are plaintext files protected by owner-only filesystem permissions; no desktop keyring or PowerShell is required.
- **Windows:** use the [Windows setup guide](setup-guide.md). Existing current-user DPAPI encryption and PowerShell helpers are retained.
- **Verification:** [historical integration record](docs/verification.md) and [Linux verification](docs/setup-linux.md#verification).

The remote MCP manages cloud files; the local uploader reads local files. Uploads reject existing names by default and require explicit `overwrite=true` to replace them. Authorizing the official application grants its requested account permissions; this wrapper does not create server-enforced folder isolation.

Automatic refresh needs the matching application's AppKey, SecretKey and refresh token. The official experience route may require manual reauthorization. Multipart upload does not have persisted resume state in this MCP; previous direct API resume experiments do not establish MCP resume support. See the [Windows refresh/resume notes](docs/refresh-and-resume.md) and Linux guide for backend-specific details.
