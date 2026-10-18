# -*- coding: utf-8 -*-
"""scanner.py —— 自动扫描本机已安装的游戏
来源：Steam、Epic、Windows 注册表、GameUX（Windows 游戏资源管理器）
"""
import json
import os
import re
import winreg
from dataclasses import dataclass, asdict

# ---------------- 数据模型 ----------------
@dataclass
class Game:
    name: str
    source: str            # Steam / Epic / 注册表 / GameUX / 手动添加
    launch: str = ""       # 启动命令（exe 路径或协议 URL）
    install_dir: str = ""  # 安装目录
    uninstall: str = ""    # 卸载命令
    icon: str = ""         # 主程序/exe 路径（信息展示用）

    @property
    def uid(self) -> str:
        return self.name.strip().lower()

    def to_dict(self):
        return asdict(self)

    @staticmethod
    def from_dict(d):
        return Game(**d)

# ---------------- 过滤规则 ----------------
# 已知游戏发行商（注册表 Publisher 命中即视为游戏）
GAME_PUBLISHERS = [
    "valve", "steam", "ubisoft", "electronic arts", "ea sports", "activision",
    "blizzard", "bethesda", "2k", "firaxis", "square enix", "cd projekt",
    "capcom", "sega", "atlus", "bandai", "koei", "tecmo", "netease", "tencent",
    "mihoyo", "hoyoverse", "cognosphere", "riot", "perfect world", "deep silver",
    "thq", "paradox", "remedy", "io interactive", "larian", "digital extremes",
    "grinding gear", "mojang", "rockstar", "telltale", "psyonix", "supergiant",
    "focus home", "focus entertainment", "techland", "warner bros", "wb games",
    "xbox game", "microsoft studios", "innervation", "krafton", "pentiment",
    "hoftime", "jetsoft", "game science", "游戏科学",
]
# 名称关键词
GAME_KEYWORDS = ["game", "游戏", "遊戲"]
# 排除项：平台/工具类软件（不是游戏本体）
EXCLUDE_NAMES = [
    "epic games launcher", "epic online services", "steam", "steam client",
    "ubisoft connect", "uplay", "ea app", "ea desktop", "origin",
    "battle.net", "battlenet", "wegame", "xbox", "gamebar", "geforce",
    "unreal engine", "redistributable", "anticheat", "easyanticheat",
    "battleeye", "nvidia", "amd software", "directx", "unity", "vcredist",
    "steamworks", "战网", "安全管家", "微端", "workbuddy",
]

def _is_excluded(name: str) -> bool:
    n = name.lower()
    return any(x in n for x in EXCLUDE_NAMES)

# ---------------- 注册表工具 ----------------
def _reg_str(key, value: str) -> str:
    try:
        v, _ = winreg.QueryValueEx(key, value)
        return str(v) if v is not None else ""
    except OSError:
        return ""

def _norm(path: str) -> str:
    return path.replace("\\\\", "\\").strip('"').strip() if path else ""

# ---------------- Steam ----------------
def scan_steam() -> list:
    games = []
    steam_path = ""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as k:
            steam_path = _norm(_reg_str(k, "SteamPath"))
    except OSError:
        return games
    vdf = os.path.join(steam_path, "steamapps", "libraryfolders.vdf")
    if not os.path.isfile(vdf):
        return games
    try:
        text = open(vdf, encoding="utf-8", errors="ignore").read()
    except OSError:
        return games
    libs = [_norm(m) for m in re.findall(r'"path"\s+"([^"]+)"', text)]
    for lib in libs:
        apps = os.path.join(lib, "steamapps")
        if not os.path.isdir(apps):
            continue
        for fn in os.listdir(apps):
            if not (fn.startswith("appmanifest_") and fn.endswith(".acf")):
                continue
            try:
                data = open(os.path.join(apps, fn), encoding="utf-8", errors="ignore").read()
            except OSError:
                continue
            name = re.search(r'"name"\s+"([^"]+)"', data)
            appid = re.search(r'"appid"\s+"(\d+)"', data)
            state = re.search(r'"StateFlags"\s+"(\d+)"', data)
            installdir = re.search(r'"installdir"\s+"([^"]+)"', data)
            if not (name and appid and installdir):
                continue
            if _is_excluded(name.group(1)):
                continue
            if state and state.group(1) != "4":   # 4 = 完整安装
                continue
            aid = appid.group(1)
            gdir = os.path.join(apps, "common", installdir.group(1))
            games.append(Game(
                name=name.group(1), source="Steam",
                launch=f"steam://rungameid/{aid}",
                install_dir=gdir,
                uninstall=f"steam://uninstall/{aid}",
            ))
    return games

