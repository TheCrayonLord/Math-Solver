@echo off
cd /d "%~dp0"
python -m pip install --quiet --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
  echo.
  echo Could not install the required packages. Is Python installed and on PATH?
  pause
  exit /b 1
)
python -m streamlit run app.py
pause
