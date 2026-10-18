# -*- coding: utf-8 -*-
"""favicons.py —— 网页页签图标：下载 favicon -> PNG 缓存
纯标准库 + GDI+（解码 ICO/PNG/JPG/BMP/GIF 等任意格式，无需 Pillow）
获取顺序与浏览器一致：首页 HTML 的 <link rel=icon> 声明优先，/favicon.ico 兜底"""
import ctypes
import ctypes.wintypes as wt
import os
import re
import time
import urllib.request
from urllib.parse import urljoin

import icon_extractor   # 复用 _png 编码器

CACHE = os.path.join(os.environ["APPDATA"], "GameManager", "favicons")
TARGET = 16             # 页签图标显示尺寸
FAIL_RETRY = 7 * 86400  # 下载失败后 7 天内不重试

_gdiplus = ctypes.WinDLL("gdiplus")


class _StartupInput(ctypes.Structure):
    _fields_ = [("Version", ctypes.c_uint32), ("DebugEventCallback", ctypes.c_void_p),
                ("SuppressBackgroundThread", wt.BOOL), ("SuppressExternalCodecs", wt.BOOL)]


class _Rect(ctypes.Structure):
    _fields_ = [("X", ctypes.c_int), ("Y", ctypes.c_int),
                ("Width", ctypes.c_int), ("Height", ctypes.c_int)]


class _BitmapData(ctypes.Structure):
    _fields_ = [("Width", ctypes.c_uint), ("Height", ctypes.c_uint),
                ("Stride", ctypes.c_int), ("PixelFormat", ctypes.c_int),
                ("Scan0", ctypes.c_void_p), ("Reserved", ctypes.c_void_p)]


_gdiplus.GdipCreateBitmapFromFile.argtypes = [wt.LPCWSTR, ctypes.POINTER(ctypes.c_void_p)]
_gdiplus.GdipCreateBitmapFromFile.restype = ctypes.c_int
_gdiplus.GdipGetImageWidth.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint)]
_gdiplus.GdipGetImageHeight.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint)]
_gdiplus.GdipBitmapLockBits.argtypes = [ctypes.c_void_p, ctypes.POINTER(_Rect),
                                        ctypes.c_uint, ctypes.c_int, ctypes.POINTER(_BitmapData)]
_gdiplus.GdipBitmapUnlockBits.argtypes = [ctypes.c_void_p, ctypes.POINTER(_BitmapData)]
_gdiplus.GdipDisposeImage.argtypes = [ctypes.c_void_p]

_token = ctypes.c_void_p()
_inited = False


def _ensure():
    global _inited
    if not _inited:
        si = _StartupInput()
        si.Version = 1
        if _gdiplus.GdiplusStartup(ctypes.byref(_token), ctypes.byref(si), None) != 0:
            raise OSError("GDI+ 初始化失败")
        _inited = True


def decode_file(path: str):
    """GDI+ 解码图片文件 -> (w, h, rgba)；失败返回 None"""
    _ensure()
    bmp = ctypes.c_void_p()
    if _gdiplus.GdipCreateBitmapFromFile(path, ctypes.byref(bmp)) != 0 or not bmp.value:
        return None
    try:
        w, h = ctypes.c_uint(), ctypes.c_uint()
        _gdiplus.GdipGetImageWidth(bmp, ctypes.byref(w))
        _gdiplus.GdipGetImageHeight(bmp, ctypes.byref(h))
        w, h = w.value, h.value
        if not (0 < w <= 512 and 0 < h <= 512):
            return None
        rc = _Rect(0, 0, w, h)
        bd = _BitmapData()
        if _gdiplus.GdipBitmapLockBits(bmp, ctypes.byref(rc), 1, 0x26200A,
                                       ctypes.byref(bd)) != 0:   # 1=读, 0x26200A=32bppARGB
            return None
        try:
            buf = ctypes.string_at(bd.Scan0, abs(bd.Stride) * h)
        finally:
            _gdiplus.GdipBitmapUnlockBits(bmp, ctypes.byref(bd))
        # ARGB DWORD 小端 -> 内存字节 B,G,R,A -> 转 RGBA
        stride = abs(bd.Stride)
        out = bytearray(w * h * 4)
        for y in range(h):
            row = buf[y * stride:y * stride + w * 4]
            base = y * w * 4
            for x in range(0, w * 4, 4):
                out[base + x] = row[x + 2]        # R
                out[base + x + 1] = row[x + 1]    # G
                out[base + x + 2] = row[x]        # B
                out[base + x + 3] = row[x + 3]    # A
        return w, h, bytes(out)
    finally:
        _gdiplus.GdipDisposeImage(bmp)


