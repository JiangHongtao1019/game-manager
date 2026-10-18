# -*- coding: utf-8 -*-
import os

for base in [r"C:\WeGameApps\英雄联盟（含经典模式）", r"D:\WeGameApps\QQ飞车"]:
    print("=" * 30)
    print(base)
    if not os.path.isdir(base):
        print("  (目录不存在)")
        continue
    for root, dirs, files in os.walk(base):
        depth = root[len(base):].count(os.sep)
        if depth >= 2:
            dirs[:] = []
        for f in files:
            if f.lower().endswith(".exe"):
                p = os.path.join(root, f)
                try:
                    mb = os.path.getsize(p) / 1048576
                except OSError:
                    mb = 0
                print(f"  {p[len(base) + 1:]}  ({mb:.1f} MB)")
