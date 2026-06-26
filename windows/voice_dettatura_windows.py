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
import json
import logging
import queue
import re
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
eventi: queue.Queue[str] = queue.Queue()      # "ascolto"/"trascrivo"/"nascosto" verso l'overlay
livelli = collections.deque([0.0] * N_BARRE, maxlen=N_BARRE)
blocks: list[np.ndarray] = []
stream = None
recording = False
key_down = False
voice_key_down = False                         # debounce del tasto on/off voce
recording_started_at: float | None = None
model: WhisperModel | None = None


# --- voce in uscita "agenti": interruttore + TTS di Windows, tutto in questo file ---
FLAG_VOICE_ON = BASE / "VOICE_ON"          # se esiste, la voce in uscita e' accesa
PID_FILE = BASE / "voce_pid"               # PID dell'ultima lettura: una voce per volta
VOCE_RATE = int(CFG.get("voce_rate", 0))   # System.Speech: da -10 (lenta) a +10 (veloce)


def voce_attiva() -> bool:
    return FLAG_VOICE_ON.exists()


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


def _ps_voce(rate: int) -> list[str]:
    """Comando PowerShell con System.Speech (incluso in Windows): voce italiana se c'e'."""
    script = (
        "$ErrorActionPreference='SilentlyContinue';"
        "Add-Type -AssemblyName System.Speech;"
        "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer;"
        "$v=$s.GetInstalledVoices()|"
        "?{$_.Enabled -and $_.VoiceInfo.Culture.Name -like 'it*'}|"
        "select -First 1;"
        "if($v){$s.SelectVoice($v.VoiceInfo.Name)};"
        "$s.Volume=100;"
        "$s.Rate=" + str(int(rate)) + ";"
        "$t=[Console]::In.ReadToEnd();"
        "if($t){$s.Speak($t)}"
    )
    return ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script]


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
        _ps_voce(VOCE_RATE),
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


def stop_recording() -> None:
    global stream, recording, recording_started_at
    if not recording:
        return
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
    if not has_voice(audio):
        eventi.put("nascosto")
        return

    eventi.put("trascrivo")
    threading.Thread(target=transcribe_and_paste, args=(audio,), daemon=True).start()


def transcribe_and_paste(audio: np.ndarray) -> None:
    try:
        segments, _info = load_model().transcribe(
            audio,
            language=CFG.get("language", "it"),
            vad_filter=True,
        )
        text = " ".join(segment.text.strip() for segment in segments).strip()
        eventi.put("nascosto")
        if not text:
            return
        paste_text(text)
        # modalita' conversazione: voce accesa = la domanda parte da sola
        if voce_attiva() and INVIO_AUTOMATICO:
            time.sleep(0.1)
            keyboard_controller.press(Key.enter)
            keyboard_controller.release(Key.enter)
        print("Inserito:", text)
    except Exception:
        logging.exception("errore trascrizione/incolla")
        eventi.put("nascosto")
        print("Errore durante la trascrizione. Dettagli in voice.log")


def paste_text(text: str) -> None:
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
    if previous is not None:
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
            stato = "Voce spenta"
        else:
            FLAG_VOICE_ON.touch()
            stato = "Voce accesa"
        logging.info(stato)
        pronuncia(stato)
    except Exception:
        logging.exception("errore commutazione voce")


def on_press(key) -> None:
    global key_down, voice_key_down
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

    def _disegna_trascrivo(self) -> None:
        self.canvas.delete("all")
        self._pill()
        self.canvas.create_text(
            LARGHEZZA / 2, 15, text=BRAND, fill="#F4F4F4",
            font=("Segoe UI", 11, "normal"),
        )
        self.canvas.create_text(
            LARGHEZZA / 2, 44, text="Trascrivo...", fill="#FFFFFF",
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
        self.root.after(60, self.tick)

    def run(self) -> None:
        self.root.after(60, self.tick)
        self.root.mainloop()


def main() -> None:
    logging.basicConfig(
        filename=LOG,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    print("Voice Dettatura Windows v1.2")
    print("Ctrl destro: tieni premuto, parla, rilascia -> il testo viene incollato.")
    print("Tasto Menu: accende/spegne la voce agenti (legge le risposte ad alta voce).")
    print("Chiudi questa finestra per fermare la dettatura.")
    threading.Thread(target=worker, daemon=True).start()
    threading.Thread(target=watchdog, daemon=True).start()
    threading.Thread(target=load_model, daemon=True).start()
    keyboard.Listener(on_press=on_press, on_release=on_release).start()
    Pannello().run()


if __name__ == "__main__":
    main()
