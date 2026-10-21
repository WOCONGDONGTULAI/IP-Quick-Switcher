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
- 一键应用静态 IP + 子网掩码 + 网关 + 首选/备用 DNS
- 一键切回 DHCP 自动获取
- 实时显示当前网卡配置与执行日志
- 配置保存在 `ip_profiles.json`，便携，可放 U 盘随身携带

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
| `sticker.py` | 桌面贴纸小面板（无边框） |
| `win_desktop.py` | 桌面层嵌入（WorkerW 附着） |
| `app.py` | 完整管理界面 |
| `net_tools.py` | netsh 命令封装、网卡解析、IP 校验 |
| `config_store.py` | 方案读写（JSON 持久化） |
| `test_offline.py` | 解析与校验单测（跨平台可跑） |
| `test_commands.py` | 命令拼装单测（跨平台可跑） |
| `build.bat` | 打包脚本（同时产出两个 exe） |
| `run.bat` / `run_sticker.bat` | 源码启动脚本 |

## 免责

请只在你有权限的网络里使用，别乱改公共网络配置导致 IP 冲突。
