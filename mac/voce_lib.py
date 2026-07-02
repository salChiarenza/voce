"""Funzioni pure del tool Voce: config e interruttore voce.

Le funzioni runtime (audio, hotkey, TTS) stanno in detta.py e parla.py;
qui solo logica testabile senza hardware.
"""
import json
import logging
import re
import shutil
import subprocess
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


# --- glossario e detta pulito: la trascrizione grezza diventa testo curato ---

def glossario_iniziale(cfg):
    """Prompt iniziale per Whisper coi termini del mestiere: cosi' nomi propri
    e brand (LeaderAI, Systeme.io, nomi clienti) escono scritti giusti."""
    voci = [v for v in cfg.get("glossario", []) if v.strip()]
    if not voci:
        return None
    return "Glossario: " + ", ".join(voci) + "."


def applica_sostituzioni(testo, sostituzioni):
    """Correzioni ricorrenti 'sbagliato -> giusto', a parola intera e senza
    distinguere maiuscole: quello che il glossario non basta a fissare."""
    for sbagliato, giusto in sostituzioni.items():
        testo = re.sub(
            r"\b" + re.escape(sbagliato) + r"\b", giusto, testo, flags=re.IGNORECASE
        )
    return testo


def serve_pulizia(testo, cfg):
    """Detta pulito solo se attivo in config e la dettatura e' lunga: le
    dettature corte (comandi rapidi) devono incollare subito, senza attese."""
    if not cfg.get("detta_pulito", False):
        return False
    minimo = int(cfg.get("pulizia_min_parole", 15))
    return len(testo.split()) >= minimo


def prompt_pulizia(testo, glossario=()):
    """Istruzioni per chi sistema il dettato (modello locale o agente).
    Formulazione numerata con esempio esplicito: e' quella che fa risolvere
    bene i ripensamenti anche al modello Apple on-device (collaudata 02/07)."""
    righe = [
        "Correggi questa dettatura vocale seguendo le regole nell'ordine:",
        # ogni regola su UNA riga sola: spezzarle fa perdere la regola al modello on-device
        '1. Quando chi parla si corregge, vale SOLO l\'ultima versione detta. "martedì anzi no facciamo mercoledì" significa MERCOLEDÌ: scrivi solo "mercoledì" e cancella "martedì" e "anzi no facciamo".',
        "2. Cancella gli intercalari: ehm, cioè, ecco.",
        "3. Sistema punteggiatura e maiuscole.",
        "4. Non riassumere, non aggiungere niente, non tradurre.",
    ]
    if glossario:
        righe.append("5. Scrivi correttamente questi nomi: " + ", ".join(glossario) + ".")
    righe.append("Rispondi SOLO col testo corretto, senza commenti ne' virgolette.")
    righe.append("")
    righe.append("TESTO DA SISTEMARE:")
    righe.append(testo)
    return "\n".join(righe)


def shortcut_pulizia_disponibile(nome):
    """True se il Comando Rapido del modello Apple on-device esiste su questo
    computer (solo macOS: altrove la CLI `shortcuts` non c'e')."""
    if not shutil.which("shortcuts"):
        return False
    try:
        esito = subprocess.run(
            ["shortcuts", "list"], capture_output=True, text=True, timeout=10
        )
        return nome in (esito.stdout or "").splitlines()
    except Exception:
        return False


def pulisci_con_shortcut(testo, nome, timeout=10, glossario=()):
    """Corsia veloce: modello Apple on-device via Comando Rapido (~1s, zero
    cloud). Torna il testo sistemato, o None se qualcosa va storto: il
    chiamante allora ripiega sull'agente o sul grezzo."""
    import tempfile
    try:
        with tempfile.TemporaryDirectory() as d:
            ingresso = Path(d) / "in.txt"
            uscita = Path(d) / "out.txt"
            ingresso.write_text(prompt_pulizia(testo, glossario))
            esito = subprocess.run(
                ["shortcuts", "run", nome, "-i", str(ingresso),
                 "-o", str(uscita), "--output-type", "public.plain-text"],
                capture_output=True, timeout=timeout,
            )
            if esito.returncode != 0 or not uscita.exists():
                return None
            pulito = uscita.read_text().strip()
            return pulito or None
    except Exception:
        logging.getLogger("voce").exception("pulizia con Comando Rapido fallita")
        return None


def comando_agente(_quale=None):
    """L'agente gia' presente sul PC che fa la pulizia: Claude Code prima,
    Codex come riserva. Nessuno dei due installato -> niente pulizia.

    Avvio "spoglio" (misurato: ~2-3s in meno a chiamata): la pulizia non deve
    caricare MCP, tool, settings ne' salvare la sessione su disco."""
    if shutil.which("claude"):
        return [
            "claude", "--model", "haiku", "-p",
            "--tools", "",              # nessun tool built-in
            "--strict-mcp-config",      # senza --mcp-config = zero server MCP
            "--setting-sources", "",    # niente settings utente/progetto
            "--no-session-persistence", # niente sessione salvata su disco
        ]
    if shutil.which("codex"):
        return ["codex", "exec"]
    return None


def pulisci_con_agente(testo, comando, timeout=10, glossario=()):
    """Passa il dettato all'agente locale e torna il testo sistemato.
    Qualsiasi problema (errore, output vuoto, timeout) -> testo originale:
    la dettatura non deve MAI perdersi per colpa della pulizia."""
    try:
        esito = subprocess.run(
            comando + [prompt_pulizia(testo, glossario)],
            capture_output=True, text=True, timeout=timeout,
        )
        pulito = (esito.stdout or "").strip()
        if esito.returncode != 0 or not pulito:
            return testo
        return pulito
    except Exception:
        logging.getLogger("voce").exception("pulizia con agente fallita: tengo il grezzo")
        return testo


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
