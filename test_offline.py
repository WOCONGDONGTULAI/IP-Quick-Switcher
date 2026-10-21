# -*- coding: utf-8 -*-
"""
脱机测试：验证 netsh 输出解析、IP 校验、命令拼装。
在 macOS / Linux 上也能跑（不依赖 Windows）。
"""
import re
import sys

sys.path.insert(0, ".")

from net_tools import parse_interface_table, valid_ip

# ---- 真实中文系统输出样例 ----
SAMPLE_CN = """
Idx     Met         MTU          状态                名称
---  ----------  ----------  ------------  ---------------------------
  1          75  4294967295  connected     Loopback Pseudo-Interface 1
 14          25        1500  disconnected  以太网
  7          35        1500  connected     WLAN
 18          15        1500  connected     以太网 2
"""

# ---- 真实英文系统输出样例 ----
SAMPLE_EN = """

Idx     Met         MTU          State                Name
---  ----------  ----------  ------------  ---------------------------
  1          75  4294967295  connected     Loopback Pseudo-Interface 1
 12          25        1500  connected     Ethernet
  9          35        1500  connected     Wi-Fi
"""


def test_parse_cn():
    res = parse_interface_table(SAMPLE_CN)
    names = [r["name"] for r in res]
    assert "Loopback Pseudo-Interface 1" in names, names
    assert "以太网" in names, names
    assert "以太网 2" in names, names
    assert "WLAN" in names, names
    # 名称含空格不能被截断
    assert res[0]["name"] == "Loopback Pseudo-Interface 1", res[0]
    assert res[0]["state"] == "connected"
    assert res[0]["idx"] == 1
    print("OK  parse cn:", names)


def test_parse_en():
    res = parse_interface_table(SAMPLE_EN)
    names = [r["name"] for r in res]
    assert "Ethernet" in names, names
    assert "Wi-Fi" in names, names
    print("OK  parse en:", names)


def test_valid_ip():
    good = ["192.168.1.1", "10.0.0.254", "255.255.255.0", "8.8.8.8", "0.0.0.0"]
    bad = ["192.168.1", "192.168.1.256", "192.168.1.-1", "abc.d.e.f",
           "192.168.1.1.1", "256.1.1.1", "01.1.1.1", "", "192.168.1."]
    for g in good:
        assert valid_ip(g), f"should be valid: {g}"
    for b in bad:
        assert not valid_ip(b), f"should be invalid: {b!r}"
    assert not valid_ip("", allow_empty=False)
    assert valid_ip("", allow_empty=True)
    print("OK  valid_ip")


if __name__ == "__main__":
    test_parse_cn()
    test_parse_en()
    test_valid_ip()
    print("\nALL TESTS PASSED")
