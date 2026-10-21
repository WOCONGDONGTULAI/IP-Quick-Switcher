# -*- coding: utf-8 -*-
"""
托盘图标 + 开机自启。

用 ctypes 直接调 Win32，不依赖 pystray/Pillow —— 单文件打包后依然可用。
"""
import ctypes
import os
import struct
import sys

# ---- Win32 常量 ----
WM_APP = 0x8000
WM_TRAY = WM_APP + 1
WM_LBUTTONDBLCLK = 0x0203
WM_RBUTTONUP = 0x0205
WM_COMMAND = 0x0111
WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
NIM_ADD = 0x00000000
NIM_MODIFY = 0x00000001
NIM_DELETE = 0x00000002
NIF_MESSAGE = 0x00000001
NIF_ICON = 0x00000002
NIF_TIP = 0x00000004
NIF_INFO = 0x00000010
IMAGE_ICON = 1
LR_LOADFROMFILE = 0x00000010
LR_DEFAULTSIZE = 0x00000040
IDC_ARROW = 32512
TPM_RIGHTBUTTON = 0x0002
MF_STRING = 0x0000
IDI_APPLICATION = 32512

user32 = ctypes.windll.user32
shell32 = ctypes.windll.shell32
kernel32 = ctypes.windll.kernel32

# 64 位系统上指针/lParam 会超出 int 范围，统一声明成 64 位无符号数
if ctypes.sizeof(ctypes.c_void_p) == 8:
    LPARAM = ctypes.c_uint64
    WPARAM = ctypes.c_uint64
    LRESULT = ctypes.c_int64
else:
    LPARAM = ctypes.c_uint32
    WPARAM = ctypes.c_uint32
    LRESULT = ctypes.c_int32


class WNDCLASS(ctypes.Structure):
    _fields_ = [
        ("style", ctypes.c_uint),
        ("lpfnWndProc", ctypes.c_void_p),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", ctypes.c_void_p),
        ("hIcon", ctypes.c_void_p),
        ("hCursor", ctypes.c_void_p),
        ("hbrBackground", ctypes.c_void_p),
        ("lpszMenuName", ctypes.c_wchar_p),
        ("lpszClassName", ctypes.c_wchar_p),
    ]


class NOTIFYICONDATA(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_uint32),
        ("hWnd", ctypes.c_void_p),
        ("uID", ctypes.c_uint),
        ("uFlags", ctypes.c_uint),
        ("uCallbackMessage", ctypes.c_uint),
        ("hIcon", ctypes.c_void_p),
        ("szTip", ctypes.c_wchar * 128),
        ("dwState", ctypes.c_uint),
        ("dwStateMask", ctypes.c_uint),
        ("szInfo", ctypes.c_wchar * 256),
        ("uVersion", ctypes.c_uint),
        ("szInfoTitle", ctypes.c_wchar * 64),
        ("dwInfoFlags", ctypes.c_uint),
    ]


