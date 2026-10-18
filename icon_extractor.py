# -*- coding: utf-8 -*-
"""icon_extractor.py —— 从 exe 提取图标并转为 PNG（纯标准库 + Windows API）"""
import base64
import ctypes
import ctypes.wintypes as wt
import struct
import zlib

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32


class _BITMAP(ctypes.Structure):
    _fields_ = [("bmType", ctypes.c_long), ("bmWidth", ctypes.c_long),
                ("bmHeight", ctypes.c_long), ("bmWidthBytes", ctypes.c_long),
                ("bmPlanes", wt.WORD), ("bmBitsPixel", wt.WORD),
                ("bmBits", ctypes.c_void_p)]


class _BMIH(ctypes.Structure):
    _fields_ = [("biSize", ctypes.c_uint32), ("biWidth", ctypes.c_int),
                ("biHeight", ctypes.c_int), ("biPlanes", wt.WORD),
                ("biBitCount", wt.WORD), ("biCompression", ctypes.c_uint32),
                ("biSizeImage", ctypes.c_uint32), ("biXPelsPerMeter", ctypes.c_int),
                ("biYPelsPerMeter", ctypes.c_int), ("biClrUsed", ctypes.c_uint32),
                ("biClrImportant", ctypes.c_uint32)]


class _ICONINFO(ctypes.Structure):
    _fields_ = [("fIcon", ctypes.c_bool), ("xHotspot", ctypes.c_uint),
                ("yHotspot", ctypes.c_uint), ("hbmMask", ctypes.c_void_p),
                ("hbmColor", ctypes.c_void_p)]


# 显式声明签名，避免 64 位下句柄被截断
user32.PrivateExtractIconsW.argtypes = [wt.LPCWSTR, ctypes.c_int, ctypes.c_int,
                                        ctypes.c_int, ctypes.POINTER(ctypes.c_void_p),
                                        ctypes.POINTER(ctypes.c_uint), ctypes.c_uint,
                                        ctypes.c_uint]
user32.PrivateExtractIconsW.restype = ctypes.c_uint
user32.GetIconInfo.argtypes = [ctypes.c_void_p, ctypes.POINTER(_ICONINFO)]
user32.GetIconInfo.restype = wt.BOOL
user32.DestroyIcon.argtypes = [ctypes.c_void_p]
user32.DestroyIcon.restype = wt.BOOL
user32.GetDC.argtypes = [ctypes.c_void_p]
user32.GetDC.restype = ctypes.c_void_p
user32.ReleaseDC.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
gdi32.GetObjectW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
gdi32.GetObjectW.restype = ctypes.c_int
gdi32.GetDIBits.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint,
                            ctypes.c_void_p, ctypes.POINTER(_BMIH), ctypes.c_uint]
gdi32.GetDIBits.restype = ctypes.c_int
gdi32.DeleteObject.argtypes = [ctypes.c_void_p]
gdi32.DeleteObject.restype = wt.BOOL


def _hicon_to_png(hicon) -> bytes | None:
    """hIcon -> PNG 字节"""
    ii = _ICONINFO()
    if not user32.GetIconInfo(hicon, ctypes.byref(ii)) or not ii.hbmColor:
        return None
    hdc = user32.GetDC(None)
    try:
        bm = _BITMAP()
        if not gdi32.GetObjectW(ctypes.c_void_p(ii.hbmColor),
                                ctypes.sizeof(_BITMAP), ctypes.byref(bm)):
            return None
        w, h = int(bm.bmWidth), abs(int(bm.bmHeight))
        if not (0 < w <= 256 and 0 < h <= 256):
            return None
        bmi = _BMIH()
        bmi.biSize = ctypes.sizeof(_BMIH)
        bmi.biWidth, bmi.biHeight = w, -h          # 负高度 = 自顶向下
        bmi.biPlanes, bmi.biBitCount = 1, 32
        buf = ctypes.create_string_buffer(w * h * 4)
        if not gdi32.GetDIBits(hdc, ctypes.c_void_p(ii.hbmColor), 0, h,
                               buf, ctypes.byref(bmi), 0):
            return None
        px = bytearray(buf.raw[:w * h * 4])
        for i in range(0, len(px), 4):             # BGRA -> RGBA
            px[i], px[i + 2] = px[i + 2], px[i]
        if not any(px[i] for i in range(3, len(px), 4)):
            # 老式图标没有 alpha 通道：用单色掩码推断透明像素
            mstride = (w + 31) // 32 * 4
            mbmi = _BMIH()
            mbmi.biSize = ctypes.sizeof(_BMIH)
            mbmi.biWidth, mbmi.biHeight = w, -h
            mbmi.biPlanes, mbmi.biBitCount = 1, 1
            mbuf = ctypes.create_string_buffer(mstride * h)
            if gdi32.GetDIBits(hdc, ctypes.c_void_p(ii.hbmMask), 0, h,
                               mbuf, ctypes.byref(mbmi), 0):
                for y in range(h):
                    row = mbuf.raw[y * mstride:(y + 1) * mstride]
                    for x in range(w):
                        bit = (row[x // 8] >> (7 - x % 8)) & 1
                        px[(y * w + x) * 4 + 3] = 0 if bit else 255
        return _png(w, h, bytes(px))
    finally:
        gdi32.DeleteObject(ctypes.c_void_p(ii.hbmColor))
        gdi32.DeleteObject(ctypes.c_void_p(ii.hbmMask))
        user32.ReleaseDC(None, ctypes.c_void_p(hdc))


def exe_to_png(path: str, size: int = 48) -> bytes | None:
    """提取 exe 图标，返回 PNG 字节；失败返回 None"""
    hicon = ctypes.c_void_p()
    pid = ctypes.c_uint()
    n = user32.PrivateExtractIconsW(path, 0, size, size,
                                    ctypes.byref(hicon), ctypes.byref(pid), 1, 0)
    if n < 1 or not hicon.value:
        return None
    try:
        return _hicon_to_png(hicon)
    finally:
        user32.DestroyIcon(hicon)


def _png(w: int, h: int, rgba: bytes) -> bytes:
    """将 RGBA 像素打包为 PNG（8bit/RGBA，无过滤）"""
    def chunk(tag, data):
        c = tag + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)
    raw = b"".join(b"\x00" + rgba[y * w * 4:(y + 1) * w * 4] for y in range(h))
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


def photo_data(png: bytes) -> str:
    """PNG 字节 -> tkinter PhotoImage 可用的 base64 字符串"""
    return base64.b64encode(png).decode("ascii")
