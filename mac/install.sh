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

# Fase 0 (P-190): requisiti prima di scaricare o cambiare qualsiasi cosa. Sotto requisito non si
# installa: la diagnosi dice cosa manca, l'AI lo riferisce alla persona.
ESITO_DIAGNOSI=0
"$SRC_DIR/voce" diagnosi || ESITO_DIAGNOSI=$?
if [ "$ESITO_DIAGNOSI" -ne 0 ]; then
  echo
  echo "Installazione non avviata: leggi l'ESITO qui sopra. Niente e' stato installato o cambiato."
  exit "$ESITO_DIAGNOSI"
fi
echo

mkdir -p "$APP_DIR"
cp "$SRC_DIR"/INSTALLA_CON_AI.md "$VERSION_FILE" "$APP_DIR"/

command -v python3 >/dev/null 2>&1 || {
  echo "Python 3 non trovato."
  echo "Le istruzioni sono state copiate in $APP_DIR."
  echo "Chiedi al tuo agente di installare Python 3, poi rilancia questo file."
  exit 1
}

cp "$SRC_DIR"/detta.py "$SRC_DIR"/parla.py "$SRC_DIR"/voce_hook.py "$SRC_DIR"/voce_lib.py "$SRC_DIR"/voce "$SRC_DIR"/voce_launcher.c "$SRC_DIR"/Onest.ttf "$SRC_DIR/$SHORTCUT_FILE" "$APP_DIR"/
# Orecchio (Silero VAD, MIT): senza il modello la Voce va come prima, a volume
for f in silero_vad.onnx silero_vad_LICENSE.txt; do
  if [ -f "$SRC_DIR/$f" ]; then cp "$SRC_DIR/$f" "$APP_DIR"/; fi
done
python3 "$SRC_DIR/voce_hook.py" --merge-config "$SRC_DIR/config.json" "$APP_DIR/config.json"
chmod +x "$APP_DIR/voce"

python3 -m venv "$APP_DIR/.venv"
"$PY" -m pip install --upgrade pip
"$PY" -m pip install -r "$SRC_DIR/requirements.txt"

# Il doppio click apre una finestra del Terminale: a lavoro finito si richiude da sola.
CHIUSURA_FINESTRA=$(cat <<'EOS'
TTY_FINESTRA="$(tty)"
( trap '' HUP; sleep 1; osascript -e 'on run argv
tell application "Terminal"
repeat with w in windows
try
if (tty of selected tab of w) is (item 1 of argv) then close w saving no
end try
end repeat
end tell
end run' "$TTY_FINESTRA" >/dev/null 2>&1 ) </dev/null >/dev/null 2>&1 &
exit 0
EOS
)

cat > "$HOME/Desktop/Voce Dettatura.command" <<LAUNCHER
#!/bin/bash
"$APP_DIR/voce" riavvia
$CHIUSURA_FINESTRA
LAUNCHER

cat > "$HOME/Desktop/Voce Attiva Tutto.command" <<LAUNCHER
#!/bin/bash
cd "$APP_DIR"
pgrep -f "[Pp]ython.*detta\\.py" >/dev/null || ./voce riavvia
if [ -f VOICE_ON ] && [ -f MANI_LIBERE_ON ]; then
  rm -f VOICE_ON MANI_LIBERE_ON
  "$PY" parla.py --stop
  "$PY" parla.py "Voce AI spenta. Mani libere disattivate."
else
  touch VOICE_ON MANI_LIBERE_ON
  "$PY" parla.py "Voce AI accesa. Le risposte dell'agente sono audio sintetico. Mani libere attivate."
fi
$CHIUSURA_FINESTRA
LAUNCHER

chmod +x "$HOME/Desktop/Voce Dettatura.command" "$HOME/Desktop/Voce Attiva Tutto.command"

"$PY" -m py_compile "$APP_DIR"/detta.py "$APP_DIR"/parla.py "$APP_DIR"/voce_hook.py "$APP_DIR"/voce_lib.py
"$PY" "$APP_DIR/voce_hook.py" --install-hooks
"$PY" "$APP_DIR/voce_hook.py" --check-hooks

# La Voce e' un servizio di macOS (parte all'accesso, riparte da sola) e i permessi sono dell'app
# «Voce LeaderAI»: prima le richieste a schermo, poi l'avvio, cosi' i permessi valgono subito.
"$APP_DIR/voce" permessi || echo "Permessi non completati: rilancia \"$APP_DIR/voce\" permessi, poi \"$APP_DIR/voce\" riavvia."
"$APP_DIR/voce" riavvia || echo "Servizio non avviato: rilancia \"$APP_DIR/voce\" riavvia."

echo
echo "Installazione completata."
echo
echo "Prossimi passi:"
echo "1. La Voce parte da sola a ogni accesso (servizio di macOS). Per riavviarla: 'Voce Dettatura.command' dalla Scrivania."
echo "2. Nelle Impostazioni di Sistema accendi 'Voce LeaderAI' in Microfono, Accessibilita' e Monitoraggio input."
echo "3. Tieni premuto Cmd destro, parla, rilascia."
echo "4. Option + freccia sinistra tenuti un secondo: attiva (o spegne) la voce agenti."
echo "5. Cmd destro + Option: attiva la modalita' mani libere."
echo "6. Il tuo agente verifichera' FOTOCOPIA_SAL_OK e completera' la prova voce."
echo
echo "Cartella installata: $APP_DIR"
