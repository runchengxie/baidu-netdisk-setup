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

固定的上游版本跟踪了生成的字节码。安装器仅允许 `__pycache__` 中普通 `.pyc` 缓存的修改；真实源码变化或版本不符仍会停止安装。Linux 上传端使用运行目录中的独立字节码缓存，不读取或改写上游跟踪的缓存。

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

## 恢复已有应用的自动刷新

刷新代码已经实现，并不意味着刚取得的体验访问令牌可以刷新。原应用的 AppKey、对应 SecretKey 和一次新的授权码交换，可以取得独立的访问令牌及刷新令牌，不需要在 Linux 上解密迁移来的 Windows DPAPI 文件。由应用所有者到开发者控制台取得 SecretKey，不要把密钥或授权码发到聊天里。授权码交换及刷新条件见[百度官方 OAuth 指南](https://openauth.baidu.com/doc/doc.html)。

先使用原应用的非秘密 AppKey 创建独立配置：

```bash
python3 "$deployment/credential-helper.py" prepare-app --app-key '<原应用 AppKey>'
python3 "$deployment/credential-helper.py" \
  --settings "$deployment/original-app-settings.json" authorize-app
```

第二条必须在真实终端运行。在隐藏提示输入 SecretKey，打开程序显示的官方授权网址，核对原应用及权限后，将 OOB 页面显示的新授权码粘贴到下一个隐藏提示。授权码只能用一次，且有效期很短。也可粘贴包含匹配 state 的完整官方返回网址。访问令牌、刷新令牌和密钥分别保存在私有的 `original-app-authorization.json`、`original-app-secret.json`；现有体验文件及 Codex 默认登记不变。交换结果必须包含网盘权限和刷新令牌。失败信息会脱敏，程序不会自动重试授权码。

若保存过程中断，私有 `.pending-authorization` 文件保留完整的新令牌及密钥。应保留它；恢复前，该候选授权不能使用或再次交换。确认选中的是这套候选配置后，运行下面的本机恢复命令，不会再次请求 OAuth：

```bash
python3 "$deployment/credential-helper.py" \
  --settings "$deployment/original-app-settings.json" recover-app --replace
```

已有候选凭据默认保留，只有明确使用 `authorize-app --replace` 才重新授权。如果文件系统连完整恢复文件都没能写入，程序无法找回内存中已丢失的令牌；此时应取得新授权码，不能重放已使用的码。

不改变默认登记，也能单独验证候选配置：

```bash
BAIDU_MCP_SETTINGS_FILE="$deployment/original-app-settings.json" \
  "$python_path" "$deployment/check-mcp.py"
python3 "$deployment/credential-helper.py" \
  --settings "$deployment/original-app-settings.json" ensure --force
```

第一条初始化两个已部署 MCP，并只读网盘根目录。第二条会明确进行一次真实 OAuth 刷新，并私下保存返回的新令牌对，必须在新应用授权保存后才运行。刷新后再执行一次只读检查，确认新令牌可用。这些操作不写入网盘文件。选择配置的环境变量只包含非秘密路径，并传递给 Python 帮助程序和 Node 工作进程。

应把本次 Linux 结果与历史 Windows 证据分开记录。旧记录中，原应用的分享曾返回 `invalid app`，体验应用的分享可用；根目录读取或刷新成功不能证明分享、上传能力完全相同。不会悄悄替换体验配置或新增默认连接。账户和权限检查完成后，再明确选择是否调整默认用途。

应用授权失败时，工具输出脱敏的 `[阶段/错误码]`，不会显示服务端原始描述。`exchange/invalid_client` 表示 AppKey/SecretKey 组合被拒绝；`exchange/invalid_grant` 表示一次性授权码被拒绝，可能已过期、使用过或属于其他应用。`exchange/network_failure` 表示网络或 TLS 失败，`input/invalid_code` 表示本地输入校验未通过。返回网址缺少 state 或 state 不匹配也分别报告；可以复制 OOB 页面单独显示的授权码，不要绕过不匹配的 state。`publication/storage_failure` 应先检查待恢复文件，不要重复交换。排除报告的问题后应取得新授权码，不能盲目重放可能已使用的旧码。排查时只分享安全的错误分类和提示，不要发送授权码、密钥、令牌或含凭据的返回网址。
