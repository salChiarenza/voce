#!/bin/bash
set -euo pipefail

SRC_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$HOME/VoiceDettaturaMac"
PY="$APP_DIR/.venv/bin/python"

echo "Voice Dettatura Mac v1.0.1"
echo

if [ "$(uname -s)" != "Darwin" ]; then
  echo "Questo installer e' pensato per macOS."
  exit 1
fi

if [ "$(uname -m)" != "arm64" ]; then
  echo "Questa versione e' pensata per Mac Apple Silicon (M1 o successivo)."
  echo "Puoi continuare a tuo rischio, ma non e' la configurazione consigliata."
fi

command -v python3 >/dev/null 2>&1 || {
  echo "Python 3 non trovato. Installa Python 3 e rilancia l'installer."
  exit 1
}

mkdir -p "$APP_DIR"
cp "$SRC_DIR"/detta.py "$SRC_DIR"/parla.py "$SRC_DIR"/voce_hook.py "$SRC_DIR"/voce_lib.py "$SRC_DIR"/config.json "$SRC_DIR"/voce "$APP_DIR"/
chmod +x "$APP_DIR/voce"

python3 -m venv "$APP_DIR/.venv"
"$PY" -m pip install --upgrade pip
"$PY" -m pip install -r "$SRC_DIR/requirements.txt"

cat > "$HOME/Desktop/Voice Dettatura Mac.command" <<LAUNCHER
#!/bin/bash
cd "$APP_DIR"
exec "$PY" detta.py
LAUNCHER

cat > "$HOME/Desktop/Voice On-Off.command" <<LAUNCHER
#!/bin/bash
cd "$APP_DIR"
if [ -f VOICE_ON ]; then
  ./voce off >/dev/null
  "$PY" parla.py "Voce spenta"
else
  ./voce on >/dev/null
  "$PY" parla.py "Voce accesa"
fi
exit 0
LAUNCHER

chmod +x "$HOME/Desktop/Voice Dettatura Mac.command" "$HOME/Desktop/Voice On-Off.command"

"$PY" -m py_compile "$APP_DIR"/detta.py "$APP_DIR"/parla.py "$APP_DIR"/voce_hook.py "$APP_DIR"/voce_lib.py

echo
echo "Installazione completata."
echo
echo "Prossimi passi:"
echo "1. Apri 'Voice Dettatura Mac.command' dalla Scrivania."
echo "2. Se macOS chiede permessi, abilita Microfono, Accessibilita' e Monitoraggio input."
echo "3. Tieni premuto Cmd destro, parla, rilascia."
echo
echo "Cartella installata: $APP_DIR"
