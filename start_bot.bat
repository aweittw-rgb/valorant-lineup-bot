@echo off
chcp 65001 > nul
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [1/3] 建立虛擬環境...
    py -m venv .venv
)

echo [2/3] 安裝套件...
".venv\Scripts\python.exe" -m pip install -U pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt

echo [3/3] 啟動機器人...
".venv\Scripts\python.exe" bot.py
pause
