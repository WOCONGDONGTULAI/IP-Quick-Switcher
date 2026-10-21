# -*- coding: utf-8 -*-
"""
Windows 桌面层操作：让窗口真正“贴”在桌面上，而不是悬浮在所有窗口之上。

原理
----
Windows 的桌面背景由 Explorer 的一个 WorkerW 窗口承载。Win10 之后这个 WorkerW
不会一直存在，需要先给 Progman 发送私有的 0x052C 消息让它生成。
把我们的窗口 SetParent 到这个 WorkerW，它就变成了桌面的一部分：

  - 按 Win+D 显示桌面时，跟着桌面一起出现
  - 打开其他程序时被正常遮挡，不再碍事
  - 不出现在任务栏，也不出现在 Alt+Tab

两个必须知道的副作用
--------------------
1. 成为子窗口后就不能再用 -topmost 置顶了（二者互斥）。所以贴纸提供三种模式：
   desktop（嵌入桌面）/ top（悬浮置顶）/ normal（普通窗口）。
2. Explorer 崩溃或被重启后 WorkerW 会重建，附着会失效。上层需要在刷新循环里
   周期性重试 attach()，这里也提供了 detach() 供切换模式时恢复独立窗口。
"""
import sys

_IS_WIN = sys.platform == "win32"

# 通知 Progman 生成承载桌面的 WorkerW（Windows 私有消息）
WM_SPAWN_WORKER = 0x052C
SMTO_NORMAL = 0x0000

# SetWindowPos 用到的常量
HWND_TOP = 0
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040


def is_supported():
    """桌面嵌入只在 Windows 上可用。"""
    return _IS_WIN


def _user32():
    import ctypes
    return ctypes.WinDLL("user32", use_last_error=True)


def find_desktop_worker(timeout_ms=800):
    """
    找到承载桌面图标/壁纸的那个 WorkerW，返回句柄；失败返回 0。

    判定方式：枚举所有顶层窗口，找出包含 SHELLDLL_DefView 子窗口的那个 WorkerW。
    """
    if not _IS_WIN:
        return 0
    import ctypes
    from ctypes import wintypes

    user32 = _user32()
    user32.FindWindowW.restype = wintypes.HWND
    user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    user32.SendMessageTimeoutW.restype = wintypes.LPARAM
    user32.SendMessageTimeoutW.argtypes = [
        wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
        wintypes.UINT, wintypes.UINT, ctypes.POINTER(wintypes.DWORD),
    ]
    user32.EnumWindows.restype = wintypes.BOOL
    user32.EnumWindows.argtypes = [ctypes.c_void_p, wintypes.LPARAM]
    user32.FindWindowExW.restype = wintypes.HWND
    user32.FindWindowExW.argtypes = [wintypes.HWND, wintypes.HWND,
                                     wintypes.LPCWSTR, wintypes.LPCWSTR]

    progman = user32.FindWindowW("Progman", None)
    if not progman:
        return 0

    # 这一步让 Explorer 把桌面拆出一个独立的 WorkerW
    result = wintypes.DWORD()
    user32.SendMessageTimeoutW(progman, WM_SPAWN_WORKER, 0, 0,
                               SMTO_NORMAL, timeout_ms, ctypes.byref(result))

    found = wintypes.HWND(0)
    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def _enum_cb(hwnd, _lparam):
        # 只看 WorkerW，且它的子窗口里有 SHELLDLL_DefView 才是桌面那一层
        if user32.FindWindowExW(hwnd, None, "SHELLDLL_DefView", None):
            found.value = hwnd
            return False  # 找到就停止枚举
        return True

    user32.EnumWindows(WNDENUMPROC(_enum_cb), 0)
    return found.value or 0


def attach(hwnd, timeout_ms=800):
    """
    把窗口挂到桌面层。成功返回 True。

    注意 SETPARENT 后窗口坐标系变成 WorkerW 的客户区坐标，
    而 WorkerW 通常覆盖整个屏幕且原点一致，所以位置不会跳。
    """
    if not _IS_WIN or not hwnd:
        return False
    worker = find_desktop_worker(timeout_ms)
    if not worker:
        return False

    import ctypes
    from ctypes import wintypes
    user32 = _user32()
    user32.SetParent.restype = wintypes.HWND
    user32.SetParent.argtypes = [wintypes.HWND, wintypes.HWND]
    user32.SetWindowPos.restype = wintypes.BOOL
    user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int,
                                    ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                    wintypes.UINT]

    prev = user32.SetParent(wintypes.HWND(hwnd), wintypes.HWND(worker))
    if not prev:
        return False
    # 挂上去之后要确保可见，并避免抢焦点
    user32.SetWindowPos(wintypes.HWND(hwnd), wintypes.HWND(HWND_TOP), 0, 0, 0, 0,
                        SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW)
    return True


def detach(hwnd):
    """解除桌面附着，恢复成独立顶层窗口。成功返回 True。"""
    if not _IS_WIN or not hwnd:
        return False
    import ctypes
    from ctypes import wintypes
    user32 = _user32()
    user32.SetParent.restype = wintypes.HWND
    user32.SetParent.argtypes = [wintypes.HWND, wintypes.HWND]
    prev = user32.SetParent(wintypes.HWND(hwnd), wintypes.HWND(None))
    return bool(prev)


def is_attached(hwnd):
    """判断窗口当前是否已挂在桌面层（父窗口是桌面 WorkerW）。"""
    if not _IS_WIN or not hwnd:
        return False
    import ctypes
    from ctypes import wintypes
    user32 = _user32()
    user32.GetParent.restype = wintypes.HWND
    user32.GetParent.argtypes = [wintypes.HWND]
    parent = user32.GetParent(wintypes.HWND(hwnd))
    return bool(parent)
