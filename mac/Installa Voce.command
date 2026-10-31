#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
"$SCRIPT_DIR/install.sh"

# Se l'installazione e' riuscita il doppio click non deve lasciare una finestra aperta;
# se e' fallita lo script si ferma qui sopra e la finestra resta per leggere il messaggio.
echo
echo "Questa finestra si chiude da sola tra 10 secondi."
TTY_FINESTRA="$(tty)"
( trap '' HUP; sleep 10; osascript -e 'on run argv
tell application "Terminal"
repeat with w in windows
try
if (tty of selected tab of w) is (item 1 of argv) then close w saving no
end try
end repeat
end tell
end run' "$TTY_FINESTRA" >/dev/null 2>&1 ) </dev/null >/dev/null 2>&1 &
exit 0
