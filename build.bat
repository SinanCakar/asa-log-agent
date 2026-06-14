@echo off
echo === ASA Log Agent build (Windows) ===
pip install pyinstaller mss pytesseract Pillow
pyinstaller --onefile --name ASA_LogAgent ^
  --add-data "agent.ini;." ^
  asa_log_agent.py
echo.
echo Tamam: dist\ASA_LogAgent.exe
echo agent.ini, logparse.py, ocr.py ile ayni klasorde tutun (build sirasinda).
echo ONKOSUL: Tesseract-OCR kurulu olmali (agent.ini tesseract_path veya PATH).
echo   https://github.com/UB-Mannheim/tesseract/wiki
pause
