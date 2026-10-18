# -*- coding: utf-8 -*-
"""诊断：通过快捷方式启动应用，枚举所有可见窗口并截图"""
import ctypes
import ctypes.wintypes as wt
import os
import sys
import time

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
OUT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, r"D:\game_manager")

# 1. 模拟用户双击桌面快捷方式
os.startfile(r"C:\Users\MECHREVO\Desktop\游戏管理器.lnk")
time.sleep(10)

# 2. 枚举可见顶层窗口
WNDENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
wins = []

def cb(hwnd, _lp):
    if user32.IsWindowVisible(hwnd):
        buf = ctypes.create_unicode_buffer(512)
        user32.GetWindowTextW(hwnd, buf, 512)
        cls = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, cls, 256)
        rect = wt.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        w, h = rect.right - rect.left, rect.bottom - rect.top
        pid = wt.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if (buf.value or w * h > 40000):
            wins.append((buf.value, cls.value, w, h, pid.value, rect.left, rect.top))
    return True

user32.EnumWindows(WNDENUMPROC(cb), 0)
print("=== 可见窗口 ===")
for t, c, w, h, pid, x, y in wins:
    print(f"[{c}] {t!r:40s} {w}x{h} @({x},{y}) pid={pid}")

# 3. GDI 截图
user32.SetProcessDPIAware()
sw, sh = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
hdc = user32.GetDC(None)
mdc = gdi32.CreateCompatibleDC(hdc)
bmp = gdi32.CreateCompatibleBitmap(hdc, sw, sh)
gdi32.SelectObject(mdc, bmp)
gdi32.BitBlt(mdc, 0, 0, sw, sh, hdc, 0, 0, 0x00CC0020)


class BMIH(ctypes.Structure):
    _fields_ = [("biSize", ctypes.c_uint32), ("biWidth", ctypes.c_int),
                ("biHeight", ctypes.c_int), ("biPlanes", wt.WORD),
                ("biBitCount", wt.WORD), ("biCompression", ctypes.c_uint32),
                ("biSizeImage", ctypes.c_uint32), ("biXPelsPerMeter", ctypes.c_int),
                ("biYPelsPerMeter", ctypes.c_int), ("biClrUsed", ctypes.c_uint32),
                ("biClrImportant", ctypes.c_uint32)]


bmi = BMIH()
bmi.biSize, bmi.biWidth, bmi.biHeight = ctypes.sizeof(BMIH), sw, -sh
bmi.biPlanes, bmi.biBitCount = 1, 32
buf = ctypes.create_string_buffer(sw * sh * 4)
gdi32.GetDIBits(mdc, bmp, 0, sh, buf, ctypes.byref(bmi), 0)
px = bytearray(buf.raw[:sw * sh * 4])
for i in range(0, len(px), 4):
    px[i], px[i + 2] = px[i + 2], px[i]      # BGRA -> RGBA
import icon_extractor
png = os.path.join(OUT, "screen.png")
with open(png, "wb") as f:
    f.write(icon_extractor._png(sw, sh, bytes(px)))
gdi32.DeleteObject(bmp)
gdi32.DeleteDC(mdc)
user32.ReleaseDC(None, hdc)
print("截图:", png, f"({sw}x{sh})")
