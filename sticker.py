# -*- coding: utf-8 -*-
"""
IP 切换器 - 桌面贴纸（前端显示）

职责收窄：**只负责显示**
    - 列出所有方案，当前选中的方案名前带一个小绿点
    - 点击某个方案即切换到该方案
    - 可以拖动位置、拖右下角改变大小
    - 「固定」模式（由主界面控制）下，拖动和缩放都锁死，只剩点击切换

所有设置（显示模式 / 透明度 / 大小 / 固定 / 位置）都由主界面写入
sticker_config.json，贴纸只读+ 监听该文件变化，不会自己改配置。
"""
import ctypes
import json
import os
import sys
import tkinter as tk

from net_tools import list_interfaces, apply_profile, set_dhcp, get_status, is_admin
from config_store import ProfileStore
from win_desktop import attach as desktop_attach
from win_desktop import detach as desktop_detach
from win_desktop import is_supported as desktop_supported
from tray import TrayIcon

SETTINGS_FILE = "sticker_config.json"

# 磨砂玻璃深色主题（文字浅色，选中开关反色高亮）
BG = "#232329"            # 磨砂底色基调（与 DWM 渐变一致）
BG_ITEM = "#232329"
BG_ITEM_HOVER = "#2e2e36"
FG = "#f2f2f4"
FG_DIM = "#a8a8b0"
GREEN = "#4caf50"
TOGGLE_OFF_BG = "#3b3b44"   # 未选中开关：深色胶囊
TOGGLE_OFF_KNOB = "#f2f2f4" # 未选中圆点：白色
TOGGLE_ON_BG = "#f2f2f4"    # 选中开关：反色为浅色胶囊
TOGGLE_ON_KNOB = "#232329"  # 选中圆点：深色


def enable_acrylic(hwnd, alpha=0.80):
    """Windows 10/11 磨砂玻璃（亚克力模糊）背景。

    gradient 的 alpha 通道承担透明度 —— 窗口级 -alpha 会禁用模糊，不能用。
    """
    if not hwnd:
        return False
    try:
        hwnd = int(hwnd)
    except Exception:
        return False

    class ACCENT_POLICY(ctypes.Structure):
        _fields_ = [
            ("AccentState", ctypes.c_int),
            ("AccentFlags", ctypes.c_int),
            ("GradientColor", ctypes.c_uint),
            ("AnimationId", ctypes.c_int),
            ("BlurRegionId", ctypes.c_int),
        ]

    class WINCOMPATTRDATA(ctypes.Structure):
        _fields_ = [
            ("Attribute", ctypes.c_int),
            ("Data", ctypes.c_void_p),
            ("SizeOfData", ctypes.c_size_t),
        ]

    r, g, b = 0x23, 0x23, 0x29          # 与 BG 一致
    a = max(0, min(255, int(alpha * 255)))
    gradient = (a << 24) | (b << 16) | (g << 8) | r   # ABGR

    accent = ACCENT_POLICY()
    accent.AccentState = 4               # ACCENT_ENABLE_ACRYLICBLURBEHIND
    accent.AccentFlags = 2
    accent.GradientColor = gradient
    data = WINCOMPATTRDATA()
    data.Attribute = 19                  # WINDOWCOMPOSITIONATTRIB_ACCENT
    data.Data = ctypes.cast(ctypes.byref(accent), ctypes.c_void_p)
    data.SizeOfData = ctypes.sizeof(accent)
    try:
        return bool(ctypes.windll.user32.SetWindowCompositionAttribute(
            hwnd, ctypes.byref(data)))
    except Exception:
        return False


def disable_composition(hwnd):
    hwnd = int(hwnd) if hwnd else 0
    if not hwnd:
        return False
    class ACCENT_POLICY(ctypes.Structure):
        _fields_ = [
            ("AccentState", ctypes.c_int),
            ("AccentFlags", ctypes.c_int),
            ("GradientColor", ctypes.c_uint),
            ("AnimationId", ctypes.c_int),
            ("BlurRegionId", ctypes.c_int),
        ]

    class WINCOMPATTRDATA(ctypes.Structure):
        _fields_ = [
            ("Attribute", ctypes.c_int),
            ("Data", ctypes.c_void_p),
            ("SizeOfData", ctypes.c_size_t),
        ]

    accent = ACCENT_POLICY()
    accent.AccentState = 0
    data = WINCOMPATTRDATA()
    data.Attribute = 19
    data.Data = ctypes.cast(ctypes.byref(accent), ctypes.c_void_p)
    data.SizeOfData = ctypes.sizeof(accent)
    try:
        return bool(ctypes.windll.user32.SetWindowCompositionAttribute(
            hwnd, ctypes.byref(data)))
    except Exception:
        return False


