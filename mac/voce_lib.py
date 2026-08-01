"""Funzioni pure del tool Voce: config e interruttore voce.

Le funzioni runtime (audio, hotkey, TTS) stanno in detta.py e parla.py;
qui solo logica testabile senza hardware.
"""
import json
import logging
import re
import shutil
import subprocess
import sys
from pathlib import Path


def _base_operativa(module_file=None, argv0=None, cwd=None):
    """Trova la cartella runtime anche quando gli script sono symlink.

    Python risolve il percorso fisico dello script prima di costruire
    ``sys.path``. Sul Mac di Sal, quindi, ``__file__`` puo' puntare alla repo
    pubblica anche se l'app e' stata avviata da ``tools/voce``: config locale
    e flag VOICE_ON/MANI_LIBERE_ON resterebbero invisibili. ``sys.argv[0]``
    conserva invece il percorso realmente invocato.
    """
    modulo = Path(module_file or __file__)
    invocato = Path(argv0 if argv0 is not None else sys.argv[0]).expanduser()
    if not invocato.is_absolute():
        invocato = Path(cwd or Path.cwd()) / invocato
    candidato = invocato.parent
    try:
        if (candidato / "voce_lib.py").resolve() == modulo.resolve():
            return candidato
    except OSError:
        pass
    return modulo.parent


BASE = _base_operativa()
SOURCE_BASE = Path(__file__).resolve().parent
CONFIG_DEFAULT = SOURCE_BASE / "config.json"
CONFIG_LOCAL = BASE / "config.local.json"
FLAG_VOICE_ON = BASE / "VOICE_ON"
FLAG_PARLANDO = BASE / "PARLANDO"  # esiste mentre l'agente sta leggendo una risposta ad alta voce
FLAG_MANI_LIBERE_ON = BASE / "MANI_LIBERE_ON"  # esiste quando l'ascolto continuo e' attivo


def carica_config():
    """Carica l'unico config prodotto e applica solo gli override personali.

    Sulla macchina di Sal i file Python in `tools/voce` sono symlink alla repo
    pubblica: SOURCE_BASE punta quindi alla sorgente unica, mentre BASE resta il
    percorso operativo locale che contiene `config.local.json` e i flag runtime.
    Nell'installazione cliente i due percorsi coincidono e si usa normalmente
    il `config.json` aggiornato dall'installer.
    """
    with open(CONFIG_DEFAULT, encoding="utf-8") as f:
        cfg = json.load(f)
    if CONFIG_LOCAL.exists():
        with open(CONFIG_LOCAL, encoding="utf-8") as f:
            locali = json.load(f)
        if not isinstance(locali, dict):
            raise ValueError(f"Configurazione locale non valida: {CONFIG_LOCAL}")
        cfg.update(locali)
    return cfg


def config_scrivibile():
    """File dove salvare apprendimenti personali senza sporcare il prodotto."""
    if CONFIG_LOCAL.exists() or BASE != SOURCE_BASE:
        return CONFIG_LOCAL
    return CONFIG_DEFAULT


def voce_attiva():
    """La voce in uscita parla solo se esiste il file flag VOICE_ON."""
    return FLAG_VOICE_ON.exists()


def mani_libere_attive():
    """L'ascolto continuo e' attivo solo se esiste il file flag MANI_LIBERE_ON.

    Su file (come VOICE_ON) invece che una variabile in memoria: cosi' un
    lanciatore esterno (es. lo .command sul Desktop) puo' accenderla insieme
    alla voce con un solo click, non solo il combo da tastiera."""
    return FLAG_MANI_LIBERE_ON.exists()


def timeout_scaduto(attivo, inizio, ora, limite_sec):
    """True se un'operazione attiva dura oltre il limite indicato."""
    return bool(attivo and inizio is not None and (ora - inizio) > limite_sec)


# Whisper-italiano inventa testo sul silenzio/rumore ("Grazie.", "Sottotitoli…")
# e lo fa con alta confidenza (no_speech_prob ~0): i suoi punteggi interni NON
# distinguono il parlato vero. Per questo qui filtriamo in due modi indipendenti:
# l'energia dell'audio (c'e' stato parlato?) e una rete sulle frasi-fantasma note.

SOGLIA_VOCE = 0.004  # RMS minima sotto la quale consideriamo l'audio "non parlato"


def audio_fuori_scala(rms, massimo=1.0):
    """True se l'rms e' impossibile per uno stream float32 sano: i sample vivono
    in [-1, 1], quindi rms <= 1 sempre. Sopra = CoreAudio ha rimappato il device
    sotto lo stream e consegna dati corrotti (caso 09/07: rms 3-4 per ~20s,
    Whisper allucinava). Meglio scartare che trascrivere spazzatura."""
    return rms > massimo


