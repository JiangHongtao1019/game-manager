# -*- coding: utf-8 -*-
"""app.py —— 游戏中心：一键启动 / 跳转路径 / 一键卸载"""
import ctypes
import json
import os
import subprocess
import threading
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk, filedialog, messagebox
from urllib.parse import urlparse, quote

import favicons
import icon_extractor
import scanner
from scanner import Game

__version__ = "1.1"

# ---------------- 配置存取 ----------------
APP_DIR = os.path.join(os.environ["APPDATA"], "GameManager")
CONFIG_PATH = os.path.join(APP_DIR, "config.json")

def load_config() -> dict:
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception:
        cfg = {}
    cfg.setdefault("manual", [])
    cfg.setdefault("hidden", [])
    cfg.setdefault("launch_override", {})
    cfg.setdefault("bookmarks", {})
    return cfg

def save_config(cfg: dict):
    os.makedirs(APP_DIR, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

# ---------------- 主题 ----------------
BG = "#0f1116"          # 主背景
SIDE = "#0b0d12"        # 侧栏
CARD = "#181c24"        # 卡片
CARD_HOVER = "#222a3a"
BORDER = "#273044"
BORDER_H = "#3b4a6b"
ACCENT = "#5b8cff"
ACCENT_HOVER = "#4a7bf0"
TEXT = "#eceef2"
SUB = "#8a93a5"
DANGER = "#ef5350"
ENTRY_BG = "#171b23"
BTN_SUB = "#232936"     # 次级按钮
PILL = "#242c3f"        # 网页页签
PILL_HOVER = "#303b55"
BAR_BG = "#0c0f16"
FONT = "Microsoft YaHei UI"
AVATAR_COLORS = ["#e5484d", "#e08c48", "#d2b23f", "#5aa74c",
                 "#3fa88d", "#4f8cff", "#8a63d3", "#d05cb8"]
CHIP_COLORS = {"Steam": "#3d6fd9", "Epic": "#8b5cf6", "注册表": "#c96f3b",
               "GameUX": "#2f9e8f", "手动添加": "#4e9e56"}

def mk_btn(parent, text, cmd, bg_, fg_, hover, padx=12):
    return tk.Button(parent, text=text, command=cmd, bg=bg_, fg=fg_,
                     activebackground=hover, activeforeground=fg_, relief="flat",
                     bd=0, padx=padx, pady=4, font=(FONT, 9), cursor="hand2")

def short_path(p: str, n=52) -> str:
    if not p:
        return ""
    return p if len(p) <= n else p[:n // 2 - 4] + "…" + p[-n // 2:]

def round_rect(cv, x1, y1, x2, y2, r, **kw):
    """在 Canvas 上画圆角矩形"""
    pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
           x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    return cv.create_polygon(pts, smooth=True, **kw)

def fmt_size(n) -> str:
    """字节数 -> 人类可读"""
    if n is None:
        return "—"
    if n >= 1024 ** 3:
        return f"{n / 1024 ** 3:.1f} GB"
    if n >= 1024 ** 2:
        return f"{n / 1024 ** 2:.0f} MB"
    if n >= 1024:
        return f"{n / 1024:.0f} KB"
    return f"{n} B"


def default_tabs(g: Game) -> list:
    """安全预置页签：只放确定性链接（Steam 官方清单数据 + 搜索页本身），
    具体攻略站（如暗黑核）由用户点 ＋ 手动添加"""
    tabs = []
    if getattr(g, "appid", ""):
        tabs.append({"name": "Steam商店",
                     "url": f"https://store.steampowered.com/app/{g.appid}/"})
    tabs.append({"name": "搜攻略",
                 "url": "https://www.baidu.com/s?wd=" + quote(g.name + " 攻略")})
    tabs.append({"name": "B站视频",
                 "url": "https://search.bilibili.com/all?keyword=" + quote(g.name)})
    return tabs

def _shell_exec(exe: str, args: str | None):
    """ShellExecuteW 启动 —— 与双击一致：自动 UAC 提权、无控制台窗口"""
    wd = os.path.dirname(exe) if os.path.isfile(exe) else None
    r = ctypes.windll.shell32.ShellExecuteW(None, "open", exe, args, wd, 1)
    if r <= 32:
        raise OSError(f"启动失败（ShellExecute 返回 {r}）")

# ---------------- 圆角按钮 ----------------
class RoundButton(tk.Canvas):
    def __init__(self, master, text, cmd=None, bg_=BTN_SUB, fg_="#c9d1e0",
                 hover="#39445c", h=30, r=10, padx=14, fs=9, bold=False, enabled=True):
        f = tkfont.Font(family=FONT, size=fs, weight="bold" if bold else "normal")
        w = f.measure(text) + padx * 2
        if not enabled:
            bg_ = hover = "#252b39"
            fg_ = "#6b7488"
        super().__init__(master, width=w, height=h, bg=master["bg"],
                         highlightthickness=0, cursor="hand2" if enabled else "arrow")
        self._base, self._hover, self._enabled = bg_, hover, enabled
        self._rect = round_rect(self, 1, 1, w - 1, h - 1, r, fill=bg_, outline="")
        self.create_text(w // 2, h // 2, text=text, fill=fg_, font=f)
        if enabled and cmd:
            self.bind("<Button-1>", lambda e: cmd())
        self.bind("<Enter>", lambda e: self._set(self._hover))
        self.bind("<Leave>", lambda e: self._set(self._base))

    def _set(self, c):
        if self._enabled:
            self.itemconfigure(self._rect, fill=c)

    def set_canvas_bg(self, c):
        self.configure(bg=c)

# ---------------- 折叠开关 / 网页页签 ----------------
class Chevron(tk.Label):
    """信息行尾的折叠开关小箭头（自带交互，不参与卡片递归绑定）"""

    def __init__(self, master, card):
        super().__init__(master, bg=CARD, fg=SUB, font=(FONT, 8),
                         cursor="hand2", text="▸")
        self.bind("<Button-1>", lambda e: card.toggle_expand())
        self.bind("<Enter>", lambda e: self.configure(fg=ACCENT))
        self.bind("<Leave>", lambda e: self.configure(fg=SUB))

    def set_open(self, on):
        self.configure(text="▾" if on else "▸")


class WebPill(tk.Label):
    """网页页签药丸按钮（自带点击/右键/悬停交互）"""

    def __init__(self, master, text, cmd, menu=None, image=None):
        super().__init__(master, text=text, image=image or "", compound="left",
                         bg=PILL, fg="#c9d1e0", font=(FONT, 8), padx=10, pady=4,
                         cursor="hand2")
        self._menu = menu
        self.bind("<Button-1>", lambda e: cmd())
        self.bind("<Enter>", lambda e: self.configure(bg=PILL_HOVER))
        self.bind("<Leave>", lambda e: self.configure(bg=PILL))
        if menu:
            self.bind("<Button-3>", lambda e: menu(e))

# ---------------- 侧栏导航项 ----------------
class NavItem(tk.Frame):
    def __init__(self, master, icon, label, cmd):
        super().__init__(master, bg=SIDE, cursor="hand2")
        self._cmd, self._active = cmd, False
        self.ind = tk.Frame(self, bg=SIDE, width=3)
        self.ind.pack(side="left", fill="y")
        body = tk.Frame(self, bg=SIDE)
        body.pack(side="left", fill="x", expand=True)
        self.ic = tk.Label(body, text=icon, bg=SIDE, fg="#7c8699",
                           font=(FONT, 10), width=3, anchor="w")
        self.ic.pack(side="left", pady=8)
        self.tx = tk.Label(body, text=label, bg=SIDE, fg="#aab3c5",
                           font=(FONT, 10), anchor="w")
        self.tx.pack(side="left")
        self.ct = tk.Label(body, text="", bg=SIDE, fg="#5c6577", font=(FONT, 8))
        self.ct.pack(side="right", padx=(0, 16))
        for w in (self, body, self.ic, self.tx, self.ct):
            w.bind("<Button-1>", lambda e: cmd())
            w.bind("<Enter>", lambda e: self._hl(True))
            w.bind("<Leave>", lambda e: self._hl(False))

    def _hl(self, on):
        if self._active:
            return
        bg_ = "#141a28" if on else SIDE
        for w in (self, self.ic, self.tx, self.ct):
            w.configure(bg=bg_)

    def set_active(self, a):
        self._active = a
        bg_ = "#182136" if a else SIDE
        for w in (self, self.ic, self.tx, self.ct):
            w.configure(bg=bg_)
        self.tx.configure(fg=TEXT if a else "#aab3c5")
        self.ct.configure(fg=ACCENT if a else "#5c6577")
        self.ind.configure(bg=ACCENT if a else SIDE)

    def set_count(self, n):
        self.ct.configure(text=str(n) if n else "—")

# ---------------- 路径信息对话框 ----------------
class PathDialog(tk.Toplevel):
    def __init__(self, master, game: Game):
        super().__init__(master)
        self.configure(bg=BG, padx=16)
        self.title(f"路径信息 - {game.name}")
        self.geometry("600x350")
        self.resizable(False, False)
        tk.Label(self, text=game.name, bg=BG, fg=TEXT,
                 font=(FONT, 14, "bold")).pack(anchor="w", pady=(12, 10))
        try:
            sz = fmt_size(master._sizes[game.uid])
        except Exception:
            sz = "统计中…"
        rows = [("启动命令", game.launch or "（未设置 — 可右键卡片设置启动路径）", False),
                ("安装目录", game.install_dir or "（未知）", True),
                ("占用空间", sz, False),
                ("卸载命令", game.uninstall or "（未知）", False)]
        for label, value, with_open in rows:
            tk.Label(self, text=label, bg=BG, fg=SUB,
                     font=(FONT, 8, "bold")).pack(anchor="w", pady=(6, 2))
            row = tk.Frame(self, bg=BG)
            row.pack(fill="x")
            e = tk.Entry(row, bg=ENTRY_BG, fg=TEXT, insertbackground=TEXT,
                         relief="flat", font=(FONT, 9), readonlybackground=ENTRY_BG)
            e.insert(0, value)
            e.configure(state="readonly")
            e.pack(side="left", fill="x", expand=True, ipady=3)
            mk_btn(row, "复制", lambda v=value: self.copy(v),
                   CARD, TEXT, CARD_HOVER).pack(side="left", padx=(6, 0))
            if with_open:
                mk_btn(row, "📁 打开", lambda v=value: os.startfile(v),
                       CARD, TEXT, CARD_HOVER).pack(side="left", padx=(6, 0))
        mk_btn(self, "关 闭", self.destroy, CARD, TEXT, CARD_HOVER,
               padx=28).pack(pady=16)

    def copy(self, v: str):
        self.clipboard_clear()
        self.clipboard_append(v)

# ---------------- 手动添加对话框 ----------------
class AddGameDialog(tk.Toplevel):
    def __init__(self, master, app: "App"):
        super().__init__(master)
        self.app = app
        self.configure(bg=BG, padx=16)
        self.title("手动添加游戏")
        self.geometry("480x190")
        self.resizable(False, False)
        tk.Label(self, text="添加一个不在自动扫描列表里的游戏", bg=BG, fg=SUB,
                 font=(FONT, 9)).pack(anchor="w", pady=(12, 6))
        tk.Label(self, text="游戏名称", bg=BG, fg=TEXT, font=(FONT, 9)).pack(anchor="w")
        self.name = tk.Entry(self, bg=ENTRY_BG, fg=TEXT, insertbackground=TEXT,
                             relief="flat", font=(FONT, 10))
        self.name.pack(fill="x", ipady=4, pady=(2, 8))
        tk.Label(self, text="游戏主程序 (.exe)", bg=BG, fg=TEXT, font=(FONT, 9)).pack(anchor="w")
        prow = tk.Frame(self, bg=BG)
        prow.pack(fill="x", pady=2)
        self.exe = tk.Entry(prow, bg=ENTRY_BG, fg=TEXT, insertbackground=TEXT,
                            relief="flat", font=(FONT, 10))
        self.exe.pack(side="left", fill="x", expand=True, ipady=4)
        mk_btn(prow, "浏览…", self.browse, CARD, TEXT, CARD_HOVER).pack(side="left", padx=(6, 0))
        brow = tk.Frame(self, bg=BG)
        brow.pack(fill="x", pady=(12, 0))
        mk_btn(brow, "添 加", self.save, ACCENT, "white", ACCENT_HOVER, padx=24).pack(side="right")
        mk_btn(brow, "取 消", self.destroy, CARD, TEXT, CARD_HOVER, padx=24).pack(side="right", padx=6)

    def browse(self):
        p = filedialog.askopenfilename(parent=self, title="选择游戏主程序",
                                       filetypes=[("可执行文件", "*.exe"), ("所有文件", "*.*")])
        if p:
            self.exe.delete(0, "end")
            self.exe.insert(0, p)
            if not self.name.get():
                self.name.insert(0, os.path.splitext(os.path.basename(p))[0])

    def save(self):
        name, exe = self.name.get().strip(), self.exe.get().strip()
        if not name or not (exe.lower().endswith(".exe") and os.path.isfile(exe)):
            messagebox.showwarning("提示", "请填写游戏名称并选择有效的 .exe 文件", parent=self)
            return
        d = Game(name, "手动添加", launch=exe,
                 install_dir=os.path.dirname(exe), uninstall="").to_dict()
        self.app.cfg.setdefault("manual", []).append(d)
        save_config(self.app.cfg)
        self.destroy()
        self.app.start_scan()

# ---------------- 网页页签对话框 ----------------
class BookmarkDialog(tk.Toplevel):
    """添加 / 编辑网页页签"""

    def __init__(self, app: "App", game: Game, index: int | None = None):
        super().__init__(app)
        self.app, self.game, self.index = app, game, index
        self.configure(bg=BG, padx=16)
        if index is None:
            self.title("添加网页页签")
            head, name, url = f"给「{game.name}」添加一个常用网站页签", "", ""
        else:
            self.title("编辑网页页签")
            t = app.get_tabs(game)[index]
            head, name, url = f"编辑「{game.name}」的网页页签", t["name"], t["url"]
        self.geometry("440x240")
        self.resizable(False, False)
        tk.Label(self, text=head, bg=BG, fg=SUB, font=(FONT, 9)).pack(anchor="w", pady=(12, 6))
        tk.Label(self, text="名字", bg=BG, fg=TEXT, font=(FONT, 9)).pack(anchor="w")
        self.name = tk.Entry(self, bg=ENTRY_BG, fg=TEXT, insertbackground=TEXT,
                             relief="flat", font=(FONT, 10))
        self.name.pack(fill="x", ipady=4, pady=(2, 8))
        self.name.insert(0, name)
        tk.Label(self, text="网址", bg=BG, fg=TEXT, font=(FONT, 9)).pack(anchor="w")
        self.url = tk.Entry(self, bg=ENTRY_BG, fg=TEXT, insertbackground=TEXT,
                            relief="flat", font=(FONT, 10))
        self.url.pack(fill="x", ipady=4, pady=(2, 4))
        self.url.insert(0, url)
        tk.Label(self, text="示例：暗黑核 / www.d2core.com/d4（可不带 https://）",
                 bg=BG, fg="#5c6577", font=(FONT, 7)).pack(anchor="w")
        brow = tk.Frame(self, bg=BG)
        brow.pack(fill="x", pady=(10, 0))
        mk_btn(brow, "保 存", self.save, ACCENT, "white", ACCENT_HOVER, padx=24).pack(side="right")
        mk_btn(brow, "取 消", self.destroy, CARD, TEXT, CARD_HOVER, padx=24).pack(side="right", padx=6)
        self.bind("<Return>", lambda e: self.save())

    def save(self):
        name, url = self.name.get().strip(), self.url.get().strip()
        if not name or not url:
            messagebox.showwarning("提示", "请填写名字和网址", parent=self)
            return
        if "://" not in url:
            url = "https://" + url
        if self.index is None:
            self.app.add_tab(self.game, name, url)
        else:
            self.app.edit_tab(self.game, self.index, name, url)
        self.destroy()

# ---------------- 游戏卡片（圆角卡片） ----------------
class GameCard(tk.Canvas):
    H = 78

    def __init__(self, parent, game: Game, app: "App"):
        super().__init__(parent, bg=BG, height=self.H, highlightthickness=0, cursor="hand2")
        self.game, self.app = game, app
        self._unhover = None
        self._expanded = game.uid in app._expanded
        self._panel_h = 0
        self._pills = []
        self._panel_frame = None
        self._panel_win = None
        self._sep = None
        self.bind("<Configure>", self._layout)

    def _layout(self, _e=None):
        w = self.winfo_width()
        # <Configure> 在位置移动时也会触发（如上方卡片展开导致下移），
        # 但布局只依赖宽度 —— 宽度不变就跳过，避免整列卡片无谓重建
        if w < 60 or w == getattr(self, "_lay_w", None):
            return
        self._lay_w = w
        for c in self.winfo_children():
            c.destroy()
        self.delete("all")
        self._pills = []
        self._panel_frame = self._panel_win = self._sep = None
        self._bgitem = round_rect(self, 1, 1, w - 1, self.H - 1, 16,
                                  fill=CARD, outline=BORDER)
        # 图标块
        photo = self.app.get_photo(self.game)
        tile = tk.Canvas(self, width=54, height=54, bg=CARD, highlightthickness=0)
        round_rect(tile, 0, 0, 53, 53, 15, fill="#20293a", outline="")
        if photo:
            tile.create_image(27, 27, image=photo)
        else:
            color = AVATAR_COLORS[sum(self.game.name.encode("utf-8")) % len(AVATAR_COLORS)]
            tile.create_oval(6, 6, 47, 47, fill=color, outline="")
            tile.create_text(27, 28, text=self.game.name.strip()[:1].upper(),
                             fill="white", font=(FONT, 15, "bold"))
        self.create_window(16, 12, window=tile, anchor="nw")
        # 文本区（create_window 的 width 强制宽度 -> 折叠箭头在各卡片间对齐）
        g, app = self.game, self.app
        txt = tk.Frame(self, bg=CARD)
        tk.Label(txt, text=g.name, bg=CARD, fg=TEXT, anchor="w",
                 font=(FONT, 11, "bold")).pack(anchor="w")
        sub = tk.Frame(txt, bg=CARD)
        sub.pack(anchor="w", fill="x", pady=(4, 0))
        tk.Label(sub, text=g.source, bg=CHIP_COLORS.get(g.source, "#5c6577"),
                 fg="white", font=(FONT, 7, "bold"), padx=7, pady=1).pack(side="left")
        if g.uid in app._sizes:
            self._size_lbl = tk.Label(sub, text="💾 " + fmt_size(app._sizes[g.uid]),
                                      bg=CARD, fg="#8fb3ff", font=(FONT, 8), padx=9)
        else:
            self._size_lbl = tk.Label(sub, text="💾 统计中…", bg=CARD,
                                      fg="#8fb3ff", font=(FONT, 8), padx=9)
        self._size_lbl.pack(side="left")
        if g.install_dir:
            tk.Label(sub, text=short_path(g.install_dir, 40), bg=CARD, fg=SUB,
                     font=(FONT, 8)).pack(side="left")
        self._chev = Chevron(sub, self)
        if self._expanded:
            self._chev.set_open(True)
        self._chev.pack(side="right", padx=(8, 0))
        self.create_window(88, self.H // 2, window=txt, anchor="w",
                           width=max(w - 88 - 235, 240))
        # 按钮区
        btns = tk.Frame(self, bg=CARD)
        RoundButton(btns, "🗑", lambda: app.uninstall_game(g),
                    BTN_SUB, DANGER, "#39445c", h=32, padx=10).pack(side="right", padx=(7, 0))
        RoundButton(btns, "📁", lambda: app.jump_to(g),
                    BTN_SUB, "#c9d1e0", "#39445c", h=32, padx=10).pack(side="right", padx=(7, 0))
        if g.launch:
            RoundButton(btns, "▶  启动", lambda: app.launch_game(g),
                        ACCENT, "white", ACCENT_HOVER, h=32, bold=True).pack(side="right")
        else:
            RoundButton(btns, "▶  启动", None, h=32, bold=True,
                        enabled=False).pack(side="right")
        self.create_window(w - 16, self.H // 2, window=btns, anchor="e")
        # 展开的网页页签面板
        h = self.H + self._build_panel(w) if self._expanded else self.H
        if self.winfo_height() != h:
            self.configure(height=h)
        self._bind_hovers()

    # ---------- 网页页签面板（增量式：只动面板，不重建卡片头部） ----------
    def _build_panel(self, w) -> int:
        """构建/刷新展开的页签区（换行排布 + 末尾 ＋），返回面板高度"""
        self._remove_panel()
        self._sep = self.create_line(16, self.H + 2, w - 16, self.H + 2, fill=BORDER)
        tabs = self.app.get_tabs(self.game)
        panel = tk.Frame(self, bg=CARD)
        self._panel_frame = panel
        avail = max(w - 44, 220)
        row, used = None, 0

        def place(pill):
            nonlocal row, used
            pw = pill.winfo_reqwidth()
            if row is None or used + pw > avail:
                row = tk.Frame(panel, bg=CARD)
                row.pack(fill="x", anchor="w", pady=(6, 0))
                used = 0
            pill.pack(side="left", padx=(0, 8))
            used += pw + 8

        for i, t in enumerate(tabs):
            place(self._make_pill(panel, t, i))
        place(WebPill(panel, "＋", lambda: BookmarkDialog(self.app, self.game)))
        panel.update_idletasks()
        ph = panel.winfo_reqheight()
        self._panel_win = self.create_window(16, self.H + 10, window=panel, anchor="nw")
        self._panel_h = ph + 22
        return self._panel_h

    def _remove_panel(self):
        """移除面板（销毁子控件 + 删除画布项）"""
        if self._panel_frame is not None:
            try:
                self._panel_frame.destroy()
            except tk.TclError:
                pass
        for item in (self._panel_win, self._sep):
            if item is not None:
                try:
                    self.delete(item)
                except tk.TclError:
                    pass
        self._panel_frame = self._panel_win = self._sep = None
        self._pills = []

    def _make_pill(self, parent, tab, index):
        host = urlparse(tab["url"]).netloc
        img = self.app.get_favicon(host)
        pill = WebPill(parent, tab["name"], lambda t=tab: self.app.open_url(t["url"]),
                       menu=lambda e, i=index: self._tab_menu(e, i), image=img)
        self._pills.append((pill, tab))
        return pill

    def _tab_menu(self, event, index):
        m = tk.Menu(self, tearoff=0, bg=CARD, fg=TEXT, activebackground=ACCENT,
                    activeforeground="white", bd=0, relief="flat")
        m.add_command(label="✏️ 编辑页签",
                      command=lambda: BookmarkDialog(self.app, self.game, index))
        m.add_command(label="🗑 删除页签",
                      command=lambda: self.app.delete_tab(self.game, index))
        m.tk_popup(event.x_root, event.y_root)

    def toggle_expand(self):
        """展开/收起：面板只构建一次，之后用 canvas 项显隐切换（零重建）"""
        self._expanded = not self._expanded
        if self._expanded:
            self.app._expanded.add(self.game.uid)
        else:
            self.app._expanded.discard(self.game.uid)
        try:
            self._chev.set_open(self._expanded)
        except (tk.TclError, AttributeError):
            pass
        if self._expanded:
            if self._panel_win is None:           # 首次展开才构建
                self._build_panel(self.winfo_width())
            else:
                self.itemconfigure(self._sep, state="normal")
                self.itemconfigure(self._panel_win, state="normal")
            self.configure(height=self.H + self._panel_h)
        else:
            if self._panel_win is not None:
                self.itemconfigure(self._sep, state="hidden")
                self.itemconfigure(self._panel_win, state="hidden")
            self.configure(height=self.H)

    def rebuild_panel(self):
        """页签数据变化后重刷（仅在展开状态）"""
        if self._expanded:
            self._build_panel(self.winfo_width())
            self.configure(height=self.H + self._panel_h)

    def on_favicon(self, host):
        if not self._pills:
            return
        img = self.app.get_favicon(host)
        if not img:
            return
        for pill, tab in self._pills:
            if urlparse(tab["url"]).netloc == host:
                try:
                    pill.configure(image=img, text=tab["name"])
                except tk.TclError:
                    pass

    def _bind_hovers(self):
        def bindall(w):
            if isinstance(w, (RoundButton, Chevron, WebPill)):
                return
            w.bind("<Enter>", self._enter, add="+")
            w.bind("<Leave>", self._leave, add="+")
            w.bind("<Double-Button-1>", lambda e: self.app.launch_game(self.game), add="+")
            w.bind("<Button-3>", lambda e: self.app.show_menu(e, self.game), add="+")
            for c in w.winfo_children():
                bindall(c)
        bindall(self)

    def set_size(self, n):
        try:
            self._size_lbl.configure(text="💾 " + fmt_size(n))
        except (tk.TclError, AttributeError):
            pass

    def _enter(self, _e):
        if self._unhover:
            self.after_cancel(self._unhover)
            self._unhover = None
        self._paint(True)

    def _leave(self, _e):
        if self._unhover:
            self.after_cancel(self._unhover)
        self._unhover = self.after(50, lambda: self._paint(False))

    def _paint(self, on):
        fill = CARD_HOVER if on else CARD
        try:
            self.itemconfigure(self._bgitem, fill=fill,
                               outline=BORDER_H if on else BORDER)
        except tk.TclError:
            return
        def p(w):
            try:
                if isinstance(w, RoundButton):
                    w.set_canvas_bg(fill)
                elif isinstance(w, (tk.Frame, tk.Label, tk.Canvas)) and w.cget("bg") in (CARD, CARD_HOVER):
                    w.configure(bg=fill)
            except tk.TclError:
                pass
            for c in w.winfo_children():
                p(c)
        p(self)

# ---------------- 主窗口 ----------------
NAV_ITEMS = [("全部", "🎮", "全部游戏"), ("Steam", "🕹", "Steam"),
             ("Epic", "🌐", "Epic"), ("本地", "💾", "本地安装"),
             ("手动添加", "✏️", "手动添加")]

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("游戏管理器")
        self.configure(bg=BG)
        # 按屏幕比例设定窗口大小并居中（适配高分辨率 / 高 DPI 屏幕）
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        w = min(max(int(sw * 0.60), 980), 1560)
        h = min(max(int(sh * 0.80), 640), 1060)
        self.geometry(f"{w}x{h}+{(sw - w) // 2}+{max((sh - h) // 3, 0)}")
        self.minsize(760, 540)
        self._setup_styles()
        try:  # 窗口/任务栏图标
            _icon = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico")
            if os.path.isfile(_icon):
                self.iconbitmap(_icon)
        except tk.TclError:
            pass
        self.cfg = load_config()
        self.games: list[Game] = []
        self._photos: dict[str, tk.PhotoImage] = {}
        self._sizes: dict[str, int | None] = {}
        self._cards: dict[str, GameCard] = {}
        self._size_running = False
        self._expanded: set[str] = set()          # 展开网页区的游戏 uid
        self._fav_images: dict[str, tk.PhotoImage] = {}
        self._fav_pending: set[str] = set()
        self._fav_running = False
        self.scanning = False
        self.filter = "全部"
        self.menu_game: Game | None = None
        self._build_sidebar()
        self._build_main()
        self._build_menu()
        self.nav["全部"].set_active(True)
        self.start_scan()

    # ---------- 界面搭建 ----------
    def _setup_styles(self):
        """必须在创建任何 ttk 控件之前调用；显式指定 master，
        避免 tkinter 偷偷创建隐藏的默认根窗口（即多余的 'tk' 空白弹窗）"""
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("Vertical.TScrollbar", background=BTN_SUB, troughcolor=BG,
                        bordercolor=BG, arrowcolor=SUB, relief="flat", gripcount=0)
        style.configure("Scan.Horizontal.TProgressbar", troughcolor="#151a26",
                        background=ACCENT, bordercolor="#151a26",
                        lightcolor=ACCENT, darkcolor=ACCENT, thickness=3)

    def _build_sidebar(self):
        side = tk.Frame(self, bg=SIDE, width=210)
        side.pack(side="left", fill="y")
        side.pack_propagate(False)
        logo = tk.Frame(side, bg=SIDE)
        logo.pack(fill="x", padx=18, pady=(22, 16))
        tk.Label(logo, text="🎮", bg=SIDE, fg=TEXT, font=(FONT, 16)).pack(side="left")
        tk.Label(logo, text="游戏中心", bg=SIDE, fg=TEXT,
                 font=(FONT, 14, "bold")).pack(side="left", padx=9)
        tk.Frame(side, bg="#1a2130", height=1).pack(fill="x", padx=14)
        tk.Label(side, text="平台", bg=SIDE, fg="#5c6577",
                 font=(FONT, 8)).pack(anchor="w", padx=24, pady=(12, 4))
        self.nav: dict[str, NavItem] = {}
        for key, icon, label in NAV_ITEMS:
            n = NavItem(side, icon, label, lambda k=key: self._set_filter(k))
            n.pack(fill="x", padx=8, pady=1)
            self.nav[key] = n
        tk.Frame(side, bg=SIDE).pack(fill="both", expand=True)
        tk.Frame(side, bg="#1a2130", height=1).pack(fill="x", padx=14, pady=(6, 4))
        for icon, label, cmd in (("＋", "添加游戏", lambda: AddGameDialog(self, self)),
                                 ("⚙", "设置", self.popup_settings),
                                 ("ℹ", "关于", self._about)):
            NavItem(side, icon, label, cmd).pack(fill="x", padx=8, pady=1)
        tk.Label(side, text=f"v{__version__}", bg=SIDE, fg="#3d4656",
                 font=(FONT, 7)).pack(pady=(2, 8))

    def _build_main(self):
        main = tk.Frame(self, bg=BG)
        main.pack(side="right", fill="both", expand=True)
        head = tk.Frame(main, bg=BG)
        head.pack(fill="x", padx=26, pady=(20, 2))
        tk.Label(head, text="游戏中心", bg=BG, fg=TEXT,
                 font=(FONT, 16, "bold")).pack(anchor="w")
        tk.Label(head, text="自动发现本机游戏 · 双击卡片立即启动", bg=BG, fg=SUB,
                 font=(FONT, 8)).pack(anchor="w")
        bar = tk.Frame(main, bg=BG)
        bar.pack(fill="x", padx=26, pady=(10, 8))
        sf = tk.Frame(bar, bg=ENTRY_BG, highlightthickness=1, highlightbackground=BORDER)
        sf.pack(side="left", fill="x", expand=True)
        tk.Label(sf, text="🔍", bg=ENTRY_BG, fg=SUB,
                 font=(FONT, 9)).pack(side="left", padx=(10, 4), pady=6)
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *a: self.refresh_cards())
        e = tk.Entry(sf, textvariable=self.search_var, bg=ENTRY_BG, fg=TEXT,
                     insertbackground=TEXT, relief="flat", font=(FONT, 10),
                     highlightthickness=0)
        e.pack(side="left", fill="x", expand=True, padx=(0, 10), pady=6)
        rb = tk.Frame(bar, bg=BG)
        rb.pack(side="right")
        RoundButton(rb, "⟳ 刷新", self.start_scan).pack(side="right", padx=(8, 0))
        RoundButton(rb, "＋ 添加游戏", lambda: AddGameDialog(self, self),
                    ACCENT, "white", ACCENT_HOVER, bold=True).pack(side="right")
        self.progress = ttk.Progressbar(main, style="Scan.Horizontal.TProgressbar",
                                        mode="indeterminate")
        st = tk.Frame(main, bg=BAR_BG)
        st.pack(fill="x", side="bottom")
        self.status = tk.Label(st, text="正在扫描…", bg=BAR_BG, fg=SUB, anchor="w",
                               font=(FONT, 8), padx=18, pady=5)
        self.status.pack(fill="x")
        body = tk.Frame(main, bg=BG)
        body.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(body, bg=BG, highlightthickness=0, bd=0)
        sb = ttk.Scrollbar(body, orient="vertical", command=self.canvas.yview)
        sb.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.canvas.configure(yscrollcommand=sb.set)
        self.inner = tk.Frame(self.canvas, bg=BG)
        self._win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>",
                        lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>",
                         lambda e: self.canvas.itemconfigure(self._win, width=e.width))
        self.canvas.bind_all("<MouseWheel>",
                             lambda e: self.canvas.yview_scroll(-e.delta // 120, "units"))

    def _build_menu(self):
        self.menu = tk.Menu(self, tearoff=0, bg=CARD, fg=TEXT, relief="flat",
                            activebackground=ACCENT, activeforeground="white",
                            font=(FONT, 9), bd=0)
        self.menu.add_command(label="▶ 启动", command=lambda: self.launch_game(self.menu_game))
        self.menu.add_command(label="📁 查看路径", command=lambda: self.show_path(self.menu_game))
        self.menu.add_command(label="📂 跳转到所在位置", command=lambda: self.jump_to(self.menu_game))
        self.menu.add_command(label="🔧 设置启动路径", command=lambda: self.set_launch(self.menu_game))
        self.menu.add_separator()
        self.menu.add_command(label="🚫 隐藏此游戏", command=lambda: self.hide_game(self.menu_game))
        self.menu.add_command(label="🗑 卸载", command=lambda: self.uninstall_game(self.menu_game))

    # ---------- 筛选 ----------
    def _set_filter(self, key):
        self.filter = key
        for k, n in self.nav.items():
            n.set_active(k == key)
        self.refresh_cards()

    def _match(self, g: Game) -> bool:
        f = self.filter
        if f == "全部":
            return True
        if f == "本地":
            return g.source in ("注册表", "GameUX")
        return g.source == f

    def _update_nav_counts(self):
        counts = dict.fromkeys((k for k, _, _ in NAV_ITEMS), 0)
        for g in self.games:
            if g.source == "Steam":
                counts["Steam"] += 1
            elif g.source == "Epic":
                counts["Epic"] += 1
            elif g.source in ("注册表", "GameUX"):
                counts["本地"] += 1
            elif g.source == "手动添加":
                counts["手动添加"] += 1
        counts["全部"] = len(self.games)
        for k, n in self.nav.items():
            n.set_count(counts.get(k, 0))

    # ---------- 扫描 ----------
    def start_scan(self):
        self.scanning = True
        self.games = []
        self.refresh_cards()
        self.progress.pack(fill="x", padx=26, pady=(0, 6))
        self.progress.start(12)
        threading.Thread(target=self._scan_worker, daemon=True).start()

    def _scan_worker(self):
        try:
            games = scanner.scan_all()
        except Exception:
            games = []
        try:
            manual = [Game.from_dict(d) for d in self.cfg.get("manual", [])]
        except Exception:
            manual = []
        icons: dict[str, bytes] = {}
        for g in games + manual:
            try:
                ex = scanner.icon_exe(g)
                if not ex:
                    continue
                g.icon = ex                     # 记录本地主程序，供跳转/图标用
                png = icon_extractor.exe_to_png(ex)
                if png:
                    icons[g.uid] = png
            except Exception:
                pass
        try:
            if self.winfo_exists():
                self.after(0, lambda: self._apply_scan(games, manual, icons))
        except tk.TclError:
            pass

    def _apply_scan(self, games, manual, icons):
        self.scanning = False
        try:
            self.progress.stop()
            self.progress.pack_forget()
        except tk.TclError:
            pass
        hidden = set(self.cfg.get("hidden", []))
        for g in games + manual:
            ov = self.cfg.get("launch_override", {}).get(g.uid)
            if ov:
                g.launch = ov
        self.games = sorted((g for g in games + manual if g.uid not in hidden),
                            key=lambda g: g.name.lower())
        self._photos = {}
        for uid, png in icons.items():
            try:
                ph = tk.PhotoImage(data=icon_extractor.photo_data(png), master=self)
                if ph.width() > 48 or ph.height() > 48:
                    k = max(-(-ph.width() // 48), -(-ph.height() // 48))
                    ph = ph.subsample(k, k)
                self._photos[uid] = ph
            except tk.TclError:
                pass
        self._update_nav_counts()
        self.refresh_cards()
        self._start_size_worker()

    # ---------- 磁盘占用统计 ----------
    def _start_size_worker(self):
        if self._size_running:
            return
        self._size_running = True
        threading.Thread(target=self._size_worker, daemon=True).start()

    def _size_worker(self):
        for g in list(self.games):
            try:
                if g.uid not in self._sizes:
                    if g.install_dir and os.path.isdir(g.install_dir):
                        self._sizes[g.uid] = scanner.dir_size(g.install_dir)
                    else:
                        self._sizes[g.uid] = None
                    self.after(0, lambda u=g.uid: self._notify_size(u))
            except Exception:
                pass
        self._size_running = False
        try:
            self.after(0, self._update_status)
        except tk.TclError:
            pass

    def _notify_size(self, uid):
        card = self._cards.get(uid)
        if card is not None:
            card.set_size(self._sizes.get(uid))
        self._update_status()

    def _update_status(self):
        q = self.search_var.get().strip().lower() if hasattr(self, "search_var") else ""
        shown = sum(1 for g in self.games if self._match(g) and q in g.name.lower())
        known = [v for v in self._sizes.values() if v]
        txt = f"共 {len(self.games)} 款游戏"
        if known or not self._size_running:
            txt += f" · 磁盘占用 {fmt_size(sum(known))}"
        else:
            txt += " · 磁盘占用统计中…"
        txt += f" · 显示 {shown} 款 · 右键卡片更多操作"
        self.set_status(txt)

    # ---------- 网页页签 ----------
    def get_tabs(self, g: Game) -> list:
        bm = self.cfg.get("bookmarks", {})
        if g.uid in bm:
            return bm[g.uid]
        return default_tabs(g)

    def _materialize_tabs(self, g: Game) -> list:
        """首次修改前把当前生效页签固化进配置（之后不再自动生成预置）"""
        bm = self.cfg.setdefault("bookmarks", {})
        if g.uid not in bm:
            bm[g.uid] = [dict(t) for t in default_tabs(g)]
        return bm[g.uid]

    def add_tab(self, g: Game, name: str, url: str):
        self._materialize_tabs(g).append({"name": name, "url": url})
        save_config(self.cfg)
        self._refresh_card_panel(g)

    def edit_tab(self, g: Game, index: int, name: str, url: str):
        tabs = self._materialize_tabs(g)
        if 0 <= index < len(tabs):
            tabs[index] = {"name": name, "url": url}
            save_config(self.cfg)
            self._refresh_card_panel(g)

    def delete_tab(self, g: Game, index: int):
        tabs = self._materialize_tabs(g)
        if 0 <= index < len(tabs):
            tabs.pop(index)
            save_config(self.cfg)
            self._refresh_card_panel(g)

    def _refresh_card_panel(self, g: Game):
        card = self._cards.get(g.uid)
        if card is not None:
            card.rebuild_panel()

    def open_url(self, url: str):
        if "://" not in url:
            url = "https://" + url
        try:
            os.startfile(url)
        except OSError:
            messagebox.showerror("错误", f"无法打开链接：\n{url}")

    # ---------- favicon ----------
    def get_favicon(self, host: str):
        """取页签 favicon（缓存命中立即返回，否则触发后台下载）"""
        if not host:
            return None
        img = self._fav_images.get(host)
        if img:
            return img
        png, should = favicons.lookup(host)
        if png:
            try:
                img = tk.PhotoImage(data=icon_extractor.photo_data(png))
                self._fav_images[host] = img
                return img
            except tk.TclError:
                return None
        if should and host not in self._fav_pending:
            self._fav_pending.add(host)
            self._start_fav_worker()
        return None

    def _start_fav_worker(self):
        if self._fav_running:
            return
        self._fav_running = True
        threading.Thread(target=self._fav_worker, daemon=True).start()

    def _fav_worker(self):
        while self._fav_pending:
            host = next(iter(self._fav_pending))
            try:
                favicons.fetch(host)
            except Exception:
                pass
            self._fav_pending.discard(host)
            try:
                self.after(0, lambda h=host: self._favicon_ready(h))
            except tk.TclError:
                return
        self._fav_running = False

    def _favicon_ready(self, host):
        if self.get_favicon(host):
            for card in list(self._cards.values()):
                card.on_favicon(host)

    def get_photo(self, g: Game):
        return self._photos.get(g.uid)

    def refresh_cards(self):
        for c in self.inner.winfo_children():
            c.destroy()
        q = self.search_var.get().strip().lower() if hasattr(self, "search_var") else ""
        shown = [g for g in self.games if self._match(g) and q in g.name.lower()]
        if self.scanning:
            tk.Label(self.inner, text="⏳  正在扫描本机游戏…", bg=BG, fg=SUB,
                     font=(FONT, 12)).pack(pady=80)
        elif not shown:
            tip = "没有匹配的游戏" if q else "此分类下暂无游戏"
            tk.Label(self.inner, text="🎮", bg=BG, fg="#2a3348",
                     font=(FONT, 34)).pack(pady=(90, 8))
            tk.Label(self.inner, text=tip, bg=BG, fg=SUB,
                     font=(FONT, 11)).pack()
        else:
            self._cards = {}
            for g in shown:
                c = GameCard(self.inner, g, self)
                c.pack(fill="x", padx=24, pady=4)
                self._cards[g.uid] = c
        self._update_status()

    # ---------- 操作 ----------
    def launch_game(self, g: Game):
        if not g:
            return
        if not g.launch:
            messagebox.showinfo("提示", "未找到该游戏的启动程序，\n请右键卡片 → 「设置启动路径」")
            return
        try:
            if "://" in g.launch:
                os.startfile(g.launch)
            else:
                _shell_exec(g.launch, None)   # 双击语义：需要提权时自动弹 UAC
            self.set_status(f"已启动：{g.name}")
        except Exception as e:
            messagebox.showerror("启动失败", str(e))

    def show_path(self, g: Game):
        if g:
            PathDialog(self, g)

    def jump_to(self, g: Game):
        """在资源管理器中直接跳到游戏所在位置（优先选中主程序）"""
        if not g:
            return
        target = ""
        for cand in (g.launch, g.icon):
            if cand and cand.lower().endswith(".exe") and os.path.isfile(cand):
                target = cand
                break
        try:
            if target:
                subprocess.Popen(f'explorer /select,"{target}"')
            elif g.install_dir and os.path.isdir(g.install_dir):
                os.startfile(g.install_dir)
            else:
                messagebox.showwarning("提示", "未找到该游戏的安装位置")
        except Exception as e:
            messagebox.showerror("打开失败", str(e))

    def set_launch(self, g: Game):
        if not g:
            return
        p = filedialog.askopenfilename(title=f"选择「{g.name}」的启动程序",
                                       filetypes=[("可执行文件", "*.exe"), ("所有文件", "*.*")])
        if not p:
            return
        self.cfg.setdefault("launch_override", {})[g.uid] = p
        save_config(self.cfg)
        g.launch = p
        self.refresh_cards()
        self.set_status(f"已更新「{g.name}」的启动路径")

    def hide_game(self, g: Game):
        if not g:
            return
        if g.source == "手动添加":
            self.cfg["manual"] = [d for d in self.cfg.get("manual", []) if d["name"] != g.name]
        else:
            self.cfg.setdefault("hidden", []).append(g.uid)
        save_config(self.cfg)
        if g in self.games:
            self.games.remove(g)
        self._update_nav_counts()
        self.refresh_cards()
        self.set_status(f"已隐藏「{g.name}」（可在 ⚙ 设置中恢复）")

    def uninstall_game(self, g: Game):
        if not g:
            return
        if g.source == "手动添加":
            if messagebox.askyesno("移除条目", f"「{g.name}」为手动添加。\n仅从列表中移除，不删除文件。继续？"):
                self.cfg["manual"] = [d for d in self.cfg.get("manual", []) if d["name"] != g.name]
                save_config(self.cfg)
                self.start_scan()
            return
        if not g.uninstall:
            messagebox.showwarning("无法卸载",
                                   "未找到该游戏的卸载程序。\n可右键 → 跳转到所在位置手动删除。")
            return
        if not messagebox.askyesno("确认卸载",
                                   f"确定要卸载「{g.name}」吗？\n将运行其官方卸载程序。"):
            return
        try:
            if "://" in g.uninstall:
                os.startfile(g.uninstall)
            else:
                s = g.uninstall.strip()
                exe, args = s, ""
                if s.startswith('"'):
                    exe, _, rest = s[1:].partition('"')
                    args = rest.strip()
                else:
                    parts = s.split(None, 1)
                    if len(parts) == 2:
                        exe, args = parts
                _shell_exec(exe, args or None)
            self.set_status(f"已启动「{g.name}」的卸载程序，完成后请点击「⟳ 刷新」")
        except Exception as e:
            messagebox.showerror("卸载失败", str(e))

    def popup_settings(self):
        m = tk.Menu(self, tearoff=0, bg=CARD, fg=TEXT, activebackground=ACCENT,
                    activeforeground="white", font=(FONT, 9), bd=0)
        m.add_command(label="👁 恢复所有隐藏的游戏", command=self.restore_hidden)
        m.add_command(label="📝 打开配置文件", command=lambda: os.startfile(CONFIG_PATH))
        m.tk_popup(self.winfo_pointerx(), self.winfo_pointery())

    def restore_hidden(self):
        n = len(self.cfg.get("hidden", []))
        if not n:
            messagebox.showinfo("提示", "当前没有已隐藏的游戏")
            return
        self.cfg["hidden"] = []
        save_config(self.cfg)
        self.start_scan()
        messagebox.showinfo("完成", f"已恢复 {n} 个隐藏的游戏")

    def _about(self):
        messagebox.showinfo("关于", f"游戏中心 v{__version__}\n\n自动扫描 Steam / Epic / 注册表中的游戏\n"
                                     "一键启动 · 跳转路径 · 一键卸载 · 磁盘占用统计")

    def show_menu(self, event, g: Game):
        self.menu_game = g
        self.menu.tk_popup(event.x_root, event.y_root)

    def set_status(self, text: str):
        self.status.configure(text=text)

# ---------------- 入口 ----------------
def main():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    App().mainloop()

if __name__ == "__main__":
    main()