def _app_dir():
    """配置和方案都放 exe 同级（打包后也一样），源码运行时是脚本目录。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


class Settings:
    """只读贴纸设置 + 监听主界面的改动。"""

    DEFAULTS = {
        "enabled": True,
        "x": None,
        "y": None,
        "w": 220,
        "h": None,          # None = 按方案数自适应
        "alpha": 0.92,
        "mode": "top",      # desktop / top / normal
        "fixed": False,     # 固定后不能拖动/缩放
    }

    def __init__(self, path=None):
        self.path = path or os.path.join(_app_dir(), SETTINGS_FILE)
        self.data = dict(self.DEFAULTS)
        self._mtime = 0.0
        self.load()

    def load(self):
        try:
            if os.path.exists(self.path):
                self._mtime = os.path.getmtime(self.path)
                with open(self.path, "r", encoding="utf-8") as f:
                    stored = json.load(f)
                if isinstance(stored, dict):
                    self.data.update(stored)
        except Exception:
            pass
        return self.data

    def reload_if_changed(self):
        """主界面改过配置就重载。返回是否变了。"""
        try:
            m = os.path.getmtime(self.path)
        except OSError:
            return False
        if m != self._mtime:
            self._mtime = m
            self.load()
            return True
        return False


class Sticker(tk.Tk):
    def __init__(self):
        super().__init__()
        self.settings = Settings()
        self.store = ProfileStore()
        self.interfaces = []
        self.current_iface = ""
        self.active_index = -1          # 当前生效的方案下标
        self._drag = None
        self._resize = None
        self._attached = False
        self._items = []                # 每个方案的行 frame
        self._last_signature = None

        self.overrideredirect(True)
        self.configure(bg=BG)
        try:
            self.attributes("-toolwindow", True)
        except Exception:
            pass

        self._apply_alpha()
        self._apply_mode()
        self._load_geometry()

        self._build_ui()
        self.refresh()
        self._register_pid()

        # 松手时保存几何；固定模式下会被忽略
        self.bind("<ButtonRelease-1>", lambda e: self._save_geometry())

        self.tray = TrayIcon(self, tip="IP 快速切换器 - 贴纸")
        self.protocol("WM_DELETE_WINDOW", self._hide)

        self._tick()

    def _register_pid(self):
        """把自己 PID 登记到文件，主界面靠它判断贴纸是否在运行。"""
        try:
            path = os.path.join(_app_dir(), "sticker.pid")
            with open(path, "w", encoding="utf-8") as f:
                f.write(str(os.getpid()))
        except Exception:
            pass

    def _unregister_pid(self):
        try:
            path = os.path.join(_app_dir(), "sticker.pid")
            with open(path, "r", encoding="utf-8") as f:
                if (f.read() or "").strip() == str(os.getpid()):
                    os.remove(path)
        except Exception:
            pass

    # ---------------- 窗口行为 ----------------
    def _apply_alpha(self):
        """磨砂玻璃模式：不用窗口级 -alpha（会禁用模糊），透明度走 DWM 渐变通道。"""
        self.after(200, lambda: enable_acrylic(
            self._hwnd(), float(self.settings.data.get("alpha", 0.80))))

    def _apply_mode(self):
        mode = self.settings.data.get("mode", "top")
        try:
            self.attributes("-topmost", mode == "top")
        except Exception:
            pass
        if mode != "desktop":
            if self._attached:
                desktop_detach(self._hwnd())
                self._attached = False
            return
        if not self._attached:
            self._attached = desktop_attach(self._hwnd())

    def _hwnd(self):
        if not desktop_supported():
            return 0
        try:
            self.update_idletasks()
            return int(self.frame(), 16)
        except Exception:
            return 0

    def _locked(self):
        """固定模式下不能拖动/缩放。"""
        return bool(self.settings.data.get("fixed"))

    def _load_geometry(self):
        self.update_idletasks()
        d = self.settings.data
        w = int(d.get("w") or 220)
        h = d.get("h")
        h = int(h) if h else self._estimate_height()
        x, y = d.get("x"), d.get("y")
        if x is None or y is None:
            x = self.winfo_screenwidth() - w - 24
            y = self.winfo_screenheight() - h - 80
        x = max(0, min(int(x), self.winfo_screenwidth() - 60))
        y = max(0, min(int(y), self.winfo_screenheight() - 60))
        self.geometry(f"{w}x{h}+{x}+{y}")
        self.resizable(True, True)

    def _estimate_height(self):
        try:
            n = max(1, len(self.store.load()))
        except Exception:
            n = 1
        return 46 + n * 34 + 10   # 上下留白 + 每行高度

    # ---------------- 界面 ----------------
    def _build_ui(self):
        self.list_frame = tk.Frame(self, bg=BG)
        self.list_frame.pack(fill=tk.BOTH, expand=True)

        # 拖动区域：整个空白处都能拖
        self.list_frame.bind("<ButtonPress-1>", self._on_drag_start)
        self.list_frame.bind("<B1-Motion>", self._on_drag_move)

        # 右下角缩放把手
        # Windows 的 X11 光标名（nwse/size_ne）在 tk 里不被识别，统一用默认光标
        self.grip = tk.Label(self, text="◢", bg=BG, fg=FG_DIM)
        self.grip.place(relx=1.0, rely=1.0, x=-14, y=-2, anchor=tk.SE)
        self.grip.bind("<ButtonPress-1>", self._on_resize_start)
        self.grip.bind("<B1-Motion>", self._on_resize_move)
        self.grip.bind("<ButtonRelease-1>", self._on_resize_end)

        self._rebuild_items([])

    def _rebuild_items(self, profiles):
        """按方案列表重建行：左侧方案信息，右侧 iOS 风格开关。

        开关方向与颜色即选中状态：
            未选中 = 深色胶囊，白点在右（参考图样式）
            选中   = 反色浅色胶囊，深点在左（与未选中方向、颜色均相反）
        """
        for item in self._items:
            for w in item:
                if w is not None:
                    try:
                        w.destroy()
                    except Exception:
                        pass
        self._items = []

        if not profiles:
            lbl = tk.Label(
                self.list_frame, text="暂无方案\n去主界面添加", bg=BG, fg=FG_DIM,
                font=("Microsoft YaHei UI", 9), justify=tk.CENTER,
            )
            lbl.pack(expand=True, pady=18)
            self._items.append((lbl, None))
            return

        for idx, p in enumerate(profiles):
            name = p.get("name") or "未命名"
            ip = p.get("ip") or "DHCP"
            active = (idx == self.active_index)

            row = tk.Frame(self.list_frame, bg=BG, cursor="hand2")
            row.pack(fill=tk.X, padx=6, pady=3)

            text_col = tk.Frame(row, bg=BG)
            text_col.pack(side=tk.LEFT, fill=tk.X, expand=True)
            tk.Label(
                text_col, text=name, bg=BG, fg=FG if active else FG_DIM,
                anchor=tk.W, font=("Microsoft YaHei UI", 9, "bold"),
            ).pack(fill=tk.X)
            tk.Label(
                text_col, text=ip, bg=BG, fg=FG_DIM if active else "#707078",
                anchor=tk.W, font=("Consolas", 8),
            ).pack(fill=tk.X)

            toggle = tk.Canvas(
                row, width=44, height=24, bg=BG, highlightthickness=0,
            )
            toggle.pack(side=tk.RIGHT, padx=(6, 2))
            self._draw_toggle(toggle, active)

            for w in (row, text_col, toggle):
                w.bind("<Button-1>", lambda e, i=idx: self.apply_index(i))
            for child in text_col.winfo_children():
                child.bind("<Button-1>", lambda e, i=idx: self.apply_index(i))

            self._items.append((row, toggle))

    def _draw_toggle(self, cv, on):
        """画胶囊开关。on=True 反色反向。"""
        cap = TOGGLE_ON_BG if on else TOGGLE_OFF_BG
        knob = TOGGLE_ON_KNOB if on else TOGGLE_OFF_KNOB
        cv.delete("all")
        # 胶囊 = 左半圆 + 矩形 + 右半圆
        cv.create_oval(1, 1, 23, 23, fill=cap, outline=cap)
        cv.create_rectangle(12, 1, 32, 23, fill=cap, outline=cap)
        cv.create_oval(21, 1, 43, 23, fill=cap, outline=cap)
        # 圆点：未选中在右（参考图），选中反到左
        cx = 14 if on else 30
        cv.create_oval(cx - 8, 4, cx + 8, 20, fill=knob, outline=knob)

    def _hover(self, row, on):
        try:
            row.configure(bg=BG_ITEM_HOVER if on else BG)
        except Exception:
            pass

    def _mark_active(self):
        """重画每行开关：选中项反色反向，其余保持参考图样式。"""
        for i, item in enumerate(self._items):
            toggle = item[1]
            if toggle is None:
                continue
            try:
                self._draw_toggle(toggle, i == self.active_index)
            except Exception:
                pass

    # ---------------- 刷新 ----------------
    def _tick(self):
        """定时检查：配置有没有被主界面改掉、方案有没有变。"""
        if self.settings.reload_if_changed():
            self._apply_alpha()
            self._apply_mode()
            self._load_geometry()
        self.refresh()
        try:
            self.after(1200, self._tick)
        except Exception:
            pass

    def refresh(self):
        try:
            profiles = self.store.load()
        except Exception:
            profiles = []
        sig = (len(profiles), self.settings.data.get("x"), self.settings.data.get("y"),
               self.settings.data.get("w"), self.settings.data.get("h"))
        if sig != self._last_signature:
            self._last_signature = sig
            self._rebuild_items(profiles)
        self._detect_active(profiles)

    def _detect_active(self, profiles):
        """根据当前网卡实际 IP 判断哪个方案生效中。"""
        if not self.current_iface:
            ifaces = list_interfaces()
            connected = [i for i in ifaces if i.get("state") == "connected"]
            if not connected:
                return
            self.current_iface = connected[0]["name"]
        try:
            st = get_status(self.current_iface)
        except Exception:
            return
        cur = (st.get("ips") or [""])[0]
        idx = -1
        for i, p in enumerate(profiles):
            if p.get("ip") and p["ip"] == cur:
                idx = i
                break
        if idx != self.active_index:
            self.active_index = idx
            self._mark_active()

    # ---------------- 切换 ----------------
    def apply_index(self, idx):
        try:
            profiles = self.store.load()
        except Exception:
            return
        if idx < 0 or idx >= len(profiles):
            return
        p = profiles[idx]
        if not self.current_iface:
            ifaces = list_interfaces()
            connected = [i for i in ifaces if i.get("state") == "connected"]
            if connected:
                self.current_iface = connected[0]["name"]
        if not self.current_iface:
            return

        self.active_index = idx
        self._mark_active()

        if not is_admin():
            self.tray.notify("需要管理员权限才能切换 IP\n请在主界面点「以管理员重启」")
            return
        try:
            apply_profile(self.current_iface, p)
            self.tray.notify(f"已切换到「{p.get('name')}」")
        except Exception as e:
            self.tray.notify(f"切换失败：{e}")

    # ---------------- 拖动 / 缩放 ----------------
    def _save_geometry(self):
        """拖动/缩放后把位置大小写回配置（固定模式不写）。"""
        if self._locked():
            return
        try:
            d = dict(self.settings.data)
            d["x"] = self.winfo_x()
            d["y"] = self.winfo_y()
            d["w"] = self.winfo_width()
            d["h"] = self.winfo_height()
            with open(self.settings.path, "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False, indent=2)
            self.settings._mtime = os.path.getmtime(self.settings.path)
        except Exception:
            pass

    def _on_drag_start(self, e):
        if self._locked():
            return
        self._drag = {"x": e.x_root - self.winfo_x(), "y": e.y_root - self.winfo_y()}

    def _on_drag_move(self, e):
        if self._locked() or not self._drag:
            return
        self.geometry(f"+{e.x_root - self._drag['x']}+{e.y_root - self._drag['y']}")
        if self._attached:      # 桌面层模式下要重新附着，否则位置不跟
            self.after_idle(lambda: self._reattach())

    def _reattach(self):
        if not self._attached:
            return
        try:
            h = self._hwnd()
            if h:
                desktop_detach(h)
                self._attached = desktop_attach(h)
        except Exception:
            pass

    def _on_resize_start(self, e):
        if self._locked():
            return
        self._resize = {
            "x": e.x_root, "y": e.y_root,
            "w": self.winfo_width(), "h": self.winfo_height(),
        }

    def _on_resize_move(self, e):
        if self._locked() or not self._resize:
            return
        r = self._resize
        w = max(150, r["w"] + (e.x_root - r["x"]))
        h = max(90, r["h"] + (e.y_root - r["y"]))
        self.geometry(f"{w}x{h}")
        if self._attached:
            self.after_idle(self._reattach)

    def _on_resize_end(self, e):
        self._resize = None
        self._save_geometry()

    # ---------------- 托盘 ----------------
    def _hide(self):
        self.withdraw()

    def _show(self):
        self.deiconify()
        self.lift()

    def quit_app(self):
        self._unregister_pid()
        try:
            self.tray.stop()
        except Exception:
            pass
        self.destroy()

    def on_close(self):
        self._save_geometry()
        self._hide()


if __name__ == "__main__":
    Sticker().mainloop()