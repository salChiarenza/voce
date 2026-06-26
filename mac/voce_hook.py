"""Hook Stop: se la voce è attiva (flag VOICE_ON), legge ad alta voce l'ultima risposta.

Input su stdin (JSON):
- Claude Code: campo "transcript_path" -> si estrae l'ultimo messaggio dell'assistente.
- Codex: campo "last_assistant_message" -> si usa direttamente.
Non deve mai bloccare l'agente: ogni errore esce in silenzio con exit 0.
"""
import json
import sys

from voce_lib import voce_attiva, estrai_ultima_risposta
from parla import parla


def main():
    if not voce_attiva():
        return
    try:
        dati = json.load(sys.stdin)
    except Exception:
        return
    testo = dati.get("last_assistant_message") or ""
    if not testo and dati.get("transcript_path"):
        try:
            testo = estrai_ultima_risposta(dati["transcript_path"])
        except Exception:
            return
    if testo:
        parla(testo)  # Popen: parte e non aspetta la fine


if __name__ == "__main__":
    main()
    sys.exit(0)
