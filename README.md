# IP 快速切换器（IP Quick Switcher）

Windows 上一键切换网卡 IP 配置的小工具。两种前端：

1. **桌面贴纸** —— 无边框小面板，贴在桌面上实时显示当前 IP，一键切换
2. **完整管理界面** —— 增删改多套配置方案

## 功能

### 桌面贴纸（`sticker.py` + `win_desktop.py`）

- 无标题栏、无边框，**鼠标拖动**到任意位置，位置自动记忆
- 实时显示：网卡名、当前 IP、网关、DHCP/静态
- 支持**透明度**调节（50% ~ 100%）
- 默认每 5 秒自动刷新，可在菜单里关掉
- 右键菜单：一键切换任意方案 / 切 DHCP / 显示模式 / 调透明度 / 打开管理界面
- 不占任务栏（`-toolwindow`）
- 偏好设置存在 `sticker_config.json`（记得加进 `.gitignore`）

#### 三种显示模式

贴纸不再只有"永远置顶"一种活法，右键菜单 →「显示模式」里三选一：

| 模式 | 效果 | 适合 |
|---|---|---|
| **嵌入桌面层**（默认，推荐） | 真正成为桌面的一部分。Win+D 显示桌面时跟着出现；打开其他程序时被正常遮挡 | 长期挂着看 IP，不想打扰干活 |
| **悬浮置顶** | 永远盖在其他窗口之上，不会被任何东西挡住 | 需要时刻盯着/随时能点到 |
| **普通窗口** | 正常层叠，会被其他窗口盖住 | 偶尔看看 |

「嵌入桌面层」的原理（`win_desktop.py`）：Windows 的桌面背景由 Explorer 的一个
`WorkerW` 窗口承载，给 `Progman` 发送私有消息 `0x052C` 让它生成后，把贴纸
`SetParent` 挂上去即可。副作用有两个，心里有数：

1. 成为子窗口后就没法 `-topmost` 了，所以置顶和嵌入互斥，只能二选一
2. **资源管理器崩溃或重启后附着会失效** —— 贴纸会自动在刷新周期里重试贴回，
   也可以右键 →「显示模式」→「重新贴回桌面」手动触发

> 该模式依赖 Windows Shell，非 Windows 系统下菜单项会自动置灰。

### 完整管理界面（`app.py`）

- 自动列出本机所有网卡（含中文名、英文名、带编号的如"以太网 2"）
- 保存多套配置方案，名称自定义（如"办公室""实验室""家里"）
- **顶部快捷切换栏**：每个方案一枚按钮，点一下就切过去，右侧一键切 DHCP
- 一键应用静态 IP + 子网掩码 + 网关 + 首选/备用 DNS
- 一键切回 DHCP 自动获取
- 实时显示当前网卡配置与执行日志
- **系统托盘图标**：双击托盘唤回窗口，右键菜单退出；点窗口 X 只是收进托盘
- **开机自动运行**：首次运行自动写入注册表，界面顶部有「开机自启」勾选框随时开关
- 配置保存在 `ip_profiles.json`，便携，可放 U 盘随身携带

### 托盘与开机自启（`tray.py`）

纯 `ctypes` 直接调 Win32 实现，**不依赖 pystray / Pillow** —— 单文件 exe 打包后照样能用。

- 托盘图标：双击唤回主界面，右键弹出「显示主界面 / 退出」
- 气泡提示：最小化到托盘时给一条提醒
- 开机自启：写 `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` 的 `IPSwitcher` 项，
  只影响当前用户，不需要管理员权限。贴纸右键菜单里也能直接开关

> 注意：托盘消息用 `after` 定时非阻塞轮询处理（不用 `GetMessage` 死循环），
> 否则主窗口会卡在启动阶段起不来。

## 使用方式

### 方式一：直接运行源码（需装 Python）

