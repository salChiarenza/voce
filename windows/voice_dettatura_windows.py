"""Voice Dettatura Windows.

Tieni premuto Ctrl destro, parla, rilascia: il testo viene incollato dove hai il
cursore. Il tasto Menu accende/spegne la voce agenti (legge le risposte ad alta voce).
Trascrizione locale con faster-whisper (niente cloud). Tutto in questo unico file.

Mentre parli compare in basso al centro una pill scura con il marchio
"salchiarenza.ai" e una barra di lineette verdi disposte ad arco "a sorriso"
che si muovono col volume. L'overlay non ruba mai il focus: continui a scrivere
nel programma dove sei. Per fermare la dettatura chiudi la finestra.
"""
from __future__ import annotations

import collections
import ctypes
import json
import logging
import logging.handlers
import queue
import re
import shutil
import subprocess
import threading
import time
import tkinter as tk
from pathlib import Path

import numpy as np
import pyperclip
import sounddevice as sd
from faster_whisper import WhisperModel
from pynput import keyboard
from pynput.keyboard import Controller, Key

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
INVIO_AUTOMATICO = bool(CFG.get("invio_automatico", True))
RITARDO_INVIO_AUTOMATICO = float(CFG.get("invio_automatico_ritardo_sec", 2.5))
RITARDO_INVIO_CONVERSAZIONE = float(CFG.get("invio_automatico_ritardo_conversazione_sec", 0.3))
VOICE_THRESHOLD = float(CFG.get("voice_threshold", 0.004))
MIN_RECORDING_SEC = float(CFG.get("min_recording_sec", 0.4))
MAX_RECORDING_SEC = float(CFG.get("max_recording_sec", 90))

# --- aspetto della pill (uguale alla versione Mac) ---
BRAND = CFG.get("brand", "salchiarenza.ai")
COLORE = CFG.get("colore", "#7ED321")        # verde delle lineette
N_BARRE = int(CFG.get("barre", 18))
SCALA_VOLUME = float(CFG.get("scala_volume", 200))
LARGHEZZA, ALTEZZA = 300, 72
RAGGIO = 16
SFONDO_PILL = "#141414"
TRASPARENTE = "magenta"                       # colore reso invisibile dalla finestra

keyboard_controller = Controller()
commands: queue.Queue[str] = queue.Queue()    # "start"/"stop" dal thread tastiera al worker audio
eventi: queue.Queue[str] = queue.Queue()      # "ascolto"/"trascrivo"/"sistemo"/"nascosto" verso l'overlay
livelli = collections.deque([0.0] * N_BARRE, maxlen=N_BARRE)
blocks: list[np.ndarray] = []
stream = None
recording = False
key_down = False
voice_key_down = False                         # debounce del tasto on/off voce
recording_started_at: float | None = None
model: WhisperModel | None = None
ultima_pressione_utente = 0.0                  # annulla l'Invio automatico in attesa


# --- voce in uscita "agenti": interruttore + TTS di Windows, tutto in questo file ---
FLAG_VOICE_ON = BASE / "VOICE_ON"          # se esiste, la voce in uscita e' accesa
PID_FILE = BASE / "voce_pid"               # PID dell'ultima lettura: una voce per volta
VOCE_RATE = int(CFG.get("voce_rate", 0))   # System.Speech: da -10 (lenta) a +10 (veloce)
VOCE_NOME = str(CFG.get("voce_nome", ""))  # scelta guidata alla prima installazione


def voce_attiva() -> bool:
    """Voce agenti accesa = conversazione vera con l'agente (botta e risposta,
    niente tempo di rilettura). Usata per scegliere la pausa pre-Invio."""
    return FLAG_VOICE_ON.exists()


# --- glossario e detta pulito: la trascrizione grezza diventa testo curato ---
# (gemelli delle funzioni in mac/voce_lib.py: stessi nomi, stesso contratto)

def glossario_iniziale(cfg) -> str | None:
    """Prompt iniziale per Whisper coi termini del mestiere: cosi' nomi propri
    e brand (LeaderAI, nomi clienti) escono scritti giusti."""
    voci = [v for v in cfg.get("glossario", []) if v.strip()]
    if not voci:
        return None
    return "Glossario: " + ", ".join(voci) + "."


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


def comando_agente() -> list | None:
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


