# Windows setup

[简体中文（完整指南）](setup-guide.zh-CN.md) · [Linux setup](docs/setup-linux.md)

Use Windows, PowerShell 7, Node/npm, Git, uv and Codex CLI. The [complete Chinese guide](setup-guide.zh-CN.md) includes the official authorization flow, permissions, screenshots-independent steps and troubleshooting. For Linux, use the separate guide; DPAPI files cannot be moved to Linux and decrypted there.

In PowerShell, supply explicit private configuration and data roots:

```powershell
& ./scripts/install.ps1 -DataRoot $dataRoot -ConfigRoot $configRoot
$deployment = Join-Path $configRoot 'deployments/baidu-netdisk-mcp'
& (Join-Path $deployment 'save-experience-authorization.ps1')
& (Join-Path $deployment 'check-authorization.ps1') -Online
```

The installer retains the pinned official source and bridge. The authorization script prompts for the official authorization result URL without displaying it, encrypts tokens for the current Windows user and restricts file permissions. Do not send credential-bearing URLs to chat, issues or logs. Get the current experience application entry from the [official preparation instructions](https://github.com/baidu-netdisk/mcp#使用准备); confirm the requested permissions yourself. A copied encrypted file is not portable between users or computers.

Automatic refresh requires the same application's AppKey, SecretKey and refresh token; experience access alone does not supply the application's secret. Uploads default to rejecting existing destination names, explicit overwrite requires authorization, and persisted multipart resume is not implemented. Windows `.env` and encrypted credential formats are unchanged by the Linux backend.
