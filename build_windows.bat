@echo off
rem Builds dist\AJAZZ Control\AJAZZ Control.exe
cd /d "%~dp0"
python -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install -r requirements.txt pyinstaller
pyinstaller --noconfirm --clean --windowed --name "AJAZZ Control" --icon assets\icon.png --add-data "assets;assets" --collect-submodules winrt ajazz_control.py