def estrai_grezzi_dal_log(log_path, massimo=50) -> list:
    """Ultime dettature grezze dal log (righe 'INFO grezzo: ...')."""
    try:
        righe = Path(log_path).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    grezzi = [r.split("INFO grezzo: ", 1)[1] for r in righe if "INFO grezzo: " in r]
    return grezzi[-massimo:]


def unisci_sostituzioni(attuali: dict, nuove: dict) -> dict:
    """Solo coppie nuove e sensate: mai sovrascrivere quelle esistenti,
    mai identita' o spazzatura."""
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
    """Legge le ultime dettature grezze, chiede all'agente le correzioni
    ricorrenti sicure e le aggiunge alle sostituzioni del config."""
    grezzi = estrai_grezzi_dal_log(log_path)
    if not grezzi:
        return {}
    try:
        esito = subprocess.run(
            comando + [prompt_apprendimento(grezzi)],
            capture_output=True, text=True, timeout=timeout,
        )
        proposte = estrai_json(esito.stdout or "")
        cfg = json.loads(Path(config_path).read_text(encoding="utf-8"))
        nuove = unisci_sostituzioni(cfg.get("sostituzioni", {}), proposte)
        if nuove:
            cfg.setdefault("sostituzioni", {}).update(nuove)
            Path(config_path).write_text(
                json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )
        return nuove
    except Exception:
        logging.exception("apprendimento sostituzioni fallito")
        return {}


def impara_dagli_errori_giornaliero() -> None:
    """Apprendimento automatico, una volta al giorno all'avvio (gemello Mac)."""
    marcatore = BASE / "APPRENDIMENTO_ULTIMO"
    oggi = time.strftime("%Y-%m-%d")
    try:
        if marcatore.read_text().strip() == oggi:
            return
    except OSError:
        pass
    if not CFG.get("debug_dettature", False):
        return  # senza log dei testi non c'e' niente da cui imparare
    comando = COMANDO_APPRENDIMENTO or comando_agente()
    if not comando:
        return
    nuove = impara_sostituzioni(LOG, BASE / "config.json", comando)
    if nuove:
        CFG.setdefault("sostituzioni", {}).update(nuove)  # attive da subito
        logging.info("imparate sostituzioni: %s", nuove)
    marcatore.write_text(oggi)


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
COMANDO_APPRENDIMENTO = comando_agente() if CFG.get("debug_dettature", False) else None


def pulisci_per_voce(testo: str) -> str:
    """Markdown -> testo piano leggibile a voce."""
    testo = re.sub(r"```.*?```", " codice omesso. ", testo, flags=re.DOTALL)
    testo = re.sub(r"`([^`]*)`", r"\1", testo)
    testo = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", testo)
    testo = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", testo)
    testo = re.sub(r"https?://\S+", " ", testo)
    testo = re.sub(r"^#{1,6}\s*", "", testo, flags=re.MULTILINE)
    testo = re.sub(r"[*_]{1,3}([^*_\n]+)[*_]{1,3}", r"\1", testo)
    testo = re.sub(r"^\s*[-*•>]\s+", "", testo, flags=re.MULTILINE)
    return re.sub(r"\s+", " ", testo).strip()


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
    """Ferma la lettura in corso (uccide il PowerShell precedente)."""
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
    """Legge il testo ad alta voce con la voce italiana di Windows. Non blocca."""
    testo = pulisci_per_voce(testo)
    if not testo:
        return
    ferma_voce()  # una voce per volta
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


def load_model() -> WhisperModel:
    global model
    if model is None:
        logging.info("carico modello faster-whisper: %s", CFG["model"])
        model = WhisperModel(
            CFG["model"],
            device=CFG.get("device", "cpu"),
            compute_type=CFG.get("compute_type", "int8"),
        )
    return model


def audio_fuori_scala(rms: float, massimo: float = 1.0) -> bool:
    """True se l'rms e' impossibile per uno stream float32 sano: i sample vivono
    in [-1, 1], quindi rms <= 1 sempre. Sopra = il driver ha rimappato il device
    sotto lo stream e consegna dati corrotti (caso Mac 09/07: rms 3-4 per ~20s,
    Whisper allucinava). Meglio scartare che trascrivere spazzatura."""
    return rms > massimo


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


