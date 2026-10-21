# -*- coding: utf-8 -*-
"""
脱机测试：验证 netsh 输出解析、IP 校验、命令拼装。
在 macOS / Linux 上也能跑（不依赖 Windows）。
"""
import re
import sys

sys.path.insert(0, ".")

import net_tools
from net_tools import parse_interface_table, valid_ip, parse_config_kv, prefix_to_mask, get_status

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


# ---- 中文 Windows: netsh interface ipv4 show config ----
CONFIG_CN = '''
接口 "以太网" 的配置
    DHCP 已启用:                          是
    IP 地址:                              192.168.1.100
    子网前缀:                             192.168.1.0/24 (掩码 255.255.255.0)
    默认网关:                             192.168.1.1
    网关跃点数:                           0
    InterfaceMetric:                      25
    静态配置的 DNS 服务器:                114.114.114.114
                                          8.8.8.8
    用哪个后缀注册:                       仅主要
    通过 DHCP 配置的 WINS 服务器:         无
'''

# ---- 英文 Windows ----
CONFIG_EN = '''
Configuration for interface "Ethernet"
    DHCP enabled:                         Yes
    IP Address:                           192.168.2.157
    Subnet Prefix:                        192.168.2.0/24 (mask 255.255.255.0)
    Default Gateway:                      192.168.2.1
    Gateway Metric:                       0
    InterfaceMetric:                      25
    Statically Configured DNS Servers:    8.8.8.8
                                          1.1.1.1
    Register with which suffix:           Primary only
    WINS servers configured through DHCP: None
'''

# ---- 静态 IP，多个 IP，DHCP 关闭 ----
CONFIG_STATIC = '''
接口 "以太网" 的配置
    DHCP 已启用:                          否
    IP 地址:                              10.0.0.5
                                          10.0.0.6
    子网前缀:                             10.0.0.0/8 (掩码 255.0.0.0)
    默认网关:                             10.0.0.1
    静态配置的 DNS 服务器:                10.0.0.2
'''


def _stub(status_text):
    def fake_run(cmd):
        return 0, status_text, ""
    net_tools._run = fake_run


def test_prefix_to_mask():
    assert prefix_to_mask("192.168.1.0/24") == "255.255.255.0"
    assert prefix_to_mask("/16") == "255.255.0.0"
    assert prefix_to_mask("/8") == "255.0.0.0"
    assert prefix_to_mask("/32") == "255.255.255.255"
    assert prefix_to_mask("/0") == "0.0.0.0"
    assert prefix_to_mask("nonsense") is None
    assert prefix_to_mask("/33") is None
    print("OK  prefix_to_mask")


def test_parse_config_cn():
    _stub(CONFIG_CN)
    st = get_status("以太网")
    assert st["dhcp"] is True, st
    assert st["ips"] == ["192.168.1.100"], st
    assert st["gateways"] == ["192.168.1.1"], st
    assert st["masks"] == ["255.255.255.0"], st
    # continuation 行的第二个 DNS 必须抓到
    assert st["dns"] == ["114.114.114.114", "8.8.8.8"], st
    print("OK  get_status 中文:", st["ips"], st["dns"])


def test_parse_config_en():
    _stub(CONFIG_EN)
    st = get_status("Ethernet")
    assert st["dhcp"] is True, st
    assert st["ips"] == ["192.168.2.157"], st
    assert st["masks"] == ["255.255.255.0"], st
    assert st["dns"] == ["8.8.8.8", "1.1.1.1"], st
    print("OK  get_status 英文:", st["ips"], st["dns"])


def test_parse_config_static_multi_ip():
    _stub(CONFIG_STATIC)
    st = get_status("以太网")
    assert st["dhcp"] is False, st
    assert st["ips"] == ["10.0.0.5", "10.0.0.6"], st
    assert st["masks"] == ["255.0.0.0"], st
    assert st["dns"] == ["10.0.0.2"], st
    print("OK  get_status 静态多 IP:", st["ips"])


def test_prefix_without_mask_text():
    # 有些系统不在括号里给 mask，只给前缀长度
    _stub('''接口 "以太网" 的配置
    DHCP 已启用:                          否
    IP 地址:                              172.16.5.9
    子网前缀:                             172.16.0.0/16
    默认网关:                             172.16.0.1
''')
    st = get_status("以太网")
    assert st["masks"] == ["255.255.0.0"], st
    print("OK  无显式 mask 也能换算")


if __name__ == "__main__":
    test_parse_cn()
    test_parse_en()
    test_valid_ip()
    test_prefix_to_mask()
    test_parse_config_cn()
    test_parse_config_en()
    test_parse_config_static_multi_ip()
    test_prefix_without_mask_text()
    print("\nALL TESTS PASSED")
