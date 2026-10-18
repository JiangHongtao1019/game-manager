# -*- coding: utf-8 -*-
"""capture_screenshot.py —— 截取「游戏管理器」主窗口 -> docs/screenshot.png
PrintWindow(PW_RENDERFULLCONTENT) 优先，全黑则回退 置前后台+BitBlt。"""
import ctypes
import ctypes.wintypes as wt
import os
import sys
import time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # D:\game_manager
sys.path.insert(0, BASE)

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
user32.SetProcessDPIAware()          # 物理像素坐标


def find_window():
    found = []

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def cb(hwnd, _lp):
        if user32.IsWindowVisible(hwnd):
            buf = ctypes.create_unicode_buffer(64)
            user32.GetWindowTextW(hwnd, buf, 64)
            if buf.value == "游戏管理器":
                found.append(hwnd)
        return True

    user32.EnumWindows(cb, 0)
    return found[0] if found else None


hwnd = find_window()
if not hwnd:                          # 应用没在运行 -> 启动并等扫描完成
    os.startfile(r"C:\Users\MECHREVO\Desktop\游戏管理器.lnk")
    time.sleep(12)
    hwnd = find_window()
if not hwnd:
    raise SystemExit("未找到「游戏管理器」窗口")

if user32.IsIconic(hwnd):             # 最小化则还原
    user32.ShowWindow(hwnd, 9)
    time.sleep(0.8)

rect = wt.RECT()
user32.GetWindowRect(hwnd, ctypes.byref(rect))
w, h = rect.right - rect.left, rect.bottom - rect.top
print(f"窗口尺寸: {w}x{h}")

hdc = user32.GetWindowDC(hwnd)
mdc = gdi32.CreateCompatibleDC(hdc)
bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
gdi32.SelectObject(mdc, bmp)
user32.PrintWindow.argtypes = [wt.HWND, wt.HDC, wt.UINT]
user32.PrintWindow.restype = wt.BOOL
ok = user32.PrintWindow(hwnd, mdc, 2)  # PW_RENDERFULLCONTENT
print("PrintWindow:", bool(ok))


class BMIH(ctypes.Structure):
    _fields_ = [("biSize", ctypes.c_uint32), ("biWidth", ctypes.c_int),
                ("biHeight", ctypes.c_int), ("biPlanes", wt.WORD),
                ("biBitCount", wt.WORD), ("biCompression", ctypes.c_uint32),
                ("biSizeImage", ctypes.c_uint32), ("biXPelsPerMeter", ctypes.c_int),
                ("biYPelsPerMeter", ctypes.c_int), ("biClrUsed", ctypes.c_uint32),
                ("biClrImportant", ctypes.c_uint32)]


bmi = BMIH()
bmi.biSize, bmi.biWidth, bmi.biHeight = ctypes.sizeof(BMIH), w, -h
bmi.biPlanes, bmi.biBitCount = 1, 32
buf = ctypes.create_string_buffer(w * h * 4)
gdi32.GetDIBits(mdc, bmp, 0, h, buf, ctypes.byref(bmi), 0)
px = bytearray(buf.raw[:w * h * 4])

if not any(px[i] + px[i + 1] + px[i + 2] > 30 for i in range(0, len(px), 4)):
    print("PrintWindow 全黑 -> 回退 BitBlt")   # 置前后台直接从屏幕拷贝
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.8)
    sdc = user32.GetDC(None)
    gdi32.BitBlt(mdc, 0, 0, w, h, sdc, rect.left, rect.top, 0x00CC0020)
    user32.ReleaseDC(None, sdc)
    gdi32.GetDIBits(mdc, bmp, 0, h, buf, ctypes.byref(bmi), 0)
    px = bytearray(buf.raw[:w * h * 4])

for i in range(0, len(px), 4):
    px[i], px[i + 2] = px[i + 2], px[i]      # BGRA -> RGBA

gdi32.DeleteObject(bmp)
gdi32.DeleteDC(mdc)
user32.ReleaseDC(hwnd, hdc)

import icon_extractor
out = os.path.join(BASE, "docs", "screenshot.png")
os.makedirs(os.path.dirname(out), exist_ok=True)
with open(out, "wb") as f:
    f.write(icon_extractor._png(w, h, bytes(px)))
print("已保存:", out)
