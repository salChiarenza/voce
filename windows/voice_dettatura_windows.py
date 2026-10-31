"""Voice Dettatura Windows.

Tieni premuto Ctrl destro, parla, rilascia: il testo viene incollato dove hai il
cursore. Il tasto Menu, tenuto premuto un secondo, accende/spegne la voce agenti
(legge le risposte ad alta voce).
Trascrizione locale con faster-whisper (niente cloud). Tutto in questo unico file.

Mentre parli compare in basso al centro una pill scura con il logo "LeaderAI."
(il punto verde cresce con la voce e pulsa mentre trascrive) e una barra di
lineette verdi disposte ad arco "a sorriso" che si muovono col volume. L'overlay non ruba mai il focus: continui a scrivere
nel programma dove sei. Per fermare la dettatura chiudi la finestra.
"""
from __future__ import annotations

import collections
import ctypes
import json
import logging
import logging.handlers
import math
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
from pathlib import Path

import numpy as np
import pyperclip
import sounddevice as sd
from faster_whisper import WhisperModel
from pynput import keyboard, mouse
from pynput.keyboard import Controller, Key

try:  # nelle vecchie installazioni il modulo voce agenti era opzionale
    import voce_hook as voce_agenti
except ImportError:
    voce_agenti = None

try:  # beep di sistema: solo Windows, mai bloccante
    import winsound
except Exception:  # pragma: no cover - fuori da Windows
    winsound = None

BASE = Path(__file__).resolve().parent
LOG = BASE / "voice.log"
CFG = json.loads((BASE / "config.json").read_text(encoding="utf-8"))

SAMPLE_RATE = int(CFG.get("sample_rate", 16000))
HOTKEY = getattr(Key, CFG.get("hotkey", "f8"))
TASTO_VOCE = getattr(Key, CFG.get("tasto_voce", "f9"), None)  # on/off voce agenti
# P-085 (gemella del Mac): il tasto della voce conta solo se TENUTO. Un tocco
# per sbaglio (il Menu sta accanto al Ctrl destro, il tasto-detta) non accende
# e non spegne la voce. Pavimento mezzo secondo: una soglia a 0 «per far prima»
# rimetterebbe il difetto.
VOCE_TENUTA_SEC = max(0.5, float(CFG.get("voce_tenuta_sec", 1.0)))
INVIO_AUTOMATICO = bool(CFG.get("invio_automatico", True))
# pause pre-Invio: chiavi invio_automatico_ritardo_*_sec, scelte da ritardo_invio()
VOICE_THRESHOLD = float(CFG.get("voice_threshold", 0.004))
MIN_RECORDING_SEC = float(CFG.get("min_recording_sec", 0.4))
MAX_RECORDING_SEC = float(CFG.get("max_recording_sec", 90))
# Coda al rilascio del tasto-detta (gemella Mac): il microfono resta in
# ascolto ancora un attimo, cosi' l'ultima sillaba non si perde se il tasto
# viene mollato un pelo prima di finire la frase.
CODA_RILASCIO_SEC = float(CFG.get("coda_rilascio_sec", 0.5))

# tetto DURO: ferma anche col tasto fisicamente giu' (tasto incastrato); stessa chiave del Mac
MAX_RECORDING_TASTO_SEC = float(CFG.get("max_registrazione_tasto_sec", 300))

# Trascrizione progressiva (gemella Mac, 04/09): segmenti chiusi su una pausa
# trascritti in sottofondo mentre si registra; al rilascio resta la coda.
PROGRESSIVA = bool(CFG.get("trascrizione_progressiva", False))
PROGRESSIVA_BLOCCO_SEC = float(CFG.get("trascrizione_progressiva_blocco_sec", 12))
PROGRESSIVA_SOGLIA_SILENZIO = float(CFG.get("trascrizione_progressiva_soglia_silenzio", 0.010))

# --- aspetto della pill (uguale alla versione Mac) ---
BRAND = CFG.get("brand", "LeaderAI.")
COLORE = CFG.get("colore", "#7ED321")        # verde delle lineette
VERDE_FIRMA = "#56C842"                       # il punto del logo "LeaderAI."
ALONE_PUNTO = ("#1F3A1B", "#2E5A27")          # verde sfumato sul fondo: la luce del punto
N_BARRE = int(CFG.get("barre", 18))
SCALA_VOLUME = float(CFG.get("scala_volume", 200))
LARGHEZZA, ALTEZZA = 300, 72
RAGGIO = 16
SFONDO_PILL = "#141414"
TRASPARENTE = "magenta"                       # colore reso invisibile dalla finestra

keyboard_controller = Controller()
commands: queue.Queue = queue.Queue()         # ("start", istante del tasto)/"stop" dal thread tastiera al worker audio
eventi: queue.Queue[str] = queue.Queue()      # "ascolto"/"trascrivo"/"sistemo"/"nascosto" verso l'overlay
livelli = collections.deque([0.0] * N_BARRE, maxlen=N_BARRE)
blocks: list[np.ndarray] = []
rms_blocks: list[float] = []                   # parallelo a blocks: volume per blocco, per trovare le pause
sessione_progressiva = None                    # sessione della registrazione in corso (None se spenta)
turno_utente_token = None                      # resta aperto fino a incolla e Invio
stream = None
recording = False
key_down = False
voice_key_down = False                         # debounce del tasto on/off voce
voce_timer = None                              # il conto del tasto voce: parte alla pressione, si annulla al rilascio
recording_started_at: float | None = None
model: WhisperModel | None = None
ultima_pressione_utente = 0.0                  # annulla l'Invio automatico in attesa
ultimo_tasto_utente = None                     # quale gesto: un Invio arrivato mentre il testo compariva e' un si'
pressioni_tasto = 0                            # pressioni del tasto-detta: una nuova nella coda del rilascio = si continua


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
        """Dalla pressione del tasto a quando il testo e' incollato: e' il tratto in cui
        Esc butta la dettatura (gemella Mac, 31/10/2026). L'attesa dell'Invio no."""
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


# --- Ultime dettature, solo in memoria (gemella Mac, 31/10/2026) ---
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


coda_dettature = CodaDettature()
ultime_dettature = UltimeDettature()  # menu Voce: ultimo testo e suo audio, solo in memoria
_lock_appunti = threading.Lock()  # incolla e menu non si scambiano gli Appunti a meta'


# --- voce in uscita "agenti": interruttore + TTS di Windows, tutto in questo file ---
FLAG_VOICE_ON = BASE / "VOICE_ON"          # se esiste, la voce in uscita e' accesa
FLAG_TURNO_UTENTE = BASE / "TURNO_UTENTE"  # dalla prima parola fino all'Invio automatico
PID_FILE = BASE / "voce_pid"               # PID dell'ultima lettura: una voce per volta
VOCE_RATE = int(CFG.get("voce_rate", 0))   # System.Speech: da -10 (lenta) a +10 (veloce)
VOCE_NOME = str(CFG.get("voce_nome", ""))  # scelta guidata alla prima installazione


def voce_attiva() -> bool:
    """Voce agenti accesa = conversazione vera con l'agente (botta e risposta,
    niente tempo di rilettura). Usata per scegliere la pausa pre-Invio."""
    return FLAG_VOICE_ON.exists()


def apri_turno_utente() -> str:
    """Apre il turno con token: una trascrizione vecchia non chiude la nuova."""
    token = f"{os.getpid()}:{time.monotonic_ns()}"
    FLAG_TURNO_UTENTE.write_text(token, encoding="utf-8")
    return token


def chiudi_turno_utente(token: str | None) -> None:
    if not token:
        return
    try:
        if FLAG_TURNO_UTENTE.read_text(encoding="utf-8").strip() == token:
            FLAG_TURNO_UTENTE.unlink(missing_ok=True)
    except OSError:
        pass


# --- glossario e detta pulito: la trascrizione grezza diventa testo curato ---
# (gemelli delle funzioni in mac/voce_lib.py: stessi nomi, stesso contratto)

def glossario_iniziale(cfg) -> str | None:
    """Prompt iniziale per Whisper coi termini del mestiere: cosi' nomi propri
    e brand (LeaderAI, nomi clienti) escono scritti giusti. Solo l'elenco dei
    nomi, senza l'etichetta «Glossario:», che Whisper leggeva come un documento
    e non come parlato (parole e punteggiatura saltate; banco Mac 11/10/2026:
    35 parole sbagliate su 800 con l'etichetta, 18 senza). (Gemella di
    glossario_iniziale in mac/voce_lib.py.)"""
    voci = [v for v in cfg.get("glossario", []) if v.strip()]
    if not voci:
        return None
    return ", ".join(voci) + "."


def rimuovi_eco_glossario(testo, glossario=()):
    """Whisper a volte ricopia il suggerimento del glossario in testa alla
    trascrizione (caso reale Mac 29/08/2026: "non lo so, mi arrendo" diventato
    "Glossario, mi arrendo."). La parola "Glossario" seguita da :/,/. in
    apertura non e' mai stata dettata: si toglie, insieme agli eventuali nomi
    del glossario ricopiati subito dopo. Nel corpo della frase non si tocca
    niente. (Gemella di rimuovi_eco_glossario in mac/voce_lib.py.)"""
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


def applica_sostituzioni(testo: str, sostituzioni: dict) -> str:
    """Correzioni ricorrenti 'sbagliato -> giusto', a parola intera e senza
    distinguere maiuscole: quello che il glossario non basta a fissare."""
    for sbagliato, giusto in sostituzioni.items():
        testo = re.sub(
            r"\b" + re.escape(sbagliato) + r"\b", giusto, testo, flags=re.IGNORECASE
        )
    return testo


def converti_punteggiatura_dettata(testo: str) -> str:
    """I segni di punteggiatura DETTATI diventano segni veri: "si parte punto
    esclamativo" -> "si parte!". (Gemella di converti_punteggiatura_dettata
    in mac/voce_lib.py: stesse regole, stessi casi.)

    Solo comandi inequivocabili al singolare: "punto" e "virgola" da soli
    restano parole. Con l'articolo davanti ("il punto esclamativo") si sta
    parlando DEL segno e non si tocca; "venirne a capo" resta un idioma.
    Il segno si attacca alla parola prima, al posto dell'eventuale segno gia'
    messo da Whisper; dopo ! ? e a-capo la frase riparte maiuscola."""
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


# --- trascrizione progressiva: funzioni pure (gemelle di mac/voce_lib.py) ---
# Dati reali Mac 27/08→04/09: 517 dettature su 1.422 oltre i 30s; Whisper
# partiva solo al rilascio e 90s di parlato costavano 17s di attesa.

def trova_taglio(rms, campioni, inizio, freq=16000, soglia=0.010,
                 silenzio_min_sec=0.5, blocco_min_sec=12.0):
    """Indice (escluso) del blocco dove chiudere il segmento aperto da
    `inizio`, o None se un punto sicuro non c'e' ancora. Si taglia SOLO alla
    fine di un silenzio continuo di almeno silenzio_min_sec (ogni blocco
    sotto soglia) e SOLO se il segmento chiuso dura almeno blocco_min_sec:
    dentro un silenzio non c'e' nessuna parola da spezzare."""
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


def unisci_segmenti(pezzi, glossario=()):
    """Rincolla i testi dei segmenti in un testo solo: spazi singoli, mai due
    segni attaccati, maiuscola dopo un punto; dopo una frase lasciata a meta'
    l'iniziale maiuscola di Whisper torna minuscola, tranne nomi del
    glossario e sigle."""
    fine_frase = ".!?…"
    segni = fine_frase + ",;:"
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
        if ultimo in segni:
            p = p.lstrip(segni + " ")
            if not p:
                continue
        if p[0] in segni:  # ", e poi" dopo una parola nuda: si attacca
            testo += p
            continue
        prima = p.split(" ", 1)[0]
        if ultimo in fine_frase:
            p = p[0].upper() + p[1:]
        elif (p[0].isupper() and not prima.isupper()
              and prima.strip(segni).lower() not in protetti):
            p = p[0].lower() + p[1:]
        testo += " " + p
    return testo


def prompt_con_contesto(glossario_prompt, precedente, max_caratteri=200):
    """initial_prompt per un segmento: glossario + coda del testo del segmento
    prima (ultimi ~max_caratteri, a inizio parola). Senza niente torna None."""
    coda = " ".join((precedente or "").split())
    if len(coda) > max_caratteri:
        coda = coda[-max_caratteri:]
        spazio = coda.find(" ")
        if 0 <= spazio < len(coda) - 1:
            coda = coda[spazio + 1:]
    parti = [p for p in (glossario_prompt, coda) if p]
    return " ".join(parti) or None


def scegli_casella(candidati):
    """Indice della casella migliore tra quelle trovate nella finestra.

    candidati = [(y, larghezza), ...] con y che cresce verso il basso. Nelle
    chat la casella di scrittura sta in fondo: si prende la piu' in basso, a
    parita' la piu' larga. None se non c'e' nessuna casella.
    (Gemella di scegli_casella in mac/voce_lib.py.)"""
    if not candidati:
        return None
    return max(range(len(candidati)), key=lambda i: (candidati[i][0], candidati[i][1]))


def in_zona_scrittura(y_casella, y_finestra, altezza_finestra, quota=0.4):
    """True se la casella sta nella parte bassa della finestra: la casella di
    scrittura delle chat sta in fondo, mentre in alto ci sono barra degli
    indirizzi e campi di ricerca che non vanno MAI presi. Meglio nessun click
    che un click nella barra sbagliata.
    (Gemella di in_zona_scrittura in mac/voce_lib.py.)"""
    return y_casella >= y_finestra + altezza_finestra * quota


def casella_ammissibile(y_casella, altezza_casella, y_finestra, altezza_finestra,
                        quota=0.4, quota_documento=0.5):
    """True se nella casella si puo' scrivere senza fare danni: parte bassa
    della finestra (le chat) oppure area ALTA almeno meta' finestra (il
    documento di Blocco Note/Word, che parte dall'alto). Le barre in alto
    sono basse di statura: fuori da entrambe le porte.
    (Gemella di casella_ammissibile in mac/voce_lib.py.)"""
    if in_zona_scrittura(y_casella, y_finestra, altezza_finestra, quota):
        return True
    return altezza_casella >= altezza_finestra * quota_documento


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


def file_audio_da_eliminare(nomi, massimo):
    """Quali file audio conservati vanno eliminati per restare entro `massimo`:
    i nomi contengono il timestamp, quindi l'ordine alfabetico e' l'ordine
    temporale. Con massimo <= 0 (conservazione spenta) si elimina tutto.
    (Gemella di file_audio_da_eliminare in mac/voce_lib.py.)"""
    ordinati = sorted(nomi)
    if massimo <= 0:
        return ordinati
    return ordinati[:-massimo] if len(ordinati) > massimo else []


def salva_audio_recente(audio, cartella, massimo, freq=16000):
    """Salva la dettatura come WAV e tiene solo le ultime `massimo` (le piu'
    vecchie si eliminano da sole). Tutto resta sul computer del proprietario:
    serve a riascoltare le frasi capite male e tarare glossario e
    sostituzioni su casi veri. Spenta di default (`conserva_audio_n` = 0).
    (Gemella di salva_audio_recente in mac/voce_lib.py.)"""
    import wave
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