def _declare_prototypes():
    """显式声明关键 Win32 函数的参数与返回类型，避免 64 位指针被截断。"""
    try:
        shell32.Shell_NotifyIconW.argtypes = [ctypes.c_uint, ctypes.POINTER(NOTIFYICONDATA)]
        shell32.Shell_NotifyIconW.restype = ctypes.c_bool
    except Exception:
        pass
    for fn in ("CreateWindowExW", "RegisterClassW", "DefWindowProcW", "CreatePopupMenu",
               "AppendMenuW", "TrackPopupMenu", "DestroyMenu", "LoadImageW",
               "LoadIconW", "PostMessageW", "SetForegroundWindow", "DestroyWindow"):
        try:
            f = getattr(user32, fn)
            # 这几个返回 HANDLE/HWND/HMENU/HICON，保持 c_void_p；
            # 其余（如 TrackPopupMenu 的命令号）必须用整数，否则拿到 None
            if fn in ("CreateWindowExW", "DefWindowProcW", "LoadImageW", "LoadIconW",
                      "SetForegroundWindow", "DestroyWindow"):
                f.restype = ctypes.c_void_p
            else:
                f.restype = ctypes.c_int
        except Exception:
            pass
    try:
        user32.CreateWindowExW.argtypes = [
            ctypes.c_ulong, ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_ulong,
            ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
        ]
        user32.CreateWindowExW.restype = ctypes.c_void_p
        user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASS)]
        user32.RegisterClassW.restype = ctypes.c_ushort
        user32.DefWindowProcW.argtypes = [ctypes.c_void_p, ctypes.c_uint, WPARAM, LPARAM]
        user32.DefWindowProcW.restype = LRESULT
        user32.CreatePopupMenu.restype = ctypes.c_void_p
        user32.AppendMenuW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_wchar_p]
        user32.TrackPopupMenu.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_int, ctypes.c_int,
                                          ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p]
        user32.TrackPopupMenu.restype = ctypes.c_uint
        user32.LoadImageW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint,
                                       ctypes.c_int, ctypes.c_int, ctypes.c_uint]
        user32.LoadImageW.restype = ctypes.c_void_p
        user32.LoadIconW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p]
        user32.LoadIconW.restype = ctypes.c_void_p
        user32.PostMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, WPARAM, LPARAM]
        user32.SetForegroundWindow.argtypes = [ctypes.c_void_p]
        user32.DestroyMenu.argtypes = [ctypes.c_void_p]
        user32.PeekMessageW.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint,
                                        ctypes.c_uint, ctypes.c_uint]
        user32.PeekMessageW.restype = ctypes.c_bool
        user32.GetMessageW.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint]
        kernel32.GetModuleHandleW.restype = ctypes.c_void_p
        kernel32.GetModuleHandleW.argtypes = [ctypes.c_wchar_p]
    except Exception:
        pass


_declare_prototypes()


def _resource_ico_path():
    """打包后从 exe 自身取图标；源码运行时返回空（用系统默认图标）。"""
    if not getattr(sys, "frozen", False):
        return ""
    return sys.executable


