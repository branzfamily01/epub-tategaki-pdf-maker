@echo off
setlocal
py -m pip install --upgrade pip
py -m pip install -r requirements.txt pyinstaller==6.14.1
pyinstaller --noconfirm --clean --windowed --onefile --name "EPUB-Tategaki-PDF-Maker" --paths src main.py
if errorlevel 1 exit /b 1
echo.
echo Build complete: dist\EPUB-Tategaki-PDF-Maker.exe
pause
