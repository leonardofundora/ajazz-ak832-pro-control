#!/bin/bash
# Crea "AJAZZ Control.app" en la carpeta dist/.  Uso:  bash build_mac.sh
set -e
cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
  echo "Falta Python 3. Instálalo desde https://www.python.org/downloads/macos/ y vuelve a ejecutar."
  exit 1
fi

python3 -m venv .venv-mac
source .venv-mac/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt pyinstaller

pyinstaller --noconfirm --clean --windowed \
  --name "AJAZZ Control" \
  --icon assets/icon.png \
  --add-data "assets:assets" \
  --osx-bundle-identifier com.ajazz.control \
  ajazz_control.py

echo
echo "Listo: dist/AJAZZ Control.app"
echo "Arrástrala a Aplicaciones. La primera vez ábrela con clic derecho > Abrir."
