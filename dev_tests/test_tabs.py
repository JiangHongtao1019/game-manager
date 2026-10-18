# -*- coding: utf-8 -*-
"""v1.1 网页页签功能测试：预置 / 添加暗黑核 / 展开 / 编辑 / 删除 / favicon"""
import os
import sys
import time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

from app import App, load_config, save_config, default_tabs
from scanner import Game

results = []

# 清理上轮测试残留（保证幂等）：移除暗黑IV已有的页签记录
_cfg = load_config()
_cfg.get("bookmarks", {}).pop("《暗黑破坏神® iv》", None)
save_config(_cfg)


def check(name, ok):
    print(("[OK] " if ok else "[FAIL] ") + name)
    results.append(ok)
    return ok


# ---------- A. GDI+ 解码器（离线，用应用自己的 icon.ico） ----------
import favicons
dec = favicons.decode_file(os.path.join(BASE, "icon.ico"))
check(f"GDI+ 解码 icon.ico -> {dec[0]}x{dec[1]}" if dec else "GDI+ 解码失败",
      dec is not None and dec[0] == 256 and dec[1] == 256)
w, h, px = favicons._shrink(256, 256, dec[2])
check(f"降采样 256->16: {w}x{h}", w == 16 and h == 16)

# ---------- B. 网络获取 favicon（尽力而为，失败仅警告） ----------
net_ok = True
try:
    png = favicons.fetch("www.d2core.com")
    if png:
        check("下载暗黑核 favicon 成功", True)
    else:
        print("[警告] 暗黑核 favicon 下载失败（网络）—— 不计入失败")
        net_ok = False
except Exception as e:
    print(f"[警告] favicon 网络异常: {e}")
    net_ok = False

# ---------- C. 应用级测试 ----------
a = App()


def report(elapsed=0):
    if not a.games and elapsed < 30:
        a.after(2000, lambda: report(elapsed + 2))
        return
    d4 = next((g for g in a.games if "暗黑" in g.name), None)
    bg3 = next((g for g in a.games if "Baldur" in g.name), None)
    check("找到暗黑IV", d4 is not None)

    # 预置页签
    if d4:
        tabs = a.get_tabs(d4)
        check(f"暗黑IV 预置页签 = {[t['name'] for t in tabs]}（应为 搜攻略/B站视频）",
              len(tabs) == 2 and all(t["name"] in ("搜攻略", "B站视频") for t in tabs))
    if bg3:
        tabs = a.get_tabs(bg3)
        has = any(t["name"] == "Steam商店" and f"/app/{bg3.appid}/" in t["url"] for t in tabs)
        check(f"BG3 预置含 Steam商店 (appid={bg3.appid})", has and len(tabs) == 3)

    # 添加暗黑核（用户测试用例）
    if d4:
        a.add_tab(d4, "暗黑核", "https://www.d2core.com/d4")
        tabs = a.get_tabs(d4)
        ok = any(t["name"] == "暗黑核" and t["url"] == "https://www.d2core.com/d4" for t in tabs)
        check("添加「暗黑核」页签", ok and len(tabs) == 3)
        cfg2 = load_config()
        saved = any(t.get("name") == "暗黑核"
                    for t in cfg2.get("bookmarks", {}).get(d4.uid, []))
        check("已持久化到 config.json", saved)

    # 展开 / 折叠（耗时测量：首次构建 + 二次显隐切换）
    card = a._cards.get(d4.uid) if d4 else None
    if check("找到暗黑IV卡片", card is not None) and card:
        t0 = time.perf_counter()
        card.toggle_expand()
        a.update()
        dt = (time.perf_counter() - t0) * 1000
        check(f"首次展开耗时 {dt:.0f}ms（<100ms）", dt < 100)
        check(f"展开后高度 {card.winfo_height()} > {card.H}", card.winfo_height() > card.H)
        check(f"药丸数 {len(card._pills)} == 3", len(card._pills) == 3)
        for label in ("二次", "三次"):
            t0 = time.perf_counter()
            card.toggle_expand()      # 收起
            a.update()
            card.toggle_expand()      # 再展开
            a.update()
            dt2 = (time.perf_counter() - t0) * 1000
            check(f"{label}切换(收+开)耗时 {dt2:.0f}ms（<100ms）", dt2 < 100)
        t0 = time.perf_counter()
        card.toggle_expand()
        a.update()
        dt = (time.perf_counter() - t0) * 1000
        check(f"收起耗时 {dt:.0f}ms（<100ms）", dt < 100)
        check(f"折叠后高度 {card.winfo_height()} == {card.H}", card.winfo_height() == card.H)
        # 单击卡片 = 展开/收起（手风琴：同时只展开一张）
        card.event_generate("<Button-1>", x=40, y=40)
        a.update()
        check("单击卡片展开", card.winfo_height() > card.H)
        time.sleep(0.35)                        # 间隔拉开，避免被判为双击
        card.event_generate("<Button-1>", x=40, y=40)
        a.update()
        check("再单击收起", card.winfo_height() == card.H)
        other = next((c for c in a._cards.values() if c is not card), None)
        other.event_generate("<Button-1>", x=40, y=40)
        a.update()
        check("另一张卡展开", other.winfo_height() > other.H)
        time.sleep(0.35)
        card.event_generate("<Button-1>", x=40, y=40)
        a.update()
        check("手风琴：展开暗黑IV自动收起另一张",
              card.winfo_height() > card.H and other.winfo_height() == other.H)

    # 编辑 / 删除
    if d4:
        tabs = a.get_tabs(d4)
        idx = next(i for i, t in enumerate(tabs) if t["name"] == "暗黑核")
        a.edit_tab(d4, idx, "暗黑核攻略", "https://www.d2core.com/d4")
        check("编辑页签", any(t["name"] == "暗黑核攻略" for t in a.get_tabs(d4)))
        a.delete_tab(d4, idx)
        check("删除页签", not any("暗黑核" in t["name"] for t in a.get_tabs(d4)))
        a.add_tab(d4, "暗黑核", "https://www.d2core.com/d4")   # 加回作为演示数据

    # favicon 出现在药丸上
    if card and net_ok:
        t0 = time.time()
        while time.time() - t0 < 20 and "www.d2core.com" not in a._fav_images:
            a.update()
            time.sleep(0.4)
        print("已获取 favicon:", sorted(a._fav_images))
        pill_img = None
        for pill, tab in card._pills:
            if tab["name"] == "暗黑核":
                pill_img = pill.cget("image")
        check("暗黑核药丸显示 favicon", "www.d2core.com" in a._fav_images and bool(pill_img))

    print()
    print(f"===== 通过 {sum(1 for r in results if r)}/{len(results)} =====")
    a.destroy()
    sys.exit(0 if all(results) else 1)


a.after(12000, lambda: report(0))
a.mainloop()