def e_allucinazione(testo: str) -> bool:
    """Scarta frasi-fantasma e collassi di Whisper prima dell'incolla."""
    normalizzato = _normalizza(testo)
    if not normalizzato:
        return True
    if normalizzato in _FRASI_FANTASMA:
        return True
    if "sottotitoli" in normalizzato and (
        "a cura di" in normalizzato or "creati dalla comunit" in normalizzato
    ):
        return True
    return _ripetizione_patologica(testo)


def invio_da_annullare(
    ultima_pressione: float, riferimento: float, nuova_registrazione: bool
) -> bool:
    """Qualsiasi tasto fisico o nuova dettatura blocca l'Enter automatico."""
    return ultima_pressione > riferimento or nuova_registrazione


def has_voice(audio: np.ndarray) -> bool:
    flat = np.asarray(audio, dtype="float32").reshape(-1)
    if flat.size == 0:
        return False
    return float(np.sqrt(np.mean(flat * flat))) >= VOICE_THRESHOLD


def audio_callback(indata, frames, current_time, status) -> None:
    if status:
        logging.warning("audio status: %s", status)
    blocks.append(indata.copy())
    livelli.append(float(np.sqrt(np.mean(indata ** 2))))  # volume per le lineette


def start_recording() -> None:
    global blocks, stream, recording, recording_started_at
    if recording:
        return
    ferma_voce()  # se l'agente sta parlando, ti zittisco: tocca a te
    blocks = []
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
    logging.info("registrazione avviata")
    eventi.put("ascolto")
    beep(880, 80)


def finestra_frontale():
    """Handle della finestra in primo piano ORA: e' il bersaglio del testo
    dettato (gemello di app_frontale() in mac/detta.py)."""
    try:
        return ctypes.windll.user32.GetForegroundWindow()
    except Exception:
        return None


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


# --- cursore automatico nella casella (gemello Mac, richiesta 29/08/2026) ---
# Riattivare la finestra non basta se dentro nessuna casella di testo ha il
# focus: il Ctrl+V cadrebbe nel vuoto e il proprietario dovrebbe prendere il
# mouse. Qui, via UI Automation di Windows, si controlla dove sta il focus e,
# se non e' una casella, il click nella casella di scrittura lo fa l'app.

_UIA_EDIT, _UIA_DOCUMENT = 50004, 50030  # ControlType: Edit, Document
_UIA_PROP_CONTROLTYPE = 30003
_UIA_SCOPE_DISCENDENTI = 4


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
        fuoco = uia.GetFocusedElement()
        if fuoco is not None and fuoco.CurrentControlType in (_UIA_EDIT, _UIA_DOCUMENT):
            return True  # il cursore e' gia' in una casella
        radice = uia.ElementFromHandle(hwnd)
        condizione = uia.CreateOrCondition(
            uia.CreatePropertyCondition(_UIA_PROP_CONTROLTYPE, _UIA_EDIT),
            uia.CreatePropertyCondition(_UIA_PROP_CONTROLTYPE, _UIA_DOCUMENT),
        )
        trovate = radice.FindAll(_UIA_SCOPE_DISCENDENTI, condizione)
        rett_finestra = radice.CurrentBoundingRectangle
        altezza_finestra = rett_finestra.bottom - rett_finestra.top
        candidate = []
        for i in range(trovate.Length):
            elemento = trovate.GetElement(i)
            r = elemento.CurrentBoundingRectangle
            # solo la parte bassa della finestra: in alto ci sono barra degli
            # indirizzi e campi di ricerca, e un click li' sarebbe un danno vero
            if not in_zona_scrittura(r.top, rett_finestra.top, altezza_finestra):
                continue
            candidate.append((elemento, (r.top, r.right - r.left)))
        scelta = scegli_casella([geometria for _, geometria in candidate])
        if scelta is None:
            logging.info("cursore automatico: nessuna casella di testo nella finestra")
            return False
        candidate[scelta][0].SetFocus()
        time.sleep(0.1)
        logging.info("cursore automatico: messo nella casella di scrittura")
        return True
    except Exception:
        logging.exception("cursore automatico fallito: incollo dove sta il focus")
        return None


