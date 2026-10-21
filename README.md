# IP 快速切换器（IP Quick Switcher）

Windows 上一键切换网卡 IP 配置的小工具。图形界面，预设方案，双击即切。

## 功能

- 自动列出本机所有网卡（含中文名、英文名、带编号的如"以太网 2"）
- 保存多套配置方案，名称自定义（如"办公室""实验室""家里"）
- 一键应用静态 IP + 子网掩码 + 网关 + 首选/备用 DNS
- 一键切回 DHCP 自动获取
- 实时显示当前网卡配置与执行日志
- 自动 UAC 提权（打包后的 exe 启动即请求管理员权限）
- 配置保存在 `ip_profiles.json`，便携，可放 U 盘随身携带

## 使用方式

### 方式一：直接运行源码（需装 Python）

1. 安装 [Python 3.8+](https://www.python.org/downloads/)，安装时勾选 **Add Python to PATH**
2. 双击 `run.bat`；或命令行执行：

```
python app.py
```

> 切换 IP 必须管理员权限。若未提权，点界面上的「以管理员重启」按钮。

### 方式二：打包成独立 exe（推荐，可给别人用）

在**本项目的 Windows 电脑**上：

```
build.bat
```

打包完成后 exe 在 `dist\IPSwitcher.exe`。把它拷到任何 Windows 机器都能直接双击运行，不需要装 Python。

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

## 文件说明

| 文件 | 说明 |
|---|---|
| `app.py` | 图形界面主程序 |
| `net_tools.py` | netsh 命令封装、网卡解析、IP 校验 |
| `config_store.py` | 方案读写（JSON 持久化） |
| `test_offline.py` | 解析与校验单测（跨平台可跑） |
| `test_commands.py` | 命令拼装单测（跨平台可跑） |
| `build.bat` | 打包脚本 |
| `run.bat` | 源码启动脚本 |

## 免责

请只在你有权限的网络里使用，别乱改公共网络配置导致 IP 冲突。
