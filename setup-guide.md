# 从零配置百度网盘官方 MCP

这份指南适合在 Windows 上，让 Codex 查看和整理自己的百度网盘，并上传本地文件。远程网盘服务来自百度，本项目提供安装和授权保存脚本。

个人体验路线不需要自己申请 API Key，也不用购买本项目的任何服务。你需要一个百度账号，在百度页面登录，确认允许 `mcp_server` 读写网盘，再把授权结果保存在本机。扫码只是登录的一种方式，登录后仍要确认应用授权。

百度将这条路线标为限时体验，应用信息可能变更，不能当作永久可用的正式应用。长期正式接入需要按开放平台要求申请自己的应用。本指南核对时间为 2026 年 10 月 8 日，最新入口以[官方 README](https://github.com/baidu-netdisk/mcp#使用准备)为准。

## 先分清三个名称

| 名称 | 大白话解释 | 体验路线需要自己申请吗 |
|---|---|---|
| API Key／AppKey／client_id | 告诉百度“哪个应用在请求授权”的应用标识 | 不需要，授权链接已使用官方体验应用 |
| SecretKey／client_secret | 正式应用的私密密钥，用于部分令牌交换和刷新流程 | 不需要输入体验应用的 SecretKey |
| Access Token | 你授权后得到的访问凭证，工具凭它访问网盘 | 需要取得并保存，有有效期 |

授权结果网址里包含 Access Token，整条网址都应当按密码处理。只粘贴到本机脚本的隐藏输入框，不发给聊天、GitHub Issue 或其他人。

## 第一步，准备软件和项目文件

电脑上需要 Windows、PowerShell 7、Node.js 和 npm、Git、uv，以及能运行的 Codex CLI。uv 会为上传程序准备 Python 3.12 和对应依赖，无需另行手动配置 Python 环境。

官方安装入口分别为 [PowerShell](https://learn.microsoft.com/powershell/scripting/install/installing-powershell-on-windows)、[Node.js](https://nodejs.org/en/download)、[Git](https://git-scm.com/downloads/win)、[uv](https://docs.astral.sh/uv/getting-started/installation/) 和 [Codex](https://developers.openai.com/codex/cli/)。按各自官方说明安装，之后重新打开 PowerShell。

执行下面这些命令，每个都应该显示版本号。

```powershell
pwsh --version
node --version
npm.cmd --version
git --version
uv --version
codex --version
```

本指南需要和本项目的 `scripts` 文件夹一起使用。单独复制这一个 Markdown 文件不会自动安装启动程序。

从[公开仓库](https://github.com/runchengxie/baidu-netdisk-setup)下载完整 ZIP，或者在 PowerShell 运行下面两行。项目放在自己的 `code/baidu-netdisk-setup`。

```powershell
New-Item -ItemType Directory -Force -Path (Join-Path $env:USERPROFILE 'code') | Out-Null
git clone https://github.com/runchengxie/baidu-netdisk-setup.git (Join-Path $env:USERPROFILE 'code/baidu-netdisk-setup')
```

如果该位置已经有项目，直接进入现有目录，不要再次克隆到同一个位置。

```powershell
$project = Join-Path $env:USERPROFILE 'code/baidu-netdisk-setup'
Set-Location $project
Test-Path ./scripts/install.ps1
```

最后一个命令应返回 `True`。如果项目放在别的位置，修改 `$project`。

## 第二步，安装两个 MCP

在同一个 PowerShell 窗口运行下面这段。数据目录可选择任意有足够空间的位置；示例使用用户目录，不要求电脑一定有 D 盘。

```powershell
$dataRoot = Join-Path $env:USERPROFILE 'data'
$configRoot = Join-Path $env:USERPROFILE '.config/runchengxie'
& ./scripts/install.ps1 -DataRoot $dataRoot -ConfigRoot $configRoot
$deployment = Join-Path $configRoot 'deployments/baidu-netdisk-mcp'
```

脚本会下载固定版本的桥接工具和百度官方上传源码，创建 Python 环境，然后登记两个连接。

- `baidu-netdisk` 用于查看网盘、创建文件夹、复制、移动、改名、搜索和创建分享。
- `baidu-netdisk-local-uploader` 用于读取本机文件并上传到网盘。

安装结束时看到 `Registered remote and local-upload MCPs`。此时还没有授权，连接暂时不能使用是正常现象。

如果已经有本工作区的 `workspace.toml`，脚本也可从中读取 `data_root` 和 `config_root`，不需要重复传参。

```powershell
& ./scripts/install.ps1
```

安装依赖需要联网。如果下载失败，修好网络后重新运行安装命令。脚本不会覆盖已有百度源码目录来强行切换版本，版本不匹配时会停下提示。

## 第三步，在百度页面登录并确认授权

打开[百度官方体验授权页面](https://openapi.baidu.com/oauth/2.0/authorize?response_type=token&client_id=QHOuRXiepJBMjtk0esLhrPoNlQyYd0mF&redirect_uri=oob&scope=basic,netdisk)。这是官方 README 当前链接使用的应用标识；如果以后失效，先回官方 README 找最新入口。

1. 检查地址属于 `openapi.baidu.com`。
2. 使用页面提供的方式登录自己的百度账号；页面提供扫码时可以扫码。
3. 确认页面显示的应用名称为 `mcp_server`，阅读基础资料和网盘读写权限，再自行决定是否授权。
4. 点击授权后，会跳到 `https://openapi.baidu.com/oauth/2.0/login_success`。
5. 从浏览器地址栏复制完整网址，包括 `#` 后的内容。页面可能没有明显正文，地址栏仍是这一流程的关键。

这个授权不是只读授权。当前 MCP 也不能保证只能修改某一个文件夹；有特定应用目录限制的其他 Skill 是另一套接入方式。平时可以要求 Codex 只操作指定路径，但这属于操作约束，并不等同于百度服务器实施的文件夹权限隔离。

## 第四步，把授权结果保存到本机

回到刚才的 PowerShell，运行这一整行。

```powershell
& (Join-Path $deployment 'save-experience-authorization.ps1')
```

出现隐藏输入提示后，粘贴刚刚复制的完整网址，再按回车。粘贴内容不会显示出来。成功后会显示 `Saved Windows-user-encrypted authorization`。

如果重新打开了 PowerShell，先恢复变量，再执行保存命令。

```powershell
$deployment = Join-Path $env:USERPROFILE '.config/runchengxie/deployments/baidu-netdisk-mcp'
& (Join-Path $deployment 'save-experience-authorization.ps1')
```

令牌写在配置目录中的 `experience-token.json`，使用当前 Windows 用户加密，并限制文件权限。Codex 配置只保存启动命令。换电脑、换 Windows 用户时重新授权，不要以为复制这个文件就能登录。

## 第五步，检查授权和连接

先查看授权状态，并用百度接口做一次只读验证。

```powershell
& (Join-Path $deployment 'check-authorization.ps1') -Online
```

正常结果包含 `decryptable: true`、`onlineErrno: 0` 和 `onlineValid: true`。`status` 是根据保存时间估计的有效期，`onlineValid` 则是这次请求是否真的成功。

再检查两个 MCP 的协议连接。

```powershell
$settings = Get-Content -Raw (Join-Path $deployment 'settings.json') | ConvertFrom-Json
$python = Join-Path $settings.officialDir '.venv/Scripts/python.exe'
& $python (Join-Path $deployment 'check-mcp.py')
```

应分别看到 `remote` 和 `local` 的 `initialized: true`，远程连接还应显示 `rootListingErrno: 0`。检查只读取网盘根目录，并列出工具名称，不会上传文件。

最后重启 Codex，让它加载新增连接。先输入一个只读请求。

> 帮我列出百度网盘根目录，先只读取。

`codex mcp get baidu-netdisk` 显示 `enabled: true` 只能证明配置已登记；真正是否可用，要看上面的连接检查和实际只读请求。

## 平时怎么使用

> 查看百度网盘某个目录的所有文件，逐页读取。

> 把指定文件复制到指定目录，遇到重名先停下来。

> 用 baidu-netdisk-local-uploader，把本机这个文件上传到 /测试上传，遇到同名文件停止，不要覆盖。

本地上传工具的 `remote_directory` 参数是文件夹路径，文件名取自本地文件名。目标文件夹应当已存在。默认 `overwrite=false`，遇到同名文件返回冲突；只有用户明确允许时才使用 `overwrite=true`。

大文件会分片上传，但这套工具没有保存断点状态。网络恢复后的重试与关闭程序后的断点续传是不同能力，不能据此承诺中断后接着上传。

| 功能 | 当前实测边界 |
|---|---|
| 列目录、创建、复制、移动、改名 | 已验证；列表需分页 |
| 图片、视频、文档分类列表 | 已验证命中测试对象 |
| 文本、链接和本地小文件上传 | 已验证；远程文本同名上传可能另存副本 |
| 同名复制覆盖 | 已通过；移动／改名覆盖曾报冲突 |
| 分享 | 官方体验授权成功；本机原应用授权曾返回 invalid app |
| 接收分享并下载 | 提取码和查看成功，已有登录账号下载成功；匿名下载 403，独立第三方账号未测 |
| 自然语言、全文、图片文字搜索 | 返回成功但尚未命中已知内容，不能按成熟搜索能力使用 |
| 2 GiB 上传与中断恢复 | 本地 MCP 的 513 片上传、大小核对与三处分片下载抽查通过；完整 SHA-256 和中断恢复由另一个官方 API 测试脚本验证，本 MCP 没有自动续传 |
| 删除、下载 | 当前远程 MCP 工具目录中没有这两项；API 测试过不等于 MCP 已提供 |

更多公开测试摘要见 [验证范围](docs/verification.md)。

## 授权到期后怎么办

启动工具会检查保存的有效期，到期前七天提示，到期后要求重新授权。工具尚未自动刷新令牌，也没有后台定时提醒。

体验路线重新做第三步和第四步，会更新同一份授权文件。然后重启 Codex 的两个 MCP 连接。

本指南的体验流程目前只保存访问令牌，本项目不持有体验应用的 SecretKey。正式应用如要自动刷新，需要该应用的 SecretKey 和刷新令牌，另行配置安全的刷新流程。详细条件和断点续传方案见 [自动刷新与续传说明](docs/refresh-and-resume.md)。

已经有自己应用的加密授权文件，也可在安装时指定 `-TokenFile`。文件需使用本项目兼容的 Windows 加密字段格式，包含 `access_token`、`saved_at_utc` 和 `expires_in`；普通明文令牌 JSON 不能直接使用。

```powershell
& ./scripts/install.ps1 -DataRoot $dataRoot -ConfigRoot $configRoot -TokenFile '自己的加密授权文件完整路径'
```

指定后，远程操作和本地上传会共同使用该授权。体验授权的保存脚本默认更新 `experience-token.json`，不会替你刷新自己的应用文件；应使用自己应用的授权流程。

## 常见卡点

- 提示脚本找不到，检查路径是不是被换行拆开，以及 `$deployment` 是否已在当前窗口定义。
- PowerShell 策略阻止脚本时，先阅读脚本内容；确认愿意运行后，可用 `pwsh -NoProfile -ExecutionPolicy Bypass -File 脚本路径` 只为这次进程运行，不必更改全局策略。
- 有 `enabled: true` 仍连不上，检查网络、授权文件和在线检查结果。
- 搜索没有结果，进入已知目录逐页查找，不能直接认定文件不存在。
- 改名或移动显示解析错误，先查原路径、新路径和文件 ID；曾出现操作成功但返回 JSON 不完整的情况，直接重试可能重复操作。
- 体验应用失效，先查看百度官方入口是否已变更。体验应用并没有永久可用保证。

## 文件放在哪里和怎样移除

源代码项目可以放在 `code/baidu-netdisk-setup`。下载的程序放在数据根目录的 `baidu-netdisk-mcp/runtime`，授权和设置放在配置根目录的 `deployments/baidu-netdisk-mcp`。这些目录用途不同，公开 GitHub 仓库只包含项目脚本和说明。

```powershell
codex mcp remove baidu-netdisk
codex mcp remove baidu-netdisk-local-uploader
```

上面只移除 Codex 连接。需要撤销百度侧授权时，进入[百度授权管理](https://passport.baidu.com/accountbind)解除对应应用关联。

## 资料来源

- [百度官方 MCP 项目与授权入口](https://github.com/baidu-netdisk/mcp)
- [mcp-remote 桥接工具](https://github.com/punkpeye/mcp-remote)
- [百度网盘开放平台](https://pan.baidu.com/union)

桥接工具把百度的远程 SSE 连接转成本地 STDIO，让 Codex 能调用它。它不负责百度登录，也不会增加百度授予的权限。