def serve_pulizia(testo: str, cfg) -> bool:
    """Detta pulito solo se attivo in config e la dettatura e' lunga: le
    dettature corte (comandi rapidi) devono incollare subito, senza attese."""
    if not cfg.get("detta_pulito", False):
        return False
    minimo = int(cfg.get("pulizia_min_parole", 15))
    return len(testo.split()) >= minimo


def prompt_pulizia(testo: str, glossario=()) -> str:
    """Istruzioni per chi sistema il dettato (stessa formulazione del Mac:
    regole numerate su UNA riga ciascuna, collaudata il 02/07)."""
    righe = [
        "Correggi questa dettatura vocale seguendo le regole nell'ordine:",
        '1. Quando chi parla si corregge, vale SOLO l\'ultima versione detta. "martedì anzi no facciamo mercoledì" significa MERCOLEDÌ: scrivi solo "mercoledì" e cancella "martedì" e "anzi no facciamo".',
        "2. Cancella gli intercalari: ehm, cioè, ecco.",
        "3. Sistema punteggiatura e maiuscole.",
        "4. Non riassumere, non aggiungere niente, non tradurre.",
    ]
    if glossario:
        # NON "scrivi questi nomi": il modellino lo eseguiva alla lettera
        # e appendeva l'intero glossario in coda al testo (bug 03/07)
        righe.append("5. Se nel testo compare uno di questi nomi, scrivilo esattamente così: " + ", ".join(glossario) + ". Non aggiungere mai nomi che chi parla non ha detto.")
    righe.append("Rispondi SOLO col testo corretto, senza commenti ne' virgolette.")
    righe.append("")
    righe.append("TESTO DA SISTEMARE:")
    righe.append(testo)
    return "\n".join(righe)


def comandi_agente() -> list:
    """TUTTI gli agenti gia' presenti sul PC, in ordine di preferenza: Claude
    Code, poi Codex (gemella Mac). L'app non impone un agente: usa quello
    che il proprietario ha. Chi chiama prova la lista in ordine e si ferma al
    primo che risponde (chiedi_arbitro). Nessuno installato -> lista vuota."""
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


def comando_agente() -> list | None:
    """Il primo agente disponibile (compatibilita'). None se non ce n'e'."""
    comandi = comandi_agente()
    return comandi[0] if comandi else None


def _catena_arbitri(comando) -> list:
    """Un comando solo (lista di stringhe) o una lista di comandi -> lista di comandi."""
    if not comando:
        return []
    if isinstance(comando[0], str):
        return [list(comando)]
    return [list(c) for c in comando if c]


def chiedi_arbitro(comando, prompt: str, timeout: int = 60) -> tuple:
    """Passa il prompt agli agenti locali in ordine e torna (proposte, errore)
    del PRIMO che risponde (gemella Mac). errore=None = risposta valida;
    altrimenti riassume il guasto di ogni agente provato."""
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


def estrai_grezzi_dal_log(log_path, massimo=50) -> list:
    """Ultime dettature grezze dal log (righe 'INFO grezzo: ...')."""
    try:
        righe = Path(log_path).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    grezzi = [r.split("INFO grezzo: ", 1)[1] for r in righe if "INFO grezzo: " in r]
    return grezzi[-massimo:]


def unisci_sostituzioni(attuali: dict, nuove: dict) -> dict:
    """Filtra la forma delle proposte, senza approvarne la correttezza:
    solo stringhe nuove, mai identita' o sovrascritture."""
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


def estrai_json(testo: str) -> dict:
    """Primo oggetto JSON piatto trovato nella risposta dell'agente."""
    inizio, fine = testo.find("{"), testo.rfind("}")
    if inizio == -1 or fine <= inizio:
        return {}
    try:
        esito = json.loads(testo[inizio:fine + 1])
        return esito if isinstance(esito, dict) else {}
    except json.JSONDecodeError:
        return {}


def risposta_arbitro(returncode: int, stdout: str, stderr: str = "") -> tuple:
    """Gemella Mac: (proposte, errore). Proposte solo se l'agente ha risposto
    davvero; altrimenti l'errore reale (uscita non zero o risposta senza
    JSON) da mettere nel registro, invece di "nessuna correzione sicura"."""
    stdout = (stdout or "").strip()
    stderr = (stderr or "").strip()
    if returncode != 0:
        return {}, f"agente uscito con codice {returncode}: {(stdout or stderr)[:200]}"
    if "{" not in stdout:
        return {}, f"agente senza JSON: {(stdout or stderr or 'risposta vuota')[:200]}"
    return estrai_json(stdout), None


def prompt_apprendimento(grezzi) -> str:
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


def impara_sostituzioni(log_path, config_path, comando, timeout=60) -> dict:
    """Legge le dettature e registra proposte da verificare. Non osserva
    correzioni umane e non modifica le sostituzioni attive nel config."""
    grezzi = estrai_grezzi_dal_log(log_path)
    if not grezzi:
        return {}
    try:
        proposte, errore = chiedi_arbitro(comando, prompt_apprendimento(grezzi), timeout)
        if errore:
            logging.warning("apprendimento sostituzioni: agente fallito (%s)", errore)
            return {}
        cfg = json.loads(Path(config_path).read_text(encoding="utf-8"))
        proposte = unisci_sostituzioni(cfg.get("sostituzioni", {}), proposte)
        if proposte:
            logging.info(
                "apprendimento sostituzioni: proposte da verificare, non applicate: %s",
                json.dumps(proposte, ensure_ascii=False),
            )
        return proposte
    except Exception:
        logging.exception("apprendimento sostituzioni fallito")
        return {}


def impara_dagli_errori_giornaliero() -> None:
    """Raccolta di proposte, una volta al giorno all'avvio (gemello Mac)."""
    marcatore = BASE / "APPRENDIMENTO_ULTIMO"
    oggi = time.strftime("%Y-%m-%d")
    try:
        if marcatore.read_text().strip() == oggi:
            return
    except OSError:
        pass
    if not CFG.get("debug_dettature", False):
        return  # senza log dei testi non c'e' niente da cui imparare
    comando = COMANDO_APPRENDIMENTO or comandi_agente()  # tutti gli agenti presenti, in ordine
    if not comando:
        return
    impara_sostituzioni(LOG, BASE / "config.json", comando)
    # Ripasso degli audio conservati (gemello Mac): processo a parte e
    # sganciato, cosi' il secondo modello non pesa sulla dettatura in diretta.
    if int(CFG.get("conserva_audio_n", 0)) > 0:
        distacco = (
            getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            | getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )
        subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), "--ripasso"],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, creationflags=distacco,
        )
        logging.info("ripasso audio avviato in sottofondo")
    marcatore.write_text(oggi)


# --- ripasso degli audio conservati (gemello di mac/voce_lib.py) ---
# Un secondo riconoscitore ritrascrive con calma le dettature conservate;
# dove i due non sono d'accordo l'agente propone coppie nel registro.
# Nessuna proposta diventa una sostituzione attiva. Da collaudare su PC reale.

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
    """Il testo scritto in diretta per quell'audio (None se non c'e')."""
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
    """Coppie (versione_live, versione_ripasso) dove le due trascrizioni non
    sono d'accordo; punteggiatura e maiuscole non contano."""
    from difflib import SequenceMatcher

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
    """casi = [(frase_in_diretta, versione_A_live, versione_B_ripasso), ...]."""
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
    """Gemella Mac: seconda trascrizione (faster-whisper) con la stessa
    pulizia del vivo e proposte dell'agente nel registro, senza modificare
    il config. Due modelli non sostituiscono una verifica della frase."""
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
    casi = []
    modello = WhisperModel(modello_ripasso, device="cpu", compute_type="int8")
    for wav in sorted(Path(cartella).glob("dettatura_*.wav"))[-massimo_file:]:
        vivo = abbina_audio_a_grezzo(wav.name, grezzi)
        if not vivo:
            continue
        try:
            segmenti, _ = modello.transcribe(
                str(wav), language=CFG.get("language", "it"),
                initial_prompt=glossario_iniziale(CFG),
            )
            secondo = " ".join(s.text.strip() for s in segmenti).strip()
        except Exception:
            logging.exception("ripasso: trascrizione fallita su %s", wav.name)
            continue
        secondo = rimuovi_eco_glossario(secondo, CFG.get("glossario", []))
        secondo = applica_sostituzioni(secondo, CFG.get("sostituzioni", {}))
        secondo = converti_punteggiatura_dettata(secondo)
        for viva, seconda in disaccordi_parole(vivo, secondo):
            casi.append((vivo, viva, seconda))
    if not casi:
        logging.info("ripasso audio: i due riconoscitori sono d'accordo su tutto")
        return {}
    try:
        proposte, errore = chiedi_arbitro(comando, prompt_arbitro_ripasso(casi), timeout)
        if errore:
            logging.warning("ripasso audio: %d disaccordi, arbitro fallito (%s)",
                            len(casi), errore)
            return {}
        cfg = json.loads(Path(config_path).read_text(encoding="utf-8"))
        proposte = unisci_sostituzioni(cfg.get("sostituzioni", {}), proposte)
        if proposte:
            logging.info(
                "ripasso audio: proposte da verificare, non applicate: %s (da %d disaccordi)",
                json.dumps(proposte, ensure_ascii=False), len(casi),
            )
        else:
            logging.info("ripasso audio: %d disaccordi, nessuna nuova proposta", len(casi))
        return proposte
    except Exception:
        logging.exception("ripasso audio fallito")
        return {}


def pulizia_inventa_nomi(grezzo: str, pulito: str, glossario=()) -> bool:
    """Gemello della guardia Mac: nessun nome nuovo senza una forma simile."""
    from difflib import SequenceMatcher

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


def pulizia_sospetta(grezzo: str, pulito: str, glossario=()) -> bool:
    """Gemello Mac: blocca nomi inventati e variazioni oltre il 25%."""
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


def pulisci_con_agente(testo: str, comando: list, timeout=10, glossario=()):
    """Passa il dettato all'agente locale e torna il testo sistemato, oppure
    None se non ce l'ha fatta (errore, output vuoto, timeout, pulizia sospetta).

    Gemello Mac. Il chiamante fa sempre `pulito or testo`, quindi la dettatura
    non si perde MAI; in piu' cosi' la corsia SA di aver fallito e puo' mettersi
    in pausa invece di ripresentare 20s di timeout a ogni dettatura."""
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
        logging.exception("pulizia con agente fallita: tengo il grezzo")
        return None


GLOSSARIO_PROMPT = glossario_iniziale(CFG)  # nomi/brand scritti giusti da Whisper
# L'agente resta disponibile per l'apprendimento giornaliero, ma non entra piu'
# nel percorso interattivo: su Windows il testo grezzo viene incollato subito.
COMANDO_APPRENDIMENTO = comandi_agente() if CFG.get("debug_dettature", False) else None


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


def _ps_string(valore: str) -> str:
    return "'" + valore.replace("'", "''") + "'"


def _ps_voce(rate: int, voice_name: str = "") -> list[str]:
    """Comando PowerShell con System.Speech (incluso in Windows): voce italiana se c'e'."""
    script = (
        "$ErrorActionPreference='SilentlyContinue';"
        "Add-Type -AssemblyName System.Speech;"
        "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer;"
        "$wanted=" + _ps_string(voice_name) + ";"
        "$voices=@($s.GetInstalledVoices()|"
        "?{$_.Enabled -and $_.VoiceInfo.Culture.Name -like 'it*'});"
        "$v=$null;"
        "if($wanted){$v=$voices|?{$_.VoiceInfo.Name -eq $wanted}|select -First 1};"
        "if(-not $v){$v=$voices|select -First 1};"
        "if($v){$s.SelectVoice($v.VoiceInfo.Name)};"
        "$s.Volume=100;"
        "$s.Rate=" + str(int(rate)) + ";"
        "$t=[Console]::In.ReadToEnd();"
        "if($t){$s.Speak($t)}"
    )
    return ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script]


_CSHARP_MIC = (
    "using System;using System.Runtime.InteropServices;"
    '[Guid("5CDF2C82-841E-4546-9722-0CF74078229A"),'
    "InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]"
    "public interface IAudioEndpointVolume{"
    "int A();int B();int GetChannelCount(out int c);"
    "int SetMasterVolumeLevel(float l,Guid g);"
    "int SetMasterVolumeLevelScalar(float l,Guid g);"
    "int GetMasterVolumeLevel(out float l);"
    "int GetMasterVolumeLevelScalar(out float l);}"
    '[Guid("D666063F-1587-4E43-81F1-B948E807363F"),'
    "InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]"
    "public interface IMMDevice{int Activate(ref Guid iid,int ctx,IntPtr p,"
    "[MarshalAs(UnmanagedType.IUnknown)] out object o);}"
    '[Guid("A95664D2-9614-4F35-A746-DE8DB63617E6"),'
    "InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]"
    "public interface IMMDeviceEnumerator{int A();"
    "int GetDefaultAudioEndpoint(int flow,int role,out IMMDevice dev);}"
    '[ComImport,Guid("BCDE0395-E52F-467C-8E3D-C4579291692E")]'
    "public class MMDeviceEnumerator{}"
    "public class Mic{"
    "static IAudioEndpointVolume E(){"
    "IMMDeviceEnumerator e=(IMMDeviceEnumerator)(new MMDeviceEnumerator());"
    "IMMDevice d;e.GetDefaultAudioEndpoint(1,1,out d);"  # 1 = eCapture (microfono)
    "Guid iid=typeof(IAudioEndpointVolume).GUID;object o;"
    "d.Activate(ref iid,1,IntPtr.Zero,out o);return (IAudioEndpointVolume)o;}"
    "public static float Get(){float v;E().GetMasterVolumeLevelScalar(out v);return v;}"
    "public static void Set(float v){E().SetMasterVolumeLevelScalar(v,Guid.Empty);}}"
)


def script_volume_ingresso(nuovo=None) -> str:
    """Script PowerShell che legge (e se richiesto imposta) il volume del
    microfono di sistema, 0-100. Usa Core Audio via C# inline: sta dentro .NET
    di Windows, quindi niente pip sul PC del cliente — stessa scelta del TTS.
    Stampa sempre il valore RILETTO, cosi' il chiamante non si fida della
    scrittura: su alcuni device l'ingresso non e' regolabile."""
    corpo = "$ErrorActionPreference='Stop';Add-Type -TypeDefinition @\"\n" + _CSHARP_MIC + "\n\"@;"
    if nuovo is not None:
        corpo += "[Mic]::Set(%s);" % round(max(0, min(100, int(nuovo))) / 100, 4)
    return corpo + "[Math]::Round([Mic]::Get()*100)"


def _volume_ingresso(nuovo=None):
    """Esegue lo script e torna il volume riletto 0-100 (None se non si puo')."""
    try:
        esito = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-Command", script_volume_ingresso(nuovo)],
            capture_output=True, text=True, timeout=15,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return int(esito.stdout.strip())
    except Exception:
        return None


