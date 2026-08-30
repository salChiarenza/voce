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
import time
from difflib import SequenceMatcher
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


SOGLIA_GUASTI_CORSIA = 2
RIPOSO_CORSIA_SEC = 600  # 10 minuti


def corsia_utilizzabile(guasti, ultimo_guasto, ora,
                        soglia=SOGLIA_GUASTI_CORSIA, riposo=RIPOSO_CORSIA_SEC):
    """Una corsia di pulizia (Comando Rapido o agente locale) si spegne dopo
    `soglia` fallimenti di fila, per non regalare secondi morti a ogni
    dettatura. Ma deve poter TORNARE: dopo `riposo` secondi si riprova.

    Caso 27-29/07/2026: la corsia veloce si spegneva e basta, e il processo di
    Sal restava in piedi 2 giorni e 16 ore. Risultato: per giorni interi ogni
    dettatura passava dall'agente lento (12 timeout da 20s il solo 29/07), e
    dopo quei 20s si incollava comunque il grezzo. Uno spegnimento senza via di
    ritorno, in un processo che vive per giorni, e' uno spegnimento definitivo."""
    if guasti < soglia:
        return True
    if ultimo_guasto is None:
        return False
    return (ora - ultimo_guasto) >= riposo


def registra_esito_corsia(guasti, riuscito, ora):
    """Torna (nuovi_guasti, momento_ultimo_guasto). Un successo azzera tutto:
    contano solo i fallimenti DI FILA, non quelli sparsi nel tempo."""
    if riuscito:
        return 0, None
    return guasti + 1, ora


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


# --- cursore automatico: il click nella casella lo fa l'app, non l'utente ---
# (richiesta 29/08/2026: Sal passa di finestra in finestra e detta; non deve
# mai prendere il mouse per cliccare nella casella di scrittura.)

RUOLI_CASELLA = {"AXTextField", "AXTextArea", "AXSearchField", "AXComboBox"}


def ruolo_editabile(ruolo):
    """True se il ruolo Accessibility e' una casella dove si puo' scrivere."""
    return str(ruolo or "") in RUOLI_CASELLA


def scegli_casella(candidati):
    """Indice della casella migliore tra quelle trovate nella finestra.

    candidati = [(y, larghezza), ...] con y che cresce verso il basso (come
    nelle coordinate Accessibility). Nelle chat la casella di scrittura sta
    in fondo alla finestra: si prende la piu' in basso, a parita' la piu'
    larga. None se non c'e' nessuna casella."""
    if not candidati:
        return None
    return max(range(len(candidati)), key=lambda i: (candidati[i][0], candidati[i][1]))


def in_zona_scrittura(y_casella, y_finestra, altezza_finestra, quota=0.4):
    """True se la casella sta nella parte bassa della finestra.

    La casella di scrittura delle chat sta in fondo; le caselle in alto sono
    barra degli indirizzi del browser o campi di ricerca della toolbar, e non
    vanno MAI prese (provato su Chrome il 29/08/2026: senza questo filtro il
    testo sarebbe finito nella barra degli indirizzi). Meglio nessun click
    che un click nella barra sbagliata."""
    return y_casella >= y_finestra + altezza_finestra * quota


# --- audio conservato: riascoltare le frasi capite male per tarare Voce ---

def file_audio_da_eliminare(nomi, massimo):
    """Quali file conservati vanno eliminati per restare entro `massimo`.

    I nomi contengono il timestamp, quindi l'ordine alfabetico e' l'ordine
    temporale: si tolgono i piu' vecchi. Con massimo <= 0 (conservazione
    spenta) si elimina tutto: nessun audio deve restare indietro."""
    ordinati = sorted(nomi)
    if massimo <= 0:
        return ordinati
    return ordinati[:-massimo] if len(ordinati) > massimo else []


