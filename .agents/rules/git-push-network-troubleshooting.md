# Git Push 与网络排错规则 (/learn 成果)

> 适用环境：Windows 11 + VS Code + Clash Verge (TUN 模式) + Git for Windows

---

## 📌 问题现象与复盘

在 Windows 11 环境下执行 `git push origin main` 推送代码到 GitHub 时，频繁出现以下两种典型失败：
1. **现象 A**：`Connection closed by 198.18.0.31 port 443` 或连接静默挂死，但在终端单独执行 `ssh -T git@ssh.github.com`（仅握手认证）却能正常通过；
2. **现象 B**：尝试配置代理命令时报错 `Connection closed by UNKNOWN port 65535` 或 `fatal: ssh variant 'simple' does not support setting port`。

---

## 🔍 根本原因深度分析

### 1. TUN 虚拟网卡巨型帧（MTU 9000）与物理网卡不匹配引发“TCP黑洞”
- **机制**：
  Clash Verge 开启 TUN 模式后，会在 Windows 中创建名为 `Meta` 的虚拟网卡，其默认 MTU 被设置为 **9000 (Jumbo Frame)**；然而主机的物理网卡（如 WLAN 或 以太网）MTU 仅为标准的 **1500**。
- **为什么认证能通但 Push 失败**：
  - `ssh -T` 仅进行几百字节的密钥协商小包交互，包大小远低于 1500，故能顺利通过；
  - `git push` 在发送 commit 和 packfile（数十 KB 至数 MB）时，TCP 尝试按照 MTU 9000 发送大报文。底层物理网卡无法发送超过 1500 字节的巨型帧，且中间节点未返回 ICMP Fragmentation Needed 报文，导致 TCP 大包在网络层静默丢弃（即“TCP黑洞”），连接被 TUN 网卡地址 `198.18.0.31` 强制断开。

### 2. Git for Windows 内置 MSYS2 OpenSSH 的路径与参数切分缺陷
- **机制**：
  Windows 系统中通常存在两个 `ssh.exe`：
  - Windows 原生 OpenSSH：`C:\Windows\System32\OpenSSH\ssh.exe`
  - Git for Windows 附带的 MSYS2/Cygwin 架构 OpenSSH：`C:\Program Files\Git\usr\bin\ssh.exe`
- **冲突点**：
  Git 默认调用自带的 MSYS2 版 `ssh.exe`。当在命令行或环境变量中传递包含 Windows 驱动器盘符（如 `C:/Users/...`）、中文路径或复杂嵌套双引号的 `ProxyCommand` 时，MSYS2 解释器会出现转义剥离或把路径当 POSIX 处理，导致目标端口被解析为 65535，最终抛出 `UNKNOWN port 65535` 异常退出。

---

## 🛠️ 最佳实践与标准解决方案 (Golden Standard)

为彻底杜绝此问题，推荐在项目仓库或全局 Git 中固定采用以下配置：

### 1. 显式绑定 Windows 原生系统 OpenSSH
避免使用 Git 自带的 MSYS2 `ssh.exe`，在当前仓库或全局指定系统自带的 OpenSSH：
```bash
git config core.sshCommand "C:/Windows/System32/OpenSSH/ssh.exe -F C:/Users/Acer/.ssh/config_github"
```

### 2. 配置纯英文路径的专属 SSH 代理配置 (`~/.ssh/config_github`)
在纯英文路径（例如 `C:/Users/Acer/.ssh/config_github`）下创建配置文件：
```ssh
Host github.com ssh.github.com
    HostName ssh.github.com
    Port 443
    User git
    IdentityFile C:/Users/Acer/.ssh/id_ed25519_wsl
    ProxyCommand C:/PROGRA~1/Git/mingw64/bin/connect.exe -H 127.0.0.1:7890 %h %p
    StrictHostKeyChecking no
```

> **核心优势**：
> - **绕过 TUN 网卡 MTU 陷阱**：TCP 数据流直接发送至本地回环地址 `127.0.0.1:7890`（Loopback MTU 极大且无物理层丢包），由代理客户端接管真正的外部连接，彻底解决 9000 vs 1500 巨型帧丢包；
> - **使用 HTTP CONNECT 隧道 (`-H`)**：相比 SOCKS5 (`-S`)，`-H` 隧道在 Windows mingw64 `connect.exe` 下响应更迅捷、握手无延迟；
> - **免命令行双引号转义**：将 `ProxyCommand` 写入独立配置文件，避免在 PowerShell 或 Git 环境变量中拼接多重转义字符。
