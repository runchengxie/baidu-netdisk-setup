# Linux 配置指南

[English](setup-linux.md) · [项目说明](../README.zh-CN.md) · [Windows 指南](../setup-guide.zh-CN.md)

在 Linux 上安装两个官方 MCP，凭据使用权限受限的私有文件。需要 Python 3.12+、Node/npm、Git、uv 和 Codex CLI，不需要桌面密钥环或 PowerShell。官方源码固定为 `b3983d330fea79c7b72e6b7014803e1830148d2c`，桥接固定为 `mcp-remote@0.14.3`，不会修改上游源码。

## 安装或准备

从机器配置确认 `CODE_ROOT`、`DATA_ROOT`、`CONFIG_ROOT`。优先使用命令行 `--code-root`、`--data-root`、`--config-root`，其次是同名环境变量，再其次是明确传入的 TOML 文件；文件使用 `[roots]` 和大写键名，不会自动搜索私人配置。

```bash
python3 scripts/install-linux.py --workspace-config "$CONFIG_ROOT/shared/workspace.toml" \
  --prepare-only
python3 scripts/install-linux.py --workspace-config "$CONFIG_ROOT/shared/workspace.toml" \
  --skip-registration
```

第一条只准备启动程序和私有设置，不下载依赖、不登记 MCP。第二条安装固定版本依赖，仍不登记。检查完成后，不带这两个开关运行即可登记两条连接。未知部署、符号链接、错误或被修改的上游版本及不匹配的根目录会导致停止；保留已有凭据及历史 Windows 运行目录。

依赖放在 `DATA_ROOT/baidu-netdisk-mcp/runtime/linux`，启动程序和私有设置放在 `CONFIG_ROOT/deployments/baidu-netdisk-mcp`。登记使用稳定部署路径，不引用任务工作树。设置记录 Linux 的 `.venv/bin/python`。

## 私下保存授权

Linux 凭据是**磁盘上的明文文件**，由目录 `0700` 和文件 `0600` 权限保护。同一用户运行的程序和 root 可以读取。部署目录应位于支持 Linux 所有者及权限的文件系统上；不会自动放宽检查或修改迁移文件的权限。两条 MCP 都拒绝错误所有者、组或其他用户可访问的文件、符号链接、源码目录中的凭据、未知有效期及已过期令牌。旧 Windows DPAPI 文件不能直接使用。

从[官方使用准备说明](https://github.com/baidu-netdisk/mcp#使用准备)获取当前授权入口，在浏览器确认应用身份和请求权限。含令牌的返回网址必须保密。体验授权为限时入口，到期后可能需要人工重新授权。自有应用则使用授权响应中的访问令牌、可选刷新令牌和剩余有效秒数；本项目不需要也无法获取其他应用的 SecretKey。

```bash
deployment="$CONFIG_ROOT/deployments/baidu-netdisk-mcp"
python3 "$deployment/credential-helper.py" save
```

在隐藏提示中粘贴刚取得的完整官方授权返回网址，包括 `#` 后内容。只接受 `https://openapi.baidu.com/oauth/2.0/login_success` 返回页。也可直接输入访问令牌，再按提示输入可选刷新令牌和剩余有效秒数。已有凭据默认保留，只有明确添加 `--replace` 才替换。不要把令牌发到聊天、写进命令参数、环境启动脚本或公开文件。内部 `token` 子命令只供启动程序捕获管道读取，拒绝直接输出到终端。

使用自有应用自动刷新时，先在私有 `settings.json` 设置与授权一致的非秘密 `appKey`，再运行 `credential-helper.py save-secret` 隐藏输入 SecretKey。应用密钥与 OAuth 令牌分开保存，格式带版本。Linux 后端不读取 Windows `.env` 覆盖项，以自己的私有设置为准。

```bash
python3 "$deployment/credential-helper.py" ensure
```

这里只输出脱敏后的有效期和刷新状态。材料匹配时，剩余有效期七天以内会尝试自动刷新。两个 MCP 共用操作系统管理的锁，锁内重新读取令牌；进程退出后占用自动释放。令牌以私有文件原子保存；最终替换失败时保留 `.pending-refresh` 恢复文件，并阻止再次刷新。材料缺失时仍可使用未过期令牌；过期或有效期不明会阻止启动。本地上传每次调用都检查凭据，一次上传固定使用一个令牌。远程请求在令牌到期后停止，更新时等待进行中的请求结束再重连，不重放写入。不保证跨进程进行中的上传一定不受服务端令牌轮换影响。

## 登记与只读验证

依赖和授权准备好后，不带 `--skip-registration` 运行安装器，或使用部署设置手动登记：

```bash
node_path="$(command -v node)"
python_path="$DATA_ROOT/baidu-netdisk-mcp/runtime/linux/official-mcp/src/baidu-netdisk/.venv/bin/python"
codex mcp add baidu-netdisk -- "$node_path" "$deployment/start-remote.mjs"
codex mcp add baidu-netdisk-local-uploader -- "$python_path" "$deployment/start-local.py"
"$python_path" "$deployment/check-mcp.py"
```

最后一条初始化两个 MCP、列出工具名称，并读取网盘根目录；不输出云端文件名或令牌，也不写入云端。更新启动程序后需要重启 Codex 连接。仅初始化成功不能证明授权有效，还应确认 `rootListingErrno=0`。本地上传端到端验证仍需另外授权范围明确的合成文件测试。

停用时运行 `codex mcp remove baidu-netdisk` 和 `codex mcp remove baidu-netdisk-local-uploader`，这不会删除私有凭据或网盘文件。不要删除其他用途的登记项。

## 验证

```bash
python3 -m unittest discover -s tests
node --test tests/test_remote_session.mjs tests/test_platform_config.mjs
python3 -m compileall -q scripts
```

Linux 测试使用合成令牌，不写网盘。Windows 专用测试在 Linux 上跳过；若要宣称 Windows 重新验证通过，应在 Windows 上运行。权限测试需要支持 POSIX 权限、且祖先目录不在 Git 仓库中的临时位置。新增覆盖权限、有效期、刷新、提供器及安装器，同时保留原有连接轮换和上传冲突测试。历史 Windows 实测仍在 [verification.md](verification.md)，不会改称 Linux 实测。应分别报告本机安装、登记、授权初始化、根目录读取四个阶段。
