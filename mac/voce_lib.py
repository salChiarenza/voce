"""Funzioni pure del tool Voce: config e interruttore voce.

Le funzioni runtime (audio, hotkey, TTS) stanno in detta.py e parla.py;
qui solo logica testabile senza hardware.
"""
import json
import logging
import re
from pathlib import Path

BASE = Path(__file__).parent
FLAG_VOICE_ON = BASE / "VOICE_ON"


def carica_config():
    with open(BASE / "config.json") as f:
        return json.load(f)


def voce_attiva():
    """La voce in uscita parla solo se esiste il file flag VOICE_ON."""
    return FLAG_VOICE_ON.exists()


def timeout_scaduto(attivo, inizio, ora, limite_sec):
    """True se un'operazione attiva dura oltre il limite indicato."""
    return bool(attivo and inizio is not None and (ora - inizio) > limite_sec)


# Whisper-italiano inventa testo sul silenzio/rumore ("Grazie.", "Sottotitoli…")
# e lo fa con alta confidenza (no_speech_prob ~0): i suoi punteggi interni NON
# distinguono il parlato vero. Per questo qui filtriamo in due modi indipendenti:
# l'energia dell'audio (c'e' stato parlato?) e una rete sulle frasi-fantasma note.

SOGLIA_VOCE = 0.004  # RMS minima sotto la quale consideriamo l'audio "non parlato"


def c_e_voce(audio, soglia=SOGLIA_VOCE):
    """True se l'audio ha l'energia di un parlato vero, non di silenzio/respiro."""
    import numpy as np  # import pigro: l'hook TTS usa voce_lib senza numpy
    a = np.asarray(audio, dtype="float32").reshape(-1)
    if a.size == 0:
        return False
    return float(np.sqrt(np.mean(a * a))) >= soglia


_FRASI_FANTASMA = {
    "grazie",
    "grazie a tutti",
    "grazie a voi",
    "grazie mille a tutti",
    "grazie per la visione",
    "grazie per l attenzione",
    "grazie per aver guardato il video",
    "ciao a tutti",
    "buona giornata a tutti",
}


def _normalizza(testo):
    testo = re.sub(r"[\s.,;:!?\-–—\"'`…()]+", " ", testo.lower())
    return testo.strip()


def e_allucinazione(testo):
    """True se il testo e' una frase-fantasma tipica di Whisper sul non-parlato.

    Il confronto e' sull'intera stringa normalizzata: una frase vera che
    contiene 'grazie' (es. 'Grazie mille per la proposta…') non viene scartata.
    """
    n = _normalizza(testo)
    if not n:
        return True
    if n in _FRASI_FANTASMA:
        return True
    return "sottotitoli" in n and ("a cura di" in n or "creati dalla comunit" in n)


def esegui_sicuro(fn, *args):
    """Esegue fn(*args) senza mai propagare eccezioni.

    Le callback di pynput girano su un thread che muore se la callback solleva:
    un solo errore spegnerebbe l'hotkey (la dettatura "si disabilita") finche'
    non si riavvia. Qui ogni errore viene loggato e ingoiato: il listener vive.
    """
    try:
        return fn(*args)
    except Exception:
        logging.getLogger("voce").exception("errore in callback voce")


def pulisci_per_voce(testo):
    """Trasforma il markdown in testo piano leggibile a voce."""
    testo = re.sub(r"```.*?```", " codice omesso. ", testo, flags=re.DOTALL)
    testo = re.sub(r"`([^`]*)`", r"\1", testo)                      # codice inline
    testo = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", testo)              # immagini
    testo = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", testo)          # link -> testo
    testo = re.sub(r"https?://\S+", " ", testo)                     # URL nudi
    testo = re.sub(r"^#{1,6}\s*", "", testo, flags=re.MULTILINE)    # titoli
    testo = re.sub(r"[*_]{1,3}([^*_\n]+)[*_]{1,3}", r"\1", testo)   # grassetto/corsivo
    testo = re.sub(r"^\s*[-*•>]\s+", "", testo, flags=re.MULTILINE) # elenchi/citazioni
    return re.sub(r"\s+", " ", testo).strip()


def estrai_ultima_risposta(transcript_path):
    """Ultimo messaggio testuale dell'assistente da un transcript JSONL di Claude Code."""
    ultimo = ""
    with open(transcript_path) as f:
        for riga in f:
            riga = riga.strip()
            if not riga:
                continue
            try:
                voce = json.loads(riga)
            except json.JSONDecodeError:
                continue
            if voce.get("type") != "assistant":
                continue
            contenuto = voce.get("message", {}).get("content", [])
            testi = [
                b.get("text", "")
                for b in contenuto
                if isinstance(b, dict) and b.get("type") == "text"
            ]
            if testi:
                ultimo = "\n".join(testi)
    return ultimo
