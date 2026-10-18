@echo off
rem 游戏管理器启动脚本（无控制台窗口）
cd /d "%~dp0"
start "" "C:\Users\MECHREVO\AppData\Local\Programs\Python\Python314\pythonw.exe" -X utf8 app.py