def volume_ingresso_sistema():
    """Volume d'ingresso del microfono di sistema, 0-100 (None se illeggibile)."""
    return _volume_ingresso()


def imposta_volume_ingresso(valore):
    """Rialza il volume d'ingresso e torna il valore riletto (None se fallito)."""
    return _volume_ingresso(valore)


def ripara_guadagno_ingresso(rms: float) -> bool:
    """Audio sotto soglia col volume d'ingresso abbassato: il guasto e' quello.
    Lo rialza e torna True. Gemello di mac/detta.py (caso 01/08/2026)."""
    causa, target = diagnosi_audio_muto(
        rms, volume_ingresso_sistema(), VOICE_THRESHOLD,
        GUADAGNO_INGRESSO_MINIMO, GUADAGNO_INGRESSO_TARGET,
    )
    if causa != "guadagno_basso":
        return False
    riletto = imposta_volume_ingresso(target)
    if riletto is None:
        logging.error(
            "volume d'ingresso del microfono basso e non rialzabile da qui: "
            "alzalo da Impostazioni > Sistema > Audio > Ingresso"
        )
    else:
        logging.warning(
            "volume d'ingresso del microfono era basso: rialzato a %s", riletto
        )
    return True


def allinea_volume_ingresso() -> None:
    """All'avvio: con l'ingresso sotto il minimo l'app nasce muta e sembra rotta."""
    attuale = volume_ingresso_sistema()
    if attuale is None or attuale >= GUADAGNO_INGRESSO_MINIMO:
        return
    riletto = imposta_volume_ingresso(GUADAGNO_INGRESSO_TARGET)
    logging.warning(
        "volume d'ingresso del microfono a %s all'avvio: rialzato a %s", attuale, riletto
    )


def ferma_voce() -> None:
    """Ferma il PowerShell e svuota l'attesa, conservando l'ultima risposta
    per Rileggi. Il PID e' condiviso anche dal lettore dell'hook."""
    try:
        if voce_agenti is not None:
            voce_agenti.svuota_pendenti()
    except Exception:
        logging.exception("errore svuotamento attesa voce")
    try:
        pid = PID_FILE.read_text().strip()
    except Exception:
        return
    if pid:
        subprocess.run(
            ["taskkill", "/PID", pid, "/T", "/F"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
        )
    try:
        PID_FILE.unlink()
    except Exception:
        pass


def pronuncia(testo: str) -> None:
    """Annuncio del toggle: stop esplicito, poi lo stesso lettore delle
    risposte. PowerShell diretto resta solo nelle installazioni senza hook."""
    testo = pulisci_per_voce(testo)
    if not testo:
        return
    ferma_voce()  # una voce per volta
    if voce_agenti is not None:
        voce_agenti.metti_in_lettura(testo, origine={"id": "generale", "nome": ""})
        return
    p = subprocess.Popen(
        _ps_voce(VOCE_RATE, VOCE_NOME),
        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        PID_FILE.write_text(str(p.pid))
    except Exception:
        pass
    try:
        p.stdin.write(testo.encode("utf-8"))
        p.stdin.close()  # non aspettiamo la fine: lo stop resta possibile
    except Exception:
        pass


def beep(freq: int, duration_ms: int) -> None:
    if CFG.get("sounds", True) and winsound is not None:
        try:
            winsound.Beep(freq, duration_ms)
        except RuntimeError:
            pass


def memoria_totale_gb() -> float | None:
    """La memoria fisica di questo PC in GB, o None se non si riesce a leggerla
    (fuori da Windows, o se il sistema non risponde)."""
    try:
        class _MemoriaStato(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]
        stato = _MemoriaStato()
        stato.dwLength = ctypes.sizeof(stato)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stato)):
            return stato.ullTotalPhys / 1024 ** 3
    except Exception:
        pass
    return None


def scegli_modello(cfg: dict, memoria_gb: float | None) -> tuple[str, str]:
    """P-088 su Windows (sul Mac e' voce_lib.scegli_modello della rc.30, con altre
    soglie): il modello di trascrizione adatto alla memoria di QUESTO PC,
    (modello, motivo). Sotto
    `memoria_minima_modello_gb` si usa `model_poca_memoria`; memoria illeggibile
    o nessun modello piccolo nel config = il modello standard, mai peggio di
    prima. La soglia a 0 spegne la regola."""
    modello = cfg["model"]
    piccolo = cfg.get("model_poca_memoria")
    if not piccolo or piccolo == modello or memoria_gb is None:
        return modello, "standard"
    try:
        soglia = float(cfg.get("memoria_minima_modello_gb", 6))
    except (TypeError, ValueError):
        soglia = 6.0
    if memoria_gb < soglia:
        return piccolo, f"PC con {memoria_gb:.0f} GB di memoria: modello piccolo"
    return modello, "standard"


def load_model() -> WhisperModel:
    global model
    if model is None:
        nome, motivo = scegli_modello(CFG, memoria_totale_gb())
        logging.info("carico modello faster-whisper: %s (%s)", nome, motivo)
        model = WhisperModel(
            nome,
            device=CFG.get("device", "cpu"),
            compute_type=CFG.get("compute_type", "int8"),
        )
    return model


_lock_trascrizione = threading.Lock()  # una trascrizione per volta (segmenti in sottofondo compresi)


# --- Orecchio: il riconoscitore di voce umana (gemella Mac, 31/10/2026) ---
# Idea dell'app open source Handy (github.com/cjpais/Handy, MIT). Il volume non sa se e'
# una voce: una porta, la tastiera o una ventola lo alzano uguale, e su quei secondi
# Whisper scrive «Grazie.». Silero VAD (github.com/snakers4/silero-vad, MIT, lo stesso
# `silero_vad.onnx` v6.2.3 del Mac) da' per ogni frame di 32 ms la probabilita' che ci sia
# una persona che parla. Valori di Handy: soglia 0,3; 60 ms di voce per dire «c'e' voce»;
# 450 ms tenuti prima e dopo. Prima di Whisper: niente voce = niente trascrizione, i silenzi
# lunghi si accorciano. Su Windows non ci sono le mani libere: l'orecchio serve solo qui.
# Il `vad_filter` di faster-whisper resta com'era. `"orecchio": false` torna a prima.

FILE_ORECCHIO = BASE / "silero_vad.onnx"
FRAME_ORECCHIO = 512      # campioni a 16 kHz (32 ms): la misura che il modello accetta
CONTESTO_ORECCHIO = 64    # campioni del frame prima che il modello vuole davanti a ogni frame


class ModelloOrecchio:
    """Silero VAD su onnxruntime, un thread solo (gemella Mac).

    Chiamabile: (ingresso [1, 576], stato [2, 1, 128]) -> (probabilita', stato nuovo)."""

    def __init__(self, percorso=None):
        import onnxruntime as ort  # gia' presente: faster-whisper lo usa per il suo vad_filter
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

    Tiene stato del modello e contesto tra un pezzo e l'altro, come il wrapper ufficiale."""

    def __init__(self, modello):
        self.modello = modello
        self.azzera()

    def azzera(self):
        self._stato = np.zeros((2, 1, 128), dtype=np.float32)
        self._contesto = np.zeros(CONTESTO_ORECCHIO, dtype=np.float32)
        self._resto = np.zeros(0, dtype=np.float32)

    def probabilita(self, campioni, fino_in_fondo=False):
        """Probabilita' dei frame completi; con `fino_in_fondo` anche dell'ultimo pezzo, a zeri."""
        a = np.concatenate([self._resto, np.asarray(campioni, dtype=np.float32).reshape(-1)])
        if fino_in_fondo and len(a) % FRAME_ORECCHIO:
            a = np.concatenate([a, np.zeros(FRAME_ORECCHIO - len(a) % FRAME_ORECCHIO, dtype=np.float32)])
        n = len(a) // FRAME_ORECCHIO
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

    Prudente apposta: basta UN frame sopra soglia per tenere quasi un secondo attorno.
    Restano fuori solo i silenzi oltre prima + dopo (896 ms), accorciati a quella misura."""
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
        a = np.asarray(audio, dtype=np.float32).reshape(-1)
        prob = self.probabilita(a)
        if not c_e_voce_umana(prob, self.soglia, self.attacco):
            return None, prob
        return a[maschera_voce(len(a), prob, self.soglia, self.prima, self.dopo)], prob


def carica_orecchio(cfg):
    """(orecchio o None, riga per il registro). Un guasto non ferma la Voce: Whisper sull'audio intero."""
    if not cfg.get("orecchio", True):
        return None, 'spento in config.json ("orecchio": false)'
    try:
        orecchio = Orecchio.da_config(cfg)
    except Exception as errore:
        return None, f"non caricato ({errore!r}): Whisper su tutto l'audio come prima"
    return orecchio, (f"Silero VAD caricato ({FILE_ORECCHIO.name}): soglia {orecchio.soglia:g}, "
                      f"voce dopo {orecchio.attacco} frame da 32 ms, margini {orecchio.prima}+{orecchio.dopo} frame")


ORECCHIO, ORECCHIO_STATO = carica_orecchio(CFG)


def _whisper_grezzo(audio: np.ndarray, prompt) -> str:
    """Un passaggio di faster-whisper, testo grezzo dei segmenti uniti.

    Prima di Whisper l'orecchio (gemella Mac, 31/10/2026): se nell'audio non c'e' una voce
    umana Whisper non parte; se c'e', i silenzi lunghi si accorciano lasciando 450 ms prima
    e dopo ogni voce. Passa di qui ogni audio: frase intera, segmenti della progressiva,
    coda, secondo passaggio, ritrascrizione dal menu."""
    if ORECCHIO is not None:
        partenza = time.monotonic()
        durata = len(audio) / SAMPLE_RATE
        try:
            preparato, _ = ORECCHIO.prepara(audio)
        except Exception:  # un guasto dell'orecchio non costa una dettatura: audio intero
            logging.exception("orecchio: errore, Whisper sull'audio intero")
            preparato = audio
        else:
            if preparato is None:
                logging.info("orecchio: nessuna voce in %.1fs (%.0f ms): Whisper non parte",
                             durata, (time.monotonic() - partenza) * 1000)
                return ""
            logging.info("orecchio: voce, %.1fs -> %.1fs (%.0f ms)",
                         durata, len(preparato) / SAMPLE_RATE, (time.monotonic() - partenza) * 1000)
        audio = preparato
    segments, _info = load_model().transcribe(
        audio,
        language=CFG.get("language", "it"),
        vad_filter=True,
        initial_prompt=prompt,
    )
    testo = " ".join(segment.text.strip() for segment in segments).strip()
    if CFG.get("debug_dettature", False):
        logging.info("whisper originale: %s", testo)
    return testo


def audio_fuori_scala(rms: float, massimo: float = 1.0) -> bool:
    """True se l'rms e' impossibile per uno stream float32 sano: i sample vivono
    in [-1, 1], quindi rms <= 1 sempre. Sopra = il driver ha rimappato il device
    sotto lo stream e consegna dati corrotti (caso Mac 09/07: rms 3-4 per ~20s,
    Whisper allucinava). Meglio scartare che trascrivere spazzatura."""
    return not 0.0 <= rms <= massimo  # anche NaN e infinito sono audio non valido


# Gemello della logica Mac (caso 01/08/2026, vedi mac/voce_lib.py): le soglie
# sono calibrate su un guadagno d'ingresso "normale". Se il sistema abbassa il
# volume del microfono scende tutto insieme e l'app diventa muta senza che nulla
# sia rotto. Livelli misurati su Mac; su Windows il guadagno e' la stessa scala
# percentuale, quindi valgono gli stessi due numeri.
GUADAGNO_INGRESSO_MINIMO = 60
GUADAGNO_INGRESSO_TARGET = 75

SOGLIA_GUASTI_CORSIA = 2
RIPOSO_CORSIA_SEC = 600  # 10 minuti


def corsia_utilizzabile(guasti, ultimo_guasto, ora,
                        soglia: int = 2, riposo: int = 600) -> bool:
    """Gemello Mac. La corsia di pulizia si spegne dopo `soglia` fallimenti di
    fila per non regalare 20s morti a ogni dettatura, ma deve poter TORNARE:
    dopo `riposo` secondi si riprova. Uno spegnimento senza via di ritorno, in
    un processo che vive giorni, e' uno spegnimento definitivo."""
    if guasti < soglia:
        return True
    if ultimo_guasto is None:
        return False
    return (ora - ultimo_guasto) >= riposo


def registra_esito_corsia(guasti, riuscito, ora):
    """Torna (nuovi_guasti, momento_ultimo_guasto). Un successo azzera tutto."""
    if riuscito:
        return 0, None
    return guasti + 1, ora


def diagnosi_audio_muto(rms: float, guadagno_ingresso, soglia_voce: float = 0.004,
                        minimo: int = 60, target: int = 75):
    """Audio tornato sotto soglia: di chi e' la colpa? Torna (causa, guadagno_da_impostare).

    - "guadagno_basso": il volume d'ingresso di sistema e' sceso. Si rialza e
      basta; riavviare non serve, il guadagno resta basso anche dopo.
    - "stream_muto": guadagno a posto, quindi e' lo stream del driver morto.
    Guadagno illeggibile = non lo si puo' incolpare: si ricade sul vecchio
    comportamento, mai peggio di prima."""
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
    "yeah",
    "yes",
    "bye",
    "thank you",
    "thanks for watching",
}

# Gemello di mac/voce_lib.py (P-117, 28/09/2026): le formule con cui finiscono
# i video di YouTube, su cui Whisper si e' allenato, vengono inventate sul
# parlato vero e non sempre uguali. L'elenco sopra confronta solo la stringa
# INTERA: una variante appena piu' lunga passava e partiva l'invio automatico.
# Un testo fatto SOLO di formule (le voci dell'elenco, le cortesie e i
# riferimenti al video, uniti da "e") e' un fantasma se parla del video o se
# ripete in ciclo (3 volte) la stessa frase nota; una frase vera ha sempre altre
# parole.
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


def _normalizza(testo: str) -> str:
    return re.sub(r"[\s.,;:!?\-–—\"'`…()]+", " ", testo.lower()).strip()


def _ripetizione_patologica(
    testo: str, soglia_ripetizioni: int = 8, soglia_quota: float = 0.6
) -> bool:
    """Riconosce i collassi di Whisper a parole o caratteri ripetuti."""
    parole = testo.split()
    if len(parole) >= soglia_ripetizioni:
        conteggi: dict[str, int] = {}
        for parola in parole:
            chiave = parola.lower()
            conteggi[chiave] = conteggi.get(chiave, 0) + 1
        piu_frequente = max(conteggi.values())
        if (
            piu_frequente >= soglia_ripetizioni
            and piu_frequente / len(parole) >= soglia_quota
        ):
            return True
    return re.search(r"(.)\1{%d,}" % (soglia_ripetizioni - 1), testo) is not None


def _solo_formule_di_chiusura(n: str) -> bool:
    """Gemella di mac/voce_lib.py. True se il testo normalizzato `n` e' fatto
    soltanto di formule di chiusura da video e parla del video o ripete in
    ciclo una frase nota. Una parola qualsiasi fuori dalle formule dice no:
    «Grazie a tutti per aver guardato il video che ti ho mandato» e' una frase
    vera, «Grazie mille, a presto» sono solo cortesie."""
    tessere: list[str] = []
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


