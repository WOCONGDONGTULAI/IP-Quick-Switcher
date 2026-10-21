# -*- coding: utf-8 -*-
"""
IP 切换器 - 桌面贴纸（桌面小组件）

无边框、可拖动、半透明，显示当前网卡 IP 并支持一键切换方案。
右键打开菜单：方案列表 / DHCP / 显示模式 / 透明度 / 退出。

显示模式有三种：
    desktop  嵌入桌面层（默认）—— 随桌面显示，不干扰其他窗口
    top      悬浮置顶        —— 永远盖在其他窗口之上
    normal   普通窗口        —— 会被正常遮挡
"""
import json
import os
import sys
import tkinter as tk
from tkinter import ttk, messagebox

from net_tools import (
    list_interfaces,
    get_status,
    apply_profile,
    set_dhcp,
    is_admin,
    run_as_admin,
)
from config_store import ProfileStore
from tray import TrayIcon, ensure_autostart, is_autostart_enabled, toggle_autostart
from win_desktop import attach as desktop_attach
from win_desktop import detach as desktop_detach
from win_desktop import is_supported as desktop_supported

APP_TITLE = "IP 贴纸"

MODES = {
    "desktop": "嵌入桌面层",
    "top": "悬浮置顶",
    "normal": "普通窗口",
}

BG = "#1e1e1e"
BG_HEADER = "#2d2d2d"
FG = "#d4d4d4"
FG_DIM = "#808080"
ACCENT = "#007acc"
OK = "#4ec9b0"
WARN = "#dcdcaa"

SETTINGS_FILE = "sticker_config.json"


class Settings:
    """贴纸自身的偏好：位置、透明度、显示模式等。"""

    DEFAULTS = {
        "x": None,
        "y": None,
        "alpha": 0.92,
        # 桌面层模式依赖 Explorer，部分机器资源管理器未就绪时贴纸会不可见；
        # 默认改为悬浮置顶，保证一启动就能看见，用户可右键改回桌面层。
        "mode": "top",
        "auto_refresh": True,
        "refresh_ms": 5000,
    }

    def __init__(self, path=None):
        # 打包后 __file__ 指向临时解压目录，配置必须在 exe 旁边才留得住
        if path:
            self.path = path
        elif getattr(sys, "frozen", False):
            self.path = os.path.join(os.path.dirname(sys.executable), SETTINGS_FILE)
        else:
            self.path = os.path.join(os.path.dirname(os.path.abspath(__file__)), SETTINGS_FILE)
        self.data = dict(self.DEFAULTS)
        stored = None
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    stored = json.load(f)
            except Exception:
                stored = None
        if isinstance(stored, dict):
            self.data.update(stored)
            # 旧版配置只有 always_on_top 布尔值，迁移到新的三档模式。
            # 注意判断依据是「旧配置里有没有 always_on_top」，不能看 mode 是否存在——
            # 因为 DEFAULTS 里已经带了 mode，那样判断永远不成立。
            if "mode" not in stored and "always_on_top" in stored:
                self.data["mode"] = "top" if stored["always_on_top"] else "desktop"

    def save(self):
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass


