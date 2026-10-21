# -*- coding: utf-8 -*-
"""
方案持久化存储。数据保存到用户目录下的 ip_profiles.json。
"""
import json
import os
import sys

DEFAULT_PROFILES = [
    {
        "name": "示例-办公网",
        "mode": "static",
        "ip": "192.168.1.100",
        "mask": "255.255.255.0",
        "gateway": "192.168.1.1",
        "dns1": "114.114.114.114",
        "dns2": "8.8.8.8",
    },
]


class ProfileStore:
    def __init__(self, filename="ip_profiles.json"):
        # 打包后 __file__ 指向临时解压目录，必须用 exe 所在目录，
        # 否则方案存不进去、每次启动都回到示例数据。
        if getattr(sys, "frozen", False):
            base = os.path.dirname(sys.executable)
        else:
            base = os.path.dirname(os.path.abspath(__file__))
        self.path = os.path.join(base, filename)

    def load(self):
        if not os.path.exists(self.path):
            return [dict(p) for p in DEFAULT_PROFILES]
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return data
        except Exception:
            pass
        return [dict(p) for p in DEFAULT_PROFILES]

    def save(self, profiles):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(profiles, f, ensure_ascii=False, indent=2)
