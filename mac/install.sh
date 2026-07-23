#!/bin/bash
set -euo pipefail

SRC_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$HOME/VoiceDettaturaMac"
PY="$APP_DIR/.venv/bin/python"
SHORTCUT_NAME="Voce LeaderAI firmato"
SHORTCUT_FILE="$SHORTCUT_NAME.shortcut"

echo "Voice Dettatura Mac v1.0.2"
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
cp "$SRC_DIR"/detta.py "$SRC_DIR"/parla.py "$SRC_DIR"/voce_hook.py "$SRC_DIR"/voce_lib.py "$SRC_DIR"/voce "$SRC_DIR/$SHORTCUT_FILE" "$SRC_DIR"/INSTALLA_CON_AI.md "$APP_DIR"/
python3 "$SRC_DIR/voce_hook.py" --merge-config "$SRC_DIR/config.json" "$APP_DIR/config.json"
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
"$PY" "$APP_DIR/voce_hook.py" --install-hooks
"$PY" "$APP_DIR/voce_hook.py" --check-hooks

if command -v shortcuts >/dev/null 2>&1; then
  if shortcuts list | grep -Fxq "$SHORTCUT_NAME"; then
    echo "Voce naturale LeaderAI gia' presente."
  else
    open "$APP_DIR/$SHORTCUT_FILE"
    echo
    echo "Si e' aperto Comandi Rapidi: clicca 'Aggiungi comando rapido'."
    read -r -p "Dopo il click, torna qui e premi Invio: " _
    if ! shortcuts list | grep -Fxq "$SHORTCUT_NAME"; then
      echo "ERRORE: '$SHORTCUT_NAME' non risulta installato."
      exit 1
    fi
  fi
  echo "Prova della voce naturale LeaderAI..."
  if ! printf '%s\n' "Voce LeaderAI pronta." | shortcuts run "$SHORTCUT_NAME"; then
    echo "ERRORE: il Comando Rapido e' presente ma la prova audio non e' riuscita."
    exit 1
  fi
else
  echo "ERRORE: Comandi Rapidi non disponibile; la voce naturale LeaderAI non puo' essere installata."
  exit 1
fi

echo
echo "Installazione completata."
echo
echo "Prossimi passi:"
echo "1. Apri 'Voice Dettatura Mac.command' dalla Scrivania."
echo "2. Se macOS chiede permessi, abilita Microfono, Accessibilita' e Monitoraggio input."
echo "3. Tieni premuto Cmd destro, parla, rilascia."
echo "4. Option + freccia sinistra: attiva la voce agenti."
echo "5. Cmd destro + Option: attiva la modalita' mani libere."
echo "6. Verifica che la risposta usi la voce naturale LeaderAI."
echo
echo "Cartella installata: $APP_DIR"