class Sticker(tk.Tk):
    def __init__(self):
        super().__init__()
        self.settings = Settings()
        self.store = ProfileStore()
        self.interfaces = []
        self.current_iface = ""
        self._drag = {"x": 0, "y": 0}
        self._attached = False

        self._build_ui()
        self._apply_window_attrs()
        self._apply_mode()

        # 托盘图标：贴纸关掉后还能从托盘唤回；并写入开机自启
        self.tray = TrayIcon(self, tip="IP 快速切换器 - 贴纸")
        ensure_autostart()
        self._load_position()
        self.refresh_interfaces()
        self.schedule_refresh()

    # ---------------- 窗口属性 ----------------
    def _apply_window_attrs(self):
        # 无边框：贴纸的关键，去掉标题栏和窗口边框
        self.overrideredirect(True)
        try:
            self.attributes("-alpha", self.settings.data["alpha"])
        except Exception:
            pass
        try:
            self.attributes("-topmost", self.settings.data["mode"] == "top")
        except Exception:
            pass
        # Windows 专用：不在任务栏显示
        try:
            self.attributes("-toolwindow", True)
        except Exception:
            pass
        self.configure(bg=BG)
        self.resizable(False, False)

    def _hwnd(self):
        """取窗口句柄；非 Windows 返回 0。"""
        if not desktop_supported():
            return 0
        try:
            self.update_idletasks()
            return int(self.frame(), 16)
        except Exception:
            return 0

    def _apply_mode(self):
        """按当前模式落到对应的窗口层级。"""
        mode = self.settings.data.get("mode", "desktop")
        try:
            self.attributes("-topmost", mode == "top")
        except Exception:
            pass
        if mode != "desktop":
            if self._attached:
                desktop_detach(self._hwnd())
                self._attached = False
            return
        # 桌面模式下不能有 -topmost，二者互斥
        if not self._attached:
            self._attached = desktop_attach(self._hwnd())

    def _load_position(self):
        # 先给个默认几何，再按上次记忆的位置摆放
        self.update_idletasks()
        w, h = 240, 132
        x = self.settings.data.get("x")
        y = self.settings.data.get("y")
        if x is None or y is None:
            x = self.winfo_screenwidth() - w - 20
            y = self.winfo_screenheight() - h - 60
        # 位置越界（比如换了显示器）就拉回屏幕内
        x = max(0, min(int(x), self.winfo_screenwidth() - 40))
        y = max(0, min(int(y), self.winfo_screenheight() - 40))
        self.geometry(f"{w}x{h}+{x}+{y}")

    # ---------------- UI ----------------
    def _build_ui(self):
        header = tk.Frame(self, bg=BG_HEADER, height=26)
        header.pack(fill=tk.X)
        header.pack_propagate(False)

        self.dot = tk.Label(header, text="●", bg=BG_HEADER, fg=OK, font=("Segoe UI", 9))
        self.dot.pack(side=tk.LEFT, padx=(8, 4))
        # 按需求：不要标题文字，只留状态点，靠 ≡ 菜单操作
        self._drag_bind(header)

        btn_close = tk.Label(header, text="×", bg=BG_HEADER, fg=FG_DIM,
                             font=("Segoe UI", 12), cursor="hand2")
        btn_close.pack(side=tk.RIGHT, padx=(0, 8))
        btn_close.bind("<Button-1>", lambda e: self.on_close())
        btn_close.bind("<Enter>", lambda e: btn_close.config(fg="#f48771"))
        btn_close.bind("<Leave>", lambda e: btn_close.config(fg=FG_DIM))

        btn_menu = tk.Label(header, text="≡", bg=BG_HEADER, fg=FG_DIM,
                            font=("Segoe UI", 13), cursor="hand2")
        btn_menu.pack(side=tk.RIGHT, padx=6)
        btn_menu.bind("<Button-1>", lambda e: self.show_menu(e))
        btn_menu.bind("<Enter>", lambda e: btn_menu.config(fg=FG))
        btn_menu.bind("<Leave>", lambda e: btn_menu.config(fg=FG_DIM))

        body = tk.Frame(self, bg=BG)
        body.pack(fill=tk.BOTH, expand=True, padx=10, pady=(6, 0))

        self.lbl_iface = tk.Label(body, text="—", bg=BG, fg=FG_DIM, anchor=tk.W,
                                  font=("Microsoft YaHei UI", 8))
        self.lbl_iface.pack(fill=tk.X)

        self.lbl_ip = tk.Label(body, text="读取中…", bg=BG, fg=FG, anchor=tk.W,
                               font=("Consolas", 15, "bold"))
        self.lbl_ip.pack(fill=tk.X)

        self.lbl_gw = tk.Label(body, text="", bg=BG, fg=FG_DIM, anchor=tk.W,
                               font=("Microsoft YaHei UI", 8))
        self.lbl_gw.pack(fill=tk.X)

        bar = tk.Frame(self, bg=BG)
        bar.pack(fill=tk.X, padx=8, pady=6)
        for text, cmd in (("方案", lambda: self.show_menu()),
                          ("DHCP", self.apply_dhcp),
                          ("刷新", self.refresh_status)):
            b = tk.Label(bar, text=text, bg="#333333", fg=FG, padx=10, pady=2,
                         font=("Microsoft YaHei UI", 8), cursor="hand2")
            b.pack(side=tk.LEFT, padx=(0, 5))
            b.bind("<Button-1>", lambda e, c=cmd: c())
            b.bind("<Enter>", lambda e, b=b: b.config(bg=ACCENT))
            b.bind("<Leave>", lambda e, b=b: b.config(bg="#333333"))

        # 让正文也能拖动，但按钮不参与
        for wgt in (body, self.lbl_iface, self.lbl_ip, self.lbl_gw, bar):
            self._drag_bind(wgt)
        # 任意位置右键都出菜单
        for cls in (self, header, body):
            cls.bind("<Button-3>", lambda e: self.show_menu(e))
        self.bind("<Escape>", lambda e: self.on_close())

    def _drag_bind(self, widget):
        widget.bind("<ButtonPress-1>", self._drag_start)
        widget.bind("<B1-Motion>", self._drag_move)

    def _drag_start(self, event):
        self._drag["x"] = event.x_root - self.winfo_x()
        self._drag["y"] = event.y_root - self.winfo_y()

    def _drag_move(self, event):
        self.geometry(f"+{event.x_root - self._drag['x']}+{event.y_root - self._drag['y']}")

    # ---------------- 右键菜单 ----------------
    def show_menu(self, event=None):
        menu = tk.Menu(self, tearoff=0, bg="#252526", fg=FG,
                       activebackground=ACCENT, activeforeground="#ffffff",
                       borderwidth=0, relief="flat")

        menu.add_command(label=f"网卡：{self._iface_name()}", state="disabled")
        menu.add_separator()

        menu.add_command(label="刷新", command=self.refresh_status)
        menu.add_separator()

        profiles = self.store.load()
        if profiles:
            for i, p in enumerate(profiles):
                menu.add_command(label=f"  切换到 {p.get('name')}",
                                 command=lambda pf=p: self.apply_profile(pf))
        else:
            menu.add_command(label="（暂无方案，请用完整版添加）", state="disabled")
        menu.add_command(label="切换到 DHCP", command=self.apply_dhcp)
        menu.add_separator()

        ar_var = tk.BooleanVar(value=self.settings.data["auto_refresh"])
        mode_var = tk.StringVar(value=self.settings.data.get("mode", "desktop"))

        sub_opacity = tk.Menu(menu, tearoff=0, bg="#252526", fg=FG,
                              activebackground=ACCENT, activeforeground="#ffffff")
        for value in (0.5, 0.7, 0.85, 0.92, 1.0):
            sub_opacity.add_command(label=f"{int(value * 100)}%",
                                    command=lambda v=value: self.set_opacity(v))

        # 显示模式三选一；桌面嵌入在不支持的系统（非 Windows）上禁用
        sub_mode = tk.Menu(menu, tearoff=0, bg="#252526", fg=FG,
                           activebackground=ACCENT, activeforeground="#ffffff")
        for key, label in MODES.items():
            state = "normal" if (key != "desktop" or desktop_supported()) else "disabled"
            if key == "desktop":
                label = f"{label}（推荐）"
            sub_mode.add_radiobutton(label=label, variable=mode_var, value=key,
                                     command=lambda k=key: self.set_mode(k),
                                     state=state)
        if self.settings.data.get("mode") == "desktop" and not self._attached:
            sub_mode.add_separator()
            sub_mode.add_command(label="重新贴回桌面", command=self.reattach_desktop)

        menu.add_cascade(label="显示模式", menu=sub_mode)
        menu.add_checkbutton(label="自动刷新", variable=ar_var,
                             command=lambda: self.toggle_auto_refresh())
        menu.add_cascade(label="透明度", menu=sub_opacity)
        menu.add_separator()

        if not is_admin():
            menu.add_command(label="以管理员重启", command=self.relaunch_admin)
        menu.add_command(label="管理方案…", command=self.open_manager)
        menu.add_separator()

        # 开机自启开关（★ 表示当前已开启）
        _on = is_autostart_enabled()
        menu.add_checkbutton(
            label="开机自动运行",
            command=self.toggle_autostart_entry,
        )
        menu.add_separator()
        menu.add_command(label="退出", command=self.quit_app)

        if event:
            menu.tk_popup(event.x_root, event.y_root)
        else:
            menu.tk_popup(self.winfo_rootx() + 10, self.winfo_rooty() + 30)

    # ---------------- 数据 ----------------
    def refresh_interfaces(self):
        try:
            self.interfaces = list_interfaces()
        except Exception:
            self.interfaces = []
        self.current_iface = self.interfaces[0]["name"] if self.interfaces else ""
        self.refresh_status()

    def _iface_name(self):
        return self.current_iface or "（无网卡）"

    def refresh_status(self):
        if not self.current_iface:
            self.lbl_ip.config(text="无网卡", fg=WARN)
            self.dot.config(fg=WARN)
            return
        try:
            st = get_status(self.current_iface)
        except Exception as e:
            self.lbl_ip.config(text="读取失败", fg=WARN)
            self.dot.config(fg=WARN)
            self.lbl_gw.config(text=str(e)[:40])
            return

        ips = st["ips"]
        if ips:
            self.lbl_ip.config(text=ips[0], fg=FG)
            extra = f" +{len(ips) - 1}" if len(ips) > 1 else ""
            self.dot.config(fg=OK)
        else:
            self.lbl_ip.config(text="未分配", fg=WARN)
            extra = ""
            self.dot.config(fg=WARN)

        gw = st["gateways"][0] if st["gateways"] else "—"
        mode = "DHCP" if st["dhcp"] else "静态"
        self.lbl_iface.config(text=f"{st['interface']}  ·  {mode}{extra}")
        self.lbl_gw.config(text=f"网关 {gw}")

    def schedule_refresh(self):
        if self.settings.data["auto_refresh"]:
            self.refresh_status()
            # Explorer 重启会让桌面附着失效，趁着刷新周期补回来
            if self.settings.data.get("mode") == "desktop" and not self._attached:
                self._attached = desktop_attach(self._hwnd())
        self.after(self.settings.data["refresh_ms"], self.schedule_refresh)

    # ---------------- 操作 ----------------
    def apply_profile(self, profile):
        name = profile.get("name")
        if not messagebox.askyesno("确认", f"切换到方案「{name}」？", parent=self):
            return
        try:
            apply_profile(self._iface_name(), profile)
        except Exception as e:
            messagebox.showerror("失败", str(e), parent=self)
            return
        self.refresh_status()

    def apply_dhcp(self):
        if not messagebox.askyesno("确认", "切换到自动获取 (DHCP)？", parent=self):
            return
        try:
            set_dhcp(self._iface_name())
        except Exception as e:
            messagebox.showerror("失败", str(e), parent=self)
            return
        self.refresh_status()

    def set_opacity(self, value):
        self.settings.data["alpha"] = value
        try:
            self.attributes("-alpha", value)
        except Exception:
            pass
        self.settings.save()

    def set_mode(self, mode):
        if mode not in MODES:
            return
        self.settings.data["mode"] = mode
        self.settings.save()
        self._apply_mode()
        # 解除附着后可能缩到后面，重新提一下
        if mode != "desktop":
            try:
                self.lift()
            except Exception:
                pass

    def reattach_desktop(self):
        """Explorer 重启后附着会失效，用它重新贴回去。"""
        self._attached = desktop_attach(self._hwnd())
        if not self._attached:
            messagebox.showwarning("贴回桌面失败",
                                   "没有找到桌面窗口。请确认 Windows 资源管理器正在运行。",
                                   parent=self)

    def toggle_auto_refresh(self):
        self.settings.data["auto_refresh"] = not self.settings.data["auto_refresh"]
        self.settings.save()

    def relaunch_admin(self):
        if run_as_admin():
            self.on_close()
        else:
            messagebox.showerror("失败", "提权失败，请手动右键以管理员身份运行", parent=self)

    def open_manager(self):
        """打开完整版管理界面（开发态跑 app.py，打包态提示用另一个 exe）。"""
        import subprocess
        import sys
        if getattr(sys, "frozen", False):
            messagebox.showinfo("管理方案", "请运行同目录下的 IPSwitcher.exe 管理方案", parent=self)
            return
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.py")
        if os.path.exists(path):
            subprocess.Popen([sys.executable, path])
        else:
            messagebox.showinfo("提示", "未找到 app.py", parent=self)

    def on_close(self):
        """点 × 收进托盘，托盘菜单里可真正退出。"""
        self.settings.data["x"] = self.winfo_x()
        self.settings.data["y"] = self.winfo_y()
        self.settings.save()
        self.withdraw()

    def quit_app(self):
        """托盘菜单「退出」：保存位置后彻底结束。"""
        try:
            self.settings.data["x"] = self.winfo_x()
            self.settings.data["y"] = self.winfo_y()
            self.settings.save()
        except Exception:
            pass
        try:
            self.tray.stop()
        except Exception:
            pass
        self.destroy()

    def toggle_autostart_entry(self):
        """菜单里开关开机自启。"""
        enabled = is_autostart_enabled()
        if toggle_autostart(not enabled):
            messagebox.showinfo(
                "开机自启",
                "已开启开机自动运行" if not enabled else "已关闭开机自动运行",
                parent=self,
            )
        else:
            messagebox.showerror("失败", "写入注册表失败，请检查权限", parent=self)


if __name__ == "__main__":
    Sticker().mainloop()