1. 安装 [Python 3.8+](https://www.python.org/downloads/)，安装时勾选 **Add Python to PATH**
2. 按需双击：

| 想做什么 | 双击 |
|---|---|
| 桌面贴纸悬浮窗 | `run_sticker.bat` |
| 完整管理界面 | `run.bat` |

或命令行执行：

```
python sticker.py
python app.py
```

> 切换 IP 必须管理员权限。贴纸的右键菜单里有「以管理员重启」。
> 贴纸默认展示第一个网卡；方案需要在完整管理界面里添加，贴纸只负责快速调用。

### 方式二：打包成独立 exe（推荐，可给别人用）

在**本项目的 Windows 电脑**上：

```
build.bat
```

打包完成后 exe 在 `dist\` 下，拷到任何 Windows 机器都能直接双击运行，不需要装 Python：

| 文件 | 说明 |
|---|---|
| `dist\IPSwitcherSticker.exe` | 桌面贴纸悬浮窗 |
| `dist\IPSwitcher.exe` | 完整管理界面 |

如果想在没有 Python 的机器上再打包一次，需先装 Python 和 PyInstaller：

```
python -m pip install pyinstaller
```

### 打包踩坑记录（血泪教训，2026-10-21）

打包出来双击没反应、或者一闪就没，99% 是下面这几个原因：

1. **打包用的 Python 必须带 tkinter**。
   精简版 / embeddable 版 Python 没有 `_tkinter.pyd`，GUI 起来就崩。
   验证：`python -c "import tkinter; print(tkinter.TkVersion)"`，报错就是不能用。
   实在装不了带 tk 的官方版，可以用 [python-build-standalone](https://github.com/astral-sh/python-build-standalone/releases)
   的 `install_only` 包 —— 标准布局、自带 tcl/tk，PyInstaller 收集得最干净。

2. **别加 `--uac-admin`**。带了这参数每次启动都要过 UAC，非交互环境直接静默退出，
   看起来就是「双击没反应」。真要提权在程序里用「以管理员重启」按钮即可。

3. **conda 环境（micromamba/miniconda）打包会缺 DLL**。tcl/tk 和 libffi 都在 `Library\bin`，
   PyInstaller 默认搜不到，报 `_tkinter` 或 `_ctypes` DLL load failed。
   实在要用 conda 就得手动 `--add-binary` 把 `Library\bin\*.dll` 塞进去，很麻烦。

4. 打包命令的推荐形态（配合第 1 条的 Python）：

   ```
   python -m PyInstaller --noconfirm --clean --onefile --noconsole ^
       --name IPSwitcher --version-file version_info.txt app.py
   ```

5. **下载验证时先看文件大小**。raw 下载被截断会得到一个残缺 exe，症状和代码 bug 一模一样
   （弹 Error 框），容易误判。10MB 的 exe 如果只剩 6MB，就是没下全。

## 底层命令

工具实际执行的 netsh 命令（这也是最可靠的写法）：

```
netsh interface ipv4 set address name="以太网" static 192.168.2.157 255.255.255.0 192.168.2.1 1
netsh interface ipv4 set dnsservers name="以太网" static 114.114.114.114 primary validate=no
netsh interface ipv4 add dnsservers name="以太网" 8.8.8.8 index=2 validate=no
```

切回 DHCP：

```
netsh interface ipv4 set address name="以太网" dhcp
netsh interface ipv4 set dnsservers name="以太网" dhcp
```

### 注意点

- 静态 IP 用 **`static`**（位置参数），**不要**写成 `source=static`，后者会报错
- 网卡名必须和 `netsh interface ipv4 show interfaces` 输出里的完全一致
- 网关要和 IP 在同一子网，否则可能配置失败或无法上网

## 常见问题

**提示"找不到接口"** —— 网卡名不匹配。程序会自动列出真实网卡名，从下拉框里选即可，不用手敲。

**切换后没生效** —— 程序会自动显示当前配置，核对一下。必要时禁用再启用网卡。

**公司/学校电脑改完被自动改回去** —— 这是组策略（MDM）强制管控，本地改不动，需要找 IT 管理员解锁。

**有 VPN / 虚拟机网卡时** —— 别选错对象，虚拟网卡一般名为 `VirtualBox Host-Only Network`、`VMware Network Adapter`、`Hyper-V Virtual Switch` 等。

**贴纸没显示出来** —— 默认模式下它属于桌面层：先试试 Win+D 显示桌面。
如果还是没出现，多半是资源管理器重启过导致附着失效，右键 →「显示模式」→
「重新贴回桌面」即可；想彻底不依赖桌面层就切成「悬浮置顶」模式。
位置和透明度记在 `sticker_config.json`，删掉这个文件即可恢复默认摆放。

## 文件说明

| 文件 | 说明 |
|---|---|
| `sticker.py` | 桌面贴纸小面板（无边框、无标题文字） |
| `win_desktop.py` | 桌面层嵌入（WorkerW 附着） |
| `app.py` | 完整管理界面（含顶部方案快捷栏） |
| `tray.py` | 托盘图标 + 开机自启（纯 ctypes Win32，零依赖） |
| `net_tools.py` | netsh 命令封装、网卡解析、IP 校验 |
| `config_store.py` | 方案读写（JSON 持久化） |
| `test_offline.py` | 解析与校验单测（跨平台可跑） |
| `test_commands.py` | 命令拼装单测（跨平台可跑） |
| `build.bat` | 打包脚本（同时产出两个 exe） |
| `run.bat` / `run_sticker.bat` | 源码启动脚本 |
| `release.py` / `release.bat` | 自动发版脚本 |

## 版本发布

版本号规则：**纯数字递增**（1、2、3 ……）。数字最大那个就是最新版，
到 [Releases](https://github.com/WOCONGDONGTULAI/IP-Quick-Switcher/releases) 页面一眼就看得出来。

每次改动发布成新版本：

```
python release.py          # 自动取当前最大版本号 +1
python release.py --dry-run # 只预览，不实际发布
```

Windows 上也可以直接双击 `release.bat`，它会先预览再让你确认。

脚本做的事：读取现有 tag → 取最大数字 → +1 → 在当前 `main` 分支最新提交上打 tag 并创建 Release，
更新说明自动从两次版本之间的 commit message 汇总。全程只调 API，不需要本地 clone。

> 前提：安装 [GitHub CLI](https://cli.github.com) 并执行一次 `gh auth login`。

每个 Release 自带 **Source code**（zip / tar.gz）附件，即该版本的完整源码。
exe 因为要在 Windows 上编译，不随 Release 提供 —— 下载源码后跑 `build.bat` 即可生成。

## 免责

请只在你有权限的网络里使用，别乱改公共网络配置导致 IP 冲突。
