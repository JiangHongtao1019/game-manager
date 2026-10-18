# -*- coding: utf-8 -*-
import tkinter as tk
from app import App, fmt_size

a = App()

def report(elapsed=0):
    if (not a._size_running and a._sizes) or elapsed > 80:
        tops = [w for w in a.winfo_children() if isinstance(w, tk.Toplevel)]
        print("多余 Toplevel 窗口:", tops if tops else "无 [OK]")
        print("游戏数:", len(a.games), "| 图标数:", len(a._photos), "| 已统计:", len(a._sizes))
        total = sum(v for v in a._sizes.values() if v)
        print("磁盘占用合计: %.1f GB" % (total / 1024 ** 3))
        for g in a.games:
            v = a._sizes.get(g.uid)
            print(f"  {g.name[:30]:34s} {fmt_size(v) if v is not None else '-'}")
        a.destroy()
    else:
        a.after(3000, lambda: report(elapsed + 3))

a.after(15000, lambda: report(0))
a.mainloop()
print("SMOKE OK")