def stop_recording() -> None:
    global stream, recording, recording_started_at
    if not recording:
        return
    finestra_bersaglio = finestra_frontale()  # bersaglio: la finestra davanti ORA, non a fine pulizia
    recording = False
    started = recording_started_at
    recording_started_at = None
    if stream is not None:
        stream.stop()
        stream.close()
        stream = None
    logging.info("registrazione fermata")
    beep(660, 80)

    if not blocks or started is None:
        eventi.put("nascosto")
        return
    duration = time.monotonic() - started
    if duration < MIN_RECORDING_SEC:
        eventi.put("nascosto")
        return

    audio = np.concatenate(blocks, axis=0)[:, 0]
    rms = float(np.sqrt(np.mean(audio ** 2)))
    if audio_fuori_scala(rms):  # sample fuori [-1,1]: stream corrotto, Whisper allucinerebbe
        logging.warning("scartato: audio fuori scala (rms %.2f > 1), stream corrotto", rms)
        eventi.put("nascosto")
        return
    if not has_voice(audio):
        # il Mac lo scriveva, qui si scartava in silenzio: senza questa riga
        # una dettatura persa non lasciava alcuna traccia da diagnosticare.
        logging.info("scartato: volume sotto soglia (mic muto/occupato?)")
        eventi.put("nascosto")
        ripara_guadagno_ingresso(rms)
        return

    eventi.put("trascrivo")
    threading.Thread(
        target=transcribe_and_paste, args=(audio, finestra_bersaglio), daemon=True
    ).start()


def transcribe_and_paste(audio: np.ndarray, finestra_bersaglio) -> None:
    try:
        try:
            conservato = salva_audio_recente(
                audio, BASE / "audio_recenti",
                CFG.get("conserva_audio_n", 0), freq=SAMPLE_RATE,
            )
            if conservato:
                logging.info("audio conservato: %s", conservato.name)
        except Exception:
            logging.exception("conservazione audio fallita")
        segments, _info = load_model().transcribe(
            audio,
            language=CFG.get("language", "it"),
            vad_filter=True,
            initial_prompt=GLOSSARIO_PROMPT,
        )
        text = " ".join(segment.text.strip() for segment in segments).strip()
        text = rimuovi_eco_glossario(text, CFG.get("glossario", []))
        if e_allucinazione(text):
            logging.info("scartato come allucinazione (%d caratteri)", len(text))
            eventi.put("nascosto")
            return
        text = applica_sostituzioni(text, CFG.get("sostituzioni", {}))
        text = converti_punteggiatura_dettata(text)
        # Windows non ha una corsia locale rapida equivalente al Comando
        # Rapido Apple. Il vecchio ripiego Claude/Codex poteva bloccare ogni
        # dettatura per 20s: ora il grezzo viene incollato subito.
        if CFG.get("debug_dettature", False) and text:
            logging.info("grezzo: %s", text)
        eventi.put("nascosto")
        if not text:
            return
        riattiva_bersaglio(finestra_bersaglio)
        casella = metti_cursore_in_casella(finestra_bersaglio)
        senza_casella = casella is False  # finestra letta: di caselle non ce n'e'
        paste_text(text, conserva_appunti=senza_casella)
        if senza_casella:
            # incolla alla cieca: il testo resta negli Appunti (Ctrl+V dove
            # serve) e il beep avvisa che la frase NON e' arrivata
            if winsound is not None:
                winsound.MessageBeep(winsound.MB_ICONHAND)
            logging.info("incollato alla cieca: testo conservato negli Appunti")
        # invio automatico: parte sempre. La pausa prima dell'Invio dipende
        # dal contesto: a voce ON e' conversazione vera con l'agente (botta e
        # risposta), a voce OFF serve tempo per correggere il testo incollato.
        if INVIO_AUTOMATICO and not senza_casella:
            attesa = (
                RITARDO_INVIO_CONVERSAZIONE
                if voce_attiva()
                else RITARDO_INVIO_AUTOMATICO
            )
            time.sleep(0.15)  # il Ctrl+V sintetico non conta come gesto dell'utente
            riferimento = time.monotonic()
            trascorso = 0.0
            annullato = False
            while trascorso < attesa:
                time.sleep(min(0.1, attesa - trascorso))
                trascorso = time.monotonic() - riferimento
                if invio_da_annullare(
                    ultima_pressione_utente, riferimento, recording
                ):
                    annullato = True
                    break
            if annullato:
                logging.info(
                    "invio automatico ANNULLATO "
                    "(tasto premuto o nuova dettatura in corso)"
                )
            else:
                keyboard_controller.press(Key.enter)
                keyboard_controller.release(Key.enter)
                logging.info("invio automatico premuto")
        print("Inserito:", text)
    except Exception:
        logging.exception("errore trascrizione/incolla")
        eventi.put("nascosto")
        print("Errore durante la trascrizione. Dettagli in voice.log")