def e_allucinazione(testo: str) -> bool:
    """Scarta frasi-fantasma, loro combinazioni e collassi di Whisper prima dell'incolla."""
    normalizzato = _normalizza(testo)
    if not normalizzato:
        return True
    if normalizzato in _FRASI_FANTASMA:
        return True
    if "sottotitoli" in normalizzato and (
        "a cura di" in normalizzato or "creati dalla comunit" in normalizzato
    ):
        return True
    if _solo_formule_di_chiusura(normalizzato):
        return True
    return _ripetizione_patologica(testo)


def invio_da_annullare(
    ultima_pressione: float, riferimento: float, nuova_registrazione: bool
) -> bool:
    """Qualsiasi tasto o clic fisico o nuova dettatura blocca l'Enter automatico."""
    return ultima_pressione > riferimento or nuova_registrazione


def invio_di_sal_durante_incolla(ultimo_tasto, tasto_invio, ultima_pressione, riferimento, fine_incolla):
    """Gemella Mac (30/10/2026): True se l'ultimo gesto e' un Invio premuto MENTRE
    il testo stava comparendo (dopo `riferimento`, entro la fine dell'incolla).
    Cadeva su una casella vuota e poi annullava l'Invio automatico: e' un si'.
    Un altro tasto o un clic dopo restano un annullamento."""
    if ultimo_tasto != tasto_invio or ultimo_tasto is None:
        return False
    return riferimento < ultima_pressione <= fine_incolla


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


def destinazione_agente(nome_app="", url=""):
    """True quando il testo e' destinato a una chat con un agente AI
    (gemella di mac/voce_lib.py: stesso nome, stesso contratto). Su Windows
    `nome_app` e' il titolo della finestra bersaglio piu' il nome del suo
    eseguibile: i browser mettono il titolo della pagina nel titolo della
    finestra, le app desktop e i terminali il proprio nome."""
    nome = str(nome_app or "").strip().lower()
    indirizzo = str(url or "").strip().lower()
    if any(marcatore in nome for marcatore in ("chatgpt", "claude", "codex", "antigravity", "gemini")):
        return True
    return any(
        dominio in indirizzo
        for dominio in ("chatgpt.com", "chat.openai.com", "claude.ai", "gemini.google.com")
    )


def ritardo_invio(cfg, voce_accesa, chat_ai):
    """Secondi di pausa prima dell'Invio automatico, scelti dal contesto
    (gemella di mac/voce_lib.py): voce agenti accesa = botta e risposta;
    chat AI a voce spenta = il testo si vede e parte quasi subito (dati Mac
    30/08→04/09: con la pausa dei documenti il 40% degli Invii veniva
    annullato a mano); documenti, email, social = tempo per correggere."""
    if voce_accesa:
        return float(cfg.get("invio_automatico_ritardo_conversazione_sec", 0.3))
    if chat_ai:
        return float(cfg.get("invio_automatico_ritardo_chat_ai_sec", 2.0))
    return float(cfg.get("invio_automatico_ritardo_sec", 2.5))


def has_voice(audio: np.ndarray, volte: float = 1.0) -> bool:
    """True se l'audio ha l'energia di un parlato: almeno `volte` la soglia di voce."""
    flat = np.asarray(audio, dtype="float32").reshape(-1)
    if flat.size == 0:
        return False
    return float(np.sqrt(np.mean(flat * flat))) >= VOICE_THRESHOLD * volte


guasti_cattura = set()  # soli flag PortAudio: nessun log/UI nel callback


def _avvisa_errore_audio(testo):
    eventi.put(("errore_audio", testo))


def audio_callback(indata, frames, current_time, status) -> None:
    if status.input_overflow:
        guasti_cattura.add("input_overflow")
    if status.input_underflow:
        guasti_cattura.add("input_underflow")
    blocks.append(indata.copy())
    rms = float(np.sqrt(np.mean(indata ** 2)))
    rms_blocks.append(rms)  # parallelo a blocks: serve a trovare le pause
    livelli.append(rms)     # volume per le lineette


def start_recording(pressione=None) -> None:
    """`pressione`: istante (monotonic) del tasto-detta, per il registro."""
    global blocks, rms_blocks, stream, recording, recording_started_at
    global sessione_progressiva, turno_utente_token
    if recording:
        coda_dettature.annulla_avvio()
        return
    turno_utente_token = apri_turno_utente()
    coda_dettature.apri(turno_utente_token)
    try:
        guasti_cattura.clear()
        # Gemella Mac (30/10/2026): prima microfono e segnali, poi il lavoro lento. Qui lo
        # stream si apre a ogni registrazione e un anello che tenga l'attimo prima non
        # c'e'; la voce si zittisce prima solo se l'agente sta leggendo (c'e' il suo PID),
        # perche' la sua lettura nelle casse non finisca nel messaggio.
        parlava = PID_FILE.exists()
        if parlava:
            ferma_voce()  # se l'agente sta parlando, ti zittisco: tocca a te
        blocks = []
        rms_blocks = []
        livelli.extend([0.0] * N_BARRE)
        stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="float32",
            callback=audio_callback,
        )
        stream.start()
        recording = True
        recording_started_at = time.monotonic()
        eventi.put("ascolto")
        beep(880, 80)
        if pressione is None:
            logging.info("registrazione avviata")
        else:  # quanto dopo il tasto si e' aperto il microfono: l'attacco perso si legge
            logging.info("registrazione avviata (%.2fs dopo il tasto)", recording_started_at - pressione)
        if not parlava:
            ferma_voce()  # svuota l'attesa: nessuna lettura parte sopra la dettatura
        # mentre si parla, la finestra davanti accende il suo albero UI Automation
        threading.Thread(target=_sveglia_accessibilita, args=(finestra_frontale(),), daemon=True).start()
        if PROGRESSIVA:
            sessione_progressiva = SessioneProgressiva(blocks, rms_blocks)
            sessione_progressiva.avvia()
    except Exception:
        recording = False
        _avvisa_errore_audio("Microfono non disponibile: ripeti.")
        _concludi_dettatura(turno_utente_token, fallita=True)
        turno_utente_token = None
        raise


def finestra_frontale():
    """Handle della finestra in primo piano ORA: e' il bersaglio del testo
    dettato (gemello di app_frontale() in mac/detta.py)."""
    try:
        return ctypes.windll.user32.GetForegroundWindow()
    except Exception:
        return None


def nome_finestra(hwnd) -> str:
    """Titolo della finestra bersaglio + nome del suo eseguibile: e' quello
    che destinazione_agente() legge per riconoscere una chat AI (gemello di
    localizedName() + scheda del browser su Mac)."""
    if not hwnd:
        return ""
    parti = []
    try:
        user32 = ctypes.windll.user32
        titolo = ctypes.create_unicode_buffer(512)
        user32.GetWindowTextW(hwnd, titolo, 512)
        parti.append(titolo.value)
        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        processo = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid.value)  # QUERY_LIMITED_INFORMATION
        if processo:
            try:
                percorso = ctypes.create_unicode_buffer(1024)
                lunghezza = ctypes.c_ulong(1024)
                if ctypes.windll.kernel32.QueryFullProcessImageNameW(
                    processo, 0, percorso, ctypes.byref(lunghezza)
                ):
                    parti.append(Path(percorso.value).stem)
            finally:
                ctypes.windll.kernel32.CloseHandle(processo)
    except Exception:
        logging.exception("impossibile leggere la finestra bersaglio")
    return " ".join(p for p in parti if p)


def riattiva_bersaglio(hwnd) -> None:
    """Se nel frattempo (dettatura lunga + pulizia) Sal cambia finestra, il
    testo deve arrivare comunque li' dove parlava, non dove si trova ora il
    focus. Riporta avanti la finestra-bersaglio prima di incollare."""
    if not hwnd:
        return
    try:
        if ctypes.windll.user32.GetForegroundWindow() == hwnd:
            return
        ctypes.windll.user32.SetForegroundWindow(hwnd)
        time.sleep(0.2)  # tempo al focus di spostarsi davvero prima del Ctrl+V
    except Exception:
        logging.exception("impossibile riattivare la finestra bersaglio")


# --- se davanti non c'e' dove scrivere, il testo torna nell'ultima chat AI ---
# Gemella del Mac (18/09/2026): due dettature per Claude fatte con Gmail
# davanti (nessuna casella) erano finite alla cieca e perse. L'ultima chat AI
# dove una dettatura e' arrivata e' la base di chi parla con un agente: se la
# finestra davanti e' leggibile e non ha caselle, si torna li'.
_ultima_chat_ai = None  # handle dell'ultima chat AI dove il testo e' arrivato


def finestra_viva(hwnd) -> bool:
    """True se la finestra esiste ancora: una chat chiusa non e' una riserva."""
    try:
        return bool(hwnd) and bool(ctypes.windll.user32.IsWindow(hwnd))
    except Exception:
        return False


def _bersaglio_di_riserva(hwnd, chat_agente):
    """L'ultima chat AI usata, se e' un'altra finestra da `hwnd` ed e' ancora
    aperta; None se non c'e' o se il bersaglio e' gia' una chat AI (li' il
    testo arriva comunque, anche senza casella leggibile)."""
    if chat_agente or not _ultima_chat_ai or _ultima_chat_ai == hwnd:
        return None
    return _ultima_chat_ai if finestra_viva(_ultima_chat_ai) else None


# --- cursore automatico nella casella (gemello Mac, richiesta 29/08/2026) ---
# Riattivare la finestra non basta se dentro nessuna casella di testo ha il
# focus: il Ctrl+V cadrebbe nel vuoto e il proprietario dovrebbe prendere il
# mouse. Qui, via UI Automation di Windows, si controlla dove sta il focus e,
# se non e' una casella, il click nella casella di scrittura lo fa l'app.

_UIA_EDIT, _UIA_DOCUMENT = 50004, 50030  # ControlType: Edit, Document
_UIA_PROP_CONTROLTYPE = 30003
_UIA_SCOPE_DISCENDENTI = 4
# Gemella di AX_ATTESA_RISVEGLIO_SEC del Mac (17/09/2026): le app Chromium/
# Electron costruiscono l'albero UI Automation solo dopo il primo tocco. Se il
# primo giro e' vuoto si aspetta questo tempo e si riguarda una volta.
ATTESA_RISVEGLIO_SEC = 0.5
GIRI_RISVEGLIO = 5    # giri di ricerca in tutto: al massimo due secondi in piu'
# Dove stava la casella l'ultima volta, per finestra e taglia: se l'albero resta
# addormentato dopo tutti i giri si clicca li' (gemella del Mac, 17/09/2026).
# Vive anche su file accanto all'app: a ogni riavvio l'app riparte gia' istruita.
_caselle_ricordate = {}
FILE_CASELLE_RICORDATE = BASE / "caselle_ricordate.json"


def _carica_caselle_ricordate():
    try:
        _caselle_ricordate.update(caselle_da_json(FILE_CASELLE_RICORDATE.read_text(encoding="utf-8")))
    except OSError:
        pass  # prima volta: nessuna memoria


def _salva_caselle_ricordate():
    try:
        FILE_CASELLE_RICORDATE.write_text(caselle_in_json(_caselle_ricordate), encoding="utf-8")
    except OSError:
        logging.warning("memoria delle caselle non salvata: %s", FILE_CASELLE_RICORDATE)


_carica_caselle_ricordate()


def _geo_rett(r):
    """(x, y, larghezza, altezza) da un rettangolo UI Automation."""
    return (r.left, r.top, r.right - r.left, r.bottom - r.top)


def _ricorda_casella(nome, geo_finestra, geo_casella):
    chiave = chiave_casella(nome, geo_finestra)
    relativa = posizione_relativa(geo_finestra, geo_casella) if geo_finestra and geo_casella else None
    if chiave is None or relativa is None:
        return
    nuova = chiave not in _caselle_ricordate
    if nuova:
        logging.info("cursore automatico: casella ricordata per %s (finestra %sx%s)", *chiave)
    if nuova or _caselle_ricordate[chiave] != relativa:
        _caselle_ricordate[chiave] = relativa
        _salva_caselle_ricordate()


def _punto_ricordato(nome, geo_finestra):
    relativa = _caselle_ricordate.get(chiave_casella(nome, geo_finestra))
    return punto_da_relativa(geo_finestra, relativa) if relativa else None