def aggiorna_scarti_fuori_scala(contatore, rms, soglia_riavvio=2):
    """Policy sull'audio fuori scala: torna (nuovo_contatore, scartare, riavviare).
    Un episodio isolato e' un transitorio che si riassorbe da solo (caso 09/07:
    ~20s poi tutto ok): si scarta e basta. Dal secondo di fila la corruzione
    persiste e conviene il riavvio pulito dello stream (stesso rimedio del
    cambio device e dello stream muto)."""
    if not audio_fuori_scala(rms):
        return 0, False, False
    contatore += 1
    return contatore, True, contatore >= soglia_riavvio


def c_e_voce(audio, soglia=SOGLIA_VOCE):
    """True se l'audio ha l'energia di un parlato vero, non di silenzio/respiro."""
    import numpy as np  # import pigro: l'hook TTS usa voce_lib senza numpy
    a = np.asarray(audio, dtype="float32").reshape(-1)
    if a.size == 0:
        return False
    return float(np.sqrt(np.mean(a * a))) >= soglia


# Le soglie dell'app (SOGLIA_VOCE 0.004, mani libere 0.018) sono calibrate su un
# guadagno d'ingresso di sistema "normale". Se il Mac abbassa il volume del
# microfono, tutto scende insieme e l'app diventa muta senza che nulla sia rotto.
# Misure del 01/08/2026 nella stanza di Sal, rumore ambiente:
#   guadagno 36 -> 0.0021 | 55 -> 0.0028 | 65 -> 0.0040 | 75 -> 0.0062-0.0074 | 100 -> 0.0120
# Sotto 60 il parlato normale (0.012-0.024 a guadagno giusto) scivola verso
# SOGLIA_VOCE e non raggiunge mai la soglia mani libere. A 100 il solo rumore
# ambiente supera SOGLIA_VOCE e sfiora 0.018: il VAD si auto-innescherebbe.
GUADAGNO_INGRESSO_MINIMO = 60
GUADAGNO_INGRESSO_TARGET = 75


def diagnosi_audio_muto(rms, guadagno_ingresso, soglia_voce=SOGLIA_VOCE,
                        minimo=GUADAGNO_INGRESSO_MINIMO, target=GUADAGNO_INGRESSO_TARGET):
    """Audio tornato sotto soglia: di chi e' la colpa? Torna (causa, guadagno_da_impostare).

    Due guasti diversi si presentano identici nel log ("volume sotto soglia"),
    ma hanno rimedi opposti:
      - "guadagno_basso": il volume d'ingresso di sistema e' sceso (caso
        01/08/2026: 36/100, parlato a rms 0.0014). Si rialza e basta. Riavviare
        il processo NON serve, il guadagno resta abbassato anche dopo.
      - "stream_muto": il guadagno e' a posto, quindi e' lo stream CoreAudio
        incantato sotto il device (caso 08/07: Microfono di iPhone). Rimedio:
        il riavvio pulito del processo.
    Guadagno illeggibile (non-Mac, osascript fallito) = non lo si puo'
    incolpare: si ricade sul vecchio rimedio, mai peggio di prima."""
    if rms >= soglia_voce:
        return "ok", None
    if guadagno_ingresso is not None and guadagno_ingresso < minimo:
        return "guadagno_basso", target
    return "stream_muto", None


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
    # Whisper allucina anche in inglese su code audio/rumore (caso reale
    # 06/07: "Yeah." dalla coda dell'annuncio TTS zittito). Confronto solo
    # sull'INTERA stringa: un "yeah" dentro una frase vera non viene toccato.
    "yeah",
    "yes",
    "bye",
    "thank you",
    "thanks for watching",
}


def _normalizza(testo):
    testo = re.sub(r"[\s.,;:!?\-–—\"'`…()]+", " ", testo.lower())
    return testo.strip()


def _ripetizione_patologica(testo, soglia_ripetizioni=8, soglia_quota=0.6):
    """True se il testo e' dominato da un collasso ripetuto: e' il difetto
    classico di Whisper su audio corto/ambiguo (visto 06/07: "мент" ripetuto
    centinaia di volte, poi "版" cinese ripetuto senza spazi). Due controlli,
    non dipendono da lingua/alfabeto:
    1. una PAROLA (separata da spazi) che copre la maggior parte del testo;
    2. un CARATTERE ripetuto tante volte di fila senza spazi (cinese,
       giapponese...: li' lo split per parole vede tutto come "1 parola sola"
       e il controllo 1 non si accorge di niente)."""
    parole = testo.split()
    if len(parole) >= soglia_ripetizioni:
        conteggi = {}
        for p in parole:
            chiave = p.lower()
            conteggi[chiave] = conteggi.get(chiave, 0) + 1
        piu_frequente = max(conteggi.values())
        if piu_frequente >= soglia_ripetizioni and piu_frequente / len(parole) >= soglia_quota:
            return True
    return re.search(r"(.)\1{%d,}" % (soglia_ripetizioni - 1), testo) is not None