# ---------------- Epic ----------------
def scan_epic() -> list:
    games = []
    mdir = r"C:\ProgramData\Epic\EpicGamesLauncher\Data\Manifests"
    if not os.path.isdir(mdir):
        return games
    for fn in os.listdir(mdir):
        if not fn.endswith(".item"):
            continue
        try:
            data = json.load(open(os.path.join(mdir, fn), encoding="utf-8"))
        except Exception:
            continue
        if "games" not in (data.get("AppCategories") or []):
            continue
        name = data.get("DisplayName") or data.get("DisplayName_s") or ""
        app = data.get("AppName") or ""
        loc = data.get("InstallLocation") or ""
        if not (name and app):
            continue
        if _is_excluded(name):
            continue
        games.append(Game(
            name=name, source="Epic",
            launch=f"com.epicgames.launcher://apps/{app}?action=launch&silent=true",
            install_dir=loc,
            uninstall=f"com.epicgames.launcher://apps/{app}?action=uninstall",
        ))
    return games

# ---------------- GameUX（Windows 游戏资源管理器）----------------
def scan_gameux() -> list:
    games = []
    root = r"SOFTWARE\Microsoft\Windows\CurrentVersion\GameUX\Games"
    try:
        base = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, root)
    except OSError:
        return games
    i = 0
    while True:
        try:
            sub = winreg.EnumKey(base, i); i += 1
        except OSError:
            break
        try:
            with winreg.OpenKey(base, sub) as k:
                name = _reg_str(k, "DisplayName")
                exe = _norm(_reg_str(k, "ConfigExePath"))
                gdir = _norm(_reg_str(k, "ConfigApplicationPath"))
        except OSError:
            continue
        if name and exe and os.path.isfile(exe):
            games.append(Game(name=name, source="GameUX", launch=exe,
                              install_dir=gdir or os.path.dirname(exe)))
    return games

