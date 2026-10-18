# -*- coding: utf-8 -*-
"""capture_screenshot.py —— 截取「游戏管理器」主窗口 -> docs/screenshot.png
自带 App 实例：等扫描完成 -> 展开暗黑IV网页页签 -> 等 favicon -> PrintWindow 截图"""
import ctypes
import ctypes.wintypes as wt
import os
import sys
import time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
OUT = os.path.join(BASE, "docs", "screenshot.png")

# 注意：icon_extractor 导入时会给 gdi32.GetDIBits 设置全局 argtypes，
# 必须复用它的 _BMIH 结构体类，避免类型冲突
import icon_extractor
from icon_extractor import _BMIH as BMIH
from app import App

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
user32.SetProcessDPIAware()          # 物理像素坐标


def capture(title="游戏管理器") -> bool:
    found = []

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def cb(hwnd, _lp):
        if user32.IsWindowVisible(hwnd):
            buf = ctypes.create_unicode_buffer(64)
            user32.GetWindowTextW(hwnd, buf, 64)
            if buf.value == title:
                found.append(hwnd)
        return True

    user32.EnumWindows(cb, 0)
    if not found:
        return False
    hwnd = found[0]
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, 9)
        time.sleep(0.8)
    rect = wt.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    w, h = rect.right - rect.left, rect.bottom - rect.top
    hdc = user32.GetWindowDC(hwnd)
    mdc = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
    gdi32.SelectObject(mdc, bmp)
    user32.PrintWindow.argtypes = [wt.HWND, wt.HDC, wt.UINT]
    user32.PrintWindow.restype = wt.BOOL
    user32.PrintWindow(hwnd, mdc, 2)      # PW_RENDERFULLCONTENT
    bmi = BMIH()
    bmi.biSize, bmi.biWidth, bmi.biHeight = ctypes.sizeof(BMIH), w, -h
    bmi.biPlanes, bmi.biBitCount = 1, 32
    buf = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(mdc, bmp, 0, h, buf, ctypes.byref(bmi), 0)
    px = bytearray(buf.raw[:w * h * 4])
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mdc)
    user32.ReleaseDC(hwnd, hdc)
    if not any(px[i] + px[i + 1] + px[i + 2] > 30 for i in range(0, len(px), 4)):
        return False                       # 全黑视为失败
    for i in range(0, len(px), 4):
        px[i], px[i + 2] = px[i + 2], px[i]   # BGRA -> RGBA
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "wb") as f:
        f.write(icon_extractor._png(w, h, bytes(px)))
    print(f"已保存: {OUT} ({w}x{h})")
    return True


a = App()


def shot():
    # 展开暗黑IV卡片（其页签含测试数据「暗黑核」）
    d4 = next((g for g in a.games if "暗黑" in g.name), None)
    if d4:
        card = a._cards.get(d4.uid)
        if card and not card._expanded:
            card.toggle_expand()
    # 等 favicon 加载（最多 15 秒）
    t0 = time.time()
    while time.time() - t0 < 15 and len(a._fav_images) < 3:
        a.update()
        time.sleep(0.3)
    time.sleep(0.3)
    a.update()
    if not capture():
        print("截图失败")
    a.destroy()


a.after(12000, shot)
a.mainloop()
