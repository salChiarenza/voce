#!/bin/bash
set -euo pipefail

SRC_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$HOME/VoiceDettaturaMac"
PY="$APP_DIR/.venv/bin/python"
VERSION_FILE="$SRC_DIR/../VERSION"
SHORTCUT_NAME="Voce LeaderAI firmato"
SHORTCUT_FILE="$SHORTCUT_NAME.shortcut"

[ -f "$VERSION_FILE" ] || {
  echo "File VERSION mancante: usa la copia completa della repo Voce (git clone)."
  exit 1
}
VERSION="$(tr -d '[:space:]' < "$VERSION_FILE")"

echo "Voce LeaderAI $VERSION (Mac)"
echo

if [ "$(uname -s)" != "Darwin" ]; then
  echo "Questo installer e' pensato per macOS."
  exit 1
fi

if [ "$(uname -m)" != "arm64" ]; then
  echo "Installazione interrotta: Voce Mac richiede Apple Silicon (M1 o successivo)."
  exit 1
fi

mkdir -p "$APP_DIR"
cp "$SRC_DIR"/INSTALLA_CON_AI.md "$VERSION_FILE" "$APP_DIR"/

command -v python3 >/dev/null 2>&1 || {
  echo "Python 3 non trovato."
  echo "Le istruzioni sono state copiate in $APP_DIR."
  echo "Chiedi al tuo agente di installare Python 3, poi rilancia questo file."
  exit 1
}

cp "$SRC_DIR"/detta.py "$SRC_DIR"/parla.py "$SRC_DIR"/voce_hook.py "$SRC_DIR"/voce_lib.py "$SRC_DIR"/voce "$SRC_DIR/$SHORTCUT_FILE" "$APP_DIR"/
python3 "$SRC_DIR/voce_hook.py" --merge-config "$SRC_DIR/config.json" "$APP_DIR/config.json"
chmod +x "$APP_DIR/voce"

python3 -m venv "$APP_DIR/.venv"
"$PY" -m pip install --upgrade pip
"$PY" -m pip install -r "$SRC_DIR/requirements.txt"

cat > "$HOME/Desktop/Voce Dettatura.command" <<LAUNCHER
#!/bin/bash
cd "$APP_DIR"
exec "$PY" detta.py
LAUNCHER

cat > "$HOME/Desktop/Voce Attiva Tutto.command" <<LAUNCHER
#!/bin/bash
cd "$APP_DIR"
if ! pgrep -f "[Pp]ython.*detta\\.py" >/dev/null; then
  nohup "$PY" detta.py >> voce.log 2>&1 &
  sleep 3
fi
if [ -f VOICE_ON ] && [ -f MANI_LIBERE_ON ]; then
  rm -f VOICE_ON MANI_LIBERE_ON
  "$PY" parla.py --stop
  "$PY" parla.py "Voce AI spenta. Mani libere disattivate."
else
  touch VOICE_ON MANI_LIBERE_ON
  "$PY" parla.py "Voce AI accesa. Le risposte dell'agente sono audio sintetico. Mani libere attivate."
fi
exit 0
LAUNCHER

chmod +x "$HOME/Desktop/Voce Dettatura.command" "$HOME/Desktop/Voce Attiva Tutto.command"

"$PY" -m py_compile "$APP_DIR"/detta.py "$APP_DIR"/parla.py "$APP_DIR"/voce_hook.py "$APP_DIR"/voce_lib.py
"$PY" "$APP_DIR/voce_hook.py" --install-hooks
"$PY" "$APP_DIR/voce_hook.py" --check-hooks

echo
echo "Installazione completata."
echo
echo "Prossimi passi:"
echo "1. Apri 'Voce Dettatura.command' dalla Scrivania."
echo "2. Se macOS chiede permessi, abilita Microfono, Accessibilita' e Monitoraggio input."
echo "3. Tieni premuto Cmd destro, parla, rilascia."
echo "4. Option + freccia sinistra: attiva la voce agenti."
echo "5. Cmd destro + Option: attiva la modalita' mani libere."
echo "6. Il tuo agente verifichera' FOTOCOPIA_SAL_OK e completera' la prova voce."
echo
echo "Cartella installata: $APP_DIR"
