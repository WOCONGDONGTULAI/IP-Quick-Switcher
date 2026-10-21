# -*- coding: utf-8 -*-
"""
IP 快速切换器 - Windows
图形界面入口
"""
import tkinter as tk
from tkinter import ttk, messagebox

from net_tools import (
    list_interfaces,
    get_current_config,
    apply_profile,
    set_dhcp,
    is_admin,
    run_as_admin,
)
from config_store import ProfileStore

APP_TITLE = "IP 快速切换器"


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("860x560")
        self.resizable(True, True)

        self.store = ProfileStore()
        self.profiles = self.store.load()
        self.interfaces = []

        self._build_ui()
        self._refresh_interfaces()
        self._refresh_profile_list()

        if not is_admin():
            self.status_var.set("提示：当前不是管理员，切换 IP 可能失败。建议右键以管理员身份运行。")

    # ---------------- UI ----------------
    def _build_ui(self):
        pad = {"padx": 8, "pady": 4}

        top = ttk.Frame(self)
        top.pack(fill=tk.X, **pad)

        ttk.Label(top, text="网卡:").pack(side=tk.LEFT)
        self.iface_var = tk.StringVar()
        self.iface_combo = ttk.Combobox(top, textvariable=self.iface_var, width=42, state="readonly")
        self.iface_combo.pack(side=tk.LEFT)
        self.iface_combo.bind("<<ComboboxSelected>>", lambda e: self._show_current())

        ttk.Button(top, text="刷新网卡", command=self._refresh_interfaces).pack(side=tk.LEFT, padx=4)
        ttk.Button(top, text="当前配置", command=self._show_current).pack(side=tk.LEFT, padx=4)
        ttk.Button(top, text="以管理员重启", command=self._relaunch_admin).pack(side=tk.LEFT, padx=4)

        body = ttk.Frame(self)
        body.pack(fill=tk.BOTH, expand=True, **pad)

        left = ttk.Frame(body)
        left.pack(side=tk.LEFT, fill=tk.Y)

        ttk.Label(left, text="预设方案").pack(anchor=tk.W)
        self.plist = tk.Listbox(left, width=32, height=18)
        self.plist.pack(fill=tk.Y, expand=True)
        self.plist.bind("<<ListboxSelect>>", lambda e: self._select_profile())

        btns = ttk.Frame(left)
        btns.pack(fill=tk.X, pady=4)
        ttk.Button(btns, text="应用选中", command=self._apply_selected).pack(fill=tk.X, pady=2)
        ttk.Button(btns, text="新增", command=self._new_profile).pack(fill=tk.X, pady=2)
        ttk.Button(btns, text="保存", command=self._save_profile).pack(fill=tk.X, pady=2)
        ttk.Button(btns, text="删除", command=self._delete_profile).pack(fill=tk.X, pady=2)
        ttk.Button(btns, text="切换到 DHCP", command=self._apply_dhcp).pack(fill=tk.X, pady=2)

        right = ttk.Frame(body)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(10, 0))

        form = ttk.LabelFrame(right, text="方案详情")
        form.pack(fill=tk.X)

        self.f_name = tk.StringVar()
        self.f_ip = tk.StringVar()
        self.f_mask = tk.StringVar()
        self.f_gw = tk.StringVar()
        self.f_dns1 = tk.StringVar()
        self.f_dns2 = tk.StringVar()

        rows = [
            ("名称", self.f_name),
            ("IP 地址", self.f_ip),
            ("子网掩码", self.f_mask),
            ("默认网关", self.f_gw),
            ("首选 DNS", self.f_dns1),
            ("备用 DNS", self.f_dns2),
        ]
        for i, (label, var) in enumerate(rows):
            ttk.Label(form, text=label).grid(row=i, column=0, sticky=tk.W, padx=6, pady=3)
            ttk.Entry(form, textvariable=var, width=34).grid(row=i, column=1, sticky=tk.W, padx=6, pady=3)

        out = ttk.LabelFrame(right, text="输出")
        out.pack(fill=tk.BOTH, expand=True, pady=6)
        self.log = tk.Text(out, height=12, wrap=tk.WORD)
        self.log.pack(fill=tk.BOTH, expand=True)
        self.log.configure(state=tk.DISABLED)

        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(self, textvariable=self.status_var, anchor=tk.W, relief=tk.SUNKEN).pack(fill=tk.X, side=tk.BOTTOM)

    # ---------------- 逻辑 ----------------
    def _append_log(self, text):
        self.log.configure(state=tk.NORMAL)
        self.log.insert(tk.END, text + "\n")
        self.log.see(tk.END)
        self.log.configure(state=tk.DISABLED)

    def _refresh_interfaces(self):
        try:
            ifaces = list_interfaces()
        except Exception as e:
            messagebox.showerror("错误", f"获取网卡列表失败：{e}")
            return
        self.interfaces = ifaces
        labels = []
        for it in ifaces:
            state = it.get("state", "")
            cn = {"connected": "已连接", "disconnected": "未连接"}.get(state, state)
            labels.append(f"{it['name']}  ({cn})" if cn else it["name"])
        self.iface_combo["values"] = labels
        if ifaces:
            self.iface_combo.current(0)
        self._append_log(f"发现 {len(ifaces)} 个网卡")

    def _current_iface(self):
        idx = self.iface_combo.current()
        if idx < 0 or idx >= len(self.interfaces):
            return None
        return self.interfaces[idx]["name"]

    def _show_current(self):
        name = self._current_iface()
        if not name:
            return
        try:
            cfg = get_current_config(name)
        except Exception as e:
            self._append_log(f"读取失败：{e}")
            return
        self._append_log("—— 当前配置 ——")
        for line in cfg:
            self._append_log(line)

    def _select_profile(self):
        sel = self.plist.curselection()
        if not sel:
            return
        p = self.profiles[sel[0]]
        self.f_name.set(p.get("name", ""))
        self.f_ip.set(p.get("ip", ""))
        self.f_mask.set(p.get("mask", "255.255.255.0"))
        self.f_gw.set(p.get("gateway", ""))
        self.f_dns1.set(p.get("dns1", ""))
        self.f_dns2.set(p.get("dns2", ""))

    def _refresh_profile_list(self):
        self.plist.delete(0, tk.END)
        for p in self.profiles:
            tag = "静态" if p.get("mode", "static") == "static" else "DHCP"
            self.plist.insert(tk.END, f"[{tag}] {p.get('name')}")

    def _collect_form(self):
        return {
            "name": self.f_name.get().strip(),
            "mode": "static",
            "ip": self.f_ip.get().strip(),
            "mask": self.f_mask.get().strip() or "255.255.255.0",
            "gateway": self.f_gw.get().strip(),
            "dns1": self.f_dns1.get().strip(),
            "dns2": self.f_dns2.get().strip(),
        }

    def _new_profile(self):
        self.f_name.set("新方案")
        self.f_ip.set("")
        self.f_mask.set("255.255.255.0")
        self.f_gw.set("")
        self.f_dns1.set("")
        self.f_dns2.set("")

    def _save_profile(self):
        data = self._collect_form()
        if not data["name"]:
            messagebox.showwarning("提示", "请填写方案名称")
            return
        if not data["ip"]:
            messagebox.showwarning("提示", "请填写 IP 地址")
            return
        sel = self.plist.curselection()
        if sel:
            self.profiles[sel[0]] = data
        else:
            self.profiles.append(data)
        self.store.save(self.profiles)
        self._refresh_profile_list()
        self.status_var.set("已保存")

    def _delete_profile(self):
        sel = self.plist.curselection()
        if not sel:
            return
        if not messagebox.askyesno("确认", "确定删除该方案？"):
            return
        del self.profiles[sel[0]]
        self.store.save(self.profiles)
        self._refresh_profile_list()

    def _apply_selected(self):
        sel = self.plist.curselection()
        if not sel:
            messagebox.showwarning("提示", "请先选择一个方案")
            return
        p = self.profiles[sel[0]]
        name = self._current_iface()
        if not name:
            return
        if not messagebox.askyesno("确认", f"将网卡「{name}」切换到方案「{p.get('name')}」？"):
            return
        self._do_apply(name, p)

    def _apply_dhcp(self):
        name = self._current_iface()
        if not name:
            return
        if not messagebox.askyesno("确认", f"将网卡「{name}」改为自动获取(DHCP)？"):
            return
        try:
            out = set_dhcp(name)
        except Exception as e:
            messagebox.showerror("失败", str(e))
            self._append_log(f"错误：{e}")
            return
        self._append_log("—— 切换 DHCP ——")
        self._append_log(out)
        self.status_var.set("已切换到 DHCP")

    def _do_apply(self, iface, p):
        try:
            out = apply_profile(iface, p)
        except Exception as e:
            messagebox.showerror("失败", str(e))
            self._append_log(f"错误：{e}")
            return
        self._append_log(f"—— 应用方案 {p.get('name')} ——")
        self._append_log(out)
        self.status_var.set("已应用")
        self._show_current()

    def _relaunch_admin(self):
        if is_admin():
            messagebox.showinfo("提示", "已经是管理员权限")
            return
        ok = run_as_admin()
        if ok:
            self.destroy()
        else:
            messagebox.showerror("失败", "提权失败，请手动右键以管理员身份运行")


if __name__ == "__main__":
    App().mainloop()
