# -*- coding: utf-8 -*-
"""
IP 快速切换器 - 安装器

一个包装两样东西：
    IPSwitcher.exe         主界面（方案管理）
    IPSwitcherSticker.exe  前端显示（桌面贴纸）

用法：双击本安装器 → 选安装位置 → 安装。
安装完成后可一键启动主界面或贴纸。
"""
import ctypes
import os
import shutil
import subprocess
import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

APP_TITLE = "IP 快速切换器 · 安装"
DEFAULT_DIR = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "IPQuickSwitcher")
# 单 exe：主界面和贴纸是同一个程序，贴纸用 --sticker 参数启动
MAIN_EXE = "IPSwitcher.exe"

BG = "#f5f6f8"
ACCENT = "#2d6cdf"


def _resource_dir():
    """打包后资源在临时解压目录，源码运行时在脚本旁边。"""
    d = getattr(sys, "_MEIPASS", None)
    if d:
        return d
    return os.path.dirname(os.path.abspath(__file__))


def _source_exe(name):
    """依次在：打包资源目录、exe 同级、脚本同级 dist 目录里找。"""
    bases = [
        getattr(sys, "_MEIPASS", None),
        os.path.dirname(os.path.abspath(sys.executable)),
        os.path.dirname(os.path.abspath(__file__)),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "dist"),
    ]
    for base in bases:
        if not base:
            continue
        p = os.path.join(base, name)
        if os.path.exists(p):
            return p
    return None


def _running(name):
    out = subprocess.run(
        ["tasklist", "/FI", f"IMAGENAME eq {name}", "/NH"],
        capture_output=True,
    ).stdout.decode("gbk", "ignore")
    return name.lower() in out.lower()


def _run_hidden(cmd):
    """隐藏窗口执行（兼容不同 Python 版本）。"""
    si = None
    try:
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    except Exception:
        si = None
    try:
        subprocess.run(cmd, capture_output=True, startupinfo=si)
    except Exception:
        subprocess.run(cmd, capture_output=True)


def _create_shortcut_args(target, lnk_path, args=""):
    """带命令行参数的快捷方式（例如 --sticker 启动贴纸模式）。"""
    ps = (
        "$s = New-Object -ComObject WScript.Shell; "
        f"$l = $s.CreateShortcut('{lnk_path}'); "
        f"$l.TargetPath = '{target}'; $l.Arguments = '{args}'; $l.Save()"
    )
    _run_hidden(["powershell", "-NoProfile", "-Command", ps])


def _create_shortcut(target, lnk_path):
    """用 PowerShell 的 WScript.Shell 建快捷方式，比手写 .lnk 省事可靠。"""
    _create_shortcut_args(target, lnk_path, "")


def _set_autostart_args(entry_path, args=""):
    try:
        import winreg

        value = f'"{entry_path}"' + (f" {args}" if args else "")
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_SET_VALUE,
        ) as k:
            winreg.SetValueEx(k, "IPSwitcher", 0, winreg.REG_SZ, value)
        return True
    except Exception:
        return False


def _set_autostart(entry_path):
    return _set_autostart_args(entry_path, "")


def _set_autostart(entry_path):
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_SET_VALUE,
        ) as k:
            winreg.SetValueEx(k, "IPSwitcher", 0, winreg.REG_SZ, f'"{entry_path}"')
        return True
    except Exception:
        return False