def paste_text(text: str, conserva_appunti: bool = False) -> None:
    """Con conserva_appunti=True il ripristino degli Appunti si salta: quando
    l'incolla parte alla cieca il testo dettato deve restare recuperabile."""
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


def worker() -> None:
    while True:
        command = commands.get()
        try:
            if command == "start":
                start_recording()
            elif command == "stop":
                stop_recording()
        except Exception:
            logging.exception("errore comando audio")


def watchdog() -> None:
    while True:
        time.sleep(1)
        if recording and recording_started_at is not None:
            duration = time.monotonic() - recording_started_at
            if duration > MAX_RECORDING_SEC:
                logging.warning("registrazione oltre %.1fs: stop anti-incanto", duration)
                commands.put("stop")


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
        logging.info(stato)
        pronuncia(stato)
    except Exception:
        logging.exception("errore commutazione voce")


def on_press(key) -> None:
    global key_down, voice_key_down, ultima_pressione_utente
    ultima_pressione_utente = time.monotonic()
    if key == HOTKEY and not key_down:
        key_down = True
        commands.put("start")
    elif TASTO_VOCE is not None and key == TASTO_VOCE and not voice_key_down:
        voice_key_down = True  # debounce: un hold = una sola commutazione
        threading.Thread(target=commuta_voce, daemon=True).start()


def on_release(key) -> None:
    global key_down, voice_key_down
    if key == HOTKEY and key_down:
        key_down = False
        commands.put("stop")
    elif key == TASTO_VOCE:
        voice_key_down = False  # rilasciato: la prossima pressione ricommuta


# --- overlay: la pill "salchiarenza.ai" con la barra a sorriso (thread principale) ---

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
        self.stato = "nascosto"
        self.root.withdraw()
        self._non_rubare_focus()

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

    def _disegna_ascolto(self) -> None:
        self.canvas.delete("all")
        self._pill()
        self.canvas.create_text(
            LARGHEZZA / 2, 15, text=BRAND, fill="#F4F4F4",
            font=("Segoe UI", 11, "normal"),
        )
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
        self.canvas.create_text(
            LARGHEZZA / 2, 15, text=BRAND, fill="#F4F4F4",
            font=("Segoe UI", 11, "normal"),
        )
        self.canvas.create_text(
            LARGHEZZA / 2, 44, text=testo, fill="#FFFFFF",
            font=("Consolas", 13, "normal"),
        )

    def tick(self) -> None:
        try:
            while True:
                self.stato = eventi.get_nowait()
                if self.stato == "ascolto":
                    self.root.deiconify()
                elif self.stato == "nascosto":
                    self.root.withdraw()
        except queue.Empty:
            pass
        if self.stato == "ascolto":
            self._disegna_ascolto()
        elif self.stato == "trascrivo":
            self._disegna_trascrivo()
        elif self.stato == "sistemo":
            self._disegna_trascrivo("Sistemo...")
        self.root.after(60, self.tick)

    def run(self) -> None:
        self.root.after(60, self.tick)
        self.root.mainloop()


def main() -> None:
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
    print("Voice Dettatura Windows v1.3")
    print("Ctrl destro: tieni premuto, parla, rilascia -> il testo viene incollato.")
    print("Tasto Menu: accende/spegne Voce AI (le risposte sono audio sintetico).")
    print("Chiudi questa finestra per fermare la dettatura.")
    allinea_volume_ingresso()  # ingresso basso = app muta senza motivo apparente
    threading.Thread(target=worker, daemon=True).start()
    threading.Thread(target=watchdog, daemon=True).start()
    threading.Thread(target=load_model, daemon=True).start()
    threading.Thread(target=impara_dagli_errori_giornaliero, daemon=True).start()
    keyboard.Listener(on_press=on_press, on_release=on_release).start()
    Pannello().run()


if __name__ == "__main__":
    main()
