# -*- coding: utf-8 -*-
import scanner, icon_extractor

games = scanner.scan_all()
ok = fail = 0
for g in games:
    ex = scanner.icon_exe(g)
    png = icon_extractor.exe_to_png(ex) if ex else None
    tag = "OK " if png else "无图标"
    if png:
        ok += 1
    else:
        fail += 1
    print(f"[{tag}] {g.name:24s} {ex or '(无exe)'}")
print(f"--- 成功 {ok}, 失败 {fail}")
