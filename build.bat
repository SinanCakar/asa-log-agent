@echo off
echo === ASA Log Agent build (Windows) ===
pip install pyinstaller mss pytesseract Pillow pystray
pyinstaller --onefile --name ASA_LogAgent ^
  --noconsole ^
  --icon icon.png ^
  --add-data "agent.ini;." ^
  --add-data "icon.png;." ^
  --hidden-import tkinter ^
  --hidden-import PIL.ImageTk ^
  --hidden-import pystray ^
  asa_log_agent.py
echo.
echo Done: dist\ASA_LogAgent.exe
echo Keep agent.ini, logparse.py, ocr.py in the same folder (at build time).
echo PREREQUISITE: Tesseract-OCR installed (agent.ini tesseract_path or PATH).
echo   https://github.com/UB-Mannheim/tesseract/wiki
pause