# ---------------- 注册表（控制面板卸载列表）----------------
UNINSTALL_KEYS = [
    (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall", winreg.KEY_WOW64_64KEY),
    (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall", winreg.KEY_WOW64_32KEY),
    (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall", 0),
]

def _looks_like_game(name, publisher, instloc, uninst) -> bool:
    blob = f"{publisher}".lower()
    if any(p in blob for p in GAME_PUBLISHERS):
        return True
    if "steam://uninstall" in uninst.lower():
        return True
    loc = instloc.lower()
    if "steamapps\\common" in loc or "\\epic games\\" in loc:
        return True
    if any(k in name.lower() for k in GAME_KEYWORDS):
        return True
    return False

def _find_launch_exe(name: str, install_dir: str, icon: str) -> str:
    icon = icon.split(",")[0].strip().strip('"')
    if icon.lower().endswith(".exe") and os.path.isfile(icon):
        return icon
    if not (install_dir and os.path.isdir(install_dir)):
        return ""
    skip = ("crash", "unins", "redist", "setup", "dxsetup", "vc_redist",
            "unity", "settings", "config", "tool", "eac", "anti-cheat",
            "dump", "report", "benchmark", "handler", "helper", "sdk")
    cand = []
    for root, dirs, files in os.walk(install_dir):
        depth = root[len(install_dir):].count(os.sep)
        if depth >= 2:
            dirs[:] = []
        dirs[:] = [d for d in dirs if d.lower() not in ("__redist", "directx", "vc_redist", "engine", "data")]
        for f in files:
            if not f.lower().endswith(".exe"):
                continue
            base = os.path.splitext(f)[0].lower()
            if any(s in base for s in skip):
                continue
            cand.append(os.path.join(root, f))
    if not cand:
        return ""
    # 评分：与游戏名/安装目录名匹配优先，其次常见名，最后按文件大小
    keys = set()
    for src in (name, os.path.basename(install_dir.rstrip("\\/"))):
        s = re.sub(r"[^a-z0-9]", "", src.lower())
        if len(s) >= 4:
            keys.add(s[:6])
    def score(c: str) -> float:
        b = os.path.splitext(os.path.basename(c))[0].lower()
        s = 0.0
        if keys and any(k in b for k in keys):
            s += 10
        if b in ("game", "launch", "start", "launcher"):
            s += 5
        try:
            s += min(os.path.getsize(c) / 10_000_000, 4)
        except OSError:
            pass
        return s
    return max(cand, key=score)

def scan_registry() -> list:
    games = []
    for hive, path, flag in UNINSTALL_KEYS:
        try:
            base = winreg.OpenKey(hive, path, 0, winreg.KEY_READ | flag)
        except OSError:
            continue
        i = 0
        while True:
            try:
                sub = winreg.EnumKey(base, i); i += 1
            except OSError:
                break
            try:
                with winreg.OpenKey(base, sub) as k:
                    name = _reg_str(k, "DisplayName")
                    if not name or _is_excluded(name):
                        continue
                    publisher = _reg_str(k, "Publisher")
                    instloc = _norm(_reg_str(k, "InstallLocation"))
                    uninst = _reg_str(k, "UninstallString")
                    icon = _reg_str(k, "DisplayIcon")
            except OSError:
                continue
            if not _looks_like_game(name, publisher, instloc, uninst):
                continue
            # InstallLocation 缺失时，从卸载命令里的 exe 路径反推安装目录
            if not instloc:
                m = re.search(r'"?([A-Za-z]:\\[^"]+?\.exe)', uninst or "")
                if m:
                    d = os.path.dirname(m.group(1))
                    low = d.lower()
                    if os.path.isdir(d) and "windows" not in low and "system32" not in low:
                        instloc = d
            launch = _find_launch_exe(name, instloc, icon)
            games.append(Game(name=name, source="注册表", launch=launch,
                              install_dir=instloc, uninstall=uninst, icon=icon))
    return games

# ---------------- 汇总 ----------------
_PRIORITY = {"Steam": 0, "Epic": 1, "GameUX": 2, "注册表": 3}

def scan_all() -> list:
    all_g = scan_steam() + scan_epic() + scan_gameux() + scan_registry()
    games = []
    by_name, by_dir = {}, {}
    for g in sorted(all_g, key=lambda x: _PRIORITY.get(x.source, 9)):
        # 按安装目录生成合并键（Steam/注册表常以不同名称登记同一游戏）
        dkey = ""
        if g.install_dir:
            try:
                dkey = os.path.normcase(os.path.normpath(g.install_dir))
            except (ValueError, OSError):
                dkey = ""
        ex = by_name.get(g.uid) or (by_dir.get(dkey) if dkey else None)
        if ex:  # 同名或同目录 -> 合并为一条
            ex.launch = ex.launch or g.launch
            ex.uninstall = ex.uninstall or g.uninstall
            ex.install_dir = ex.install_dir or g.install_dir
            ex.icon = ex.icon or g.icon
            if dkey and dkey not in by_dir:
                by_dir[dkey] = ex
            continue
        by_name[g.uid] = g
        if dkey:
            by_dir[dkey] = g
        games.append(g)
    return sorted(games, key=lambda g: g.name.lower())

def icon_exe(g: "Game") -> str:
    """返回可用于提取图标 / 资源管理器定位的本地 exe 路径（找不到返回空串）"""
    for cand in (g.launch, g.icon):
        if cand and cand.lower().endswith(".exe") and os.path.isfile(cand):
            return cand
    return _find_launch_exe(g.name, g.install_dir, "")


def dir_size(path: str) -> int:
    """统计目录占用的磁盘空间（字节），迭代式 scandir 实现"""
    total, stack = 0, [path]
    while stack:
        p = stack.pop()
        try:
            with os.scandir(p) as it:
                for e in it:
                    try:
                        if e.is_symlink():
                            continue
                        if e.is_dir(follow_symlinks=False):
                            stack.append(e.path)
                        else:
                            total += e.stat(follow_symlinks=False).st_size
                    except OSError:
                        pass
        except OSError:
            pass
    return total


if __name__ == "__main__":
    for g in scan_all():
        print(f"[{g.source}] {g.name}  ->  {g.launch or '(无启动命令)'}")
