# -*- coding: utf-8 -*-
"""
Windows 网络配置底层操作，全部基于 netsh。
"""
import ctypes
import locale
import re
import subprocess
import sys


def _run(cmd):
    """执行命令并返回 (returncode, stdout, stderr) 文本。"""
    # 隐藏窗口
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    proc = subprocess.run(
        cmd,
        capture_output=True,
        startupinfo=startupinfo,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    enc = _guess_encoding(proc.stdout)
    out = proc.stdout.decode(enc, errors="replace")
    err = proc.stderr.decode(enc, errors="replace")
    return proc.returncode, out, err


def _guess_encoding(raw):
    """Windows 下 netsh 输出可能是 GBK 或 UTF-8，做粗略判断。"""
    for enc in ("utf-8", "gbk", locale.getpreferredencoding()):
        try:
            raw.decode(enc)
            return enc
        except UnicodeDecodeError:
            continue
    return "gbk"


def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        return False


def run_as_admin():
    """以管理员权限重启当前程序。"""
    try:
        rc = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, " ".join(sys.argv), None, 1
        )
        return rc > 32
    except Exception:
        return False


def parse_interface_table(text):
    """
    解析 `netsh interface ipv4 show interfaces` 的输出。
    返回 [{'name': str, 'state': str, 'idx': int}, ...]

    典型（中文系统）:
        Idx     Met         MTU          状态                名称
        ---  ----------  ----------  ------------  ---------------------------
          1          75  4294967295  connected     Loopback Pseudo-Interface 1
    典型（英文系统）:
        Idx     Met         MTU          State                Name
        ---  ----------  ----------  ------------  ---------------------------
          1          75  4294967295  connected     Loopback Pseudo-Interface 1
    """
    result = []
    started = False
    for raw in text.splitlines():
        line = raw.rstrip()
        # 分隔线之后才是数据
        if re.match(r"^\s*-{3,}\s*$", line) or re.match(r"^\s*(-{3,}\s+)+-{3,}\s*$", line):
            started = True
            continue
        if not started:
            continue
        if not line.strip():
            continue
        m = re.match(r"^\s*(\d+)\s+\d+\s+\d+\s+(\S+)\s+(.+?)\s*$", line)
        if not m:
            continue
        result.append({"idx": int(m.group(1)), "state": m.group(2), "name": m.group(3)})
    return result


def list_interfaces():
    """返回网卡列表，每项 {'name': str, 'state': str, 'idx': int}"""
    code, out, err = _run(["netsh", "interface", "ipv4", "show", "interfaces"])
    if code != 0:
        raise RuntimeError(err.strip() or out.strip() or "netsh 执行失败")
    ifaces = parse_interface_table(out)
    if not ifaces:
        # 回退：尝试用 ipconfig 解析（极少数系统 netsh 输出格式异常）
        ifaces = _fallback_interfaces()
    return ifaces


def _fallback_interfaces():
    code, out, _ = _run(["ipconfig", "/all"])
    if code != 0:
        return []
    names = []
    for raw in out.splitlines():
        m = re.match(r"^([^\s:].*?):\s*$", raw.rstrip())
        if m:
            name = m.group(1)
            if name.lower().startswith("windows ip") or not name.strip():
                continue
            names.append({"idx": 0, "state": "unknown", "name": name})
    return names


def get_current_config(iface):
    """获取指定网卡当前 IP / 掩码 / 网关 / DNS，返回可读行列表。"""
    code, out, err = _run(["netsh", "interface", "ipv4", "show", "config", f"name={iface}"])
    if code != 0:
        raise RuntimeError(err.strip() or out.strip() or "读取配置失败")

    lines = []
    capture = False
    for raw in out.splitlines():
        line = raw.rstrip()
        if "接口" in line and ("的配置" in line or "配置" in line):
            capture = True
        if not line.strip():
            if capture and lines:
                break
            continue
        if capture:
            lines.append(line.strip())
    if not lines:
        lines = [l.strip() for l in out.splitlines() if l.strip()]
    return lines


