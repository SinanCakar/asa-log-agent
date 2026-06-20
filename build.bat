@echo off
echo === ASA Log Agent build (Windows) ===
pip install pyinstaller mss pytesseract Pillow pystray
python -c "from PIL import Image; img=Image.open('icon.png').convert('RGBA'); img.save('installer/icon.ico',format='ICO',sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])"
pyinstaller --onefile --name ASA_LogAgent ^
  --noconsole ^
  --icon installer\icon.ico ^
  --add-data "agent.ini;." ^
  --add-data "icon.png;." ^
  --hidden-import tkinter ^
  --hidden-import PIL.ImageTk ^
  --hidden-import pystray ^
  --hidden-import pystray._win32 ^
  asa_log_agent.py
echo.
echo Done: dist\ASA_LogAgent.exe
echo Keep agent.ini, logparse.py, ocr.py in the same folder (at build time).
echo PREREQUISITE: Tesseract-OCR installed (agent.ini tesseract_path or PATH).
echo   https://github.com/UB-Mannheim/tesseract/wiki
pause