def salva_audio_recente(audio, cartella, massimo, freq=16000):
    """Salva la dettatura come WAV in `cartella` e tiene solo le ultime
    `massimo` (le piu' vecchie si eliminano da sole). Tutto resta sul
    computer: serve a riascoltare le frasi capite male e a tarare glossario
    e sostituzioni su casi veri, non a memoria. Spenta di default
    (`conserva_audio_n` = 0): e' una scelta del proprietario.
    Torna il percorso salvato (None se spenta)."""
    import wave
    import numpy as np  # import pigro: l'hook TTS usa voce_lib senza numpy
    massimo = int(massimo)
    cartella = Path(cartella)
    if massimo <= 0:
        return None
    cartella.mkdir(exist_ok=True)
    base = time.strftime("dettatura_%Y%m%d_%H%M%S")
    nome, progressivo = base + ".wav", 0
    while (cartella / nome).exists():  # due dettature nello stesso secondo
        progressivo += 1
        nome = f"{base}_{progressivo}.wav"
    dati = np.clip(np.asarray(audio, dtype="float32").reshape(-1), -1.0, 1.0)
    percorso = cartella / nome
    with wave.open(str(percorso), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(freq)
        w.writeframes((dati * 32767).astype("<i2").tobytes())
    for vecchio in file_audio_da_eliminare(
        [p.name for p in cartella.glob("dettatura_*.wav")], massimo
    ):
        (cartella / vecchio).unlink(missing_ok=True)
    return percorso


# --- glossario e detta pulito: la trascrizione grezza diventa testo curato ---

def glossario_iniziale(cfg):
    """Prompt iniziale per Whisper coi termini del mestiere: cosi' nomi propri
    e brand (LeaderAI, Systeme.io, nomi clienti) escono scritti giusti."""
    voci = [v for v in cfg.get("glossario", []) if v.strip()]
    if not voci:
        return None
    return "Glossario: " + ", ".join(voci) + "."


def rimuovi_eco_glossario(testo, glossario=()):
    """Whisper a volte ricopia il suggerimento del glossario in testa alla
    trascrizione (caso reale 29/08/2026: "non lo so, mi arrendo" diventato
    "Glossario, mi arrendo."). La parola "Glossario" seguita da :/,/. in
    apertura non e' mai stata dettata: si toglie, insieme agli eventuali nomi
    del glossario ricopiati subito dopo. Nel corpo della frase non si tocca
    niente, e "glossario" seguito da una parola normale resta com'e'."""
    t = testo.lstrip()
    eco = re.match(r"(?i)^glossario\s*[:,.]\s*", t)
    if not eco:
        return testo
    t = t[eco.end():]
    rimosso = True
    while rimosso:  # l'eco completo ricopia anche i nomi, uno dopo l'altro
        rimosso = False
        for voce in glossario:
            coda = re.match(r"(?i)^" + re.escape(voce) + r"\s*[:,.]\s*", t)
            if coda:
                t = t[coda.end():]
                rimosso = True
    return t


def applica_sostituzioni(testo, sostituzioni):
    """Correzioni ricorrenti 'sbagliato -> giusto', a parola intera e senza
    distinguere maiuscole: quello che il glossario non basta a fissare."""
    for sbagliato, giusto in sostituzioni.items():
        testo = re.sub(
            r"\b" + re.escape(sbagliato) + r"\b", giusto, testo, flags=re.IGNORECASE
        )
    return testo


def converti_punteggiatura_dettata(testo):
    """I segni di punteggiatura DETTATI diventano segni veri: "si parte punto
    esclamativo" -> "si parte!" (richiesta di Sal 30/08/2026: Whisper virgole
    e domande le mette a orecchio, l'esclamativo in italiano quasi mai).

    Si convertono SOLO comandi inequivocabili al singolare: "punto" e
    "virgola" da soli restano parole (li mette gia' Whisper e nel parlato
    sono ovunque). Con l'articolo davanti ("il punto esclamativo") si sta
    parlando DEL segno e non si tocca; "venirne a capo" resta un idioma.
    Il segno si attacca alla parola prima, al posto dell'eventuale segno gia'
    messo da Whisper; dopo ! ? e a-capo la frase riparte maiuscola.
    Tabelle dentro la funzione: la gemella Windows viene estratta da sola
    dai test e deve bastarsi (stesso patto di rimuovi_eco_glossario)."""
    comandi = [
        (r"punto\s+esclamativo", "!"),
        (r"punto\s+interrogativo", "?"),
        (r"punto\s+e\s+virgola", ";"),
        (r"punt(?:ini|i)\s+di\s+sospensione", "..."),
        (r"a\s+capo|nuova\s+riga", "\n"),
    ]
    articoli = {"il", "lo", "la", "i", "gli", "le", "un", "uno", "una",
                "del", "dello", "della", "dei", "degli", "delle",
                "al", "allo", "alla", "ai", "agli", "alle",
                "quel", "quello", "quella", "quei", "questo", "questa",
                "ogni", "nessun", "senza"}
    venire = {"vengo", "vieni", "viene", "veniamo", "venite", "vengono",
              "venirne", "venuto", "venuta", "venuti", "venute"}
    for motivo, segno in comandi:
        schema = re.compile(
            r"(\w[\w'’]*)?([\s.,;:]*)\b(?:" + motivo + r")\b[.,;:]?",
            re.IGNORECASE,
        )

        def rimpiazza(m, segno=segno):
            prima = m.group(1) or ""
            nuda = prima.lower()
            if nuda in articoli:
                return m.group(0)  # si parla del segno, non lo si detta
            if segno == "\n" and nuda in venire:
                return m.group(0)  # "non ne vengo a capo" resta com'e'
            if segno == "\n" and nuda == "vai":
                return segno       # "vai a capo": sparisce tutto il comando
            return prima + segno

        testo = schema.sub(rimpiazza, testo)
    testo = re.sub(r"[ \t]+\n", "\n", testo)  # niente spazi attorno alla riga nuova
    testo = re.sub(r"\n[ \t]+", "\n", testo)
    testo = re.sub(  # dopo ! ? o riga nuova la frase riparte maiuscola
        r"([!?\n])(\s*)(\w)",
        lambda m: m.group(1) + m.group(2) + m.group(3).upper(),
        testo,
    )
    return testo.strip()


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


def destinazione_agente(nome_app="", url=""):
    """True quando il testo e' destinato a una chat con un agente AI.

    In queste chat il grezzo di Whisper e' gia' l'input migliore: arriva
    subito e l'agente capisce esitazioni e ripensamenti senza affidare il
    significato a un secondo modello di pulizia.
    """
    nome = str(nome_app or "").strip().lower()
    indirizzo = str(url or "").strip().lower()
    if any(marcatore in nome for marcatore in ("chatgpt", "claude", "codex")):
        return True
    return any(
        dominio in indirizzo
        for dominio in ("chatgpt.com", "chat.openai.com", "claude.ai")
    )


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
    modellino a volte sostituisce un nome vero con uno del glossario.

    Una correzione di grafia resta ammessa solo se nel grezzo esiste una forma
    davvero simile ("leader ai" -> "LeaderAI", "AI Consal" -> "AI con Sal").
    Questo blocca il caso reale "OpenAI" -> "LeaderAI" del 01/08/2026.
    """
    g = grezzo.lower()
    p = pulito.lower()
    parole_grezze = re.findall(r"[\w]+", g, flags=re.UNICODE)

    def forma_compatibile(nome):
        nome_compatto = "".join(re.findall(r"[\w]+", nome.lower(), flags=re.UNICODE))
        if not nome_compatto:
            return False
        numero_parole = max(1, len(re.findall(r"[\w]+", nome, flags=re.UNICODE)))
        for ampiezza in range(max(1, numero_parole - 2), numero_parole + 3):
            for indice in range(0, len(parole_grezze) - ampiezza + 1):
                candidato = "".join(parole_grezze[indice:indice + ampiezza])
                if SequenceMatcher(None, nome_compatto, candidato).ratio() >= 0.82:
                    return True
        return False

    for nome in glossario:
        if nome.lower() in p and nome.lower() not in g and not forma_compatibile(nome):
            return True
    return False


def pulizia_sospetta(grezzo, pulito, glossario=()):
    """La pulizia va scartata (si tiene il grezzo) se inventa nomi mai dettati
    o cambia troppo la lunghezza: togliere intercalari e ripensamenti non puo'
    cancellare un quarto del messaggio ne' aggiungerne un quarto."""
    if pulizia_inventa_nomi(grezzo, pulito, glossario):
        return True
    parole_grezzo = len(grezzo.split())
    parole_pulito = len(pulito.split())
    if parole_grezzo == 0:
        return bool(parole_pulito)
    return (
        parole_pulito * 4 < parole_grezzo * 3
        or parole_pulito * 4 > parole_grezzo * 5
    )


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
    """Passa il dettato all'agente locale e torna il testo sistemato, oppure
    None se non ce l'ha fatta (errore, output vuoto, timeout, pulizia sospetta).

    Stesso contratto di pulisci_con_shortcut: None = corsia fallita. Il
    chiamante fa sempre `testo = pulito or testo`, quindi la dettatura non si
    perde MAI; in piu' cosi' la corsia SA di aver fallito e puo' mettersi in
    pausa invece di ripresentare il conto di 20s di timeout a ogni dettatura
    (prima tornava il grezzo e il guasto risultava indistinguibile da un
    successo)."""
    try:
        esito = subprocess.run(
            comando + [prompt_pulizia(testo, glossario)],
            capture_output=True, text=True, timeout=timeout,
        )
        pulito = (esito.stdout or "").strip()
        if esito.returncode != 0 or not pulito:
            return None
        if pulizia_sospetta(testo, pulito, glossario):
            return None
        return pulito
    except Exception:
        logging.getLogger("voce").exception("pulizia con agente fallita: tengo il grezzo")
        return None


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
