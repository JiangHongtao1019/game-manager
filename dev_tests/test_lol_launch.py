# -*- coding: utf-8 -*-
import os
import subprocess
import time

EXE = r"C:\WeGameApps\英雄联盟（含经典模式）\WeGameLauncher\launcher.exe"

def has_proc(name):
    r = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {name}"],
                       capture_output=True, text=True)
    return name.lower() in r.stdout.lower()

print("== 方式1: subprocess.Popen + CREATE_NO_WINDOW（当前应用的方式）")
p = subprocess.Popen([EXE], cwd=os.path.dirname(EXE),
                     creationflags=subprocess.CREATE_NO_WINDOW)
time.sleep(10)
print("   launcher 存活:", p.poll() is None, "| 退出码:", p.poll())
print("   子进程 TASLogin:", has_proc("TASLogin.exe"),
      "| LeagueClient:", has_proc("LeagueClient.exe"),
      "| Cross:", has_proc("Cross.exe"))

if p.poll() is not None or not (has_proc("TASLogin.exe") or has_proc("LeagueClient.exe") or has_proc("Cross.exe")):
    print("== 方式1 无效，测试 方式2: os.startfile（资源管理器双击语义）")
    os.startfile(EXE)
    time.sleep(10)
    print("   TASLogin:", has_proc("TASLogin.exe"),
          "| LeagueClient:", has_proc("LeagueClient.exe"),
          "| Cross:", has_proc("Cross.exe"))
