#!/bin/sh
cd "$(dirname "$0")"
PY=python3
command -v python3 >/dev/null 2>&1 || PY=python
"$PY" -m pip install --quiet --disable-pip-version-check -r requirements.txt || {
  echo "Could not install the required packages. Is Python 3 installed?"; exit 1; }
"$PY" -m streamlit run app.py
