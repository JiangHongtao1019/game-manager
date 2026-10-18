# -*- coding: utf-8 -*-
"""make_icon.py —— 生成应用图标 icon.ico（纯标准库，不依赖 Pillow）
渐变圆角背景 + 白色游戏手柄，超采样抗锯齿，打包为多尺寸 BMP-ICO。
"""
import math
import os
import struct

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico")

C_BG1, C_BG2 = (79, 140, 255), (138, 99, 211)   # 蓝 -> 紫
WHITE = (255, 255, 255)
DARK = (61, 111, 214)
BTN = [(364, 228, (247, 201, 72)),              # 黄
       (392, 256, (76, 217, 123)),              # 绿
       (364, 284, (82, 168, 255)),              # 蓝
       (336, 256, (234, 90, 71))]               # 红

S = 1.4        # 手柄纵向拉伸系数（减少上下留白）
C_Y = 285      # 手柄几何中心（拉伸后映射到画布中央）


def _sd_rr(px, py, cx, cy, hw, hh, r):
    """圆角矩形有符号距离（<=0 表示在形状内）"""
    dx = abs(px - cx) - (hw - r)
    dy = abs(py - cy) - (hh - r)
    ax = dx if dx > 0 else 0.0
    ay = dy if dy > 0 else 0.0
    return math.hypot(ax, ay) + min(max(dx, dy), 0.0) - r


def _pixel(x, y):
    """512 坐标系中一点的颜色 (r, g, b, a)"""
    if _sd_rr(x, y, 256, 256, 238, 238, 108) > 0:   # 圆角方形背景（不参与拉伸）
        return (0, 0, 0, 0)
    t = (x + y) / 1022                               # 对角渐变
    c = (C_BG1[0] + (C_BG2[0] - C_BG1[0]) * t,
         C_BG1[1] + (C_BG2[1] - C_BG1[1]) * t,
         C_BG1[2] + (C_BG2[2] - C_BG1[2]) * t)
    sy = C_Y + (y - 256) / S                         # 逆映射：屏幕 -> 手柄坐标系
    # ---- 以下为第一版手柄几何（通过 sy 实现纵向拉伸）----
    # 主体：横板 + 左右握把
    if (_sd_rr(x, sy, 256, 256, 162, 58, 58) <= 0
            or math.hypot(x - 129, sy - 301) <= 71
            or math.hypot(x - 383, sy - 301) <= 71):
        c = WHITE
    # 十字键
    if (_sd_rr(x, sy, 148, 256, 9.5, 37, 9) <= 0
            or _sd_rr(x, sy, 148, 256, 37, 9.5, 9) <= 0):
        c = DARK
    # 四色功能键
    for bx, by, bc in BTN:
        if math.hypot(x - bx, sy - by) <= 13:
            c = bc
    # 中央菜单键
    if (_sd_rr(x, sy, 230, 256, 12, 7, 7) <= 0
            or _sd_rr(x, sy, 282, 256, 12, 7, 7) <= 0):
        c = DARK
    return (c[0], c[1], c[2], 255)


def _render(size):
    """按目标尺寸渲染 RGBA，2x2 超采样抗锯齿"""
    inv = 512 / size
    data = bytearray(size * size * 4)
    idx = 0
    for j in range(size):
        for i in range(size):
            r = g = b = a = 0
            for dj in (0.25, 0.75):
                for di in (0.25, 0.75):
                    c = _pixel((i + di) * inv, (j + dj) * inv)
                    r += c[0]; g += c[1]; b += c[2]; a += c[3]
            data[idx] = int(r / 4 + 0.5)
            data[idx + 1] = int(g / 4 + 0.5)
            data[idx + 2] = int(b / 4 + 0.5)
            data[idx + 3] = int(a / 4 + 0.5)
            idx += 4
    return bytes(data)


def _downscale(src, sw, factor):
    """整数倍盒式降采样"""
    dw = sw // factor
    out = bytearray(dw * dw * 4)
    idx = 0
    for j in range(dw):
        for i in range(dw):
            r = g = b = a = 0
            for bj in range(factor):
                base = ((j * factor + bj) * sw + i * factor) * 4
                for _ in range(factor):
                    r += src[base]; g += src[base + 1]
                    b += src[base + 2]; a += src[base + 3]
                    base += 4
            n = factor * factor
            out[idx] = r // n; out[idx + 1] = g // n
            out[idx + 2] = b // n; out[idx + 3] = a // n
            idx += 4
    return bytes(out)


def _ico_bmp_entry(rgba, w):
    """RGBA -> ICO 的 BMP 格式条目（32bpp + AND 掩码）"""
    hdr = struct.pack("<IiiHHIIiiII", 40, w, w * 2, 1, 32, 0,
                      w * w * 4 + ((w + 31) // 32) * 4 * w, 0, 0, 0, 0)
    xor = bytearray()
    for y in range(w - 1, -1, -1):                   # 自底向上
        row = rgba[y * w * 4:(y + 1) * w * 4]
        for i in range(0, len(row), 4):              # RGBA -> BGRA
            xor.extend((row[i + 2], row[i + 1], row[i], row[i + 3]))
    return hdr + bytes(xor) + b"\x00" * (((w + 31) // 32) * 4 * w)


def build():
    master = _render(256)
    imgs = {256: master, 48: _render(48)}
    for s, f in ((128, 2), (64, 4), (32, 8), (16, 16)):
        imgs[s] = _downscale(master, 256, f)
    sizes = sorted(imgs)
    entries, blob = b"", b""
    for s in sizes:
        data = _ico_bmp_entry(imgs[s], s)
        b = s if s < 256 else 0
        entries += struct.pack("<BBBBHHII", b, b, 0, 0, 1, 32,
                               len(data), 6 + 16 * len(sizes) + len(blob))
        blob += data
    with open(OUT, "wb") as f:
        f.write(struct.pack("<HHH", 0, 1, len(sizes)) + entries + blob)
    print("已生成:", OUT)
    print("包含尺寸:", sizes, "| 文件大小:", os.path.getsize(OUT), "字节")
    # 同步导出 256px PNG 预览
    try:
        import icon_extractor
        png = os.path.join(os.path.dirname(OUT), "icon_preview.png")
        with open(png, "wb") as f:
            f.write(icon_extractor._png(256, 256, master))
        print("预览图:", png)
    except Exception as e:
        print("预览图生成失败:", e)


if __name__ == "__main__":
    build()
