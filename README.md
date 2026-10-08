# 百度网盘官方 MCP 配置助手

为 Windows + Codex 准备的配置说明和小型启动脚本。网盘服务和上传程序来自[百度官方项目](https://github.com/baidu-netdisk/mcp)，本项目负责本机安装、加密授权读取和使用说明。

从零开始请读 [setup-guide.md](setup-guide.md)。体验路线使用百度提供的应用，不需要自行申请 API Key；登录后仍需确认授权并在本机保存令牌。

## 项目范围

- 安装远程 MCP 所需的桥接工具，并登记本地上传 MCP。
- 用 Windows 当前用户加密保存授权，配置文件中不放明文令牌。
- 查询授权有效期，临近到期时提示人工重新授权。
- 上传默认拒绝已有同名文件，只有明确设置 `overwrite=true` 才允许替换。

本项目暂不自动刷新令牌，也不为官方上传程序增加持久化断点续传。体验授权是限时测试入口，正式使用应按照百度开放平台的要求申请应用。

## 验证

```powershell
python -m unittest discover -s tests
```

测试记录的公开摘要见 [docs/verification.md](docs/verification.md)。个人网盘目录、文件 ID、授权文件和实际测试状态保留在本机数据目录中。
