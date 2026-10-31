"""Funzioni pure del tool Voce: config e interruttore voce.

Le funzioni runtime (audio, hotkey, TTS) stanno in detta.py e parla.py;
qui solo logica testabile senza hardware.
"""
import collections
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import time
import threading
from difflib import SequenceMatcher
from pathlib import Path


class CodaDettature:
    """Un messaggio resta aperto finche' tutti i suoi pezzi sono pronti.

    L'ordine nasce all'avvio, non alla fine di Whisper. Il lock di consegna
    serializza clipboard e Invio senza bloccare microfono e tastiera.
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._consegna = threading.Lock()
        self._pezzi = {}
        self._revisione = 0
        self._avvii_in_attesa = 0
        self._invio_pendente = []
        self._fallita = False
        # Esc annulla (31/10/2026): pezzi buttati, quante volte, e gruppi presi ma non ancora incollati
        self._annullati = set()
        self._annulli = 0
        self._annulli_alla_presa = 0
        self._da_incollare = 0

    def interrompi_invio(self):
        with self._lock:
            self._revisione += 1
            self._avvii_in_attesa += 1

    def annulla_avvio(self):
        with self._lock:
            self._avvii_in_attesa = max(0, self._avvii_in_attesa - 1)

    def apri(self, token):
        with self._lock:
            self.annulla_avvio()
            self._revisione += 1
            self._pezzi[token] = None

    def completa(self, token, testo="", bersaglio=None, fallita=False):
        with self._lock:
            if token in self._pezzi:
                if token in self._annullati:  # Esc: il pezzo chiude la coda ma non porta testo
                    testo, fallita = "", False
                self._pezzi[token] = (testo.strip(), bersaglio)
                self._fallita = self._fallita or fallita

    def occupata(self):
        with self._lock:
            return bool(self._pezzi) or bool(self._avvii_in_attesa)

    def aperta(self):
        """Dalla pressione del tasto (o dall'avvio delle mani libere) a quando il testo e'
        incollato: e' il tratto in cui Esc butta la dettatura. L'attesa dell'Invio no."""
        with self._lock:
            return self.occupata() or self._da_incollare > 0

    def annulla(self):
        """Esc: tutto cio' che non e' ancora incollato si butta, e nessun Invio parte.

        I pezzi aperti restano in coda e si chiudono vuoti (nessun turno resta appeso);
        quelli gia' trascritti perdono il testo. Torna False se non c'era niente da buttare."""
        with self._lock:
            if not self.aperta():
                return False
            self._annulli += 1
            for token, pezzo in self._pezzi.items():
                self._annullati.add(token)
                if pezzo is not None:
                    self._pezzi[token] = ("", pezzo[1])
            self._fallita = False
            self._invio_pendente = []
            return True

    def annullato(self, token):
        with self._lock:
            return token in self._annullati

    def segno_annulli(self):
        """Cambia a ogni Esc: chi aspetta (le mani libere) sa che la frase e' stata buttata."""
        with self._lock:
            return self._annulli

    def consegna_annullata(self):
        """True se Esc e' arrivato dopo che la consegna in corso ha preso i suoi pezzi."""
        with self._lock:
            return self._annulli != self._annulli_alla_presa

    def incollato(self):
        """Il testo di un gruppo e' nella casella (o non c'era niente da incollare)."""
        with self._lock:
            self._da_incollare = max(0, self._da_incollare - 1)

    def puo_inviare(self, revisione):
        with self._lock:
            return revisione == self._revisione and not self.occupata()

    def consegna_pronte(self, consegna, chiudi):
        with self._consegna:
            with self._lock:
                if (self._avvii_in_attesa or not self._pezzi
                        or any(p is None for p in self._pezzi.values())):
                    return
                pezzi = list(self._pezzi.items())
                self._pezzi.clear()
                revisione = -1 if self._fallita else self._revisione
                self._fallita = False
                self._annulli_alla_presa = self._annulli
                gruppi = []
                for _, (testo, bersaglio) in pezzi:
                    if not testo:
                        continue
                    if gruppi and gruppi[-1][1] == bersaglio:
                        gruppi[-1][0].append(testo)
                    else:
                        gruppi.append(([testo], bersaglio))
                # Una ripresa senza parole deve completare l'Invio gia' sospeso,
                # senza reincollare la frase precedente.
                if not gruppi and self._invio_pendente:
                    gruppi = [([], self._invio_pendente[0])]
                self._invio_pendente = []
                self._da_incollare = len(gruppi)
            try:
                for testi, bersaglio in gruppi:
                    if consegna(" ".join(testi), bersaglio, revisione):
                        with self._lock:
                            if self._annulli == self._annulli_alla_presa:  # dopo Esc niente Invio
                                self._invio_pendente = [bersaglio]
            finally:
                with self._lock:
                    self._da_incollare = 0
                    for token, _ in pezzi:
                        self._annullati.discard(token)
                for token, _ in pezzi:
                    chiudi(token)


# --- La registrazione parte dal tasto, non da quando il lavoro arriva (30/10/2026) ---
# Sal, 30/10/2026: «quando io ho detto, poi mollo, poi riapro il microfono, la seconda
# dettatura non parte, si è fermata, si è bloccata». Caso 14:12:28: Sal riapre mentre
# Whisper lavora sulla frase prima; l'avvio arriva tardi (zittire la voce, due pkill, costa
# 0,18 s di mediana e fino a 0,35 s con Whisper al lavoro, 0,06 s da fermo) e l'anello di
# pre-registrazione, che doveva coprire quel ritardo, teneva 0,03 s: era `deque(maxlen=32)`
# pensato come «~1 s», ma lo stream consegna blocchi di 15 campioni (1.030 al secondo,
# misura del 30/10/2026). Nel
# wav di 1,5 s restava «…delle risorse», Whisper ha risposto «Grazie.». Misurato in
# secondi l'anello vale con qualunque blocco, e l'inizio si calcola dalla pressione.
# Blocco fisso dello stream (30/10/2026, Sal: «perché non possiamo risolverlo adesso?»).
# Di serie lo stream consegnava 15 campioni: il callback Python girava 1.030 volte al
# secondo e, con un altro thread sul GIL, i blocchi si perdevano senza alcun avviso (le
# dettature lunghe uscivano fino a 0,33 s piu' corte). Misura sull'hardware, 10 s per giro:
# carico Whisper -1,56% di serie, 0% a 30 ms; thread Python occupato -84% di serie, -33% a
# 10 ms, -1% a 20 ms, 0% a 30 ms; nessun overflow o underflow in nessun giro.
BLOCCO_AUDIO_SEC = 0.03          # 480 campioni a 16 kHz, 33 callback al secondo
BARRA_SEC = 0.001                # ogni lineetta della pill: 1 ms di voce, come la vede Sal
PRE_REGISTRAZIONE_SEC = 2.0      # audio tenuto fuori registrazione: copre un avvio in ritardo
ANTICIPO_TASTO_SEC = 0.3         # col tasto: anche l'attimo prima, Sal parla mentre preme
ANTICIPO_MANI_LIBERE_SEC = 0.5   # mani libere: il volume scatta quando Sal parla gia' da 0,2 s;
# resta sotto la pausa di 0,7 s che le mani libere aspettano dopo la voce dell'agente


class AnelloAudio:
    """Gli ultimi secondi di microfono fuori registrazione, con l'istante (monotonic)
    di arrivo di ogni blocco. Due thread: il callback audio aggiunge, il worker preleva.
    Nessun metodo solleva: un errore nel callback spegnerebbe il microfono."""

    def __init__(self, durata_sec=PRE_REGISTRAZIONE_SEC):
        self.durata = float(durata_sec)
        self._blocchi = collections.deque()

    def aggiungi(self, istante, blocco, volume):
        self._blocchi.append((istante, blocco, volume))
        limite = istante - self.durata
        try:
            while self._blocchi[0][0] < limite:
                self._blocchi.popleft()
        except IndexError:  # svuotato dal worker proprio adesso: niente da potare
            pass

    def svuota(self):
        self._blocchi.clear()

    def preleva(self, dal):
        """Blocchi e volumi arrivati da `dal` in poi; l'anello resta vuoto."""
        copia = []
        for _ in range(3):
            try:
                copia = list(self._blocchi)  # copiata in C: il callback non la cambia a meta'
                break
            except RuntimeError:  # deque mutata durante la copia: si riprova
                continue
        self._blocchi.clear()
        presi = [voce for voce in copia if voce[0] >= dal]
        return [b for _, b, _ in presi], [v for _, _, v in presi]


def volumi_barre(blocco, freq=16000, barra_sec=BARRA_SEC):
    """Volume (RMS) di ogni pezzetto da `barra_sec` del blocco, per le lineette della pill.

    Le lineette disegnano gli ultimi 18 valori: con un valore per blocco l'aspetto
    dipenderebbe dalla misura del blocco (15 campioni: 18 ms; 30 ms: mezzo secondo).
    A pezzetti di tempo restano quelle di sempre con qualunque blocco."""
    import numpy as np  # import pigro: l'hook TTS usa voce_lib senza numpy
    a = np.asarray(blocco, dtype="float32").reshape(-1)
    passo = max(1, round(freq * barra_sec))
    n = len(a) // passo * passo
    if n == 0:
        return [float(np.sqrt(np.mean(a * a)))] if a.size else []
    pezzi = a[:n].reshape(-1, passo)
    return np.sqrt(np.mean(pezzi * pezzi, axis=1)).tolist()


def inizio_pre_registrazione(ora, pressione=None, voce_zittita=None,
                             anticipo_tasto=ANTICIPO_TASTO_SEC,
                             anticipo_mani_libere=ANTICIPO_MANI_LIBERE_SEC):
    """Da quale istante la registrazione prende l'audio gia' arrivato nell'anello.

    Col tasto conta la pressione, non il momento in cui l'avvio arriva: un worker in
    ritardo non taglia piu' l'inizio della frase. Senza tasto (mani libere) si parte da
    poco prima di adesso. Se l'agente stava leggendo ad alta voce, nulla prima dello
    stop della sua voce: e' la sua lettura nelle casse, non la voce di Sal."""
    inizio = ora - anticipo_mani_libere if pressione is None else pressione - anticipo_tasto
    if voce_zittita is not None:
        inizio = max(inizio, voce_zittita)
    return inizio


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
FLAG_MASCOTTE_ON = BASE / "MASCOTTE_ON"  # esiste quando la mascotte (se configurata) deve vedersi
FILE_CASELLE_RICORDATE = BASE / "caselle_ricordate.json"  # dove stava la casella, per app e finestra
FLAG_TURNO_UTENTE = BASE / "TURNO_UTENTE"  # dalla prima parola fino all'Invio automatico


def apri_turno_utente():
    """Segnala agli hook esterni che Sal sta ancora completando il suo turno.

    Il token impedisce a una vecchia trascrizione, finita in ritardo, di
    cancellare il flag di una dettatura piu' nuova gia' iniziata.
    """
    token = f"{os.getpid()}:{time.monotonic_ns()}"
    FLAG_TURNO_UTENTE.write_text(token, encoding="utf-8")
    return token


def chiudi_turno_utente(token):
    """Chiude soltanto il turno che aveva creato *token*."""
    if not token:
        return
    try:
        if FLAG_TURNO_UTENTE.read_text(encoding="utf-8").strip() == token:
            FLAG_TURNO_UTENTE.unlink(missing_ok=True)
    except OSError:
        pass


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


def config_locale():
    """Solo le scelte personali di config.local.json ({} se il file non c'e').

    Serve a sapere cosa la persona ha scritto davvero, senza i valori del prodotto."""
    try:
        with open(CONFIG_LOCAL, encoding="utf-8") as f:
            locali = json.load(f)
    except FileNotFoundError:
        return {}
    return locali if isinstance(locali, dict) else {}


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


def mascotte_attiva():
    """La mascotte si vede solo se esiste il file flag MASCOTTE_ON (`voce grinch on`)."""
    return FLAG_MASCOTTE_ON.exists()


def timeout_scaduto(attivo, inizio, ora, limite_sec):
    """True se un'operazione attiva dura oltre il limite indicato."""
    return bool(attivo and inizio is not None and (ora - inizio) > limite_sec)


class TenutaGesto:
    """Un gesto che conta solo se TENUTO: un tocco, anche ripetuto, non scatta.

    P-085 (23/09/2026): Option + freccia sinistra accendeva la voce al primo
    tocco, ma e' anche il «vai alla parola prima» di ogni campo di testo: chi
    correggeva una frase la accendeva senza saperlo, durante una call. Il
    chiamante interroga lo stato del gesto a intervalli regolari
    (`aggiorna(giu, ora)`); torna True UNA volta, appena il gesto e' stato
    giu' per `durata_sec` di fila. Un rilascio, anche di un solo campione,
    azzera il conto; un nuovo gesto tenuto puo' scattare di nuovo."""

    def __init__(self, durata_sec):
        self.durata = float(durata_sec)
        self._inizio = None
        self._scattato = False

    def aggiorna(self, giu, ora):
        if not giu:
            self._inizio = None
            self._scattato = False
            return False
        if self._inizio is None:
            self._inizio = ora
        if not self._scattato and ora - self._inizio >= self.durata - 1e-9:  # 1e-9: gli errori dei decimali
            self._scattato = True
            return True
        return False


def stop_anti_incanto(registrando, inizio, ora, tasto_giu, tetto_soft, tetto_duro):
    """Decide se l'airbag anti-incanto deve fermare la registrazione.

    Caso reale 04/09 06:41: Sal dettava da 90s col tasto ancora premuto e il
    tetto a tempo gli ha tagliato la frase (159 parole). Il tetto "soft"
    (tetto_soft, 90s) serve contro il rilascio perso da pynput: ha senso SOLO
    se il tasto-detta NON e' piu' fisicamente giu'. Se e' giu' l'utente sta
    dettando davvero e non si ferma. Resta un tetto DURO (tetto_duro, 300s)
    che ferma comunque, per il tasto incastrato. Nel VAD mani-libere il tasto
    non c'entra: si passa tasto_giu=False e vale il solo tetto soft come prima.
    """
    if not registrando or inizio is None:
        return False
    durata = ora - inizio
    if durata > tetto_duro:
        return True
    return durata > tetto_soft and not tasto_giu


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
    return not 0.0 <= rms <= massimo  # anche NaN e infinito sono audio non valido


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

# Le formule con cui finiscono i video di YouTube, su cui Whisper si e'
# allenato: su un audio che non sa leggere (o col prompt del glossario) le
# inventa, e non sempre uguali. Il 28/09/2026 (P-117) 12 secondi di parlato
# vero sono usciti come «Grazie a tutti per aver guardato il video, vi
# ringrazio per avermi seguito, e vi ringrazio per avermi seguito.»: l'elenco
# sopra confronta solo la stringa INTERA, quella era appena piu' lunga, e
# l'invio automatico l'ha mandata in chat. Il confronto per pezzi: un testo
# fatto SOLO di queste formule (le voci dell'elenco, le cortesie qui sotto e
# i riferimenti al video, uniti da "e") e' un fantasma se parla del video o se
# ripete in ciclo (3 volte) la stessa frase nota. Una frase vera che le contiene ha
# sempre altre parole in mezzo, e resta.
_RIFERIMENTI_AL_VIDEO = (
    "per aver guardato il video", "per aver guardato questo video",
    "per aver visto il video", "per aver visto questo video",
    "per la visione", "per avermi seguito", "per averci seguito",
    "per avermi ascoltato", "per averci ascoltato",
    "al prossimo video", "nel prossimo video",
    "iscriviti al canale", "iscrivetevi al canale",
    "attiva la campanella", "attivate la campanella",
    "lascia un like", "lasciate un like", "mettete un like",
)
_CORTESIE_DI_CHIUSURA = (
    "grazie mille", "grazie tante", "vi ringrazio", "ti ringrazio",
    "ringrazio tutti", "ringrazio", "ci vediamo presto", "ci vediamo",
    "a presto", "alla prossima", "arrivederci", "buona visione",
    "buona giornata", "buona serata", "ciao",
)
_CONNETTIVI_DI_CHIUSURA = {"e", "ed"}
_RE_FORMULE_DI_CHIUSURA = re.compile(
    r"(?<!\w)(?:"
    + "|".join(
        re.escape(f) for f in sorted(
            _FRASI_FANTASMA | set(_RIFERIMENTI_AL_VIDEO) | set(_CORTESIE_DI_CHIUSURA),
            key=len, reverse=True,
        )
    )
    + r")(?!\w)"
)


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


def _solo_formule_di_chiusura(n):
    """True se il testo normalizzato `n` e' fatto soltanto di formule di
    chiusura da video (vedi sopra) e parla del video o ripete in ciclo una
    frase nota. Basta una parola qualsiasi fuori dalle formule per dire no:
    «Grazie a tutti per aver guardato il video che ti ho mandato» e' una frase
    vera, «Grazie mille, a presto» sono solo cortesie."""
    tessere = []
    fine = 0
    for m in _RE_FORMULE_DI_CHIUSURA.finditer(n):
        if any(p not in _CONNETTIVI_DI_CHIUSURA for p in n[fine:m.start()].split()):
            return False
        tessere.append(m.group(0))
        fine = m.end()
    if not tessere or any(p not in _CONNETTIVI_DI_CHIUSURA for p in n[fine:].split()):
        return False
    if any(t in _RIFERIMENTI_AL_VIDEO for t in tessere):
        return True
    # un ciclo: la stessa frase nota almeno tre volte («Grazie, grazie!» e'
    # una persona che ringrazia, non un collasso di Whisper)
    ciclo = max(tessere.count(t) for t in set(tessere)) >= 3
    return ciclo and all(t in _FRASI_FANTASMA for t in tessere)


def e_allucinazione(testo):
    """True se il testo e' una frase-fantasma tipica di Whisper sul non-parlato,
    una loro combinazione (vedi _solo_formule_di_chiusura) o un collasso a
    ripetizione (vedi _ripetizione_patologica).

    Una frase vera che contiene 'grazie' (es. 'Grazie mille per la
    proposta…') non viene scartata: il testo dev'essere fatto solo di formule.
    """
    n = _normalizza(testo)
    if not n:
        return True
    if n in _FRASI_FANTASMA:
        return True
    if "sottotitoli" in n and ("a cura di" in n or "creati dalla comunit" in n):
        return True
    if _solo_formule_di_chiusura(n):
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


def casella_ammissibile(y_casella, altezza_casella, y_finestra, altezza_finestra,
                        quota=0.4, quota_documento=0.5):
    """True se nella casella si puo' scrivere senza fare danni: o sta nella
    parte bassa della finestra (le chat), o e' ALTA almeno meta' finestra
    (l'area documento di Note/TextEdit/Word, che parte dall'alto).

    Le barre degli indirizzi e i campi di ricerca sono in alto E bassi di
    statura: restano fuori da entrambe le porte. Richiesta 30/08/2026 ("giro
    pagina e deve capire da solo dove scrivere"): prima un documento aperto
    veniva rifiutato in blocco perche' parte dall'alto."""
    if in_zona_scrittura(y_casella, y_finestra, altezza_finestra, quota):
        return True
    return altezza_casella >= altezza_finestra * quota_documento


def cornice_reale(geo_finestra, geometrie_pezzi):
    """Il rettangolo che la finestra occupa DAVVERO: l'unione di quello che
    dichiara con quelli dei suoi pezzi.

    Chrome dichiara la finestra 122 punti piu' in basso e piu' bassa di
    com'e' (misurato 08/09/2026: finestra dichiarata y=-958 alta 958, barra
    degli indirizzi a y=-1028): la fascia di scrittura calcolata su quel
    rettangolo parte 73 punti troppo in basso e le caselle vere vengono
    scartate. Le geometrie sono (x, y, larghezza, altezza)."""
    x, y, larghezza, altezza = geo_finestra
    su, giu = y, y + altezza
    sinistra, destra = x, x + larghezza
    for gx, gy, gl, ga in geometrie_pezzi:
        su, giu = min(su, gy), max(giu, gy + ga)
        sinistra, destra = min(sinistra, gx), max(destra, gx + gl)
    return sinistra, su, destra - sinistra, giu - su


def finestra_credibile(geometria, altezza_schermo_max, altezza_minima=200):
    """False per le finestre dove Sal non sta dettando di sicuro.

    Due trappole viste dal vero (08/09/2026): Claude espone come prima
    finestra una striscia alta 33 punti (AXUnknown) e il Finder espone la
    SCRIVANIA, alta 2062 punti perche' copre tutti i monitor. Prese come
    bersaglio non contengono nessuna casella e la dettatura finisce nel
    vuoto. Una finestra vera sta fra le due misure."""
    if geometria is None:
        return False
    altezza = geometria[3]
    if altezza < altezza_minima:
        return False
    return altezza <= altezza_schermo_max + 1


def schermo_del_punto(punto, schermi):
    """Indice del monitor (x, y, larghezza, altezza) che contiene il punto,
    o None se il punto non sta in nessuno o i monitor non si conoscono."""
    if punto is None or not schermi:
        return None
    px, py = punto
    for indice, (x, y, larghezza, altezza) in enumerate(schermi):
        if x <= px <= x + larghezza and y <= py <= y + altezza:
            return indice
    return None


def schermo_della_finestra(geometria, schermi):
    """Il monitor dove sta il centro della finestra, o None."""
    if geometria is None:
        return None
    x, y, larghezza, altezza = geometria
    return schermo_del_punto((x + larghezza / 2, y + altezza / 2), schermi)


def finestra_su_altro_schermo(geometria, punto_mouse, schermi):
    """True quando la finestra sta su un monitor diverso da quello del mouse,
    e tutti e due i monitor si conoscono. Con un monitor solo, o con dati
    illeggibili, e' sempre False: il mouse non diventa mai una condizione."""
    if not schermi or len(schermi) < 2:
        return False
    del_mouse = schermo_del_punto(punto_mouse, schermi)
    della_finestra = schermo_della_finestra(geometria, schermi)
    return del_mouse is not None and della_finestra is not None and del_mouse != della_finestra


def app_sul_monitor(finestre, pid_davanti, monitor, schermi, pid_proprio=None):
    """Il pid dell'app da usare come bersaglio quando l'app davanti non ha
    nessuna finestra sul monitor del mouse (dove sta la pill) e un'altra app
    ce l'ha: la finestra piu' avanti su quel monitor decide. `finestre` e'
    [(pid, geometria)] dalla piu' avanti alla piu' indietro. None quando
    l'app davanti sta gia' su quel monitor, o di la' non c'e' niente: allora
    il bersaglio resta l'app davanti, come con un monitor solo."""
    if monitor is None:
        return None
    sul_monitor = [
        pid for pid, geometria in finestre
        if pid != pid_proprio and schermo_della_finestra(geometria, schermi) == monitor
    ]
    if not sul_monitor or pid_davanti in sul_monitor:
        return None
    return sul_monitor[0]


def app_ha_finestra_sul_monitor(finestre, pid, monitor, schermi):
    """True se l'app `pid` ha almeno una finestra visibile sul monitor dato.
    Con monitor sconosciuto (None) torna True: senza dati non si blocca niente."""
    if monitor is None:
        return True
    return any(
        p == pid and schermo_della_finestra(geometria, schermi) == monitor
        for p, geometria in finestre
    )


def ordina_finestre(geometrie, punto_mouse=None, schermi=None):
    """Indici delle finestre nell'ordine in cui provarle.

    L'ordine di partenza resta quello dell'app (focalizzata, principale,
    poi le altre). Il mouse serve solo come spareggio: se sta dentro una di
    queste finestre, quella si prova per prima; poi vengono le finestre sul
    suo stesso monitor, poi le altre. Sal deve poter dettare anche con il
    mouse fermo altrove (08/09/2026), quindi il mouse non e' mai una
    condizione: sposta soltanto la precedenza. Con due monitor (Samsung,
    20/09/2026) la pill sta sul monitor del mouse e il testo deve arrivare
    li', non nella finestra rimasta sul monitor piccolo."""
    ordine = list(range(len(geometrie)))
    if punto_mouse is None:
        return ordine
    mx, my = punto_mouse
    def sotto_il_mouse(i):
        x, y, larghezza, altezza = geometrie[i]
        return x <= mx <= x + larghezza and y <= my <= y + altezza
    def su_altro_monitor(i):
        return finestra_su_altro_schermo(geometrie[i], punto_mouse, schermi)
    return sorted(ordine, key=lambda i: (not sotto_il_mouse(i), su_altro_monitor(i), i))


def chiave_casella(nome_app, geo_finestra):
    """Chiave della memoria delle caselle: stessa app e stessa taglia di
    finestra. Un'altra taglia (altra vista, altro monitor) ha la sua memoria."""
    if not nome_app or not geo_finestra:
        return None
    return (str(nome_app), int(round(geo_finestra[2])), int(round(geo_finestra[3])))


def posizione_relativa(geo_finestra, geo_casella):
    """Il punto di click dentro la casella, riferito alla finestra: frazione
    della larghezza e distanza dal bordo in basso. Il punto sta vicino al
    bordo sinistro e al fondo della casella: la casella delle chat e'
    ancorata in basso e, se si apre un pannello a fianco o il testo cresce su
    piu' righe, quel punto resta dentro. Geometrie (x, y, larghezza, altezza)
    con y verso il basso. None se finestra o casella non hanno taglia."""
    fx, fy, fl, fa = geo_finestra
    cx, cy, cl, ca = geo_casella
    if fl <= 0 or fa <= 0 or cl <= 0 or ca <= 0:
        return None
    x = cx + min(40, cl / 4)
    y = cy + ca - min(20, ca / 2)
    return ((x - fx) / fl, (fy + fa) - y)


def punto_da_relativa(geo_finestra, relativa):
    """Il punto assoluto dove cliccare, o None se cade fuori dalla finestra."""
    fx, fy, fl, fa = geo_finestra
    frazione, dal_fondo = relativa
    x = fx + frazione * fl
    y = fy + fa - dal_fondo
    if not (fx <= x <= fx + fl and fy <= y <= fy + fa):
        return None
    return (x, y)


def caselle_in_json(caselle):
    """La memoria delle caselle in testo JSON: chiavi "app|larghezza|altezza",
    valori [frazione, distanza dal fondo]. Sopravvive ai riavvii dell'app."""
    return json.dumps(
        {"|".join(str(p) for p in chiave): list(relativa) for chiave, relativa in caselle.items()},
        ensure_ascii=False, sort_keys=True,
    )


def caselle_da_json(testo):
    """La memoria delle caselle da testo JSON; testo rotto o vuoto = memoria vuota."""
    try:
        grezzo = json.loads(testo or "{}")
    except (ValueError, TypeError):
        return {}
    caselle = {}
    for chiave, relativa in (grezzo.items() if isinstance(grezzo, dict) else []):
        parti = str(chiave).rsplit("|", 2)
        if len(parti) != 3 or not isinstance(relativa, (list, tuple)) or len(relativa) != 2:
            continue
        try:
            caselle[(parti[0], int(parti[1]), int(parti[2]))] = (float(relativa[0]), float(relativa[1]))
        except (TypeError, ValueError):
            continue
    return caselle


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
    e brand (LeaderAI, Systeme.io, nomi clienti) escono scritti giusti.

    Solo l'elenco dei nomi, senza etichetta. Whisper legge il prompt come il
    testo detto subito prima: «Glossario:» davanti lo faceva sembrare un
    documento, non un parlato, e il motore large-v3 saltava parole e
    punteggiatura, oltre a ricopiare «Glossario» in testa (29/08) e a produrre
    frasi-fantasma (P-117). Banco del 11/10/2026 su 30 dettature vere: stesso
    glossario allargato, 35 parole sbagliate su 800 con l'etichetta, 18 senza."""
    voci = [v for v in cfg.get("glossario", []) if v.strip()]
    if not voci:
        return None
    return ", ".join(voci) + "."


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


# --- trascrizione progressiva (04/09/2026) ---
# Dati reali 27/08→04/09: 1.422 dettature, 517 oltre i 30s, 181 oltre i 60s.
# Whisper partiva solo al rilascio del tasto: 90s di parlato = 17s di attesa
# prima dell'incolla. Qui la logica pura (dove tagliare, come rincollare,
# cosa dire a Whisper del pezzo prima); il runtime (thread, lock) sta in
# detta.py. Windows replica queste funzioni nel suo unico file.

SILENZIO_PROGRESSIVO_SEC = 0.5   # pausa minima continua su cui e' lecito tagliare
BLOCCO_PROGRESSIVO_SEC = 12.0    # durata minima del segmento prima di cercare un taglio
# Soglia di "silenzio" tra due parole: sopra il rumore di stanza a guadagno
# giusto (0.006-0.0074, misure 01/08) e sotto il parlato piano di Sal
# (0.012-0.015). Con la pausa di 0,5s obbligatoria, spezzare una parola
# richiederebbe mezzo secondo di voce sotto questa soglia: non succede.
SOGLIA_SILENZIO_PROGRESSIVA = 0.010
CONTESTO_PROGRESSIVO_CARATTERI = 200


def trova_taglio(rms, campioni, inizio, freq=16000, soglia=SOGLIA_SILENZIO_PROGRESSIVA,
                 silenzio_min_sec=SILENZIO_PROGRESSIVO_SEC,
                 blocco_min_sec=BLOCCO_PROGRESSIVO_SEC):
    """Indice (escluso) del blocco audio dove chiudere il segmento aperto da
    `inizio`, oppure None se un punto sicuro non c'e' ancora.

    rms[i] e campioni[i] sono volume e numero di campioni del blocco i, cosi'
    come li consegna il callback audio. Si taglia SOLO alla fine di un
    silenzio continuo di almeno silenzio_min_sec (ogni blocco sotto soglia)
    e SOLO se il segmento chiuso durerebbe almeno blocco_min_sec: dentro un
    silenzio non c'e' nessuna parola da spezzare. Il resto della pausa, se
    piu' lunga, resta in testa al segmento successivo (Whisper la ignora)."""
    n = min(len(rms), len(campioni))
    durata = 0.0
    silenzio = 0.0
    for i in range(max(0, inizio), n):
        d = campioni[i] / float(freq)
        durata += d
        if rms[i] < soglia:
            silenzio += d
            if silenzio >= silenzio_min_sec and durata >= blocco_min_sec:
                return i + 1
        else:
            silenzio = 0.0
    return None


_FINE_FRASE = ".!?…"
_SEGNI = _FINE_FRASE + ",;:"


def unisci_segmenti(pezzi, glossario=()):
    """Rincolla i testi dei segmenti trascritti uno alla volta in un testo
    solo: spazi singoli, mai due segni di punteggiatura attaccati, maiuscola
    dopo un punto. Se il pezzo prima finiva a meta' frase (nessun segno, o
    una virgola) e quello dopo parte con l'iniziale maiuscola che Whisper
    mette sempre in testa, l'iniziale torna minuscola — tranne i nomi del
    glossario e le sigle, che non si toccano."""
    # nomi a piu' parole ("Claude Code"): conta la prima parola
    protetti = {v.split()[0].lower() for v in glossario if v and v.strip()}
    testo = ""
    for pezzo in pezzi:
        p = " ".join((pezzo or "").split())
        if not p:
            continue
        if not testo:
            testo = p
            continue
        ultimo = testo[-1]
        if ultimo in _SEGNI:
            p = p.lstrip(_SEGNI + " ")
            if not p:
                continue
        if p[0] in _SEGNI:  # ", e poi" dopo una parola nuda: si attacca
            testo += p
            continue
        prima = p.split(" ", 1)[0]
        if ultimo in _FINE_FRASE:
            p = p[0].upper() + p[1:]
        elif (p[0].isupper() and not prima.isupper()
              and prima.strip(_SEGNI).lower() not in protetti):
            p = p[0].lower() + p[1:]
        testo += " " + p
    return testo


def prompt_con_contesto(glossario_prompt, precedente, max_caratteri=CONTESTO_PROGRESSIVO_CARATTERI):
    """initial_prompt di Whisper per un segmento: il glossario di sempre piu'
    la coda del testo del segmento prima (ultimi ~max_caratteri, tagliati a
    inizio parola), cosi' nomi e punteggiatura restano coerenti da un pezzo
    all'altro. Senza glossario ne' testo prima torna None (come oggi)."""
    coda = " ".join((precedente or "").split())
    if len(coda) > max_caratteri:
        coda = coda[-max_caratteri:]
        spazio = coda.find(" ")
        if 0 <= spazio < len(coda) - 1:
            coda = coda[spazio + 1:]
    parti = [p for p in (glossario_prompt, coda) if p]
    return " ".join(parti) or None


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


BROWSER_CHROMIUM = (
    "com.google.chrome", "org.chromium.chromium", "com.brave.browser",
    "com.microsoft.edgemac", "company.thebrowser.browser", "com.vivaldi.vivaldi", "com.operasoftware.opera",
)


def e_browser_chromium(bundle_id):
    """True per i browser della famiglia Chrome: espongono la pagina ad
    Accessibility solo se un programma chiede l'interfaccia estesa
    (AXEnhancedUserInterface). Misurato 20/09/2026 su ChatGPT in Chrome:
    senza richiesta 286 elementi e nessuna area web, con richiesta la
    casella «Chatta con ChatGPT» dopo circa 2 secondi."""
    bundle = str(bundle_id or "").strip().lower()
    return any(bundle == b or bundle.startswith(b + ".") for b in BROWSER_CHROMIUM)


_SU_CHROMIUM = {}


def app_su_chromium(percorso_app):
    """True per le app costruite su Chromium, riconosciute dal gestore dei crash
    di Chromium dentro il pacchetto: i browser della famiglia Chrome, le app
    Electron e app come ChatGPT per Mac (23/09/2026: senza richiesta mostrava 8
    elementi e nessuna casella). Il risultato resta in memoria per app."""
    if not percorso_app:
        return False
    if percorso_app not in _SU_CHROMIUM:
        cornici = Path(percorso_app) / "Contents" / "Frameworks"
        try:
            _SU_CHROMIUM[percorso_app] = any(cornici.glob("*.framework/Versions/*/Helpers/*crashpad_handler*"))
        except OSError:
            _SU_CHROMIUM[percorso_app] = False
    return _SU_CHROMIUM[percorso_app]


def destinazione_agente(nome_app="", url=""):
    """True quando il testo e' destinato a una chat con un agente AI.

    In queste chat il grezzo di Whisper e' gia' l'input migliore: arriva
    subito e l'agente capisce esitazioni e ripensamenti senza affidare il
    significato a un secondo modello di pulizia.
    """
    nome = str(nome_app or "").strip().lower()
    indirizzo = str(url or "").strip().lower()
    if any(marcatore in nome for marcatore in ("chatgpt", "claude", "codex", "antigravity", "gemini")):
        return True
    return any(
        dominio in indirizzo
        for dominio in ("chatgpt.com", "chat.openai.com", "claude.ai", "gemini.google.com")
    )


def invio_di_sal_durante_incolla(ultimo_tasto, tasto_invio, ultima_pressione, riferimento, fine_incolla):
    """True se l'ultimo gesto di Sal e' un Invio premuto MENTRE il testo stava
    comparendo (dopo `riferimento`, entro la fine dell'incolla).

    Sal, 30/10/2026: «vedo che succede qualcosa e non invia, mi rimane la chat
    aperta». Quell'Invio cadeva su una casella ancora vuota, poi la frase
    atterrava e l'Invio automatico si annullava per «Invio premuto a mano»
    (72 casi in una settimana, a 0-1 ms dall'incolla). E' un si': si manda.
    Un altro tasto o un clic dopo restano un annullamento (l'ultimo gesto vince)."""
    if ultimo_tasto != tasto_invio or ultimo_tasto is None:
        return False
    return riferimento < ultima_pressione <= fine_incolla


def ritardo_invio(cfg, voce_accesa, chat_ai):
    """Secondi di pausa prima dell'Invio automatico, scelti dal contesto.

    - voce agenti accesa: botta e risposta con l'agente
      (`invio_automatico_ritardo_conversazione_sec`);
    - chat AI a voce spenta: il testo si vede e non c'e' nulla da rileggere
      (`invio_automatico_ritardo_chat_ai_sec`, default 2.0). Dati reali
      30/08→04/09: con la pausa dei documenti il 40% degli Invii automatici
      veniva annullato da Sal che premeva Invio a mano prima dell'app; con
      un secondo solo (04/09→17/09) Sal non faceva in tempo a bloccare
      l'Invio con uno spazio per correggere (caso 17/09 14:18): due secondi;
    - documenti, email, social: serve tempo per correggere
      (`invio_automatico_ritardo_sec`, default 2.5).
    """
    if voce_accesa:
        return float(cfg.get("invio_automatico_ritardo_conversazione_sec", 0.3))
    if chat_ai:
        return float(cfg.get("invio_automatico_ritardo_chat_ai_sec", 2.0))
    return float(cfg.get("invio_automatico_ritardo_sec", 2.5))


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


def comandi_agente():
    """TUTTI gli agenti gia' presenti sul PC, in ordine di preferenza: Claude
    Code, poi Codex. L'app non impone un agente: usa quello che il
    proprietario ha (regola di Sal 04/09/2026: i clienti hanno Claude o
    ChatGPT/Codex, non per forza entrambi). Chi chiama prova la lista in
    ordine e si ferma al primo che risponde (vedi chiedi_arbitro): se il primo
    e' installato ma rotto (sessione scaduta, CLI vecchia) si passa al
    secondo. Nessuno installato -> lista vuota.

    Avvio "spoglio" di Claude (misurato: ~2-3s in meno a chiamata): niente
    MCP, tool, settings ne' sessione salvata su disco."""
    comandi = []
    if shutil.which("claude"):
        comandi.append([
            "claude", "--model", "haiku", "-p",
            "--tools", "",              # nessun tool built-in
            "--strict-mcp-config",      # senza --mcp-config = zero server MCP
            "--setting-sources", "",    # niente settings utente/progetto
            "--no-session-persistence", # niente sessione salvata su disco
        ])
    if shutil.which("codex"):
        comandi.append(["codex", "exec", "--skip-git-repo-check"])
    return comandi


def comando_agente(_quale=None):
    """Il primo agente disponibile (compatibilita': la corsia di pulizia
    interattiva ne usa uno solo). None se non ce n'e'."""
    comandi = comandi_agente()
    return comandi[0] if comandi else None


def _catena_arbitri(comando):
    """Accetta un comando solo (lista di stringhe) o una lista di comandi;
    torna sempre una lista di comandi."""
    if not comando:
        return []
    if isinstance(comando[0], str):
        return [list(comando)]
    return [list(c) for c in comando if c]


def chiedi_arbitro(comando, prompt, timeout=60):
    """Passa il prompt agli agenti locali in ordine e torna (proposte, errore)
    del PRIMO che risponde. Prima l'arbitro era uno solo: Claude installato
    ma con la sessione scaduta significava zero apprendimento ogni notte
    anche con Codex a portata di mano (caso reale 04/09/2026: 5 notti a
    vuoto). errore=None = risposta valida; altrimenti riassume il guasto di
    ogni agente provato, cosi' il registro dice CHI ha fallito e perche'."""
    errori = []
    for cmd in _catena_arbitri(comando):
        try:
            esito = subprocess.run(
                cmd + [prompt], capture_output=True, text=True, timeout=timeout,
            )
        except Exception as exc:
            errori.append(f"{cmd[0]}: {type(exc).__name__}: {exc}")
            continue
        proposte, errore = risposta_arbitro(esito.returncode, esito.stdout, esito.stderr)
        if errore is None:
            return proposte, None
        errori.append(f"{cmd[0]}: {errore}")
    return {}, ("; ".join(errori) if errori else "nessun agente locale installato")


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
    """Filtra la forma delle proposte, senza certificarne il significato.
    Una coppia valida resta da verificare: non e' una correzione attiva."""
    buone = {}
    for sbagliato, giusto in nuove.items():
        if not isinstance(sbagliato, str) or not isinstance(giusto, str):
            continue
        sbagliato, giusto = sbagliato.strip(), giusto.strip()
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


def risposta_arbitro(returncode, stdout, stderr=""):
    """(proposte, errore) dalla risposta dell'agente locale. Proposte solo se
    l'agente ha risposto davvero; altrimenti l'errore reale da mettere nel
    registro. Caso vero del 04/09/2026: la CLI con la sessione OAuth scaduta
    esce con codice 1 e stampa `Failed to authenticate: ...` su stdout; prima
    quel testo passava per una risposta senza coppie e nel registro finiva
    "nessuna correzione sicura", cinque notti su cinque."""
    stdout = (stdout or "").strip()
    stderr = (stderr or "").strip()
    if returncode != 0:
        return {}, f"agente uscito con codice {returncode}: {(stdout or stderr)[:200]}"
    if "{" not in stdout:
        return {}, f"agente senza JSON: {(stdout or stderr or 'risposta vuota')[:200]}"
    return estrai_json(stdout), None


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
    """Propone correzioni nel registro esistente, senza modificare il config.
    Il dettato non mostra le correzioni reali del proprietario: l'arbitro
    formula ipotesi. Anche le coppie restituite sono solo proposte."""
    grezzi = estrai_grezzi_dal_log(log_path)
    if not grezzi:
        return {}
    try:
        proposte, errore = chiedi_arbitro(comando, prompt_apprendimento(grezzi), timeout)
        if errore:
            logging.getLogger("voce").warning(
                "apprendimento sostituzioni: agente fallito (%s)", errore)
            return {}
        with open(config_path, encoding="utf-8") as f:
            cfg = json.load(f)
        nuove = unisci_sostituzioni(cfg.get("sostituzioni", {}), proposte)
        if nuove:
            logging.getLogger("voce").info(
                "apprendimento sostituzioni: proposte da verificare, non applicate: %s",
                json.dumps(nuove, ensure_ascii=False),
            )
        return nuove
    except Exception:
        logging.getLogger("voce").exception("apprendimento sostituzioni fallito")
        return {}


# --- ripasso notturno: riascolta gli audio conservati e propone correzioni ---
# Mandato di Sal 30/08/2026 ("piu' la uso, piu' deve capirmi"): una volta al
# giorno un secondo riconoscitore ritrascrive con calma le dettature
# conservate; dove i due non sono d'accordo l'agente propone. Dal 05/09 le
# ipotesi restano nel registro: la concordanza non autorizza regole globali.

def estrai_grezzi_con_orario(righe):
    """[(orario, testo)] dalle righe di registro 'INFO grezzo: ...'."""
    import datetime as dt
    esiti = []
    for r in righe:
        if "INFO grezzo: " not in r:
            continue
        try:
            quando = dt.datetime.strptime(r[:19], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
        esiti.append((quando, r.split("INFO grezzo: ", 1)[1]))
    return esiti


def abbina_audio_a_grezzo(nome_wav, grezzi, tolleranza_sec=15):
    """Il testo scritto in diretta per quell'audio: il WAV porta nel nome
    l'orario del salvataggio e il grezzo compare nel registro pochi istanti
    dopo. None se nel registro non c'e' (log ruotato, debug spento)."""
    import datetime as dt
    m = re.match(r"dettatura_(\d{8}_\d{6})", nome_wav)
    if not m:
        return None
    quando = dt.datetime.strptime(m.group(1), "%Y%m%d_%H%M%S")
    migliore, distanza = None, tolleranza_sec + 1
    for orario, testo in grezzi:
        delta = (orario - quando).total_seconds()
        if 0 <= delta <= tolleranza_sec and delta < distanza:
            migliore, distanza = testo, delta
    return migliore


def disaccordi_parole(vivo, ripasso, massimo_parole=2):
    """Punti dove le due trascrizioni dello stesso audio non sono d'accordo:
    coppie (versione_live, versione_ripasso). Solo scambi corti di parole;
    differenze di sola punteggiatura o maiuscole non contano."""
    def chiave(p):
        return re.sub(r"[^\w]+", "", p.lower())
    pa, pb = vivo.split(), ripasso.split()
    sm = SequenceMatcher(None, [chiave(p) for p in pa], [chiave(p) for p in pb])
    coppie = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op != "replace" or i2 - i1 > massimo_parole or j2 - j1 > massimo_parole:
            continue
        lato_a = " ".join(pa[i1:i2]).strip(".,;:!?\"'")
        lato_b = " ".join(pb[j1:j2]).strip(".,;:!?\"'")
        if not lato_a or not lato_b or chiave(lato_a) == chiave(lato_b):
            continue
        coppie.append((lato_a, lato_b))
    return coppie


def prompt_arbitro_ripasso(casi):
    """casi = [(frase_in_diretta, versione_A_live, versione_B_ripasso), ...].
    L'arbitro sceglie solo dove e' sicuro; la risposta e' il formato gia'
    usato dall'apprendimento ({sbagliata: giusta}, vuoto se niente)."""
    righe = [
        "Due riconoscitori vocali hanno trascritto le stesse dettature in",
        "italiano e su alcune parole non sono d'accordo. Per ogni caso scegli",
        "la versione giusta nel contesto della frase, SOLO se sei sicuro.",
        'Rispondi SOLO con un oggetto JSON piatto {"versione sbagliata": "versione giusta"}',
        "con le coppie di cui sei sicuro (o {} se nessuna). Mai inventare parole terze.",
        "",
        "CASI:",
    ]
    for frase, viva, seconda in casi:
        righe.append(f'- frase: "{frase}" | A: "{viva}" | B: "{seconda}"')
    return "\n".join(righe)


def ripassa_audio_conservati(cartella, log_paths, config_path, comando,
                             modello_ripasso, massimo_file=30, timeout=180):
    """Il ripasso vero: per ogni audio conservato con un grezzo nel registro,
    seconda trascrizione col modello di ripasso (stessa pulizia del vivo,
    cosi' i disaccordi sono dei modelli e non delle nostre correzioni), poi
    arbitrato dell'agente e proposte nel registro, senza scrivere il config.
    Torna ipotesi da verificare ({} se niente o se qualcosa va storto)."""
    log = logging.getLogger("voce")
    if not comando:
        return {}
    righe = []
    for p in log_paths:
        try:
            righe += Path(p).read_text(encoding="utf-8").splitlines()
        except OSError:
            pass
    grezzi = estrai_grezzi_con_orario(righe)
    if not grezzi:
        return {}
    cfg = carica_config()
    casi = []
    memoria_fissata = False
    import mlx_whisper  # import pigro: solo il processo di ripasso lo paga
    for wav in sorted(Path(cartella).glob("dettatura_*.wav"))[-massimo_file:]:
        vivo = abbina_audio_a_grezzo(wav.name, grezzi)
        if not vivo:
            continue
        try:
            esito = mlx_whisper.transcribe(
                str(wav), path_or_hf_repo=modello_ripasso,
                language=cfg.get("lingua", "it"),
                initial_prompt=glossario_iniziale(cfg),
            )
        except Exception:
            log.exception("ripasso: trascrizione fallita su %s", wav.name)
            continue
        if not memoria_fissata:  # modello di ripasso ormai caricato: resta residente
            memoria_fissata = True
            fissa_memoria_motore(cfg)
        secondo = rimuovi_eco_glossario(esito["text"].strip(), cfg.get("glossario", []))
        secondo = applica_sostituzioni(secondo, cfg.get("sostituzioni", {}))
        secondo = converti_punteggiatura_dettata(secondo)
        for viva, seconda in disaccordi_parole(vivo, secondo):
            casi.append((vivo, viva, seconda))
    if not casi:
        log.info("ripasso audio: i due riconoscitori sono d'accordo su tutto")
        return {}
    try:
        proposte, errore = chiedi_arbitro(comando, prompt_arbitro_ripasso(casi), timeout)
        if errore:
            log.warning("ripasso audio: %d disaccordi, arbitro fallito (%s)",
                        len(casi), errore)
            return {}
        with open(config_path, encoding="utf-8") as f:
            cfg_locale = json.load(f)
        nuove = unisci_sostituzioni(cfg_locale.get("sostituzioni", {}), proposte)
        if nuove:
            log.info(
                "ripasso audio: proposte da verificare, non applicate: %s (da %d disaccordi)",
                json.dumps(nuove, ensure_ascii=False), len(casi),
            )
        else:
            log.info("ripasso audio: %d disaccordi, nessuna nuova proposta", len(casi))
        return nuove
    except Exception:
        log.exception("ripasso audio fallito")
        return {}


def pulisci_per_voce(testo):
    """Prepara l'ascolto integrale: pause, tabelle e riferimenti leggibili.

    Nessun riassunto o modello: si cambia soltanto la presentazione. Il
    risultato e' idempotente, anche se hook e lettore lo preparano entrambi.
    Come prima, il contenuto dei blocchi di codice non viene pronunciato.
    """
    def nome_file(percorso):
        percorso = percorso.strip().strip("<>")
        if percorso.startswith("file://"):
            percorso = percorso[7:]
        if not re.match(r"^(?:/|~/|[A-Za-z]:[\\/]|\\\\)", percorso):
            return percorso
        riga = re.search(r":(\d+)(?::(\d+))?$", percorso)
        posizione = ""
        if riga:
            posizione = ", riga " + riga[1]
            if riga[2]:
                posizione += ", colonna " + riga[2]
            percorso = percorso[:riga.start()]
        return re.split(r"[\\/]", percorso.rstrip("/\\"))[-1] + posizione

    def inline(riga):
        def link(m):
            etichetta, destinazione = m[1], m[2].strip().strip("<>")
            etichetta = nome_file(etichetta)
            file = nome_file(destinazione)
            if file != destinazione:
                if file.split(", riga ", 1)[0].casefold() == etichetta.casefold():
                    return file
                return etichetta + ", file " + file
            return etichetta

        riga = re.sub(r"!\[[^\]]*\]\((?:<[^>]*>|[^)\n]*)\)", "", riga)
        riga = re.sub(r"\[([^\]]+)\]\((<[^>\n]+>|[^)\n]+)\)", link, riga)
        riga = re.sub(r"(`+)(.*?)\1", lambda m: nome_file(m[2]), riga)
        # Conserva la punteggiatura dopo un URL: serve a sentire la pausa.
        riga = re.sub(
            r"https?://[^\s<>]+",
            lambda m: "collegamento" + m[0][len(m[0].rstrip(".,;:!?)]}")):],
            riga,
        )
        riga = re.sub(
            r"([\"'])((?:[A-Za-z]:[\\/]|\\\\|~?/)[A-Za-z_][^\"'\n]+)\1",
            lambda m: m[1] + nome_file(m[2]) + m[1], riga,
        )
        # Percorsi nudi senza spazi; quelli con spazi sono gia' gestiti nei
        # link e nel codice inline. La radice alfabetica esclude le date.
        riga = re.sub(
            r"(?<![\w:/\\])(?:[A-Za-z]:[\\/]|\\\\|~?/)[A-Za-z_][^\s<>\"'`]*",
            lambda m: nome_file(m[0].rstrip(".,;!?)]}"))
            + m[0][len(m[0].rstrip(".,;!?)]}")):],
            riga,
        )
        # I delimitatori interni alle parole (report_2026_09.md) sono dati.
        riga = re.sub(
            r"(?<!\w)(\*{1,3}|_{1,3})(?=\S)(.+?)(?<=\S)\1(?!\w)",
            r"\2", riga,
        )
        return re.sub(r"\s+", " ", riga).strip()

    def frase(riga):
        riga = riga.strip()
        if riga and riga.rstrip("\"'»)]}")[-1:] not in ".!?…,:;":
            riga += "."
        return riga

    def celle(riga):
        riga = riga.strip()
        if riga.startswith("|"):
            riga = riga[1:]
        if riga.endswith("|") and not riga.endswith("\\|"):
            riga = riga[:-1]
        return [c.strip().replace("\\|", "|") for c in re.split(r"(?<!\\)\|", riga)]

    # Una fence aperta protegge anche il codice incompleto; una fence di
    # altro tipo dentro il blocco non puo' chiuderla per errore.
    righe, fence = [], None
    for riga in testo.splitlines():
        if fence:
            if re.fullmatch(r"\s{0,3}" + re.escape(fence[0]) + "{" + str(len(fence)) + r",}\s*", riga):
                fence = None
            continue
        apertura = re.match(r"^\s{0,3}(`{3,}|~{3,})(.*)$", riga)
        if apertura:
            righe.extend(["", "codice omesso.", ""])
            if not apertura[2].rstrip().endswith(apertura[1]):
                fence = apertura[1]
            continue
        if re.match(r"^\s*:::writing\b", riga) or re.fullmatch(r"\s*:::\s*", riga):
            righe.append("")
            continue
        righe.append(riga)

    parti, paragrafo = [], []

    def chiudi_paragrafo(pausa=True):
        if paragrafo:
            contenuto = " ".join(paragrafo)
            parti.append(frase(contenuto) if pausa else contenuto)
            paragrafo.clear()

    i = 0
    while i < len(righe):
        riga = righe[i].strip()
        if i + 1 < len(righe) and "|" in riga:
            intestazioni, separatori = celle(riga), celle(righe[i + 1])
            if (len(intestazioni) == len(separatori)
                    and all(re.fullmatch(r":?-{3,}:?", c) for c in separatori)):
                chiudi_paragrafo()
                intestazioni = [inline(c) for c in intestazioni]
                i += 2
                inizio_dati = i
                while i < len(righe) and "|" in righe[i] and righe[i].strip():
                    valori = celle(righe[i])
                    lettura = []
                    for n in range(max(len(intestazioni), len(valori))):
                        etichetta = intestazioni[n] if n < len(intestazioni) else ""
                        etichetta = etichetta or f"Colonna {n + 1}"
                        valore = inline(valori[n]) if n < len(valori) else ""
                        lettura.append(etichetta + ": " + (valore or "vuoto"))
                    parti.append(frase("; ".join(lettura)))
                    i += 1
                if i == inizio_dati:
                    parti.append(frase("; ".join(intestazioni)))
                continue
        if not riga:
            chiudi_paragrafo()
        elif re.match(r"^(?:#{1,6}\s|[-*•>]\s|\d+[.)]\s)", riga):
            chiudi_paragrafo()
            riga = re.sub(r"^(?:#{1,6}|[-*•>])\s+", "", riga)
            riga = re.sub(r"\s+#+$", "", riga)
            parti.append(frase(inline(riga)))
        else:
            paragrafo.append(inline(riga))
        i += 1
    chiudi_paragrafo(pausa=False)
    return " ".join(p for p in parti if p)


def estrai_ultima_risposta(transcript_path):
    """Ultimo messaggio testuale dell'assistente da un transcript JSONL.

    Due dialetti, stesso file di testo riga per riga:
    - Claude Code e Codex: riga `type: assistant` con i blocchi in
      `message.content`;
    - Antigravity (Google): riga `source: MODEL` con il testo gia' pronto in
      `content` (verificato il 13/09/2026 sul transcript.jsonl reale). Senza
      questo ramo l'hook trovava il file ma non il parlato, e la voce restava
      muta con Antigravity pur essendo accesa.
    """
    ultimo = ""
    with open(transcript_path, encoding="utf-8") as f:
        for riga in f:
            riga = riga.strip()
            if not riga:
                continue
            try:
                voce = json.loads(riga)
            except json.JSONDecodeError:
                continue
            if voce.get("source") == "MODEL":
                # le righe di lavoro (piani, strumenti) non sono parlato: si
                # legge solo la risposta conclusa destinata alla persona
                if voce.get("status") not in (None, "DONE"):
                    continue
                testo = voce.get("content")
                if isinstance(testo, str) and testo.strip():
                    ultimo = testo.strip()
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


# --- Controllo di consegna (02/10/2026, da un'idea di una cliente) ---
# Una dettatura puo' risultare incollata e inviata e non arrivare mai: l'app che
# riceve il messaggio lo perde e nessuno se ne accorge. Claude Code scrive ogni
# messaggio ricevuto nel suo registro (~/.claude/projects/*/*.jsonl): dopo l'Invio
# automatico si cerca li' il messaggio; se manca si ripreme Invio, poi si reincolla.

CHIAVE_CONSEGNA_CARATTERI = 30


def cartella_registri_claude():
    """Dove Claude Code scrive i registri delle chat (CLAUDE_CONFIG_DIR se impostata)."""
    base = os.environ.get("CLAUDE_CONFIG_DIR")
    return (Path(base) if base else Path.home() / ".claude") / "projects"
CODA_REGISTRO_BYTE = 200_000       # quanta coda di ogni registro si legge
RIGA_MASSIMA_BYTE = 100_000        # righe piu' grandi (immagini, risultati di strumenti) non sono messaggi dettati


def _compatta(testo):
    return " ".join(str(testo or "").split())


def chiave_consegna(testo):
    """L'inizio del messaggio, a spazi normalizzati: basta a riconoscerlo nel registro."""
    return _compatta(testo)[:CHIAVE_CONSEGNA_CARATTERI]


def _istante_riga(valore):
    """Epoch di un `timestamp` ISO del registro (con la Z finale), None se illeggibile."""
    try:
        from datetime import datetime
        return datetime.fromisoformat(str(valore).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return None


def _testo_inviato_da_utente(riga):
    """Testo di una riga del registro che e' un messaggio dell'utente (inviato o in coda), altrimenti ''."""
    if riga.get("type") == "queue-operation":
        return riga.get("content") if riga.get("operation") == "enqueue" and isinstance(riga.get("content"), str) else ""
    if riga.get("type") != "user":
        return ""
    contenuto = riga.get("message", {}).get("content")
    if isinstance(contenuto, list):
        contenuto = " ".join(p.get("text", "") for p in contenuto if isinstance(p, dict) and p.get("type") == "text")
    return contenuto if isinstance(contenuto, str) else ""


def messaggio_in_registri(testo, dal, cartella=None, coda_byte=CODA_REGISTRO_BYTE):
    """Vero se un registro di Claude Code contiene, scritto dopo `dal` (epoch), un
    messaggio dell'utente che comprende l'inizio di `testo`.

    Conta solo cio' che e' stato scritto dopo `dal`: una frase uguale di prima
    ("Si'.") non deve far credere che quella di adesso sia arrivata."""
    chiave = chiave_consegna(testo)
    if not chiave:
        return False
    cartella = Path(cartella) if cartella else cartella_registri_claude()
    try:
        registri = list(cartella.glob("*/*.jsonl"))
    except OSError:
        return False
    for percorso in registri:
        try:
            if percorso.stat().st_mtime < dal - 1.0:
                continue
            with open(percorso, "rb") as f:
                dimensione = f.seek(0, os.SEEK_END)
                inizio = max(0, dimensione - coda_byte)
                f.seek(inizio)
                righe = f.read().decode("utf-8", "ignore").splitlines()
        except OSError:
            continue
        if inizio:
            righe = righe[1:]  # la prima puo' essere tagliata a meta'
        for grezza in reversed(righe):
            if len(grezza) > RIGA_MASSIMA_BYTE or ("queue-operation" not in grezza and '"user"' not in grezza):
                continue
            try:
                riga = json.loads(grezza)
            except ValueError:
                continue
            quando = _istante_riga(riga.get("timestamp"))
            if quando is None or quando < dal - 1.0:
                continue
            if chiave in _compatta(_testo_inviato_da_utente(riga)):
                return True
    return False


def verifica_consegna(testo, dal, arrivato, puo_intervenire, ripremi_invio, reincolla,
                      recupero_ammesso=True, attesa_sec=3.0, passo_sec=0.1,
                      attendi=time.sleep, traccia=None):
    """Dopo l'Invio: il messaggio e' arrivato? Se no, prima si ripreme Invio (puo'
    essere rimasto nella casella), poi si reincolla e si invia di nuovo.

    Le azioni sono funzioni passate da chi chiama (tastiera, app): qui c'e' solo la
    decisione. Esiti: "arrivato", "non_confermato" (non risulta e il recupero non
    e' ammesso: si scrive e basta), "recuperato", "annullato" (Sal ha ripreso la
    tastiera o sta dettando: non ci si intromette), "persa"."""
    traccia = traccia or (lambda *_a: None)

    def aspetta():
        for _ in range(max(1, int(attesa_sec / passo_sec))):
            if arrivato(testo, dal):
                return True
            attendi(passo_sec)
        return arrivato(testo, dal)

    if aspetta():
        return "arrivato"
    if not recupero_ammesso:
        return "non_confermato"
    for tentativo, agisci in ((1, ripremi_invio), (2, reincolla)):
        if not puo_intervenire():
            return "annullato"
        traccia("consegna: il messaggio non risulta in chat, tentativo %d", tentativo)
        agisci()
        if aspetta():
            return "recuperato"
    return "persa"


# --- Voce veloce anche quando un altro programma divora la RAM (01/10/2026) ---
# Caso reale: un altro processo occupa 98 GB, macOS manda in swap il modello e
# ogni dettatura passa da 1-3 s a 15-17 s. Due rimedi: il modello resta
# residente (wired limit) e, se l'app peggiora comunque, si riavvia da sola.

SOGLIA_ATTESA_LENTA_SEC = 8.0        # una trascrizione oltre questi secondi e' "lenta"
ATTESE_LENTE_DI_FILA = 3             # tre lente di fila = modello finito in swap
SILENZIO_PRIMA_RIAVVIO_SEC = 30.0    # riavvio solo dopo tanta quiete
RIAVVIO_OLTRE_MB_DEFAULT = 4500      # memoria dell'app oltre la quale si riparte (P-095)
MARGINE_MEMORIA_FISSA_MB = 512       # sopra la memoria attiva del modello
QUOTA_MASSIMA_MEMORIA_FISSA = 0.25   # mai piu' di un quarto della RAM


def tetto_memoria_fissa(attiva_bytes, ram_bytes, margine_mb=MARGINE_MEMORIA_FISSA_MB, fissa_mb=None):
    """Byte da bloccare in RAM: memoria attiva del modello + margine (o il
    valore di config `memoria_fissa_mb`), mai oltre il 25% della RAM."""
    try:
        base = int(fissa_mb) * 1024 * 1024 if fissa_mb not in (None, "") else int(attiva_bytes) + int(margine_mb) * 1024 * 1024
    except (TypeError, ValueError):
        base = int(attiva_bytes) + int(margine_mb) * 1024 * 1024
    massimo = int(int(ram_bytes) * QUOTA_MASSIMA_MEMORIA_FISSA)
    return max(0, min(base, massimo))


def conta_attese_lente(contatore, durata_sec, soglia_sec=SOGLIA_ATTESA_LENTA_SEC):
    """Attese lente consecutive: una veloce azzera il conto."""
    return contatore + 1 if durata_sec > soglia_sec else 0


def motivo_riavvio(memoria_mb, soglia_mb, attese_lente, occupata, silenzio_sec,
                   attese_di_fila=ATTESE_LENTE_DI_FILA, silenzio_minimo_sec=SILENZIO_PRIMA_RIAVVIO_SEC):
    """Perche' l'app deve riavviarsi da sola, oppure None. Mai mentre registra
    o trascrive (`occupata`) e mai prima di `silenzio_minimo_sec` di quiete.
    soglia_mb <= 0 spegne il riavvio per memoria."""
    if occupata or silenzio_sec < silenzio_minimo_sec:
        return None
    if soglia_mb and soglia_mb > 0 and memoria_mb is not None and memoria_mb > soglia_mb:
        return f"memoria dell'app {memoria_mb:.0f} MB oltre {soglia_mb:.0f} MB"
    if attese_lente >= attese_di_fila:
        return f"{attese_lente} trascrizioni di fila oltre {SOGLIA_ATTESA_LENTA_SEC:.0f} s (modello in swap?)"
    return None


def memoria_processo_mb(pid=None):
    """Memoria del processo in MB come la conta macOS (phys_footprint, la cifra
    di P-095), che include i buffer del motore: `ps rss` ne vede solo una
    frazione (253 MB contro 3669 MB misurati il 01/10/2026). None se non leggibile."""
    try:
        import ctypes
        import ctypes.util
        libproc = ctypes.CDLL(ctypes.util.find_library("proc"))
        buf = ctypes.create_string_buffer(512)
        # flavor 2 = rusage_info_v2; ri_phys_footprint e' l'ottavo uint64 dopo l'uuid (offset 72)
        if libproc.proc_pid_rusage(int(pid or os.getpid()), 2, buf) != 0:
            return None
        return int.from_bytes(buf.raw[72:80], "little") / (1024.0 * 1024.0)
    except Exception:
        return None


def fissa_memoria_motore(cfg, mx=None):
    """Tiene il modello caricato residente in RAM (mx.set_wired_limit) cosi'
    macOS non lo manda in swap. Da chiamare DOPO il caricamento del modello.
    Se qualcosa fallisce: warning e si va avanti. Torna i byte fissati o None."""
    log = logging.getLogger("voce")
    try:
        if mx is None:
            import mlx.core as mx
        attiva = getattr(mx, "get_active_memory", None) or mx.metal.get_active_memory
        ram = mx.device_info()["memory_size"]
        tetto = tetto_memoria_fissa(attiva(), ram, fissa_mb=cfg.get("memoria_fissa_mb"))
        mx.set_wired_limit(tetto)
        log.info("memoria fissa del motore: %d MB", tetto // (1024 * 1024))
        return tetto
    except Exception as e:
        log.warning("memoria fissa del motore non impostata: %s", e)
        return None


# --- Motore leggero sui Mac piccoli (01/10/2026) ---
# Il modello pieno (large-v3, 2,9 GB su disco) su un Mac da 8-16 GB e' troppo
# pesante per restare fisso in memoria (P-088, P-095). Fino a `ram_mac_piccoli_gb`
# l'app usa da sola il motore leggero; sopra, il `modello` del prodotto. Se la
# persona ha scritto `modello` nel suo config.local.json, vince la sua scelta.

MODELLO_MAC_PICCOLI_DEFAULT = "mlx-community/whisper-large-v3-turbo"
RAM_MAC_PICCOLI_GB_DEFAULT = 16


def ram_fisica_bytes():
    """RAM fisica del Mac in byte, o None se non si riesce a leggerla."""
    try:
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    except (AttributeError, OSError, ValueError):
        return None


def scegli_modello(cfg, locali, ram_bytes):
    """(modello, motivo): quale motore di trascrizione usare e perche'.

    Funzione pura. `locali` e' il contenuto di config.local.json ({} se manca).
    Con RAM non leggibile resta il motore pieno, come prima di questa regola."""
    if locali.get("modello"):
        return locali["modello"], "scelto dalla persona in config.local.json"
    if not ram_bytes:
        return cfg["modello"], "pieno: RAM del Mac non leggibile"
    try:
        soglia_gb = float(cfg.get("ram_mac_piccoli_gb", RAM_MAC_PICCOLI_GB_DEFAULT))
    except (TypeError, ValueError):
        soglia_gb = float(RAM_MAC_PICCOLI_GB_DEFAULT)
    ram_gb = ram_bytes / 1024 ** 3
    dati = f"Mac con {ram_gb:g} GB di RAM, soglia {soglia_gb:g} GB"
    if ram_gb <= soglia_gb:
        return cfg.get("modello_mac_piccoli") or MODELLO_MAC_PICCOLI_DEFAULT, f"leggero: {dati}"
    return cfg["modello"], f"pieno: {dati}"


# --- Orecchio: il riconoscitore di voce umana (31/10/2026) ---
# Ispirato all'app open source Handy (github.com/cjpais/Handy, MIT). Il volume non sa se
# e' una voce: una porta, una tastiera o un ventilatore lo alzano uguale, e su quei secondi
# Whisper scrive «Grazie.» (23 volte in 10 giorni, scartate dal filtro). Silero VAD
# (github.com/snakers4/silero-vad, MIT, modello `silero_vad.onnx` della v6.2.3) da' per
# ogni frame di 32 ms la probabilita' che ci sia una persona che parla. Parametri di Handy:
# soglia 0,3; 60 ms di voce per dire «c'e' voce»; 450 ms tenuti prima e 450 ms dopo la voce.
# Usi: mani libere che partono e si fermano sulla voce; prima di Whisper, niente voce =
# niente trascrizione, e i silenzi lunghi si accorciano lasciando quei margini. Il filtro
# delle frasi-fantasma resta come seconda rete. `"orecchio": false` torna a prima.

FILE_ORECCHIO = SOURCE_BASE / "silero_vad.onnx"
FRAME_ORECCHIO = 512      # campioni a 16 kHz (32 ms): la misura che il modello accetta
CONTESTO_ORECCHIO = 64    # campioni del frame prima che il modello vuole davanti a ogni frame


class ModelloOrecchio:
    """Silero VAD su onnxruntime, un thread solo: niente torch, ~0,07 ms per frame.

    Chiamabile: (ingresso [1, 576], stato [2, 1, 128]) -> (probabilita', stato nuovo).
    La sessione si puo' usare da piu' thread insieme; lo stato lo tiene chi chiama."""

    def __init__(self, percorso=None):
        import onnxruntime as ort  # import pigro: l'hook TTS usa voce_lib senza onnxruntime
        import numpy as np
        self._np = np
        opzioni = ort.SessionOptions()
        opzioni.intra_op_num_threads = 1   # accanto a Whisper: nessun gruppo di thread in piu'
        opzioni.inter_op_num_threads = 1
        opzioni.log_severity_level = 3
        self.percorso = Path(percorso or FILE_ORECCHIO)
        self._sessione = ort.InferenceSession(
            str(self.percorso), sess_options=opzioni, providers=["CPUExecutionProvider"])
        self._sr = np.array(16000, dtype=np.int64)

    def __call__(self, ingresso, stato):
        uscita, stato = self._sessione.run(
            None, {"input": ingresso, "state": stato, "sr": self._sr})
        return float(uscita[0][0]), stato


class FlussoOrecchio:
    """Audio a pezzi di qualunque misura -> una probabilita' per ogni frame da 512 campioni.

    Tiene lo stato del modello e il contesto tra un pezzo e l'altro, come il wrapper
    ufficiale di Silero: lo stesso audio a pezzi diversi da' le stesse probabilita'."""

    def __init__(self, modello):
        import numpy as np
        self._np = np
        self.modello = modello
        self.azzera()

    def azzera(self):
        np = self._np
        self._stato = np.zeros((2, 1, 128), dtype=np.float32)
        self._contesto = np.zeros(CONTESTO_ORECCHIO, dtype=np.float32)
        self._resto = np.zeros(0, dtype=np.float32)

    def probabilita(self, campioni, fino_in_fondo=False):
        """Probabilita' dei frame completi; con `fino_in_fondo` anche dell'ultimo pezzo, a zeri."""
        np = self._np
        a = np.concatenate([self._resto, np.asarray(campioni, dtype=np.float32).reshape(-1)])
        if fino_in_fondo and len(a) % FRAME_ORECCHIO:
            a = np.concatenate([a, np.zeros(FRAME_ORECCHIO - len(a) % FRAME_ORECCHIO, dtype=np.float32)])
        n = len(a) // FRAME_ORECCHIO
        # contesto + audio in un solo array: il frame i col suo contesto e' una fetta, niente copie
        b = np.concatenate([self._contesto, a[:n * FRAME_ORECCHIO]])
        larghezza = CONTESTO_ORECCHIO + FRAME_ORECCHIO
        uscita = []
        for i in range(n):
            ingresso = b[i * FRAME_ORECCHIO:i * FRAME_ORECCHIO + larghezza][None, :]
            p, self._stato = self.modello(ingresso, self._stato)
            uscita.append(p)
        if n:
            self._contesto = b[n * FRAME_ORECCHIO:n * FRAME_ORECCHIO + CONTESTO_ORECCHIO].copy()
        self._resto = a[n * FRAME_ORECCHIO:]
        return uscita


def frame_da_ms(ms, freq=16000):
    """Quanti frame da 32 ms fanno `ms` millisecondi (almeno uno): 60 -> 2, 450 -> 14."""
    return max(1, round(float(ms) / 1000 * freq / FRAME_ORECCHIO))


def c_e_voce_umana(probabilita, soglia=0.3, attacco=2):
    """True se almeno `attacco` frame di fila hanno voce (60 ms con 2 frame, come Handy)."""
    di_fila = 0
    for p in probabilita:
        di_fila = di_fila + 1 if p >= soglia else 0
        if di_fila >= attacco:
            return True
    return False


def maschera_voce(n_campioni, probabilita, soglia=0.3, prima=14, dopo=14, frame=FRAME_ORECCHIO):
    """Quali campioni tenere: ogni frame con voce, `prima` frame prima e `dopo` frame dopo.

    Prudente apposta: basta UN frame sopra soglia per tenere quasi un secondo attorno, cosi'
    una parola detta piano non si taglia mai. Restano fuori solo i silenzi oltre
    prima + dopo (896 ms coi valori di Handy), che si accorciano a quella misura."""
    import numpy as np
    n_frame = len(probabilita)
    tieni = np.zeros(n_frame, dtype=bool)
    for i, p in enumerate(probabilita):
        if p >= soglia:
            tieni[max(0, i - prima):min(n_frame, i + dopo + 1)] = True
    maschera = np.repeat(tieni, frame)[:n_campioni]
    if len(maschera) < n_campioni:  # campioni oltre l'ultimo frame analizzato: si tengono
        maschera = np.concatenate([maschera, np.ones(n_campioni - len(maschera), dtype=bool)])
    return maschera


class Orecchio:
    """Il riconoscitore con i parametri di Handy: decide se c'e' voce e accorcia i silenzi."""

    def __init__(self, modello, soglia=0.3, attacco_ms=60, prima_ms=450, dopo_ms=450, freq=16000):
        self.modello = modello
        self.soglia = float(soglia)
        self.attacco = frame_da_ms(attacco_ms, freq)
        self.prima = frame_da_ms(prima_ms, freq)
        self.dopo = frame_da_ms(dopo_ms, freq)
        self.freq = freq

    @classmethod
    def da_config(cls, cfg, modello=None):
        return cls(
            modello if modello is not None else ModelloOrecchio(),
            soglia=cfg.get("orecchio_soglia", 0.3),
            attacco_ms=cfg.get("orecchio_attacco_ms", 60),
            prima_ms=cfg.get("orecchio_prima_ms", 450),
            dopo_ms=cfg.get("orecchio_dopo_ms", 450),
        )

    def probabilita(self, audio):
        """Tutto l'audio, stato nuovo: una registrazione non eredita niente dalla precedente."""
        return FlussoOrecchio(self.modello).probabilita(audio, fino_in_fondo=True)

    def prepara(self, audio):
        """(audio per Whisper, probabilita'): None se non c'e' voce; altrimenti l'audio coi
        silenzi lunghi accorciati. Mai un campione tolto vicino a un frame con voce."""
        import numpy as np
        a = np.asarray(audio, dtype=np.float32).reshape(-1)
        prob = self.probabilita(a)
        if not c_e_voce_umana(prob, self.soglia, self.attacco):
            return None, prob
        return a[maschera_voce(len(a), prob, self.soglia, self.prima, self.dopo)], prob

    def vivo(self, silenzio_ms=1400):
        return OrecchioVivo(self, silenzio_ms)


class OrecchioVivo:
    """L'orecchio delle mani libere: ascolta il microfono mentre aspetta e mentre registra.

    Il callback audio chiama solo `ascolta` (un append, niente calcolo); il worker delle
    mani libere chiede `attacco()` per partire e `silenzio()` per fermarsi."""

    def __init__(self, orecchio, silenzio_ms=1400):
        self.orecchio = orecchio
        self.silenzio_frame = frame_da_ms(silenzio_ms, orecchio.freq)
        self._blocchi = collections.deque(maxlen=400)  # ~12 s di blocchi da 30 ms: mai senza fondo
        self._flusso = FlussoOrecchio(orecchio.modello)
        self.acceso = False
        self.voce_di_fila = 0
        self.silenzio_di_fila = 0

    def ascolta(self, blocco):
        self._blocchi.append(blocco)

    def accendi(self):
        if not self.acceso:
            self.azzera()
            self.acceso = True

    def spegni(self):
        self.acceso = False
        self.azzera()

    def azzera(self):
        """Butta quello che ha sentito (voce dell'agente, tasto in uso): si riparte da zero."""
        self._blocchi.clear()
        self._flusso.azzera()
        self.voce_di_fila = self.silenzio_di_fila = 0

    def _consuma(self):
        while True:
            try:
                blocco = self._blocchi.popleft()
            except IndexError:
                return
            for p in self._flusso.probabilita(blocco):
                if p >= self.orecchio.soglia:
                    self.voce_di_fila += 1
                    self.silenzio_di_fila = 0
                else:
                    self.silenzio_di_fila += 1
                    self.voce_di_fila = 0

    def attacco(self):
        """True appena ci sono 60 ms di voce di fila; da li' il silenzio si conta da zero."""
        self._consuma()
        if self.voce_di_fila >= self.orecchio.attacco:
            self.silenzio_di_fila = 0
            return True
        return False

    def silenzio(self):
        """True dopo `silenzio_ms` senza voce: la frase e' finita."""
        self._consuma()
        return self.silenzio_di_fila >= self.silenzio_frame


# --- Esc annulla la dettatura (31/10/2026) ---
# Dalla pressione del tasto (o dall'avvio delle mani libere) finche' il testo non e'
# incollato, Esc butta la dettatura: niente incolla, niente Invio. In quel tratto Esc NON
# deve arrivare all'app davanti: in Claude fermerebbe l'agente. Lo trattiene un event tap
# attivo di macOS (detta.py), acceso solo in quel tratto; qui la decisione, senza Quartz.

VK_ESC = 53  # kVK_Escape


class EscAnnulla:
    """Cosa fare di un evento di Esc: (trattenerlo?, annullare la dettatura?).

    Un Esc trattenuto lo resta fino al suo rilascio, ripetizioni comprese: anche se la
    dettatura e' gia' buttata, il tasto tenuto non deve arrivare all'app un attimo dopo."""

    SCADENZA_SEC = 3.0  # un rilascio perso non tiene acceso il filtro per sempre

    def __init__(self):
        self.trattenuto = False
        self._ultimo = 0.0

    def evento(self, giu, ripetuto, con_ctrl_o_option, finestra_aperta, ora):
        if giu:
            if ripetuto and self.trattenuto:
                self._ultimo = ora
                return True, False
            if not ripetuto:
                self.trattenuto = False  # una pressione nuova: il rilascio di prima si e' perso
                if finestra_aperta and not con_ctrl_o_option:  # Ctrl/Option + Esc restano del sistema
                    self.trattenuto, self._ultimo = True, ora
                    return True, True
            return False, False
        if self.trattenuto:
            self.trattenuto = False
            return True, False
        return False, False

    def serve(self, ora):
        """Il filtro deve restare acceso per un Esc ancora tenuto (mai oltre la scadenza)."""
        return self.trattenuto and ora - self._ultimo < self.SCADENZA_SEC


# --- Ultime dettature, solo in memoria (31/10/2026) ---
# Menu Voce: «Copia l'ultima dettatura» e «Ritrascrivi l'ultima». Testo e audio stanno
# solo qui, in memoria: niente file, niente registro. Dopo un riavvio non ci sono piu'.

def _ordine_turno(token):
    """I turni sono «pid:istante_ns»: l'ordine in cui le registrazioni sono partite."""
    try:
        return int(str(token).rsplit(":", 1)[1])
    except (IndexError, ValueError):
        return 0


class UltimeDettature:
    """L'ultimo messaggio incollato: il suo testo e l'audio dei pezzi che lo hanno fatto."""

    def __init__(self):
        self._lock = threading.Lock()
        self._in_corso = {}  # turno -> audio, solo pezzi con testo, in attesa dell'incolla
        self.testo = ""
        self.audio = []

    def pezzo(self, token, audio, testo):
        if not (testo or "").strip():
            return
        with self._lock:
            self._in_corso[token] = audio

    def consegnata(self, testo):
        if not (testo or "").strip():
            return
        with self._lock:
            self.testo = testo.strip()
            self.audio = [self._in_corso[t] for t in sorted(self._in_corso, key=_ordine_turno)]
            self._in_corso = {}

    def annulla_in_corso(self):
        with self._lock:
            self._in_corso = {}

    def disponibili(self):
        """(c'e' un testo da copiare?, c'e' un audio da ritrascrivere?)"""
        with self._lock:
            return bool(self.testo), bool(self.audio)

    def ultima(self):
        with self._lock:
            return self.testo, list(self.audio)


if __name__ == "__main__":
    # `voce_lib.py --ripasso`: processo di ripasso notturno, spawnato sganciato
    # da detta.py col gate giornaliero. Vive da solo, carica il secondo modello,
    # propone e muore: la dettatura in diretta non paga niente.
    if len(sys.argv) == 2 and sys.argv[1] == "--ripasso":
        logging.basicConfig(
            filename=str(BASE / "voce.log"), level=logging.INFO,
            format="%(asctime)s %(levelname)s %(message)s",
        )
        cfg = carica_config()
        nuove = ripassa_audio_conservati(
            BASE / "audio_recenti",
            [BASE / "voce.log"] + sorted(BASE.glob("voce.log.*"))[-1:],
            config_scrivibile(),
            comandi_agente(),
            cfg.get("modello_ripasso", "mlx-community/whisper-large-v3-turbo"),
            massimo_file=int(cfg.get("conserva_audio_n", 0)) or 30,
        )
        print(json.dumps(nuove, ensure_ascii=False))
    sys.exit(0)