def _shrink(w, h, px):
    """面积平均降采样到 ≤TARGET px"""
    if max(w, h) <= TARGET:
        return w, h, px
    nw = max(1, round(w * TARGET / max(w, h)))
    nh = max(1, round(h * TARGET / max(w, h)))
    out = bytearray(nw * nh * 4)
    for y in range(nh):
        y0, y1 = y * h // nh, (y + 1) * h // nh or h
        for x in range(nw):
            x0, x1 = x * w // nw, (x + 1) * w // nw or w
            r = g = b = a = cnt = 0
            for yy in range(y0, y1):
                base = yy * w * 4
                for xx in range(x0, x1):
                    i = base + xx * 4
                    r += px[i]; g += px[i + 1]; b += px[i + 2]; a += px[i + 3]
                    cnt += 1
            o = (y * nw + x) * 4
            out[o], out[o + 1], out[o + 2], out[o + 3] = r // cnt, g // cnt, b // cnt, a // cnt
    return nw, nh, bytes(out)


def lookup(host: str):
    """查本地缓存 -> (png|None, 需要下载吗)。0 字节文件 = 曾失败（过期才重试）"""
    if not host:
        return None, False
    p = os.path.join(CACHE, host + ".png")
    try:
        if os.path.getsize(p) == 0:
            stale = time.time() - os.path.getmtime(p) > FAIL_RETRY
            return None, stale
        with open(p, "rb") as f:
            return f.read(), False
    except OSError:
        return None, True


def fetch(host: str):
    """下载 favicon，解码并缓存；成功返回 PNG 字节"""
    os.makedirs(CACHE, exist_ok=True)
    dst = os.path.join(CACHE, host + ".png")
    dec = None
    for url in _icon_links(host) + [f"https://{host}/favicon.ico",
                                    f"http://{host}/favicon.ico"]:
        try:
            data = _get(url)
        except Exception:
            continue
        if not data:
            continue
        tmp = dst + ".tmp"
        try:
            with open(tmp, "wb") as f:
                f.write(data)
            dec = decode_file(tmp)
        except OSError:
            dec = None
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass
        if dec:
            break
    if not dec:
        open(dst, "wb").close()          # 失败占位（7 天后重试）
        return None
    w, h, px = dec
    if not any(px[i] for i in range(3, len(px), 4)):   # 全透明 = 无效图
        open(dst, "wb").close()
        return None
    w, h, px = _shrink(w, h, px)
    png = icon_extractor._png(w, h, px)
    with open(dst, "wb") as f:
        f.write(png)
    return png


_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) GameCenter/1.1"}


def _get(url: str, limit=512 * 1024) -> bytes:
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=8) as r:
        return r.read(limit)


def _icon_links(host: str) -> list:
    """解析首页 HTML 里的 <link rel=icon> 图标地址（非 SVG、非 apple-touch 优先）"""
    html = ""
    for scheme in ("https", "http"):
        try:
            html = _get(f"{scheme}://{host}/", 256 * 1024).decode("utf-8", "ignore")
            break
        except Exception:
            continue
    if not html:
        return []
    found = []
    for m in re.finditer(r"<link\b[^>]*>", html, re.I):
        tag = m.group(0)
        rel = re.search(r"rel\s*=\s*[\"']([^\"']+)[\"']", tag, re.I)
        href = re.search(r"href\s*=\s*[\"']([^\"']+)[\"']", tag, re.I)
        if not (rel and href) or "icon" not in rel.group(1).lower():
            continue
        u = href.group(1)
        if u.lower().endswith(".svg"):            # GDI+ 不支持 SVG
            continue
        if "apple-touch" in rel.group(1).lower():
            found.append(u)
        else:
            found.insert(0, u)
    return [urljoin(f"https://{host}/", u) for u in found]
