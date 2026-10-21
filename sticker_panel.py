# -*- coding: utf-8 -*-
"""
贴纸控制面板（主界面用）

按需求：**所有贴纸设置都在主界面调**，这里负责
    - 读写 sticker_config.json
    - 实时预览贴纸效果（所见即所得）
    - 勾选「固定」后贴纸只能点方案，不能拖动/缩放
    - 点「应用到桌面」后拉起/关闭贴纸进程
"""
import json
import os
import subprocess
import sys
import tkinter as tk
from tkinter import ttk

import sticker as sticker_mod
from sticker import Settings, SETTINGS_FILE


def app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def settings_path():
    return os.path.join(app_dir(), SETTINGS_FILE)


def read_settings():
    return Settings(settings_path()).data


def write_settings(**kwargs):
    """合并写入贴纸配置。"""
    path = settings_path()
    data = dict(read_settings())
    data.update(kwargs)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return data


def _state_path():
    """贴纸运行时状态（PID）存放位置，和配置同目录。"""
    return os.path.join(app_dir(), "sticker.pid")


def read_sticker_pid():
    """贴纸启动时把自身 PID 写进来，主界面据此判断是否在运行。"""
    try:
        with open(_state_path(), "r", encoding="utf-8") as f:
            pid = int((f.read() or "0").strip())
    except Exception:
        return 0
    if pid <= 0:
        return 0
    try:
        out = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
            capture_output=True,
        ).stdout.decode("gbk", "ignore")
        return pid if str(pid) in out else 0
    except Exception:
        return 0


def sticker_running():
    """贴纸和主界面是同一个 exe；贴纸启动时会登记自己的 PID。"""
    return read_sticker_pid() != 0


def kill_sticker():
    """只关贴纸进程，不动主界面。"""
    pid = read_sticker_pid()
    if pid:
        subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True)
    try:
        os.remove(_state_path())
    except Exception:
        pass


def launch_sticker():
    """拉起贴纸。打包后用同一个 exe 加 --sticker 参数。

    启动前先清掉残留的 sticker.pid：上次如果是被强杀的，文件还在，
    会让主界面误判"贴纸在运行"，下次点应用时又去杀一个不存在的 PID。
    """
    try:
        if read_sticker_pid() == 0:
            os.remove(_state_path())
    except Exception:
        pass
    if getattr(sys, "frozen", False):
        subprocess.Popen([sys.executable, "--sticker"],
                         cwd=os.path.dirname(sys.executable))
    else:
        py = sys.executable
        script = os.path.join(app_dir(), "sticker.py")
        subprocess.Popen([py, script], cwd=app_dir())