def e_allucinazione(testo):
    """True se il testo e' una frase-fantasma tipica di Whisper sul non-parlato,
    o un collasso a ripetizione (vedi _ripetizione_patologica).

    Il confronto e' sull'intera stringa normalizzata: una frase vera che
    contiene 'grazie' (es. 'Grazie mille per la proposta…') non viene scartata.
    """
    n = _normalizza(testo)
    if not n:
        return True
    if n in _FRASI_FANTASMA:
        return True
    if "sottotitoli" in n and ("a cura di" in n or "creati dalla comunit" in n):
        return True
    return _ripetizione_patologica(testo)


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


# Apple Intelligence (corsia veloce via Comando Rapido) rifiuta in blocco le
# richieste con parolacce ("Il modello non puo' fornire una risposta a questa
# richiesta"): verificato in diretta il 05/07, causa reale di gran parte dei
# fallimenti della corsia veloce (Sal ne usa spesso). Le mascheriamo solo per
# la chiamata al Comando Rapido e le rimettiamo a posto nel risultato: la
# corsia agente non ha questo problema e non viene toccata.
_VOLGARI_MASCHERA = {
    "cazzo": "trippa",
    "cazzata": "fesseria",
    "cazzate": "fesserie",
    "minchia": "capperi",
    "puttana": "sgualdrina",
    "troia": "bagascia",
    "stronzo": "mascalzone",
    "stronza": "mascalzona",
    "merda": "guazzabuglio",
    "coglione": "sempliciotto",
    "coglioni": "sempliciotti",
    "vaffanculo": "sparisci",
}
_VOLGARI_SMASCHERA = {v: k for k, v in _VOLGARI_MASCHERA.items()}


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
        # NON "scrivi questi nomi": il modellino Apple lo eseguiva alla lettera
        # e appendeva l'intero glossario in coda al testo (bug 03/07)
        righe.append("5. Se nel testo compare uno di questi nomi, scrivilo esattamente così: " + ", ".join(glossario) + ". Non aggiungere mai nomi che chi parla non ha detto.")
    righe.append("Rispondi SOLO col testo corretto, senza commenti ne' virgolette.")
    righe.append("")
    righe.append("TESTO DA SISTEMARE:")
    righe.append(testo)
    return "\n".join(righe)


def pulizia_inventa_nomi(grezzo, pulito, glossario):
    """True se la pulizia ha aggiunto nomi del glossario mai dettati: il
    modellino a volte rigurgita la lista della regola 5 in coda al testo.
    Un nome solo puo' essere una correzione legittima di grafia: soglia 2."""
    g = grezzo.lower()
    p = pulito.lower()
    aggiunti = [v for v in glossario if v.lower() in p and v.lower() not in g]
    return len(aggiunti) >= 2