class TrayIcon:
    """系统托盘图标：双击唤回窗口，右键菜单退出。"""

    def __init__(self, app, tip="IP 快速切换器"):
        self.app = app
        self.tip = tip
        self._running = False
        self.hwnd = None
        self._nid = None
        self._class_name = "IPSwitcherTrayWnd"

        hinst = kernel32.GetModuleHandleW(None)
        wnd_proc_type = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_void_p, ctypes.c_uint, WPARAM, LPARAM)
        self._wnd_proc = wnd_proc_type(self._on_message)

        wc = WNDCLASS()
        wc.lpfnWndProc = ctypes.cast(self._wnd_proc, ctypes.c_void_p).value
        wc.hInstance = hinst
        wc.lpszClassName = self._class_name
        user32.RegisterClassW(ctypes.byref(wc))

        self.hwnd = user32.CreateWindowExW(
            0, self._class_name, "IPSwitcherTray", 0,
            0, 0, 0, 0, None, None, hinst, None,
        )

        self._add_icon()
        self._running = True
        # 关键：这里绝不能跑阻塞消息循环，否则主窗口根本起不来。
        # 改用 tkinter 的 after 定时非阻塞地处理托盘消息。
        try:
            self.app.after(500, self._drain_messages)
        except Exception:
            pass

    def _drain_messages(self):
        msg = ctypes.c_void_p()
        while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):  # PM_REMOVE
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        if self._running:
            try:
                self.app.after(500, self._drain_messages)
            except Exception:
                pass

    def _icon_handle(self):
        ico = _resource_ico_path()
        if ico and os.path.exists(ico):
            h = user32.LoadImageW(None, ico, IMAGE_ICON, 0, 0, LR_LOADFROMFILE | LR_DEFAULTSIZE)
            if h:
                return h
        # MAKEINTRESOURCE: 系统图标 ID 要当指针传（值小于 65536 即可当地址用）
        return user32.LoadIconW(None, ctypes.cast(IDC_ARROW, ctypes.c_wchar_p))

    def _add_icon(self):
        nid = NOTIFYICONDATA()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATA)
        nid.hWnd = self.hwnd
        nid.uID = 1
        nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        nid.uCallbackMessage = WM_TRAY
        nid.hIcon = self._icon_handle()
        nid.szTip = self.tip
        self._nid = nid
        shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid))

    def notify(self, text, title="IP 快速切换器"):
        """气泡提示。"""
        if not self._nid:
            return
        nid = NOTIFYICONDATA()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATA)
        nid.hWnd = self.hwnd
        nid.uID = 1
        nid.uFlags = NIF_INFO
        nid.szInfo = text
        nid.szInfoTitle = title
        nid.dwInfoFlags = 0
        shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(nid))

    def _show_menu(self):
        menu = user32.CreatePopupMenu()
        user32.AppendMenuW(menu, MF_STRING, 1001, "显示主界面")
        user32.AppendMenuW(menu, MF_STRING, 1002, "退出")
        pt = ctypes.wintypes.POINT() if hasattr(ctypes, "wintypes") else None
        # 取鼠标位置
        class _POINT(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

        p = _POINT()
        user32.GetCursorPos(ctypes.byref(p))
        user32.SetForegroundWindow(self.hwnd)
        cmd = user32.TrackPopupMenu(
            menu, TPM_RIGHTBUTTON, p.x, p.y, 0, self.hwnd, None
        )
        user32.PostMessageW(self.hwnd, WM_NULL, 0, 0)
        user32.DestroyMenu(menu)
        if cmd == 1001:
            self._restore()
        elif cmd == 1002:
            self._do_quit()

    def _restore(self):
        try:
            self.app.deiconify()
            self.app.lift()
            self.app.focus_force()
        except Exception:
            pass

    def _do_quit(self):
        """主界面提供 _quit()，贴纸提供 quit_app()，谁有就用谁。"""
        for name in ("_quit", "quit_app"):
            fn = getattr(self.app, name, None)
            if callable(fn):
                fn()
                return

    def _on_message(self, hwnd, msg, wparam, lparam):
        if msg == WM_TRAY:
            if lparam == WM_LBUTTONDBLCLK:
                self._restore()
            elif lparam == WM_RBUTTONUP:
                self._show_menu()
        elif msg == WM_COMMAND:
            if wparam == 1001:
                self._restore()
            elif wparam == 1002:
                self.app._quit()
        elif msg == WM_CLOSE:
            self.app._quit()
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _pump(self):
        """保留旧接口：不再使用（改用 _drain_messages 非阻塞轮询）。"""
        return

    def stop(self):
        if self._nid:
            shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self._nid))
        self._nid = None
        self._running = False


# ---------------- 开机自启 ----------------
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _exe_path():
    if getattr(sys, "frozen", False):
        return sys.executable
    return os.path.abspath(sys.argv[0])


def is_autostart_enabled():
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ) as k:
            value, _ = winreg.QueryValueEx(k, "IPSwitcher")
            return bool(value)
    except Exception:
        return False


def set_autostart(enabled=True):
    """写/删当前用户的开机自启项。返回是否设置成功。"""
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            if enabled:
                exe = _exe_path()
                winreg.SetValueEx(k, "IPSwitcher", 0, winreg.REG_SZ, f'"{exe}"')
            else:
                try:
                    winreg.DeleteValue(k, "IPSwitcher")
                except FileNotFoundError:
                    pass
        return True
    except Exception:
        return False


def ensure_autostart():
    """首次运行自动写入开机自启（已存在则不动）。"""
    if is_autostart_enabled():
        return True
    return set_autostart(True)


def toggle_autostart(enabled):
    return set_autostart(enabled)