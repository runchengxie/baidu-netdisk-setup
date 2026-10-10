# 百度网盘官方 MCP 配置助手

为 Windows + Codex 准备的配置说明和小型启动脚本。网盘服务和上传程序来自[百度官方项目](https://github.com/baidu-netdisk/mcp)，本项目负责本机安装、加密授权读取和使用说明。

从零开始请读 [setup-guide.md](setup-guide.md)。体验路线使用百度提供的应用，不需要自行申请 API Key；登录后仍需确认授权并在本机保存令牌。

## 项目范围

- 安装远程 MCP 所需的桥接工具，并登记本地上传 MCP。
- 用 Windows 当前用户加密保存授权，配置文件中不放明文令牌。
- 私人 `.env` 配置令牌文件、AppKey 和加密密钥文件路径，公开的 `.env.example` 提供填写说明。
- 启动时检查授权，长期运行时每天检查一次；材料齐全且剩余有效期不超过七天时自动刷新。
- 上传默认拒绝已有同名文件，只有明确设置 `overwrite=true` 才允许替换。

自动刷新需要自己应用的 AppKey、SecretKey 和刷新令牌；体验授权仍需人工重新授权。本项目尚未为官方上传程序增加持久化断点续传。体验授权是限时测试入口，正式使用应按照百度开放平台的要求申请应用。

## 验证

```powershell
python -m unittest discover -s tests
node --test tests/test_remote_session.mjs
```

测试记录的公开摘要见 [docs/verification.md](docs/verification.md)。个人网盘目录、文件 ID、授权文件和实际测试状态保留在本机数据目录中。

## 自动刷新与断点续传

自动刷新已经接入两个 MCP，使用同一份加密授权与刷新锁。远程 MCP 更新 SSE 连接，本地上传在后续调用中读取新令牌。断点续传已经在独立的官方 API 测试中验证过，仍需把任务状态保存和恢复接入 MCP。具体条件及限制见 [refresh-and-resume.md](docs/refresh-and-resume.md)。

`save-app-secret.ps1` 在本机隐藏输入并加密保存 SecretKey。保存后重启两个 MCP；检查材料是否齐全不等于已向百度验证密钥，必要时可按指南运行一次手动刷新。