class Installer(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("620x500")
        self.resizable(False, False)
        self.configure(bg=BG)

        self.dir_var = tk.StringVar(value=DEFAULT_DIR)
        self.desktop_var = tk.BooleanVar(value=True)
        self.autostart_var = tk.BooleanVar(value=True)
        self.launch_var = tk.StringVar(value="none")

        self._build()
        self._check_sources()

    # ---------------- 界面 ----------------
    def _fatal(self, text):
        """致命错误：不弹框（打包后易崩），直接在界面上显示。"""
        try:
            tk.Label(
                self, text=text, bg="#fdecea", fg="#c62828",
                font=("Microsoft YaHei UI", 10), anchor=tk.W,
                wraplength=540, justify=tk.LEFT,
            ).pack(fill=tk.X, padx=22, pady=16)
            self.install_btn.config(state=tk.DISABLED)
            self.status.config(text="安装包不完整，请重新下载")
        except Exception:
            pass

    def _build(self):
        pad = {"padx": 22}

        tk.Label(self, text="IP 快速切换器", bg=BG, fg="#1a1a1a",
                 font=("Microsoft YaHei UI", 16, "bold")).pack(anchor=tk.W, pady=(22, 2), **pad)
        tk.Label(self, text="一键切换网卡 IP · 桌面贴纸实时显示", bg=BG, fg="#666",
                 font=("Microsoft YaHei UI", 9)).pack(anchor=tk.W, pady=(0, 16), **pad)

        # 安装位置
        frm = tk.Frame(self, bg="#ffffff", highlightbackground="#e0e0e0", highlightthickness=1)
        frm.pack(fill=tk.X, **pad)
        tk.Label(frm, text="安装位置", bg="#ffffff", fg="#333",
                 font=("Microsoft YaHei UI", 9, "bold")).pack(anchor=tk.W, padx=12, pady=(10, 4))
        row = tk.Frame(frm, bg="#ffffff")
        row.pack(fill=tk.X, padx=12, pady=(0, 4))
        tk.Entry(row, textvariable=self.dir_var, font=("Microsoft YaHei UI", 9),
                 relief=tk.SOLID, bd=1).pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=4)
        ttk.Button(row, text="浏览…", command=self._pick_dir, width=8).pack(side=tk.LEFT, padx=(6, 0))

        # 选项
        self.desktop_cb = tk.Checkbutton(
            self, text="创建桌面快捷方式（主界面 + 桌面贴纸）", variable=self.desktop_var,
            bg=BG, fg="#333", font=("Microsoft YaHei UI", 9), anchor=tk.W,
        )
        self.desktop_cb.pack(anchor=tk.W, pady=(14, 4), **pad)

        self.autostart_cb = tk.Checkbutton(
            self, text="开机自动运行（贴纸随开机上桌面）", variable=self.autostart_var,
            bg=BG, fg="#333", font=("Microsoft YaHei UI", 9), anchor=tk.W,
        )
        self.autostart_cb.pack(anchor=tk.W, pady=2, **pad)

        # 组件说明
        comp = tk.Frame(self, bg="#ffffff", highlightbackground="#e0e0e0", highlightthickness=1)
        comp.pack(fill=tk.X, padx=22, pady=(14, 0))
        tk.Label(comp, text="将安装：", bg="#ffffff", fg="#333",
                 font=("Microsoft YaHei UI", 9, "bold")).pack(anchor=tk.W, padx=12, pady=(10, 6))
        tk.Label(comp, text="IPSwitcher.exe    同一个程序，两种界面：", bg="#ffffff", fg="#555",
                 font=("Microsoft YaHei UI", 9), anchor=tk.W).pack(fill=tk.X, padx=12)
        tk.Label(comp, text="     · 直接双击 = 主界面（管理方案、预览贴纸、调整设置）",
                 bg="#ffffff", fg="#777", font=("Microsoft YaHei UI", 9), anchor=tk.W).pack(fill=tk.X, padx=12)
        tk.Label(comp, text="     · 带 --sticker 参数 = 桌面贴纸（只显示方案，点一下就切）",
                 bg="#ffffff", fg="#777", font=("Microsoft YaHei UI", 9), anchor=tk.W).pack(fill=tk.X, padx=12, pady=(2, 10))

        # 安装后启动
        after = tk.Frame(self, bg=BG)
        after.pack(fill=tk.X, padx=22, pady=(14, 0))
        tk.Label(after, text="安装完成后：", bg=BG, fg="#666",
                 font=("Microsoft YaHei UI", 9)).pack(side=tk.LEFT)
        for text, val in (("启动主界面", "main"), ("启动贴纸", "sticker"), ("不启动", "none")):
            tk.Radiobutton(after, text=text, value=val, variable=self.launch_var,
                           bg=BG, fg="#333", font=("Microsoft YaHei UI", 9)).pack(side=tk.LEFT, padx=6)

        # 按钮
        btns = tk.Frame(self, bg=BG)
        btns.pack(fill=tk.X, padx=22, pady=20)
        self.status = tk.Label(btns, text="", bg=BG, fg="#888", font=("Microsoft YaHei UI", 9))
        self.status.pack(side=tk.LEFT)
        ttk.Button(btns, text="取消", command=self.destroy, width=10).pack(side=tk.RIGHT, padx=(0, 8))
        self.install_btn = ttk.Button(btns, text="开始安装", command=self._install, width=12)
        self.install_btn.pack(side=tk.RIGHT)

    # ---------------- 逻辑 ----------------
    def _check_sources(self):
        if not _source_exe(MAIN_EXE):
            self._fatal(
                "安装包不完整，缺少以下文件：\n\n"
                + MAIN_EXE
                + "\n\n请重新从 GitHub 下载完整的安装包。",
            )

    def _pick_dir(self):
        d = filedialog.askdirectory(initialdir=self.dir_var.get() or DEFAULT_DIR)
        if d:
            self.dir_var.set(d)

    def _install(self):
        target = self.dir_var.get().strip()
        if not target:
            messagebox.showwarning("提示", "请填写安装位置")
            return

        # 已在运行就先提示关掉，否则复制会失败
        if _running(MAIN_EXE):
            if not messagebox.askyesno(
                "程序正在运行",
                "检测到 IP 快速切换器正在运行。\n\n继续安装会尝试覆盖，可能失败。建议先关闭它。\n\n继续吗？",
            ):
                return
            subprocess.run(["taskkill", "/IM", MAIN_EXE, "/F"], capture_output=True)

        try:
            os.makedirs(target, exist_ok=True)
        except Exception as e:
            messagebox.showerror("失败", f"无法创建目录：\n{e}")
            return

        main_path = os.path.join(target, MAIN_EXE)
        src = _source_exe(MAIN_EXE)
        try:
            shutil.copy2(src, main_path)
        except Exception as e:
            messagebox.showerror("失败", f"复制 {MAIN_EXE} 失败：\n{e}")
            return

        self.status.config(text="程序已安装，正在创建快捷方式…")

        if self.desktop_var.get():
            desktop = os.path.join(os.path.expanduser("~"), "Desktop")
            try:
                _create_shortcut(main_path, os.path.join(desktop, "IP 快速切换器.lnk"))
                # 贴纸快捷方式带 --sticker 参数，同一个 exe 启动贴纸模式
                _create_shortcut_args(
                    main_path,
                    os.path.join(desktop, "IP 贴纸.lnk"),
                    args='--sticker',
                )
            except Exception:
                pass

        if self.autostart_var.get():
            _set_autostart_args(main_path, "--sticker")   # 开机先看到贴纸

        # 已存在的自启项如果指向旧位置，纠正过来
        if not self.autostart_var.get():
            try:
                import winreg

                with winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Run",
                    0, winreg.KEY_SET_VALUE,
                ) as k:
                    winreg.DeleteValue(k, "IPSwitcher")
            except FileNotFoundError:
                pass
            except Exception:
                pass

        self.install_btn.config(state=tk.DISABLED)
        self.status.config(text="安装完成 ✓")

        launch = self.launch_var.get()
        if launch == "main":
            subprocess.Popen([main_path])
        elif launch == "sticker":
            subprocess.Popen([main_path, "--sticker"])

        # 完成提示用非阻塞的 Label，不弹 messagebox：
        # 打包后的 onefile 在部分环境里弹框会直接崩，且会挡住界面
        done = tk.Frame(self, bg="#e8f5e9", highlightbackground="#a5d6a7", highlightthickness=1)
        done.pack(fill=tk.X, padx=22, pady=(0, 8))
        tk.Label(
            done,
            text=f"安装完成 ✓\n已安装到：{target}\n"
                 + ("已创建桌面快捷方式。\n" if self.desktop_var.get() else "")
                 + ("已设置开机自动运行。\n" if self.autostart_var.get() else "")
                 + "\n现在可以关闭本窗口。",
            bg="#e8f5e9", fg="#2e7d32", justify=tk.LEFT,
            font=("Microsoft YaHei UI", 9), anchor=tk.W,
        ).pack(fill=tk.X, padx=12, pady=10)


if __name__ == "__main__":
    # 提权不是必需项，但装了提权清单可避免被组策略拦下写注册表
    Installer().mainloop()