class StickerPanel(ttk.LabelFrame):
    def __init__(self, master, on_change=None):
        super().__init__(master, text="桌面贴纸")
        self.on_change = on_change
        self.cfg = dict(read_settings())

        self.enabled = tk.BooleanVar(value=bool(self.cfg.get("enabled", True)))
        self.fixed = tk.BooleanVar(value=bool(self.cfg.get("fixed", False)))
        self.mode = tk.StringVar(value=self.cfg.get("mode", "top"))
        self.alpha = tk.DoubleVar(value=float(self.cfg.get("alpha", 0.92)))
        self.width = tk.IntVar(value=int(self.cfg.get("w", 220)))

        self._build()
        self._render_preview()

    def _build(self):
        col = ttk.Frame(self)
        col.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        left = ttk.Frame(col)
        left.pack(side=tk.LEFT, fill=tk.Y)

        ttk.Checkbutton(left, text="启用贴纸", variable=self.enabled,
                        command=self._on_toggle).grid(row=0, column=0, columnspan=2,
                                                      sticky=tk.W, pady=(0, 6))
        ttk.Checkbutton(left, text="固定位置（贴纸只能点方案，不能拖动/缩放）",
                        variable=self.fixed, command=self._on_toggle
                        ).grid(row=1, column=0, columnspan=2, sticky=tk.W, pady=(0, 8))

        ttk.Label(left, text="显示方式").grid(row=2, column=0, sticky=tk.W)
        modes = ttk.Combobox(left, textvariable=self.mode, width=12,
                            values=("top", "desktop", "normal"), state="readonly")
        modes.grid(row=2, column=1, sticky=tk.W, padx=(8, 0))
        modes.bind("<<ComboboxSelected>>", lambda e: self._on_toggle())
        self.mode_box = modes
        ttk.Label(left, text="（桌面层 / 悬浮 / 普通）", foreground="#888"
                  ).grid(row=3, column=0, columnspan=2, sticky=tk.W, pady=(0, 8))

        ttk.Label(left, text="透明度").grid(row=4, column=0, sticky=tk.W)
        alpha = tk.Scale(left, from_=0.4, to=1.0, resolution=0.05, orient=tk.HORIZONTAL,
                         variable=self.alpha, length=120, command=lambda v: self._preview_live())
        alpha.grid(row=4, column=1, sticky=tk.W, padx=(8, 0))

        ttk.Label(left, text="宽度").grid(row=5, column=0, sticky=tk.W)
        tk.Scale(left, from_=150, to=420, resolution=5, orient=tk.HORIZONTAL,
                 variable=self.width, length=120,
                 command=lambda v: self._preview_live()).grid(row=5, column=1, sticky=tk.W,
                                                             padx=(8, 0))

        btns = ttk.Frame(left)
        btns.grid(row=6, column=0, columnspan=2, sticky=tk.W, pady=(12, 0))
        ttk.Button(btns, text="应用到桌面", command=self.apply_and_show
                   ).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(btns, text="关闭贴纸", command=self.close_sticker
                   ).pack(side=tk.LEFT)

        self.status = ttk.Label(left, text="贴纸未运行", foreground="#888")
        self.status.grid(row=7, column=0, columnspan=2, sticky=tk.W, pady=(10, 0))

        # 预览
        right = ttk.Frame(col)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(14, 0))
        ttk.Label(right, text="效果预览").pack(anchor=tk.W)
        self.preview = tk.Frame(right, bg="#c8c8c8", width=260, height=200)
        self.preview.pack(fill=tk.BOTH, expand=True, pady=(4, 0))
        self.preview.pack_propagate(False)

    # ---------------- 预览 ----------------
    def _preview_live(self):
        self._render_preview()
        if self.on_change:
            self.on_change()

    def _render_preview(self):
        for c in self.preview.winfo_children():
            c.destroy()
        wpx = max(120, min(self.width.get(), 380))
        scale = wpx / 220.0
        rows = max(1, len(self._preview_profiles()))
        hpx = min(190, int((46 + rows * 34 + 10) * scale))

        inner = tk.Frame(
            self.preview, bg=sticker_mod.BG,
            width=int(wpx * 0.92), height=int(hpx * 0.82),
        )
        inner.place(relx=0.5, rely=0.5, anchor=tk.CENTER)

        a = float(self.alpha.get())
        inner.configure(bg=sticker_mod.BG)
        # 用Tk 没法真设alpha，这里用颜色深浅近似表达透明度
        base = sticker_mod.BG
        faded = self._blend(base, "#c8c8c8", 1 - a)
        inner.configure(bg=faded)

        for i, p in enumerate(self._preview_profiles()):
            row = tk.Frame(inner, bg=faded)
            row.pack(fill=tk.X, padx=2, pady=1)
            active = (i == self._preview_active())
            col = tk.Frame(row, bg=faded)
            col.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 0))
            tk.Label(col, text=p.get("name", "未命名"), bg=faded,
                     fg=sticker_mod.FG if active else "#cfcfcf", anchor=tk.W,
                     font=("Microsoft YaHei UI", max(6, int(9 * scale)))).pack(fill=tk.X)

            # 开关预览：与贴纸同款 —— 选中=浅色胶囊点在左，未选中=深色胶囊点在右
            tw = max(28, int(44 * scale))
            th = max(15, int(24 * scale))
            knob_r = max(5, int(8 * scale))
            cv = tk.Canvas(row, width=tw, height=th, bg=faded, highlightthickness=0)
            cv.pack(side=tk.RIGHT, padx=(4, int(2 * scale)))
            cap = sticker_mod.TOGGLE_ON_BG if active else sticker_mod.TOGGLE_OFF_BG
            knob = sticker_mod.TOGGLE_ON_KNOB if active else sticker_mod.TOGGLE_OFF_KNOB
            hw, hh = tw / 2, th / 2
            r = hh - 1
            cv.create_oval(1, 1, 1 + 2 * r, th - 1, fill=cap, outline=cap)
            cv.create_rectangle(hw, 1, tw - hw, th - 1, fill=cap, outline=cap)
            cv.create_oval(tw - 1 - 2 * r, 1, tw - 1, th - 1, fill=cap, outline=cap)
            cx = hw if active else tw - hw
            cv.create_oval(cx - knob_r, hh - knob_r, cx + knob_r, hh + knob_r,
                           fill=knob, outline=knob)

        grip = tk.Label(inner, text="◢", bg=faded, fg=sticker_mod.FG_DIM,
                        font=("Segoe UI", max(6, int(8 * scale))))
        if not self.fixed.get():
            grip.place(relx=1.0, rely=1.0, anchor=tk.SE)
        if self.fixed.get():
            tk.Label(inner, text="已固定", bg=faded, fg="#6fbf73",
                     font=("Microsoft YaHei UI", max(6, int(8 * scale)))).place(
                relx=0.5, rely=1.0, anchor=tk.S, y=-2)

    @staticmethod
    def _blend(c1, c2, t):
        def rgb(c):
            return tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))
        a, b = rgb(c1), rgb(c2)
        return "#%02x%02x%02x" % tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))

    def set_profiles(self, profiles, active_index=0):
        """由主界面喂入方案，预览要跟着变。"""
        self._profiles = profiles
        self._active = active_index
        self._render_preview()

    def _preview_profiles(self):
        return getattr(self, "_profiles", []) or []

    def _preview_active(self):
        return getattr(self, "_active", 0)

    # ---------------- 行为 ----------------
    def _on_toggle(self):
        self._render_preview()

    def apply_and_show(self):
        data = write_settings(
            enabled=bool(self.enabled.get()),
            fixed=bool(self.fixed.get()),
            mode=self.mode.get(),
            alpha=round(float(self.alpha.get()), 2),
            w=int(self.width.get()),
        )
        if not self.enabled.get():
            kill_sticker()
            self.status.config(text="贴纸已关闭（取消勾选可重新启用）", foreground="#888")
            if self.on_change:
                self.on_change()
            return

        kill_sticker()
        import time
        time.sleep(0.4)
        launch_sticker()
        # 等贴纸把 PID 登记上再报状态，避免刚启动就显示"未运行"
        for _ in range(25):
            time.sleep(0.4)
            if sticker_running():
                break
        self.status.config(
            text="贴纸已启动，配置已生效" if sticker_running()
            else "贴纸启动中…（若一直不出现请手动关闭重试）",
            foreground="#2e7d32" if sticker_running() else "#b26a00",
        )
        if self.on_change:
            self.on_change()

    def close_sticker(self):
        kill_sticker()
        self.status.config(text="贴纸已关闭", foreground="#888")

    def refresh_status(self):
        self.status.config(
            text="贴纸运行中" if sticker_running() else "贴纸未运行",
            foreground="#2e7d32" if sticker_running() else "#888",
        )