def _click_sintetico(x, y):
    """Click del programma nel punto (coordinate schermo); poi il puntatore
    torna dov'era, cosi' chi detta non se ne accorge (gemello del Mac)."""
    class _Punto(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

    user32 = ctypes.windll.user32
    prima = _Punto()
    user32.GetCursorPos(ctypes.byref(prima))
    user32.SetCursorPos(int(x), int(y))
    user32.mouse_event(0x0002, 0, 0, 0, 0)  # MOUSEEVENTF_LEFTDOWN
    user32.mouse_event(0x0004, 0, 0, 0, 0)  # MOUSEEVENTF_LEFTUP
    user32.SetCursorPos(prima.x, prima.y)


def _client_uia():
    """Client UI Automation (COM via comtypes), creato al bisogno. None fuori
    da Windows o senza comtypes: si rinuncia e resta il comportamento di prima."""
    try:
        import comtypes.client
        comtypes.client.GetModule("UIAutomationCore.dll")
        from comtypes.gen.UIAutomationClient import CUIAutomation, IUIAutomation
        return comtypes.client.CreateObject(CUIAutomation, interface=IUIAutomation)
    except Exception:
        return None


def _sveglia_accessibilita(hwnd):
    """Gemella del Mac: al tasto premuto tocca l'albero UI Automation della
    finestra davanti in un thread a parte, cosi' le app Chromium/Electron lo
    costruiscono mentre si parla e al rilascio la casella e' gia' visibile.
    Non tocca niente sullo schermo; qualsiasi intoppo viene ignorato."""
    if not hwnd or not CFG.get("cursore_automatico", True):
        return
    try:
        try:
            import comtypes
            comtypes.CoInitialize()  # COM va inizializzato nel thread che lo usa
        except Exception:
            pass
        uia = _client_uia()
        if uia is None:
            return
        fuoco = uia.GetFocusedElement()
        if fuoco is not None and fuoco.CurrentControlType in (_UIA_EDIT, _UIA_DOCUMENT):
            return
        radice = uia.ElementFromHandle(hwnd)
        condizione = uia.CreateOrCondition(
            uia.CreatePropertyCondition(_UIA_PROP_CONTROLTYPE, _UIA_EDIT),
            uia.CreatePropertyCondition(_UIA_PROP_CONTROLTYPE, _UIA_DOCUMENT),
        )
        radice.FindAll(_UIA_SCOPE_DISCENDENTI, condizione)
    except Exception:
        logging.debug("sveglia accessibilita' fallita", exc_info=True)


def metti_cursore_in_casella(hwnd):
    """Se nella finestra bersaglio nessuna casella di testo ha il focus, mette
    il cursore nella casella di scrittura (la piu' in basso: nelle chat sta in
    fondo). Qualsiasi intoppo = si lascia tutto com'era.
    Torna True se un posto dove scrivere c'e', False SOLO quando la finestra
    e' leggibile e di caselle non ce n'e' proprio, None quando non si sa.
    (Gemella di metti_cursore_in_casella in mac/detta.py; da collaudare su
    PC Windows reale come il resto della versione Windows.)"""
    if not hwnd or not CFG.get("cursore_automatico", True):
        return None
    try:
        uia = _client_uia()
        if uia is None:
            return None
        nome = nome_finestra(hwnd)
        radice = uia.ElementFromHandle(hwnd)
        rett_finestra = radice.CurrentBoundingRectangle
        geo_finestra = _geo_rett(rett_finestra)
        altezza_finestra = geo_finestra[3]

        def a_fuoco():
            fuoco = uia.GetFocusedElement()
            if fuoco is not None and fuoco.CurrentControlType in (_UIA_EDIT, _UIA_DOCUMENT):
                _ricorda_casella(nome, geo_finestra, _geo_rett(fuoco.CurrentBoundingRectangle))
                return True
            return False

        if a_fuoco():
            return True  # il cursore e' gia' in una casella
        condizione = uia.CreateOrCondition(
            uia.CreatePropertyCondition(_UIA_PROP_CONTROLTYPE, _UIA_EDIT),
            uia.CreatePropertyCondition(_UIA_PROP_CONTROLTYPE, _UIA_DOCUMENT),
        )

        def caselle():
            trovate = radice.FindAll(_UIA_SCOPE_DISCENDENTI, condizione)
            candidate = []
            for i in range(trovate.Length):
                elemento = trovate.GetElement(i)
                r = elemento.CurrentBoundingRectangle
                # parte bassa della finestra (chat) o area alta almeno meta'
                # finestra (documento): mai le barre in alto, che sono alte poco
                if not casella_ammissibile(
                    r.top, r.bottom - r.top, rett_finestra.top, altezza_finestra
                ):
                    continue
                candidate.append((elemento, (r.top, r.right - r.left), _geo_rett(r)))
            return candidate

        candidate = caselle()
        scelta = scegli_casella([c[1] for c in candidate])
        giri = 1
        while scelta is None and giri < GIRI_RISVEGLIO:
            # guscio vuoto di un'app Chromium/Electron appena toccata? si
            # aspetta che l'albero si accenda e si riguarda
            time.sleep(ATTESA_RISVEGLIO_SEC)
            giri += 1
            if a_fuoco():
                logging.info("cursore automatico: casella gia' a fuoco, vista al giro %s", giri)
                return True
            candidate = caselle()
            scelta = scegli_casella([c[1] for c in candidate])
            if scelta is not None:
                logging.info("cursore automatico: casella trovata al giro %s", giri)
        if scelta is None:
            # finestra ancora addormentata: si clicca dove stava la casella
            # l'ultima volta in una finestra di questa taglia, se la si e' vista
            punto = _punto_ricordato(nome, geo_finestra)
            if punto is not None:
                logging.info("cursore automatico: finestra addormentata dopo %s giri, "
                             "click dove stava la casella l'ultima volta", giri)
                _click_sintetico(*punto)
                time.sleep(0.15)
                return True
            logging.info("cursore automatico: nessuna casella di testo nella finestra (%s giri)", giri)
            return False
        elemento = candidate[scelta][0]
        _ricorda_casella(nome, geo_finestra, candidate[scelta][2])
        elemento.SetFocus()
        time.sleep(0.1)
        logging.info("cursore automatico: messo nella casella di scrittura")
        return True
    except Exception:
        logging.exception("cursore automatico fallito: incollo dove sta il focus")
        return None


def stop_recording() -> None:
    global stream, recording, recording_started_at, sessione_progressiva
    global turno_utente_token, _ultima_registrazione
    token_turno, turno_utente_token = turno_utente_token, None
    try:
        if not recording:
            _concludi_dettatura(token_turno)
            return
        finestra_bersaglio = finestra_frontale()  # bersaglio: la finestra davanti ORA, non a fine pulizia
        recording = False
        _ultima_registrazione = time.monotonic()  # Esc butta ancora il testo finche' non e' incollato
        sessione, sessione_progressiva = sessione_progressiva, None
        if sessione is not None:
            sessione.ferma()  # niente nuovi tagli: la coda la fa il thread di incolla
        started = recording_started_at
        recording_started_at = None
        if stream is not None:
            stream.stop()
            stream.close()
            stream = None
        logging.info("registrazione fermata")
        beep(660, 80)

        if guasti_cattura:
            logging.warning("cattura interrotta: %s", ", ".join(sorted(guasti_cattura)))
            _avvisa_errore_audio("Audio interrotto: ripeti.")
            _concludi_dettatura(token_turno, fallita=True)
            return

        if not blocks or started is None:
            _concludi_dettatura(token_turno)
            eventi.put("nascosto")
            return
        duration = time.monotonic() - started
        if duration < MIN_RECORDING_SEC:
            _concludi_dettatura(token_turno)
            eventi.put("nascosto")
            return

        audio = np.concatenate(blocks, axis=0)[:, 0]
        rms = float(np.sqrt(np.mean(audio ** 2)))
        if audio_fuori_scala(rms):  # sample fuori [-1,1]: stream corrotto, Whisper allucinerebbe
            logging.warning("scartato: audio fuori scala (rms %.2f > 1), stream corrotto", rms)
            _avvisa_errore_audio("Audio non valido: ripeti.")
            _concludi_dettatura(token_turno, fallita=True)
            eventi.put("nascosto")
            return
        if not has_voice(audio):
            # il Mac lo scriveva, qui si scartava in silenzio: senza questa riga
            # una dettatura persa non lasciava alcuna traccia da diagnosticare.
            logging.info("scartato: volume sotto soglia (mic muto/occupato?)")
            _avvisa_errore_audio("Non ho sentito: ripeti.")
            _concludi_dettatura(token_turno)  # niente da perdere: non trattiene il messaggio (30/10/2026)
            eventi.put("nascosto")
            ripara_guadagno_ingresso(rms)
            return

        eventi.put("trascrivo")
        threading.Thread(
            target=transcribe_and_paste,
            args=(audio, finestra_bersaglio, sessione, token_turno), daemon=True,
        ).start()
    except Exception:
        logging.getLogger("voce").exception("errore chiusura registrazione")
        recording = False
        recording_started_at = None
        if sessione_progressiva is not None:
            sessione_progressiva.ferma()
            sessione_progressiva = None
        _avvisa_errore_audio("Microfono non disponibile: ripeti.")
        _concludi_dettatura(token_turno, fallita=True)


class SessioneProgressiva:
    """Trascrizione a segmenti MENTRE si registra (gemella Mac, 04/09/2026).

    Un thread di sottofondo guarda i volumi per blocco (rms_blocks) e, quando
    il segmento aperto supera trascrizione_progressiva_blocco_sec e cade su
    una pausa di 0,5s (trova_taglio), trascrive quel segmento sotto
    _lock_trascrizione, passando a Whisper glossario + coda del testo
    precedente. Legge solo fette della lista blocks per indice: mai il
    callback audio ne' il thread tastiera. Al rilascio _trascrivi_con_sessione
    aspetta il segmento in corso, trascrive solo la coda e rincolla. Un
    errore in sottofondo alza `guasta`: si torna al passaggio unico."""

    def __init__(self, blocks_ref, rms_ref):
        self.blocks = blocks_ref
        self.rms = rms_ref
        self.campioni = []      # numero di campioni per blocco (cresce con blocks)
        self.inizio_segmento = 0
        self.pezzi = []
        self.guasta = False
        self.fermata = threading.Event()
        self.thread = threading.Thread(target=self._lavora, daemon=True)

    def avvia(self):
        self.thread.start()

    def ferma(self):
        self.fermata.set()

    def _lavora(self):
        while not self.fermata.is_set():
            time.sleep(0.2)
            n = min(len(self.blocks), len(self.rms))
            for b in self.blocks[len(self.campioni):n]:
                self.campioni.append(len(b))
            taglio = trova_taglio(
                self.rms, self.campioni, self.inizio_segmento, SAMPLE_RATE,
                PROGRESSIVA_SOGLIA_SILENZIO, blocco_min_sec=PROGRESSIVA_BLOCCO_SEC,
            )
            if taglio is None or self.fermata.is_set():
                continue
            inizio, self.inizio_segmento = self.inizio_segmento, taglio
            try:
                segmento = np.concatenate(self.blocks[inizio:taglio], axis=0)[:, 0]
                prompt = prompt_con_contesto(GLOSSARIO_PROMPT, self.pezzi[-1] if self.pezzi else "")
                partenza = time.monotonic()
                with _lock_trascrizione:
                    testo = _whisper_grezzo(segmento, prompt)
                testo = rimuovi_eco_glossario(testo, CFG.get("glossario", []))
                self.pezzi.append(testo)
                logging.info(
                    "progressiva: segmento %d (%.1fs) trascritto in %.1fs, %d parole",
                    len(self.pezzi), len(segmento) / SAMPLE_RATE, time.monotonic() - partenza,
                    len(testo.split()),
                )
            except Exception:
                logging.exception("progressiva: errore sul segmento, torno al passaggio unico")
                self.guasta = True
                return


# Gemelle del Mac: un secondo passaggio solo su un parlato vero (dai 3 secondi e
# da 5 volte la soglia di voce); i colpi e i rumori brevi no.
SECONDO_PASSAGGIO_MIN_SEC = 3.0
SECONDO_PASSAGGIO_ENERGIA = 5  # volte la soglia di voce


def _passaggio_unico(audio: np.ndarray) -> str:
    """Un passaggio Whisper sull'intero audio, col glossario, eco gia' tolto.
    Gemella di trascrivi() del Mac (P-117, 28/09/2026): se esce una
    frase-fantasma su un parlato vero (almeno 3 secondi, energia da parlato), il
    colpevole e' quasi sempre il prompt del glossario; un secondo passaggio, una
    volta sola, senza. Se anche il secondo e' un fantasma, o va in errore, torna
    il primo e il chiamante lo scarta. Da chiamare col lock di trascrizione
    preso."""
    glossario = CFG.get("glossario", [])
    testo = rimuovi_eco_glossario(_whisper_grezzo(audio, GLOSSARIO_PROMPT), glossario)
    if (GLOSSARIO_PROMPT and testo.strip() and e_allucinazione(testo)
            and len(audio) >= SECONDO_PASSAGGIO_MIN_SEC * SAMPLE_RATE
            and has_voice(audio, SECONDO_PASSAGGIO_ENERGIA)):
        logging.info("frase-fantasma su un parlato (%.1fs): secondo passaggio senza glossario", len(audio) / SAMPLE_RATE)
        try:
            riprovato = rimuovi_eco_glossario(_whisper_grezzo(audio, None), glossario)
        except Exception:
            logging.exception("secondo passaggio senza glossario fallito")
            return testo
        if riprovato.strip() and not e_allucinazione(riprovato):
            logging.info("secondo passaggio senza glossario: testo vero (%d parole)", len(riprovato.split()))
            return riprovato
    return testo


class TrascrizioneIncompleta(RuntimeError):
    def __init__(self, testo):
        super().__init__("Riconoscimento incompleto")
        self.testo = testo


def _trascrivi_con_sessione(audio: np.ndarray, sessione) -> str:
    """Testo grezzo (eco del glossario gia' tolto) dell'audio intero. Senza
    sessione, o senza segmenti chiusi (dettature sotto ~12s), e' il percorso
    di sempre: un solo passaggio Whisper. Altrimenti si trascrive solo la coda
    dall'ultimo taglio e si rincolla."""
    if sessione is not None:
        sessione.ferma()
        sessione.thread.join(timeout=120)  # FUORI dal lock: il segmento in corso lo vuole
    if sessione is None or sessione.guasta or not sessione.pezzi or sessione.thread.is_alive():
        with _lock_trascrizione:
            return _passaggio_unico(audio)
    coperti = sum(sessione.campioni[:sessione.inizio_segmento])
    if coperti > len(audio):
        logging.warning("progressiva: segmenti oltre l'audio (%d > %d), passaggio unico", coperti, len(audio))
        with _lock_trascrizione:
            return _passaggio_unico(audio)
    coda = audio[coperti:]
    pezzi = list(sessione.pezzi)
    partenza = time.monotonic()
    with _lock_trascrizione:
        if len(coda) >= SAMPLE_RATE * 0.2 and has_voice(coda):
            prompt = prompt_con_contesto(GLOSSARIO_PROMPT, pezzi[-1])
            pezzi.append(rimuovi_eco_glossario(_whisper_grezzo(coda, prompt), CFG.get("glossario", [])))
    if any(not p.strip() or e_allucinazione(p) for p in pezzi):
        logging.warning("progressiva: segmento senza testo affidabile, riprovo l'audio intero")
        validi = [p for p in pezzi if p.strip() and not e_allucinazione(p)]
        affidabile = unisci_segmenti(validi, CFG.get("glossario", []))
        try:
            with _lock_trascrizione:
                recuperato = _passaggio_unico(audio)
        except Exception as errore:
            raise TrascrizioneIncompleta(affidabile) from errore
        if recuperato.strip() and not e_allucinazione(recuperato):
            return recuperato
        raise TrascrizioneIncompleta(affidabile)
    logging.info(
        "progressiva: %d segmenti in sottofondo, coda %.1fs trascritta in %.1fs",
        len(sessione.pezzi), len(coda) / SAMPLE_RATE, time.monotonic() - partenza,
    )
    return unisci_segmenti(pezzi, CFG.get("glossario", []))


def transcribe_and_paste(
    audio: np.ndarray, finestra_bersaglio, sessione=None, token_turno=None,
) -> None:
    fallita = False
    text = ""
    try:
        if coda_dettature.annullato(token_turno):  # Esc prima che partisse Whisper: niente lavoro
            logging.info("dettatura annullata con Esc: Whisper non parte")
            return
        try:
            conservato = salva_audio_recente(
                audio, BASE / "audio_recenti",
                CFG.get("conserva_audio_n", 0), freq=SAMPLE_RATE,
            )
            if conservato:
                logging.info("audio conservato: %s", conservato)  # percorso intero
        except Exception:
            logging.exception("conservazione audio fallita")
        text = _trascrivi_con_sessione(audio, sessione)
        if e_allucinazione(text):
            logging.info("scartato come allucinazione (%d caratteri)", len(text))
            text = ""
        if not text.strip():
            # gemella Mac (30/10/2026): niente di usabile non e' un guasto, non trattiene
            # il messaggio; i guasti veri sospendono ancora l'Invio
            _avvisa_errore_audio("Non ho riconosciuto: ripeti.")
        if CFG.get("debug_dettature", False) and text:
            logging.info("grezzo: %s", text)
        text = applica_sostituzioni(text, CFG.get("sostituzioni", {}))
        text = converti_punteggiatura_dettata(text)
        chat_agente = destinazione_agente(nome_finestra(finestra_bersaglio))
        logging.info(
            "trascritto: %d parole%s",
            len(text.split()),
            " (chat agente)" if text and chat_agente else "",
        )
        # Windows non ha una corsia locale rapida equivalente al Comando
        # Rapido Apple. Il vecchio ripiego Claude/Codex poteva bloccare ogni
        # dettatura per 20s: ora il grezzo viene incollato subito.
        if CFG.get("debug_dettature", False) and text:
            logging.info("postcorrezioni: %s", text)
        if not coda_dettature.annullato(token_turno):
            ultime_dettature.pezzo(token_turno, audio, text)  # menu Voce: solo in memoria
    except TrascrizioneIncompleta as errore:
        text = converti_punteggiatura_dettata(applica_sostituzioni(errore.testo, CFG.get("sostituzioni", {})))
        fallita = True
        if not coda_dettature.annullato(token_turno):
            ultime_dettature.pezzo(token_turno, audio, text)
        _avvisa_errore_audio("Testo incompleto: controlla prima di inviare.")
    except Exception:
        logging.exception("errore trascrizione")
        text = ""
        fallita = True
        _avvisa_errore_audio("Trascrizione fallita: ripeti.")
    finally:
        _concludi_dettatura(token_turno, text, finestra_bersaglio, fallita)


def _concludi_dettatura(token, testo="", bersaglio=None, fallita=False):
    coda_dettature.completa(token, testo, bersaglio, fallita)
    threading.Thread(target=_consegna_dettature, daemon=True).start()


def _consegna_dettature():
    coda_dettature.consegna_pronte(_incolla_messaggio, chiudi_turno_utente)
    if not recording and not coda_dettature.occupata():
        eventi.put("nascosto")


# --- Controllo di consegna (02/10/2026, gemella del Mac, da un'idea di una cliente) ---
# Dopo l'Invio automatico si guarda nel registro di Claude Code se il messaggio e'
# arrivato; se no si ripreme Invio e poi si reincolla (logica in verifica_consegna).
# Il registro esiste solo per le chat di Claude Code: in una chat normale (o nel
# browser) un messaggio arrivato non vi compare mai. Per questo il recupero scatta
# solo se questo programma, nell'ultima mezz'ora, ha gia' consegnato un messaggio
# visto nel registro: altrimenti si registra l'esito e basta, senza un messaggio doppio.
_consegne_confermate: dict[str, float] = {}  # eseguibile -> istante (monotonic) dell'ultima consegna vista


def _eseguibile_finestra(hwnd) -> str:
    """Il nome del programma della finestra (l'ultima parola di nome_finestra), in minuscolo."""
    parti = nome_finestra(hwnd).split()
    return parti[-1].lower() if parti else ""


def _app_con_registro(hwnd) -> bool:
    return bool(hwnd) and _eseguibile_finestra(hwnd) in [
        str(n).lower() for n in CFG.get("verifica_consegna_app", ["Claude"])]


def _controlla_consegna(testo, hwnd, chat_agente) -> None:
    """Dopo l'Invio automatico: se il messaggio e' per Claude Code, parte la verifica su un thread a parte."""
    if not (CFG.get("verifica_consegna", True) and testo and chat_agente and _app_con_registro(hwnd)):
        return
    threading.Thread(target=_verifica_consegna, args=(testo, hwnd, time.time() - 2.0), daemon=True).start()


def _verifica_consegna(testo, hwnd, dal) -> None:
    eseguibile = _eseguibile_finestra(hwnd)
    try:
        finestra = float(CFG.get("verifica_consegna_storico_min", 30)) * 60
        recupero = time.monotonic() - _consegne_confermate.get(eseguibile, -1e9) < finestra
        riferimento = time.monotonic()

        def puo_intervenire() -> bool:
            # Sal ha ripreso la tastiera, sta dettando o e' andato in un'altra finestra: non ci si intromette
            if (recording or key_down or ultima_pressione_utente > riferimento
                    or coda_dettature.occupata()):
                return False
            return finestra_frontale() == hwnd

        def ripremi_invio() -> None:
            riattiva_bersaglio(hwnd)
            keyboard_controller.press(Key.enter)
            keyboard_controller.release(Key.enter)

        def reincolla() -> None:
            riattiva_bersaglio(hwnd)
            metti_cursore_in_casella(hwnd)
            paste_text(testo + " ")
            time.sleep(0.3)
            keyboard_controller.press(Key.enter)
            keyboard_controller.release(Key.enter)

        esito = verifica_consegna(
            testo, dal, messaggio_in_registri, puo_intervenire, ripremi_invio, reincolla,
            recupero_ammesso=recupero, traccia=logging.warning,
        )
        if esito in ("arrivato", "recuperato"):
            _consegne_confermate[eseguibile] = time.monotonic()
        if esito == "recuperato":
            logging.info("consegna: recuperata")
        elif esito == "non_confermato":
            logging.info("consegna: non risulta nel registro di Claude Code (nessuna conferma negli ultimi %d minuti: non intervengo)",
                         round(finestra / 60))
        elif esito == "annullato":
            logging.info("consegna: non risulta in chat, ma Sal ha ripreso la mano: non intervengo")
        elif esito == "persa":
            logging.warning("consegna: il messaggio non risulta in chat dopo due tentativi")
    except Exception:
        logging.exception("errore nel controllo di consegna")


def _segui_registri() -> None:
    """Voce insieme alla scrittura (gemella del Mac, 02/10/2026): legge ogni blocco di
    testo dell'agente appena e' completo, non a lavoro finito. Parla solo se la voce e'
    accesa; il gancio di fine risposta resta e non rilegge cio' che e' gia' stato letto."""
    if voce_agenti is None or not hasattr(voce_agenti, "SeguiRegistro"):
        return
    try:
        voce_agenti.SeguiRegistro(
            traccia_fn=lambda m: logging.info("voce agenti: %s", m),
        ).esegui(threading.Event())
    except Exception:
        logging.exception("voce insieme alla scrittura: non parte")


def _incolla_messaggio(text, finestra_bersaglio, revisione):
    global _ultima_chat_ai
    # gemella Mac (23/09/2026): da qui un tasto o un clic fisico ferma
    # l'Invio, anche mentre il testo compare; quelli del programma no
    riferimento = time.monotonic()
    chat_agente = destinazione_agente(nome_finestra(finestra_bersaglio))
    try:
        riattiva_bersaglio(finestra_bersaglio)
        casella = metti_cursore_in_casella(finestra_bersaglio)
        riserva = _bersaglio_di_riserva(finestra_bersaglio, chat_agente) if casella is False else None
        if riserva is not None:
            # davanti non c'e' dove scrivere: il testo torna nell'ultima chat
            # AI, dove si stava parlando (gemella del Mac, 18/09/2026)
            finestra_bersaglio = riserva
            chat_agente = True  # e' una chat AI per costruzione (vedi _ultima_chat_ai)
            logging.info("cursore automatico: davanti non c'e' dove scrivere, torno alla chat %s",
                         nome_finestra(finestra_bersaglio))
            riattiva_bersaglio(finestra_bersaglio)
            casella = metti_cursore_in_casella(finestra_bersaglio)
        senza_casella = casella is False  # finestra letta: di caselle non ce n'e'
        if coda_dettature.consegna_annullata():  # Esc mentre si cercava la casella (gemella Mac)
            logging.info("dettatura annullata con Esc: niente incolla, niente Invio")
            return False
        if text:
            paste_text(text + " ", conserva_appunti=senza_casella)
            ultime_dettature.consegnata(text)  # menu Voce: «Copia l'ultima dettatura»
        coda_dettature.incollato()  # da qui Esc torna all'app: il testo e' gia' nella casella
        fine_incolla = time.monotonic()  # da qui il testo e' nella casella: un Invio di Sal lo vede
        if senza_casella:
            # incolla alla cieca: il testo resta negli Appunti (Ctrl+V dove
            # serve) e il beep avvisa che la frase NON e' arrivata
            if winsound is not None:
                winsound.MessageBeep(winsound.MB_ICONHAND)
            logging.info("incollato alla cieca: testo conservato negli Appunti")
        if chat_agente:
            _ultima_chat_ai = finestra_bersaglio
        # gemella Mac: la riga «incollato» c'e' sempre, anche col registro dettagliato
        # spento, cosi' chi cerca testi scritti da soli li trova (P-190, 17/10/2026)
        # solo il programma (ultima parola di nome_finestra), mai il titolo: come l'app sul Mac
        logging.info("incollato (programma bersaglio: %s)",
                     (nome_finestra(finestra_bersaglio).rsplit(" ", 1)[-1] or "sconosciuto")
                     if finestra_bersaglio else "nessuno")
        # gemella Mac (23/09/2026): il testo e' arrivato, la pill si chiude
        # adesso e non dopo l'Invio; se un altro pezzo e' in arrivo resta aperta.
        if not recording and not coda_dettature.occupata():
            eventi.put("nascosto")
        # invio automatico: parte sempre. La pausa prima dell'Invio dipende
        # dal contesto: a voce ON e' conversazione vera con l'agente (botta e
        # risposta); in una chat AI a voce OFF il testo si vede e parte quasi
        # subito (dati Mac 30/08→04/09: con la pausa dei documenti il 40%
        # degli Invii veniva annullato a mano); nei documenti serve tempo per
        # correggere il testo incollato.
        # Gemella del Mac (13/09/2026): in una chat AI riconosciuta l'Invio
        # parte anche senza casella leggibile. Il Ctrl+V e' gia' andato in
        # quel punto: o il testo e' nella casella e l'Invio lo manda, o non
        # c'e' niente da mandare. Fuori dalle chat AI resta la prudenza.
        if INVIO_AUTOMATICO and (not senza_casella or chat_agente):
            attesa = ritardo_invio(CFG, voce_attiva(), chat_agente)
            inizio_attesa = time.monotonic()
            trascorso = 0.0
            while True:
                annullato = (invio_da_annullare(ultima_pressione_utente, riferimento, recording)
                             or key_down or not coda_dettature.puo_inviare(revisione)
                             or coda_dettature.consegna_annullata())  # Esc arrivato durante l'incolla
                if annullato or trascorso >= attesa:
                    break
                time.sleep(min(0.1, attesa - trascorso))
                trascorso = time.monotonic() - inizio_attesa
            if annullato:
                if coda_dettature.consegna_annullata():
                    logging.info("invio automatico ANNULLATO (Esc)")
                    return False
                if (not key_down and not recording
                        and invio_di_sal_durante_incolla(ultimo_tasto_utente, Key.enter, ultima_pressione_utente,
                                                         riferimento, fine_incolla)
                        and coda_dettature.puo_inviare(revisione)):
                    # gemella Mac (Sal, 30/10/2026: «vedo che succede qualcosa e non
                    # invia, mi rimane la chat aperta»): l'Invio premuto mentre il
                    # testo compariva e' un si', la frase parte subito.
                    keyboard_controller.press(Key.enter)
                    keyboard_controller.release(Key.enter)
                    logging.info("invio automatico premuto (Invio di Sal arrivato mentre il testo compariva)")
                    _controlla_consegna(text, finestra_bersaglio, chat_agente)
                    return False
                logging.info(
                    "invio automatico ANNULLATO "
                    "(tasto, clic o nuova dettatura in corso)"
                )
                return revisione >= 0 and not coda_dettature.puo_inviare(revisione)
            else:
                keyboard_controller.press(Key.enter)
                keyboard_controller.release(Key.enter)
                logging.info("invio automatico premuto (attesa %.1fs%s)",
                             attesa, ", chat AI" if chat_agente else "")
                _controlla_consegna(text, finestra_bersaglio, chat_agente)
        print("Inserito:", text)
    except Exception:
        logging.exception("errore trascrizione/incolla")
        print("Errore durante la trascrizione. Dettagli in voice.log")


def paste_text(text: str, conserva_appunti: bool = False) -> None:
    """Con conserva_appunti=True il ripristino degli Appunti si salta: quando
    l'incolla parte alla cieca il testo dettato deve restare recuperabile.
    Il lucchetto: una copia dal menu Voce non entra a meta' di un incolla."""
    with _lock_appunti:
        try:
            previous = pyperclip.paste()
        except Exception:
            previous = None
        pyperclip.copy(text)
        time.sleep(0.15)
        with keyboard_controller.pressed(Key.ctrl):
            keyboard_controller.press("v")
            keyboard_controller.release("v")
        time.sleep(0.3)
        if previous is not None and not conserva_appunti:
            try:
                pyperclip.copy(previous)
            except Exception:
                pass


# --- Menu Voce: le ultime dettature (gemella Mac, 31/10/2026) ---

def _negli_appunti(testo: str) -> None:
    with _lock_appunti:  # mai a meta' di un incolla
        pyperclip.copy(testo)


def copia_ultima_dettatura() -> None:
    testo, _ = ultime_dettature.ultima()
    if testo:
        _negli_appunti(testo)
        logging.info("menu: ultima dettatura copiata negli Appunti (%d parole)", len(testo.split()))


def ritrascrivi_ultima() -> None:
    """L'audio dell'ultima dettatura di nuovo nel motore principale, glossario compreso, in un
    passaggio unico per pezzo (senza progressiva): il risultato va negli Appunti, non in chat."""
    _, audio = ultime_dettature.ultima()
    if not audio:
        return
    eventi.put(("avviso", "Ritrascrivo...", 60.0))
    try:
        pezzi = []
        for pezzo in audio:
            with _lock_trascrizione:  # una trascrizione per volta, anche con le dettature
                testo = _passaggio_unico(pezzo)
            if testo.strip() and not e_allucinazione(testo):
                pezzi.append(converti_punteggiatura_dettata(
                    applica_sostituzioni(testo.strip(), CFG.get("sostituzioni", {}))))
        testo = " ".join(pezzi)
    except Exception:
        logging.exception("menu: ritrascrizione fallita")
        eventi.put(("avviso", "Ritrascrizione fallita", 2.5))
        return
    if not testo:
        eventi.put(("avviso", "Niente da ritrascrivere", 2.5))
        return
    _negli_appunti(testo)
    logging.info("menu: ultima dettatura ritrascritta, %d parole negli Appunti", len(testo.split()))
    eventi.put(("avviso", "Ritrascritta: è negli Appunti", 2.5))


def worker() -> None:
    while True:
        command = commands.get()
        pressione = None
        if isinstance(command, tuple):  # ("start", istante del tasto)
            command, pressione = command
        try:
            if command == "start":
                start_recording(pressione)
            elif command == "stop":
                stop_recording()
            elif command == "stop_coda":
                # rilascio del tasto: lo stream resta aperto e audio_callback
                # continua ad accodare blocchi, quindi basta aspettare qui
                # (mai nella callback tastiera) prima di chiudere.
                al_rilascio = pressioni_tasto
                if recording and CODA_RILASCIO_SEC > 0:
                    time.sleep(CODA_RILASCIO_SEC)
                if recording and (key_down or pressioni_tasto != al_rilascio):
                    # gemella Mac (30/10/2026): ripreso dentro la coda, e' la stessa
                    # frase e la registrazione continua invece di spezzarsi
                    logging.info("tasto ripreso nella coda del rilascio: la registrazione continua")
                    continue
                stop_recording()
            elif command == "annulla":  # Esc: la dettatura si butta (vedi annulla_dettatura)
                annulla_dettatura()
        except Exception:
            logging.exception("errore comando audio")


# Codici virtuali Windows (VK) dei tasti usabili come tasto-detta, per leggere
# lo stato FISICO del tasto dal sistema (GetAsyncKeyState) invece che fidarsi
# degli eventi pynput (gemello di _cmd_giu() su Mac, che legge Quartz).
_VK_TASTI = {
    "ctrl_r": 0xA3, "ctrl_l": 0xA2, "ctrl": 0x11,
    "alt_r": 0xA5, "alt_l": 0xA4, "alt": 0x12, "alt_gr": 0xA5,
    "shift_r": 0xA1, "shift_l": 0xA0, "shift": 0x10,
    "cmd_r": 0x5C, "cmd_l": 0x5B, "cmd": 0x5B,
    "menu": 0x5D,
}


def vk_del_tasto(nome) -> int | None:
    """VK del tasto configurato in `hotkey` (es. "ctrl_r" -> 0xA3); i tasti
    F1..F24 si ricavano dal numero. None se il tasto non e' mappato: in quel
    caso lo stato fisico non e' leggibile e vale il solo tetto soft."""
    nome = str(nome or "").strip().lower()
    if nome in _VK_TASTI:
        return _VK_TASTI[nome]
    if nome.startswith("f") and nome[1:].isdigit() and 1 <= int(nome[1:]) <= 24:
        return 0x70 + int(nome[1:]) - 1
    return None


def stop_anti_incanto(registrando, inizio, ora, tasto_giu, tetto_soft, tetto_duro) -> bool:
    """Gemella di voce_lib.stop_anti_incanto (Mac). Il tetto soft (90s) vale
    SOLO se il tasto-detta non e' piu' fisicamente giu': se e' giu' l'utente
    sta dettando davvero (caso 04/09: monologo tagliato a 90s). Il tetto duro
    (300s) ferma comunque, per il tasto incastrato."""
    if not registrando or inizio is None:
        return False
    durata = ora - inizio
    if durata > tetto_duro:
        return True
    return durata > tetto_soft and not tasto_giu


VK_TASTO_DETTA = vk_del_tasto(CFG.get("hotkey", "f8"))


def tasto_detta_giu() -> bool:
    """True se la dettatura e' manuale (key_down) E il tasto-detta e' ancora
    fisicamente premuto secondo Windows. `ctypes.windll` esiste solo su
    Windows: altrove (o senza VK mappato) si assume tasto su, cosi' vale il
    tetto soft come prima."""
    if not key_down or VK_TASTO_DETTA is None:
        return False
    user32 = getattr(getattr(ctypes, "windll", None), "user32", None)
    if user32 is None:
        return False
    try:
        return bool(user32.GetAsyncKeyState(VK_TASTO_DETTA) & 0x8000)
    except Exception:
        return False


# --- Esc annulla la dettatura (gemella Mac, 31/10/2026) ---
# Dalla pressione del tasto-detta finche' il testo non e' incollato, Esc butta la dettatura:
# niente incolla, niente Invio, la pill lo dice. In quel tratto Esc non deve arrivare all'app
# davanti (in Claude fermerebbe l'agente): lo trattiene il filtro dell'hook di tastiera che
# pynput gia' installa (`win32_event_filter` + `suppress_event()`, documentati da pynput).
# SPENTO DI SERIE su Windows (`"esc_annulla": false`): un hook che toglie un tasto alle app
# va visto girare su un PC vero prima di accenderlo ai clienti; qui e' provato solo con
# eventi finti. Fuori dalla dettatura il filtro lascia passare tutto, sempre.

VK_ESC = 0x1B
ESC_ANNULLA = bool(CFG.get("esc_annulla", False))
FINESTRA_ESC_MAX_SEC = 120     # dalla fine della registrazione all'incolla; oltre, qualcosa e' appeso
RIPETIZIONE_ESC_SEC = 1.0      # Windows ripete un tasto tenuto entro 1 s (ritardo massimo di tastiera)
_WM_TASTO_GIU = (0x0100, 0x0104)            # WM_KEYDOWN, WM_SYSKEYDOWN
_LLKHF_INIETTATO = 0x10 | 0x02              # LLKHF_INJECTED, LLKHF_LOWER_IL_INJECTED
# Ctrl, Alt e Win, sinistri e destri: con Esc sono gesti di Windows (Start, cambio finestra,
# Gestione attivita'). Il tasto-detta no: chi detta tiene giu' Ctrl destro e preme Esc.
_VK_MODIFICATORI = (0xA2, 0xA3, 0xA4, 0xA5, 0x5B, 0x5C)


class EscAnnulla:
    """Cosa fare di un evento di Esc: (trattenerlo?, annullare la dettatura?). Gemella Mac.

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
                if finestra_aperta and not con_ctrl_o_option:  # Ctrl/Alt/Win + Esc restano del sistema
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


esc_annulla = EscAnnulla()
ascoltatore_tastiera = None    # il listener pynput: serve a suppress_event()
_esc_giu = False               # Esc fisicamente giu': le ripetizioni arrivano senza rilascio
_ultimo_esc = 0.0
_ultima_registrazione = -1e9   # monotonic: l'ultima volta che una registrazione era aperta


def modificatore_di_sistema_giu() -> bool:
    """Ctrl, Alt o Win tenuti giu' (escluso il tasto-detta). Fuori da Windows: False."""
    user32 = getattr(getattr(ctypes, "windll", None), "user32", None)
    if user32 is None:
        return False
    return any(user32.GetAsyncKeyState(vk) & 0x8000 for vk in _VK_MODIFICATORI if vk != VK_TASTO_DETTA)


def finestra_esc_aperta() -> bool:
    """Una registrazione aperta, o il suo testo non ancora incollato. Una coda rimasta appesa
    per un guasto non deve togliere Esc a tutte le app per sempre: dopo due minuti non conta."""
    if recording:
        return True
    return coda_dettature.aperta() and time.monotonic() - _ultima_registrazione < FINESTRA_ESC_MAX_SEC


def _filtro_tastiera(msg, data):
    """`win32_event_filter` del listener: gira DENTRO l'hook di tastiera, prima che il tasto
    arrivi alle app. Trattiene solo Esc e solo durante una dettatura. Veloce e mai un
    errore: un'eccezione qui (diversa da quella di suppress_event) fermerebbe il listener
    di pynput, e con lui il tasto-detta. Torna sempre True: il tasto arriva ai callback."""
    global _esc_giu, _ultimo_esc
    trattieni = False
    try:
        if data.vkCode != VK_ESC or data.flags & _LLKHF_INIETTATO:
            return True  # gli altri tasti, e un Esc mandato da un programma, passano sempre
        ora = time.monotonic()
        giu = msg in _WM_TASTO_GIU
        ripetuto = giu and _esc_giu and ora - _ultimo_esc < RIPETIZIONE_ESC_SEC
        _esc_giu, _ultimo_esc = giu, ora
        trattieni, annulla = esc_annulla.evento(
            giu, ripetuto, modificatore_di_sistema_giu(), finestra_esc_aperta(), ora)
        if annulla:
            coda_dettature.annulla()  # subito: niente incolla da qui in poi
            commands.put("annulla")   # il resto (microfono, pill) lo fa il worker audio
    except Exception:
        return True
    if trattieni and ascoltatore_tastiera is not None:
        ascoltatore_tastiera.suppress_event()  # pynput: l'hook restituisce 1, nessuna app lo riceve
    return True


def annulla_dettatura() -> None:
    """Esc (worker audio): la registrazione si chiude senza Whisper, cio' che e' in coda si butta."""
    global stream, recording, recording_started_at, sessione_progressiva, turno_utente_token
    global _ultima_registrazione
    coda_dettature.annulla()  # anche un pezzo partito dopo l'Esc, ma prima di questo comando
    ultime_dettature.annulla_in_corso()
    if recording:
        recording = False
        recording_started_at = None
        _ultima_registrazione = time.monotonic()
        sessione, sessione_progressiva = sessione_progressiva, None
        if sessione is not None:
            sessione.ferma()
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:
                logging.exception("microfono non chiuso dopo Esc")
            stream = None
        token, turno_utente_token = turno_utente_token, None
        _concludi_dettatura(token)  # il pezzo si chiude vuoto: nessun turno resta appeso
    logging.info("dettatura annullata con Esc: niente incolla, niente Invio")
    eventi.put(("avviso", "Dettatura annullata", 1.5))


def watchdog() -> None:
    global key_down
    while True:
        time.sleep(1)
        ora = time.monotonic()
        tasto_giu = tasto_detta_giu()
        if stop_anti_incanto(recording, recording_started_at, ora, tasto_giu,
                             MAX_RECORDING_SEC, MAX_RECORDING_TASTO_SEC):
            duration = ora - recording_started_at
            logging.warning(
                "registrazione oltre %.1fs: stop anti-incanto (tasto giu': %s)", duration, tasto_giu
            )
            key_down = False
            commands.put("stop")


def _avviso_collegamento() -> str:
    """P-078: all'accensione si prova che il collegamento con l'agente parta
    DAVVERO (stesso comando scritto nella sua configurazione, avviato come lo
    avvia lui). Il gancio di Windows e' fallito 410 volte su 410 per due mesi
    senza che nessuno lo sapesse: ora chi accende la voce lo sente subito.
    Vuoto se funziona; mai un errore: il controllo non deve rompere l'accensione."""
    if voce_agenti is None or not hasattr(voce_agenti, "avviso_collegamento"):
        return ""
    try:
        avviso = voce_agenti.avviso_collegamento()
    except Exception:
        logging.exception("controllo del collegamento con gli agenti fallito")
        return ""
    if avviso:
        logging.warning("collegamento con gli agenti: %s", avviso)
    return " " + avviso if avviso else ""


def commuta_voce() -> None:
    """Tasto on/off della voce agenti, con conferma parlata. Lavoro bloccante
    (taskkill/PowerShell): chiamarlo sempre da un thread, mai dalla callback."""
    try:
        if FLAG_VOICE_ON.exists():
            FLAG_VOICE_ON.unlink()
            stato = "Voce AI spenta"
        else:
            FLAG_VOICE_ON.touch()
            stato = "Voce AI accesa. Le risposte dell'agente sono audio sintetico."
            stato += _avviso_collegamento()  # una sola frase: pronuncia() ferma la precedente
        logging.info(stato)
        pronuncia(stato)
    except Exception:
        logging.exception("errore commutazione voce")


def _tasto_voce_premuto() -> None:
    """Parte il conto del tasto voce: commuta solo se resta giu' per
    VOCE_TENUTA_SEC. Il Timer gira su un thread suo, dove commuta_voce (lavoro
    bloccante) puo' stare."""
    global voce_timer
    _tasto_voce_rilasciato()
    voce_timer = threading.Timer(VOCE_TENUTA_SEC, commuta_voce)
    voce_timer.daemon = True
    voce_timer.start()


def _tasto_voce_rilasciato() -> None:
    """Rilasciato prima del tempo: era un tocco, non commuta niente."""
    global voce_timer
    if voce_timer is not None:
        voce_timer.cancel()
        voce_timer = None


def on_press(key, injected=False) -> None:
    global key_down, voice_key_down, ultima_pressione_utente, ultimo_tasto_utente, pressioni_tasto
    global _ultima_registrazione
    ora = time.monotonic()
    if not injected:  # il Ctrl+V e l'Invio del programma non sono gesti dell'utente
        ultima_pressione_utente = ora
        ultimo_tasto_utente = key
    if key == HOTKEY and not key_down:
        coda_dettature.interrompi_invio()
        key_down = True
        pressioni_tasto += 1
        _ultima_registrazione = ora  # da qui Esc butta la dettatura (se esc_annulla e' acceso)
        commands.put(("start", ora))  # l'istante del tasto: il registro dice quanto dopo parte
    elif TASTO_VOCE is not None and key == TASTO_VOCE and not voice_key_down:
        voice_key_down = True  # debounce: il tasto tenuto si ripete, il conto parte una volta
        _tasto_voce_premuto()


def on_click(x, y, button, pressed, injected=False) -> None:
    """Gemella Mac (23/09/2026): un clic fisico ferma l'Invio in attesa come
    un tasto (il cursore messo nel testo per correggerlo); quello del
    cursore automatico no."""
    global ultima_pressione_utente, ultimo_tasto_utente
    if pressed and not injected:
        ultima_pressione_utente = time.monotonic()
        ultimo_tasto_utente = "clic"


def on_release(key) -> None:
    global key_down, voice_key_down
    if key == HOTKEY and key_down:
        key_down = False
        commands.put("stop_coda")  # rilascio manuale: coda di CODA_RILASCIO_SEC
    elif key == TASTO_VOCE:
        voice_key_down = False  # rilasciato: la prossima pressione riparte da zero
        _tasto_voce_rilasciato()


def crescita_punto(stato: str, volume: float, istante: float, da_quanto: float,
                   scala_volume: float = 200.0) -> float:
    """Quanto si ingrandisce il punto di "LeaderAI." (gemello Mac): alla comparsa
    della pill si accende con uno scatto, mentre parli segue la voce, mentre
    trascrive pulsa con un battito da un secondo. 0 = punto a riposo."""
    if stato == "ascolto":
        if da_quanto < 0.19:
            return -0.8 + 2.4 * da_quanto / 0.19          # da 0.2 a 1.6 volte
        if da_quanto < 0.35:
            return 0.6 - 0.6 * (da_quanto - 0.19) / 0.16  # e torna a 1
        return min(0.9, volume * scala_volume * 0.075)
    if stato in ("trascrivo", "sistemo"):
        return 0.7 * (1 - math.cos(2 * math.pi * istante)) / 2
    return 0.0


def disegno_firma(da_quanto: float, durata: float = 0.75) -> float:
    """Quanta sottolineatura verde e' disegnata (0-1): la firma della home del
    sito, che si disegna da sinistra con la stessa curva (gemello Mac)."""
    x = max(0.0, min(1.0, da_quanto / durata))
    return 4 * x ** 3 if x < 0.5 else 1 - (-2 * x + 2) ** 3 / 2


# --- overlay: la pill "LeaderAI." con la barra a sorriso (thread principale) ---

class Pannello:
    """Finestra senza bordi, sempre in primo piano, sfondo trasparente.
    Disegna la pill scura, il marchio e le lineette verdi ad arco a sorriso.
    Gira sul thread principale di Tk; legge stato e volume dalle code."""

    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.overrideredirect(True)          # niente barra del titolo
        self.root.attributes("-topmost", True)    # sopra tutte le finestre
        try:
            self.root.attributes("-transparentcolor", TRASPARENTE)  # solo Windows
        except tk.TclError:
            pass
        self.root.config(bg=TRASPARENTE)

        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = (sw - LARGHEZZA) // 2
        y = sh - ALTEZZA - 80                     # in basso, sopra la barra applicazioni
        self.root.geometry(f"{LARGHEZZA}x{ALTEZZA}+{x}+{y}")

        self.canvas = tk.Canvas(
            self.root, width=LARGHEZZA, height=ALTEZZA,
            bg=TRASPARENTE, highlightthickness=0,
        )
        self.canvas.pack()
        self.font_marchio = tkfont.Font(root=self.root, family="Segoe UI", size=12, weight="bold")
        # con una scritta di stato il marchio si ingrandisce al centro (gemello Mac)
        self.font_marchio_grande = tkfont.Font(root=self.root, family="Segoe UI", size=16, weight="bold")
        self.stato = "nascosto"
        self.comparsa = 0.0
        self.root.withdraw()
        self._non_rubare_focus()
        self._crea_controlli_voce()

    def _crea_controlli_voce(self) -> None:
        """Comandi accessibili in una finestra normale; la pill resta
        trasparente ai click e non cambia il cursore della dettatura."""
        self.controlli_voce = tk.Toplevel(self.root)
        self.controlli_voce.title("Voce AI")
        self.controlli_voce.geometry("380x130")
        self.controlli_voce.resizable(False, False)
        self.controlli_voce.protocol("WM_DELETE_WINDOW", self._chiudi)
        barra = tk.Menu(self.controlli_voce)
        self.menu_voce = tk.Menu(
            barra, tearoff=False, postcommand=self._aggiorna_menu_voce,
        )
        barra.add_cascade(label="Voce", menu=self.menu_voce)
        self.controlli_voce.config(menu=barra)
        tk.Label(
            self.controlli_voce, text=BRAND, font=("Segoe UI", 12, "bold"),
        ).pack(pady=(12, 4))
        self.stato_conversazione = tk.StringVar(value="Ascolta tutte le conversazioni")
        tk.Label(
            self.controlli_voce, textvariable=self.stato_conversazione,
            wraplength=355,
        ).pack()
        tk.Label(
            self.controlli_voce,
            text="Dal menu Voce scegli chi ascoltare, rileggi una risposta o riprendi l'ultima dettatura.",
            wraplength=355,
        ).pack(pady=6)
        self.conversazione_scelta = tk.StringVar(value="")
        self._aggiorna_menu_voce()

    def _aggiorna_menu_voce(self) -> None:
        if voce_agenti is None:
            self.menu_voce.delete(0, "end")
            self.menu_voce.add_command(label="Voce agenti non disponibile", state="disabled")
            self.stato_conversazione.set("Voce agenti da completare con l'agente.")
            self._aggiungi_ultime_dettature()
            return
        try:
            stato = voce_agenti.elenco_conversazioni()
        except Exception:
            logging.exception("errore lettura conversazioni voce")
            return
        preferita = stato["preferita"]
        self.conversazione_scelta.set(preferita or "")
        self.menu_voce.delete(0, "end")
        self.menu_voce.add_command(
            label="Rileggi ultima risposta",
            state="normal" if stato["rileggibile"] else "disabled",
            command=lambda: self._esegui_comando_voce(voce_agenti.rileggi_ultima),
        )
        self.menu_voce.add_separator()
        self.menu_voce.add_radiobutton(
            label="Ascolta tutte le conversazioni", variable=self.conversazione_scelta,
            value="", command=lambda: self._esegui_comando_voce(
                voce_agenti.scegli_conversazione, None,
            ),
        )
        descrizione = "Ascolta tutte le conversazioni"
        for conversazione in stato["conversazioni"]:
            identificativo, nome = conversazione["id"], conversazione["nome"]
            anteprima = conversazione["anteprima"]
            fonte_visibile = nome + (" · " + anteprima[:55] if anteprima else "")
            if identificativo == preferita:
                descrizione = "Ascolta: " + fonte_visibile
            etichetta = fonte_visibile + (" · in attesa" if conversazione["in_attesa"] else "")
            self.menu_voce.add_radiobutton(
                label=etichetta, variable=self.conversazione_scelta, value=identificativo,
                command=lambda fonte=identificativo: self._esegui_comando_voce(
                    voce_agenti.scegli_conversazione, fonte,
                ),
            )
        self.stato_conversazione.set(descrizione)
        self._aggiungi_ultime_dettature()

    def _aggiungi_ultime_dettature(self) -> None:
        """In fondo al menu (gemella Mac, 31/10/2026): spente finche' non c'e' una dettatura.
        Testo e audio stanno solo in memoria; il lavoro gira su un thread, mai su quello di Tk."""
        testo_pronto, audio_pronto = ultime_dettature.disponibili()
        self.menu_voce.add_separator()
        self.menu_voce.add_command(
            label="Copia l’ultima dettatura", state="normal" if testo_pronto else "disabled",
            command=lambda: self._esegui_comando_voce(copia_ultima_dettatura),
        )
        self.menu_voce.add_command(
            label="Ritrascrivi l’ultima", state="normal" if audio_pronto else "disabled",
            command=lambda: self._esegui_comando_voce(ritrascrivi_ultima),
        )

    def _esegui_comando_voce(self, funzione, *argomenti) -> None:
        def esegui():
            try:
                funzione(*argomenti)
            except Exception:
                logging.exception("errore comando voce")
            self.root.after(0, self._aggiorna_menu_voce)
        threading.Thread(target=esegui, daemon=True).start()

    def _chiudi(self) -> None:
        ferma_voce()
        self.root.destroy()

    def _non_rubare_focus(self) -> None:
        """Best-effort: rende la finestra "click-through" e non attivabile, cosi'
        l'overlay non ruba mai il focus mentre detti/scrivi (come il pannello Mac).
        Se fallisce, l'app funziona comunque."""
        try:
            import ctypes
            GWL_EXSTYLE = -20
            WS_EX_LAYERED = 0x00080000
            WS_EX_TRANSPARENT = 0x00000020
            WS_EX_NOACTIVATE = 0x08000000
            hwnd = ctypes.windll.user32.GetParent(self.canvas.winfo_id())
            stile = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            ctypes.windll.user32.SetWindowLongW(
                hwnd, GWL_EXSTYLE,
                stile | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE,
            )
        except Exception:
            logging.info("stile click-through non applicato (non critico)")

    def _pill(self) -> None:
        """Disegna lo sfondo arrotondato della pill."""
        x1, y1, x2, y2, r = 1, 1, LARGHEZZA - 1, ALTEZZA - 1, RAGGIO
        c = self.canvas
        c.create_arc(x1, y1, x1 + 2 * r, y1 + 2 * r, start=90, extent=90, fill=SFONDO_PILL, outline=SFONDO_PILL)
        c.create_arc(x2 - 2 * r, y1, x2, y1 + 2 * r, start=0, extent=90, fill=SFONDO_PILL, outline=SFONDO_PILL)
        c.create_arc(x1, y2 - 2 * r, x1 + 2 * r, y2, start=180, extent=90, fill=SFONDO_PILL, outline=SFONDO_PILL)
        c.create_arc(x2 - 2 * r, y2 - 2 * r, x2, y2, start=270, extent=90, fill=SFONDO_PILL, outline=SFONDO_PILL)
        c.create_rectangle(x1 + r, y1, x2 - r, y2, fill=SFONDO_PILL, outline=SFONDO_PILL)
        c.create_rectangle(x1, y1 + r, x2, y2 - r, fill=SFONDO_PILL, outline=SFONDO_PILL)

    def _marchio(self, crescita: float = 0.0, firma: float = 1.0, grande: bool = False) -> None:
        """Il logo: "LeaderAI." col punto verde vivo e la firma verde sotto; in
        alto mentre parli, grande al centro con una scritta di stato. Un
        marchio senza punto finale resta testo semplice."""
        c = self.canvas
        f = self.font_marchio_grande if grande else self.font_marchio
        punto = BRAND.endswith(".")
        testo = BRAND[:-1] if punto else BRAND
        cap = f.metrics("ascent") * 0.7
        lato, spazio = cap * 0.24, cap * 0.12     # punto come nel logo ufficiale (Sal 24/09/2026)
        largo_testo = f.measure(testo)
        x0 = (LARGHEZZA - largo_testo - ((spazio + lato) if punto else 0)) / 2
        base = 32 if grande else 21                  # linea di base del testo
        c.create_text(x0, base + f.metrics("descent"), text=testo, anchor="sw",
                      fill="#F7F7F7", font=f)
        if not punto:
            return
        if firma > 0:
            spessore, y_firma = cap * 0.18, base + cap * 0.34
            c.create_rectangle(x0, y_firma - spessore / 2, x0 + largo_testo * firma,
                               y_firma + spessore / 2, fill=VERDE_FIRMA, outline="")
        cx, cy = x0 + largo_testo + spazio + lato / 2, base - lato / 2
        r = lato / 2 * (1 + crescita)
        if crescita > 0.05:
            for colore, alone in zip(ALONE_PUNTO, (2.3, 1.6)):
                a = r * alone
                c.create_oval(cx - a, cy - a, cx + a, cy + a, fill=colore, outline="")
        c.create_oval(cx - r, cy - r, cx + r, cy + r, fill=VERDE_FIRMA, outline=VERDE_FIRMA)

    def _disegna_ascolto(self) -> None:
        self.canvas.delete("all")
        self._pill()
        da_quanto = time.monotonic() - self.comparsa
        self._marchio(crescita_punto(
            "ascolto", livelli[-1], time.monotonic(), da_quanto, SCALA_VOLUME,
        ), disegno_firma(da_quanto))
        valori = list(livelli)
        n = len(valori)
        passo = (LARGHEZZA - 40) / n
        centro = (n - 1) / 2
        larghezza_barra = max(2.0, passo * 0.55)
        for i, v in enumerate(valori):
            h = 5 + min(22.0, v * SCALA_VOLUME)
            x = 20 + i * passo
            y_centro = 50 - 12 * (((i - centro) / centro) ** 2)  # arco: angoli su, centro giu'
            self.canvas.create_rectangle(
                x, y_centro - h / 2, x + larghezza_barra, y_centro + h / 2,
                fill=COLORE, outline=COLORE,
            )

    def _disegna_trascrivo(self, testo: str = "Trascrivo...") -> None:
        self.canvas.delete("all")
        self._pill()
        self._marchio(crescita_punto(self.stato, 0.0, time.monotonic(), 1.0), grande=True)
        self.canvas.create_text(                 # piccola e grigia: in risalto resta LeaderAI
            LARGHEZZA / 2, 51, text=testo, fill="#B8B8B8",
            font=("Segoe UI", 9, "normal"),
        )

    def tick(self) -> None:
        try:
            while True:
                nuovo = eventi.get_nowait()
                if isinstance(nuovo, tuple) and nuovo[0] in ("errore_audio", "avviso"):
                    # ("avviso", testo, secondi): Esc e menu (gemella Mac); gli errori 4 secondi
                    self.stato = "errore_audio"
                    self._errore_fino = time.monotonic() + (nuovo[2] if len(nuovo) > 2 else 4.0)
                    self._errore_testo = nuovo[1]
                    self.root.deiconify()
                    continue
                if (nuovo in ("nascosto", "trascrivo", "sistemo")
                        and time.monotonic() < getattr(self, "_errore_fino", 0.0)):
                    continue
                if recording and nuovo in ("trascrivo", "sistemo", "nascosto"):
                    continue
                self.stato = nuovo
                if self.stato == "ascolto":
                    self._errore_fino = 0.0
                    self.comparsa = time.monotonic()
                    self.root.deiconify()
                elif self.stato == "nascosto":
                    self.root.withdraw()
        except queue.Empty:
            pass
        if (self.stato == "errore_audio"
                and time.monotonic() >= getattr(self, "_errore_fino", 0.0)):
            self.stato = "nascosto"
            self.root.withdraw()
        if self.stato == "ascolto":
            self._disegna_ascolto()
        elif self.stato == "trascrivo":
            self._disegna_trascrivo()
        elif self.stato == "sistemo":
            self._disegna_trascrivo("Sistemo...")
        elif self.stato == "errore_audio":
            self._disegna_trascrivo(self._errore_testo)
        self.root.after(60, self.tick)

    def run(self) -> None:
        self.root.after(60, self.tick)
        self.root.mainloop()


def main() -> None:
    global ascoltatore_tastiera
    FLAG_TURNO_UTENTE.unlink(missing_ok=True)  # residuo di un arresto durante la dettatura
    # Rotazione a 7 giorni (gemello Mac): con debug_dettature=true il log
    # contiene il grezzo di ogni dettatura in chiaro, non deve accumularsi
    # all'infinito.
    gestore_log = logging.handlers.TimedRotatingFileHandler(
        LOG, when="midnight", backupCount=7, encoding="utf-8"
    )
    logging.basicConfig(
        handlers=[gestore_log],
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    logging.getLogger("voce").info("glossario per Whisper: %d nomi: %s", len(CFG.get("glossario", [])), GLOSSARIO_PROMPT)
    logging.info("orecchio: %s", ORECCHIO_STATO)
    print("Voice Dettatura Windows v1.3")
    print("Ctrl destro: tieni premuto, parla, rilascia -> il testo viene incollato.")
    if ESC_ANNULLA:
        print("Esc mentre detti, o prima che il testo compaia: la dettatura si butta.")
    print("Tasto Menu tenuto premuto un secondo: accende/spegne Voce AI (le risposte sono audio sintetico).")
    print("Finestra Voce AI: dal menu Voce rileggi una risposta, scegli la conversazione, copia o ritrascrivi l'ultima dettatura.")
    print("Chiudi questa finestra per fermare la dettatura.")
    allinea_volume_ingresso()  # ingresso basso = app muta senza motivo apparente
    threading.Thread(target=worker, daemon=True).start()
    threading.Thread(target=watchdog, daemon=True).start()
    threading.Thread(target=load_model, daemon=True).start()
    threading.Thread(target=impara_dagli_errori_giornaliero, daemon=True).start()
    if CFG.get("voce_mentre_scrive", True):
        threading.Thread(target=_segui_registri, daemon=True).start()  # la voce legge ogni blocco appena scritto
    # Esc annulla: il filtro si passa SOLO se acceso. Un filtro None farebbe fermare il
    # listener al primo tasto (pynput lo chiamerebbe), e con lui il tasto-detta.
    opzioni_tastiera = {"win32_event_filter": _filtro_tastiera} if ESC_ANNULLA else {}
    logging.info("esc annulla: %s", "pronto (Esc trattenuto solo durante una dettatura)" if ESC_ANNULLA
                 else 'spento in config.json ("esc_annulla": false)')
    ascoltatore_tastiera = keyboard.Listener(on_press=on_press, on_release=on_release, **opzioni_tastiera)
    ascoltatore_tastiera.start()
    mouse.Listener(on_click=on_click).start()
    Pannello().run()


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "--ripasso":
        logging.basicConfig(
            filename=str(LOG), level=logging.INFO,
            format="%(asctime)s %(levelname)s %(message)s",
        )
        ripassa_audio_conservati(
            BASE / "audio_recenti",
            [LOG] + sorted(BASE.glob(LOG.name + ".*"))[-1:],
            BASE / "config.json",
            comandi_agente(),
            CFG.get("modello_ripasso", "small"),
            massimo_file=int(CFG.get("conserva_audio_n", 0)) or 30,
        )
        raise SystemExit(0)
    main()
