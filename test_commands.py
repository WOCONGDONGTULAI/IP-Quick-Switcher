# -*- coding: utf-8 -*-
"""
验证 apply_profile / set_dhcp 生成的 netsh 命令是否正确。
通过打桩 net_tools._run 捕获命令，不真正执行。
"""
import sys

sys.path.insert(0, ".")

import net_tools

CAPTURED = []


def fake_run(cmd):
    CAPTURED.append(list(cmd))
    return 0, "OK", ""


net_tools._run = fake_run

PROFILE = {
    "name": "测试",
    "mode": "static",
    "ip": "192.168.2.157",
    "mask": "255.255.255.0",
    "gateway": "192.168.2.1",
    "dns1": "114.114.114.114",
    "dns2": "8.8.8.8",
}


def test_apply_full():
    CAPTURED.clear()
    out = net_tools.apply_profile("以太网", PROFILE)
    assert len(CAPTURED) == 3, CAPTURED

    c0 = CAPTURED[0]
    assert c0[:6] == ["netsh", "interface", "ipv4", "set", "address", "name=以太网"], c0
    # 关键：静态 IP 用 `static`，绝不能用 `source=static`
    assert c0[6] == "static", c0
    assert "source=static" not in c0, c0
    assert c0[7:10] == ["192.168.2.157", "255.255.255.0", "192.168.2.1"], c0

    c1 = CAPTURED[1]
    assert c1[:4] == ["netsh", "interface", "ipv4", "set"], c1
    assert "dnsservers" in c1 and "static" in c1, c1
    assert "114.114.114.114" in c1 and "name=以太网" in c1, c1

    c2 = CAPTURED[2]
    assert c2[:4] == ["netsh", "interface", "ipv4", "add"], c2
    assert "dnsservers" in c2 and "name=以太网" in c2, c2
    assert "8.8.8.8" in c2 and "index=2" in c2, c2
    print("OK  apply_profile 命令正确")
    for c in CAPTURED:
        print("   ", net_tools._fmt_cmd(c))


def test_apply_no_gateway():
    CAPTURED.clear()
    p = dict(PROFILE, gateway="")
    net_tools.apply_profile("以太网", p)
    c0 = CAPTURED[0]
    assert c0[-1] == "none", c0
    print("OK  无网关 -> none")


def test_apply_no_dns():
    CAPTURED.clear()
    p = dict(PROFILE, dns1="", dns2="")
    net_tools.apply_profile("以太网", p)
    assert len(CAPTURED) == 2, CAPTURED
    c1 = CAPTURED[1]
    assert c1[:4] == ["netsh", "interface", "ipv4", "set"], c1
    assert "dnsservers" in c1 and c1[-1] == "dhcp", c1
    print("OK  无 DNS -> 自动获取")


def test_dhcp():
    CAPTURED.clear()
    net_tools.set_dhcp("WLAN")
    assert len(CAPTURED) == 2, CAPTURED
    assert CAPTURED[0][-1] == "dhcp" and CAPTURED[0][4] == "address", CAPTURED[0]
    assert CAPTURED[1][-1] == "dhcp" and CAPTURED[1][4] == "dnsservers", CAPTURED[1]
    # DHCP 才用 source=dhcp 的形式（这里是位置参数 dhcp，等价且兼容）
    print("OK  set_dhcp 命令正确")


def test_invalid_ip_rejected():
    for bad in [dict(PROFILE, ip="192.168.2.300"),
                dict(PROFILE, gateway="999.1.1.1"),
                dict(PROFILE, dns1="...")]:
        try:
            net_tools.apply_profile("以太网", bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"should reject: {bad}")
    print("OK  非法输入被拦截")


if __name__ == "__main__":
    test_apply_full()
    test_apply_no_gateway()
    test_apply_no_dns()
    test_dhcp()
    test_invalid_ip_rejected()
    print("\nALL COMMAND TESTS PASSED")