def valid_ip(value, allow_empty=False):
    """校验 IPv4 地址合法性。"""
    value = (value or "").strip()
    if not value:
        return allow_empty
    parts = value.split(".")
    if len(parts) != 4:
        return False
    for p in parts:
        if not p.isdigit():
            return False
        n = int(p)
        if n < 0 or n > 255:
            return False
        if len(p) > 1 and p[0] == "0":
            return False
    return True


def apply_profile(iface, profile):
    """应用静态方案。profile 需含 ip/mask/gateway/dns1/dns2。"""
    ip = profile.get("ip", "").strip()
    mask = profile.get("mask", "255.255.255.0").strip()
    gateway = profile.get("gateway", "").strip()
    if not valid_ip(ip):
        raise ValueError(f"IP 地址不合法：{ip}")
    if not valid_ip(mask):
        raise ValueError(f"子网掩码不合法：{mask}")
    if gateway and not valid_ip(gateway):
        raise ValueError(f"网关不合法：{gateway}")
    for key in ("dns1", "dns2"):
        dns = (profile.get(key) or "").strip()
        if dns and not valid_ip(dns):
            raise ValueError(f"DNS 不合法：{dns}")

    logs = []

    addr_cmd = [
        "netsh", "interface", "ipv4", "set", "address",
        f"name={iface}", "static", ip, mask,
    ]
    if gateway:
        addr_cmd += [gateway, "1"]
    else:
        addr_cmd += ["none"]

    code, out, err = _run(addr_cmd)
    logs.append(_fmt_cmd(addr_cmd))
    if code != 0:
        raise RuntimeError(_tail(err) or _tail(out) or "设置 IP 失败")
    logs.append("  -> IP 设置成功")

    dns_servers = [d.strip() for d in (profile.get("dns1"), profile.get("dns2")) if d and d.strip()]
    if dns_servers:
        primary = dns_servers[0]
        cmd = ["netsh", "interface", "ipv4", "set", "dnsservers",
               f"name={iface}", "static", primary, "primary", "validate=no"]
        code, out, err = _run(cmd)
        logs.append(_fmt_cmd(cmd))
        if code != 0:
            logs.append(f"  -> 首选 DNS 设置失败: {_tail(err) or _tail(out)}")
        else:
            logs.append("  -> 首选 DNS 设置成功")

        for idx, dns in enumerate(dns_servers[1:], start=2):
            cmd = ["netsh", "interface", "ipv4", "add", "dnsservers",
                   f"name={iface}", dns, f"index={idx}", "validate=no"]
            code, out, err = _run(cmd)
            logs.append(_fmt_cmd(cmd))
            if code != 0:
                logs.append(f"  -> 备用 DNS {dns} 添加失败: {_tail(err) or _tail(out)}")
            else:
                logs.append(f"  -> 备用 DNS {dns} 添加成功")
    else:
        # 未提供 DNS 时，切换为 DHCP 获取 DNS
        cmd = ["netsh", "interface", "ipv4", "set", "dnsservers", f"name={iface}", "dhcp"]
        code, out, err = _run(cmd)
        logs.append(_fmt_cmd(cmd))
        logs.append("  -> DNS 转为自动获取" if code == 0 else f"  -> DNS 自动获取失败: {_tail(err)}")

    return "\n".join(logs)


def set_dhcp(iface):
    """将网卡 IP 与 DNS 全部改为自动获取。"""
    logs = []
    for name, cmd in (
        ("IP", ["netsh", "interface", "ipv4", "set", "address", f"name={iface}", "dhcp"]),
        ("DNS", ["netsh", "interface", "ipv4", "set", "dnsservers", f"name={iface}", "dhcp"]),
    ):
        code, out, err = _run(cmd)
        logs.append(_fmt_cmd(cmd))
        if code != 0:
            logs.append(f"  -> {name} 切换失败: {_tail(err) or _tail(out)}")
        else:
            logs.append(f"  -> {name} 已设为自动获取")
    return "\n".join(logs)


def _fmt_cmd(cmd):
    parts = []
    for c in cmd:
        parts.append(f'"{c}"' if (" " in c or c == "") else c)
    return "$ " + " ".join(parts)


def _tail(text, n=3):
    lines = [l for l in (text or "").splitlines() if l.strip()]
    return " / ".join(lines[-n:])