def pulizia_sospetta(grezzo, pulito, glossario=()):
    """La pulizia va scartata (si tiene il grezzo) se inventa nomi mai dettati
    o se collassa il testo: togliere intercalari e ripensamenti non puo'
    mangiarsi oltre due terzi delle parole."""
    if pulizia_inventa_nomi(grezzo, pulito, glossario):
        return True
    return len(pulito.split()) * 3 < len(grezzo.split())


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
    """Corsia veloce: Apple Intelligence via Comando Rapido (~1s, niente
    token; di default Private Cloud Compute, "Su dispositivo" per il 100% locale). Torna il testo sistemato, o None se qualcosa va storto: il
    chiamante allora ripiega sull'agente o sul grezzo.

    Logga SEMPRE il motivo del fallimento (prima veniva inghiottito: si
    vedeva solo "FALLITA" senza sapere se era timeout, comando rotto o
    guardia pulizia_sospetta troppo aggressiva)."""
    import tempfile
    log = logging.getLogger("voce")
    testo_mascherato = applica_sostituzioni(testo, _VOLGARI_MASCHERA)
    try:
        with tempfile.TemporaryDirectory() as d:
            ingresso = Path(d) / "in.txt"
            uscita = Path(d) / "out.txt"
            ingresso.write_text(prompt_pulizia(testo_mascherato, glossario))
            esito = subprocess.run(
                ["shortcuts", "run", nome, "-i", str(ingresso),
                 "-o", str(uscita), "--output-type", "public.plain-text"],
                capture_output=True, timeout=timeout,
            )
            if esito.returncode != 0:
                log.warning(
                    "shortcut '%s' returncode %d: %s", nome, esito.returncode,
                    (esito.stderr or b"").decode(errors="replace").strip()[:200],
                )
                return None
            if not uscita.exists():
                log.warning("shortcut '%s' non ha scritto il file di uscita", nome)
                return None
            pulito = applica_sostituzioni(uscita.read_text().strip(), _VOLGARI_SMASCHERA)
            if not pulito:
                log.warning("shortcut '%s' ha risposto vuoto", nome)
                return None
            if pulizia_sospetta(testo, pulito, glossario):
                log.warning(
                    "shortcut '%s' scartato da pulizia_sospetta (nomi inventati o testo collassato)",
                    nome,
                )
                return None
            return pulito
    except subprocess.TimeoutExpired:
        log.warning("shortcut '%s' oltre il timeout di %.0fs", nome, timeout)
        return None
    except Exception:
        log.exception("pulizia con Comando Rapido fallita")
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
        if pulizia_sospetta(testo, pulito, glossario):
            return testo
        return pulito
    except Exception:
        logging.getLogger("voce").exception("pulizia con agente fallita: tengo il grezzo")
        return testo


# --- apprendimento automatico: Voce impara le parole che sbaglia sempre ---

def estrai_grezzi_dal_log(log_path, massimo=50):
    """Ultime dettature grezze dal log (righe 'INFO grezzo: ...')."""
    try:
        righe = Path(log_path).read_text().splitlines()
    except OSError:
        return []
    grezzi = [r.split("INFO grezzo: ", 1)[1] for r in righe if "INFO grezzo: " in r]
    return grezzi[-massimo:]


def unisci_sostituzioni(attuali, nuove):
    """Solo coppie nuove e sensate: mai sovrascrivere quelle esistenti (che
    Sal o il cliente possono aver messo a mano), mai identita' o spazzatura."""
    buone = {}
    for sbagliato, giusto in nuove.items():
        sbagliato, giusto = str(sbagliato).strip(), str(giusto).strip()
        if not sbagliato or not giusto:
            continue
        if sbagliato.lower() == giusto.lower():
            continue
        if len(sbagliato) > 40 or len(giusto) > 40:
            continue
        if sbagliato.lower() in (k.lower() for k in attuali):
            continue
        buone[sbagliato] = giusto
    return buone


def estrai_json(testo):
    """Primo oggetto JSON piatto trovato nella risposta dell'agente."""
    inizio = testo.find("{")
    fine = testo.rfind("}")
    if inizio == -1 or fine <= inizio:
        return {}
    try:
        esito = json.loads(testo[inizio:fine + 1])
        return esito if isinstance(esito, dict) else {}
    except json.JSONDecodeError:
        return {}


def prompt_apprendimento(grezzi):
    righe = [
        "Queste sono dettature vocali trascritte da Whisper in italiano.",
        "Trova SOLO le parole chiaramente trascritte male (non esistono o non",
        "hanno senso nel contesto) di cui sei SICURO della parola intesa.",
        'Rispondi SOLO con un oggetto JSON piatto {"sbagliata": "giusta"}.',
        "Se non trovi errori sicuri, rispondi {}.",
        "",
        "DETTATURE:",
    ]
    righe += ["- " + g for g in grezzi]
    return "\n".join(righe)


def impara_sostituzioni(log_path, config_path, comando, timeout=60):
    """Legge le ultime dettature grezze, chiede all'agente le correzioni
    ricorrenti sicure e le aggiunge alle sostituzioni del config.
    Torna le coppie nuove imparate ({} se niente o se qualcosa va storto)."""
    grezzi = estrai_grezzi_dal_log(log_path)
    if not grezzi:
        return {}
    try:
        esito = subprocess.run(
            comando + [prompt_apprendimento(grezzi)],
            capture_output=True, text=True, timeout=timeout,
        )
        proposte = estrai_json(esito.stdout or "")
        with open(config_path) as f:
            cfg = json.load(f)
        nuove = unisci_sostituzioni(cfg.get("sostituzioni", {}), proposte)
        if nuove:
            cfg.setdefault("sostituzioni", {}).update(nuove)
            with open(config_path, "w") as f:
                json.dump(cfg, f, indent=2, ensure_ascii=False)
                f.write("\n")
        return nuove
    except Exception:
        logging.getLogger("voce").exception("apprendimento sostituzioni fallito")
        return {}


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
