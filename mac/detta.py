"""Dettatura locale hold-to-talk.

Tieni premuto il tasto configurato (default: Cmd sinistro), parla, rilascia:
il testo trascritto da Whisper (in locale) viene incollato dove sta il cursore.
Un pannello nativo non-attivante (non ruba mai il focus) mostra le lineette
che si muovono col volume mentre parli. Per uscire: chiudi la finestra del Terminale.
"""
import collections
import logging
import os
import queue
import subprocess
import sys
import threading
import time

import numpy as np
import sounddevice as sd
import mlx_whisper
import AppKit
import Quartz
from PyObjCTools import AppHelper
from pynput import keyboard
from pynput.keyboard import Controller, Key

from voce_lib import (
    carica_config, voce_attiva, FLAG_VOICE_ON,
    c_e_voce, e_allucinazione, SOGLIA_VOCE, esegui_sicuro,
    timeout_scaduto, glossario_iniziale, applica_sostituzioni,
    serve_pulizia, comando_agente, pulisci_con_agente,
    shortcut_pulizia_disponibile, pulisci_con_shortcut,
    impara_sostituzioni,
)
from parla import ferma as ferma_voce, parla as pronuncia

cfg = carica_config()
TASTO = getattr(Key, cfg["hotkey"])
TASTO_VOCE = getattr(Key, cfg.get("tasto_voce", "alt_l"), None)  # on/off voce agenti
FREQ = 16000  # Whisper lavora a 16 kHz

tastiera = Controller()
registrando = False
blocchi = []
stream = None
listener = None  # listener globale della tastiera (ricreabile dal watchdog)
eventi = queue.Queue()  # il thread tastiera manda qui i cambi di stato per il pannello
comandi_audio = queue.Queue()  # il thread tastiera mette qui "start"/"stop": li esegue il worker audio
tasto_premuto = False  # stato del tasto-detta, posseduto SOLO dal thread tastiera
tasto_voce_premuto = False  # idem per il tasto on/off voce: un hold = una commutazione
inizio_registrazione = None
stop_audio_in_corso_da = None
riavvio_in_corso = False

BARRE = 18  # quante lineette nel visualizzatore
livelli = collections.deque([0.0] * BARRE, maxlen=BARRE)
MAX_REGISTRAZIONE_SEC = float(cfg.get("max_registrazione_sec", 90))
STOP_AUDIO_TIMEOUT_SEC = float(cfg.get("stop_audio_timeout_sec", 10))

# --- pannello di stato nativo (NonactivatingPanel: mai il focus) ---

LARGHEZZA, ALTEZZA = 300, 72
BRAND = "salchiarenza.ai"

app = AppKit.NSApplication.sharedApplication()
app.setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)  # niente icona Dock

pannello = AppKit.NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
    AppKit.NSMakeRect(0, 0, LARGHEZZA, ALTEZZA),
    AppKit.NSWindowStyleMaskBorderless | AppKit.NSWindowStyleMaskNonactivatingPanel,
    AppKit.NSBackingStoreBuffered,
    False,
)
pannello.setLevel_(AppKit.NSStatusWindowLevel)      # sopra tutte le finestre
pannello.setOpaque_(False)
pannello.setBackgroundColor_(AppKit.NSColor.clearColor())
pannello.setIgnoresMouseEvents_(True)
pannello.setCollectionBehavior_(
    AppKit.NSWindowCollectionBehaviorCanJoinAllSpaces
    | AppKit.NSWindowCollectionBehaviorFullScreenAuxiliary
)

vista = pannello.contentView()
vista.setWantsLayer_(True)
vista.layer().setBackgroundColor_(
    AppKit.NSColor.colorWithCalibratedWhite_alpha_(0.08, 0.92).CGColor()
)
vista.layer().setCornerRadius_(16.0)

brand = AppKit.NSTextField.labelWithString_(BRAND)
brand.setFrame_(AppKit.NSMakeRect(0, 48, LARGHEZZA, 18))
brand.setAlignment_(AppKit.NSTextAlignmentCenter)
brand.setTextColor_(AppKit.NSColor.colorWithCalibratedWhite_alpha_(0.96, 0.94))
brand.setFont_(AppKit.NSFont.systemFontOfSize_weight_(13, AppKit.NSFontWeightMedium))
vista.addSubview_(brand)

etichetta = AppKit.NSTextField.labelWithString_("")
etichetta.setFrame_(AppKit.NSMakeRect(0, 17, LARGHEZZA, 28))
etichetta.setAlignment_(AppKit.NSTextAlignmentCenter)
etichetta.setTextColor_(AppKit.NSColor.whiteColor())
etichetta.setFont_(AppKit.NSFont.monospacedSystemFontOfSize_weight_(15, AppKit.NSFontWeightRegular))
etichetta.setHidden_(True)
vista.addSubview_(etichetta)


def colore_da_hex(hex_str):
    """Da '#RRGGBB' a NSColor."""
    hex_str = hex_str.lstrip("#")
    r, g, b = (int(hex_str[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(r, g, b, 1.0)


COLORE_BARRE = colore_da_hex(cfg.get("colore", "#32D74B"))

indicatore_voce = AppKit.NSTextField.labelWithString_("● ON")
indicatore_voce.setFrame_(AppKit.NSMakeRect(LARGHEZZA - 54, 49, 42, 16))
indicatore_voce.setAlignment_(AppKit.NSTextAlignmentRight)
indicatore_voce.setTextColor_(COLORE_BARRE)
indicatore_voce.setFont_(AppKit.NSFont.monospacedSystemFontOfSize_weight_(11, AppKit.NSFontWeightSemibold))
indicatore_voce.setHidden_(True)
vista.addSubview_(indicatore_voce)


def aggiorna_indicatore_voce():
    """Mostra quando la voce agenti e' attiva e puo' inviare in automatico."""
    attiva = voce_attiva() and cfg.get("invio_automatico", True)
    indicatore_voce.setHidden_(not attiva)
    vista.layer().setBorderWidth_(1.0 if attiva else 0.0)
    vista.layer().setBorderColor_(COLORE_BARRE.CGColor())


class VistaOnda(AppKit.NSView):
    """Disegna le lineette del volume lungo un arco a sorriso:
    angoli in su, centro in giu', cosi' il pannello 'parla e sorride'."""

    def drawRect_(self, rect):
        COLORE_BARRE.setFill()
        valori = list(livelli)
        n = len(valori)
        passo = (LARGHEZZA - 40) / n
        centro = (n - 1) / 2
        for i, v in enumerate(valori):
            h = 5 + min(22.0, v * 200)              # altezza barra dal volume
            x = 20 + i * passo
            y_centro = 16 + 12 * (((i - centro) / centro) ** 2)  # arco del sorriso
            barra = AppKit.NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
                AppKit.NSMakeRect(x, y_centro - h / 2, passo * 0.55, h), 2.0, 2.0
            )
            barra.fill()


onda = VistaOnda.alloc().initWithFrame_(AppKit.NSMakeRect(0, 4, LARGHEZZA, 46))
onda.setHidden_(True)
vista.addSubview_(onda)


def _contiene_punto(rect, punto):
    return (
        rect.origin.x <= punto.x < rect.origin.x + rect.size.width
        and rect.origin.y <= punto.y < rect.origin.y + rect.size.height
    )


def schermo_attivo():
    """Usa il monitor sotto il mouse: nel normale uso e' quello dove Sal detta."""
    punto = AppKit.NSEvent.mouseLocation()
    for schermo in AppKit.NSScreen.screens():
        if _contiene_punto(schermo.frame(), punto):
            return schermo
    return AppKit.NSScreen.mainScreen()


def posiziona_pannello():
    """Tiene la pill in basso al centro del monitor attivo, anche con 2 schermi."""
    area = schermo_attivo().visibleFrame()
    x = area.origin.x + (area.size.width - LARGHEZZA) / 2
    margine_basso = min(80, max(16, area.size.height * 0.10))
    y = area.origin.y + margine_basso
    pannello.setFrameOrigin_(AppKit.NSMakePoint(x, y))


posiziona_pannello()


def stop_se_registrazione_troppo_lunga():
    """Airbag anti-incanto: non ferma mai subito, solo se resta aperta troppo."""
    global tasto_premuto
    ora = time.monotonic()
    if timeout_scaduto(registrando, inizio_registrazione, ora, MAX_REGISTRAZIONE_SEC):
        durata = ora - inizio_registrazione
        logging.getLogger("voce").warning("registrazione oltre %.1fs: stop anti-incanto", durata)
        tasto_premuto = False
        comandi_audio.put("stop")


class GestorePannello(AppKit.NSObject):
    """Vive nel thread principale: applica gli stati e anima le lineette."""

    stato = "nascosto"
    _tick = 0

    def tick_(self, timer):
        try:
            while True:
                nuovo = eventi.get_nowait()
                self.stato = nuovo
                if nuovo == "ascolto":
                    posiziona_pannello()
                    aggiorna_indicatore_voce()
                    brand.setHidden_(False)
                    etichetta.setHidden_(True)
                    onda.setHidden_(False)
                    pannello.orderFrontRegardless()  # mostra SENZA attivare l'app
                elif nuovo == "trascrivo":
                    aggiorna_indicatore_voce()
                    onda.setHidden_(True)
                    brand.setHidden_(False)
                    etichetta.setStringValue_("⏳ Trascrivo…")
                    etichetta.setHidden_(False)
                elif nuovo == "sistemo":
                    etichetta.setStringValue_("✨ Sistemo…")
                    etichetta.setHidden_(False)
                elif nuovo == "nascosto":
                    pannello.orderOut_(None)
        except queue.Empty:
            pass
        if self.stato == "ascolto":
            stop_se_registrazione_troppo_lunga()
            onda.setNeedsDisplay_(True)  # ridisegna il sorriso col volume nuovo
        # watchdog dell'hotkey: se il listener della tastiera si fosse fermato,
        # lo riaccendo (controllo ogni ~2s, non a ogni tick).
        self._tick += 1
        if self._tick % 25 == 0:
            global listener
            if listener is not None and not listener.is_alive():
                logging.getLogger("voce").warning("listener tastiera fermo: riavvio")
                listener = avvia_listener()


# --- registrazione (sul thread tastiera) e trascrizione (su un thread a parte) ---

def suono(nome):
    """Feedback acustico: Pop = registra, Bottle = trascrivo."""
    if cfg.get("suoni", True):
        subprocess.Popen(["afplay", f"/System/Library/Sounds/{nome}.aiff"])


GLOSSARIO_PROMPT = glossario_iniziale(cfg)  # nomi/brand scritti giusti da Whisper
# detta pulito, cercato una volta all'avvio: prima il modello Apple on-device
# via Comando Rapido (~1s, zero cloud), poi l'agente locale come riserva.
SHORTCUT_PULIZIA = cfg.get("pulizia_shortcut", "Voce Pulita")
if not (cfg.get("detta_pulito", False) and shortcut_pulizia_disponibile(SHORTCUT_PULIZIA)):
    SHORTCUT_PULIZIA = None
COMANDO_PULIZIA = comando_agente() if cfg.get("detta_pulito", False) else None
if cfg.get("detta_pulito", False) and SHORTCUT_PULIZIA is None and COMANDO_PULIZIA is None:
    logging.getLogger("voce").warning(
        "detta_pulito attivo ma niente Comando Rapido ne' agente (claude/codex) nel PATH")


def trascrivi(audio):
    esito = mlx_whisper.transcribe(
        audio, path_or_hf_repo=cfg["modello"], language=cfg["lingua"],
        initial_prompt=GLOSSARIO_PROMPT,
    )
    return applica_sostituzioni(esito["text"].strip(), cfg.get("sostituzioni", {}))


def incolla(testo):
    """Mette il testo in clipboard, simula Cmd+V, poi ripristina la clipboard."""
    vecchia = subprocess.run(["pbpaste"], capture_output=True).stdout
    subprocess.run(["pbcopy"], input=testo.encode())
    time.sleep(0.15)
    with tastiera.pressed(Key.cmd):
        tastiera.press("v")
        tastiera.release("v")
    time.sleep(0.4)
    subprocess.run(["pbcopy"], input=vecchia)


def su_callback(indata, frames, t, status):
    blocchi.append(indata.copy())
    livelli.append(float(np.sqrt(np.mean(indata ** 2))))  # volume per le lineette


def avvia_registrazione():
    global stream, blocchi, registrando, inizio_registrazione
    ferma_voce()  # ti zittisco se parlo io: tocca a te
    blocchi = []
    livelli.extend([0.0] * BARRE)
    stream = sd.InputStream(
        samplerate=FREQ, channels=1, dtype="float32", callback=su_callback
    )
    stream.start()
    registrando = True
    inizio_registrazione = time.monotonic()
    logging.getLogger("voce").info("registrazione avviata")
    suono("Pop")
    eventi.put("ascolto")


_lock_trascrizione = threading.Lock()


def _trascrivi_e_incolla(audio):
    """Parte pesante (Whisper ~2-3s + incolla): gira su un thread a parte e
    blindata. Se girasse sul thread della tastiera, macOS la vedrebbe "appesa"
    e disabiliterebbe l'hotkey; e un suo errore ucciderebbe il listener."""
    try:
        with _lock_trascrizione:  # una trascrizione per volta
            eventi.put("trascrivo")
            testo = trascrivi(audio)
        if e_allucinazione(testo):  # frase-fantasma di Whisper sul non-parlato: scarta
            testo = ""
        if testo and (SHORTCUT_PULIZIA or COMANDO_PULIZIA) and serve_pulizia(testo, cfg):
            eventi.put("sistemo")
            log = logging.getLogger("voce")
            # i TESTI si loggano solo col flag debug (la privacy promette
            # "nessun archivio delle dettature"); tempi ed esiti sempre.
            debug = cfg.get("debug_dettature", False)
            if debug:
                log.info("grezzo: %s", testo)
            glossario = cfg.get("glossario", [])
            inizio_pulizia = time.monotonic()
            pulito = None
            if SHORTCUT_PULIZIA:  # corsia veloce: modello Apple on-device (~1s)
                pulito = pulisci_con_shortcut(
                    testo, SHORTCUT_PULIZIA,
                    timeout=float(cfg.get("pulizia_timeout_shortcut_sec", 10)),
                    glossario=glossario,
                )
                log.info("pulizia shortcut %.1fs: %s", time.monotonic() - inizio_pulizia,
                         "ok" if pulito else "FALLITA")
                if debug and pulito:
                    log.info("pulito: %s", pulito)
            if pulito is None and COMANDO_PULIZIA:  # riserva: agente locale
                pulito = pulisci_con_agente(
                    testo, COMANDO_PULIZIA,
                    timeout=float(cfg.get("pulizia_timeout_sec", 20)),
                    glossario=glossario,
                )
                log.info("pulizia agente %.1fs", time.monotonic() - inizio_pulizia)
                if debug:
                    log.info("pulito: %s", pulito)
            testo = pulito or testo
        eventi.put("nascosto")
        if testo:
            incolla(testo)
            # modalita' conversazione: voce accesa = la domanda parte da sola
            if voce_attiva() and cfg.get("invio_automatico", True):
                time.sleep(0.1)
                tastiera.press(Key.enter)
                tastiera.release(Key.enter)
    except Exception:
        logging.getLogger("voce").exception("errore in trascrizione/incolla")
        eventi.put("nascosto")


def ferma_e_trascrivi():
    """Ferma lo stream, applica il gate sull'energia, poi lancia la trascrizione
    su un thread a parte. Gira sul WORKER audio, mai sul thread della tastiera:
    stream.stop()/close() prendono un mutex della HAL di CoreAudio e, chiamati
    dentro il callback dell'event-tap, vanno in deadlock col thread IO di
    CoreAudio sullo stesso mutex (l'hotkey si 'incanta'). Vedi _worker_audio."""
    global stream, registrando, inizio_registrazione, stop_audio_in_corso_da
    if not registrando and stream is None:
        eventi.put("nascosto")
        return
    registrando = False
    inizio_registrazione = None
    stop_audio_in_corso_da = time.monotonic()
    if stream is not None:
        try:
            stream.stop()
            stream.close()
        finally:
            stream = None
            stop_audio_in_corso_da = None
    else:
        stop_audio_in_corso_da = None
    logging.getLogger("voce").info("registrazione fermata")
    suono("Bottle")
    if not blocchi:
        eventi.put("nascosto")
        return
    audio = np.concatenate(blocchi)[:, 0]
    if len(audio) < FREQ * 0.4:  # sotto 0,4 s: pressione accidentale
        eventi.put("nascosto")
        return
    rms = float(np.sqrt(np.mean(audio ** 2)))
    logging.getLogger("voce").info("audio: %.1fs, volume rms %.4f", len(audio) / FREQ, rms)
    if not c_e_voce(audio, cfg.get("soglia_voce", SOGLIA_VOCE)):  # silenzio/respiro: niente parlato
        logging.getLogger("voce").info("scartato: volume sotto soglia (mic muto/occupato?)")
        eventi.put("nascosto")
        return
    threading.Thread(target=_trascrivi_e_incolla, args=(audio,), daemon=True).start()


def commuta_voce():
    """Tasto on/off della voce agenti, con conferma parlata."""
    if FLAG_VOICE_ON.exists():
        FLAG_VOICE_ON.unlink()
        stato = "Voce spenta"
    else:
        FLAG_VOICE_ON.touch()
        stato = "Voce accesa"
    pronuncia(stato)


def worker_audio():
    """Possiede il ciclo di vita dello stream (open/start/stop/close) FUORI dal
    thread della tastiera. Il callback dell'hotkey deve solo mettere "start"/
    "stop" in coda e tornare subito: se invece aprisse o chiudesse lo stream
    direttamente, le chiamate bloccanti di CoreAudio incastrerebbero l'event-tap
    e la dettatura si 'incanterebbe' (deadlock sul mutex HAL col thread IO)."""
    while True:
        cmd = comandi_audio.get()
        if cmd == "start":
            esegui_sicuro(avvia_registrazione)
        elif cmd == "stop":
            esegui_sicuro(ferma_e_trascrivi)


def riavvia_forzato(motivo):
    """Riavvia l'app se CoreAudio resta bloccato durante lo stop del microfono."""
    global riavvio_in_corso
    if riavvio_in_corso:
        return
    riavvio_in_corso = True
    logging.getLogger("voce").critical("riavvio forzato dettatura: %s", motivo)
    cartella = os.path.dirname(os.path.abspath(__file__))
    subprocess.Popen([sys.executable, os.path.abspath(__file__)], cwd=cartella, start_new_session=True)
    os._exit(70)


def watchdog_audio():
    """Airbag fuori dal pannello: interviene anche se l'UI resta viva ma l'audio no."""
    global tasto_premuto
    while True:
        time.sleep(0.5)
        ora = time.monotonic()
        if timeout_scaduto(registrando, inizio_registrazione, ora, MAX_REGISTRAZIONE_SEC):
            durata = ora - inizio_registrazione
            logging.getLogger("voce").warning(
                "registrazione oltre %.1fs: stop anti-incanto watchdog", durata
            )
            tasto_premuto = False
            comandi_audio.put("stop")
        if timeout_scaduto(
            stop_audio_in_corso_da is not None,
            stop_audio_in_corso_da,
            ora,
            STOP_AUDIO_TIMEOUT_SEC,
        ):
            durata = ora - stop_audio_in_corso_da
            riavvia_forzato(f"stop audio bloccato da {durata:.1f}s")


def su_pressione(tasto):
    global tasto_premuto, tasto_voce_premuto
    if tasto == TASTO and not tasto_premuto:
        tasto_premuto = True            # stato sul solo thread tastiera: niente race
        comandi_audio.put("start")      # il lavoro audio (bloccante) lo fa il worker
    elif TASTO_VOCE is not None and tasto == TASTO_VOCE and not tasto_voce_premuto:
        tasto_voce_premuto = True       # debounce: un hold = una sola commutazione
        # commuta_voce fa lavoro BLOCCANTE (pkill/shortcuts/say/pipe): MAI qui sul
        # thread della tastiera, o l'event-tap si "appende" e tutta la dettatura si
        # blocca (e il watchdog non recupera: il listener resta vivo ma incastrato).
        threading.Thread(target=esegui_sicuro, args=(commuta_voce,), daemon=True).start()


def su_rilascio(tasto):
    global tasto_premuto, tasto_voce_premuto
    if tasto == TASTO and tasto_premuto:
        tasto_premuto = False
        comandi_audio.put("stop")
    elif tasto == TASTO_VOCE:
        tasto_voce_premuto = False      # rilasciato: la prossima pressione ricommuta


# macOS disabilita un event-tap appena una callback tarda anche una sola volta
# (kCGEventTapDisabledByTimeout) o per timeout di sistema (ByUserInput). pynput
# 1.8.2 NON lo riaccende: il thread del listener resta VIVO ma sordo e l'hotkey
# "si disabilita ogni tanto" senza che il watchdog su is_alive() se ne accorga.
# Qui intercettiamo i due eventi di disabilitazione e riaccendiamo il tap subito.
_TAP_DISABILITATO = (
    Quartz.kCGEventTapDisabledByTimeout,
    Quartz.kCGEventTapDisabledByUserInput,
)


class ListenerResiliente(keyboard.Listener):
    """Listener tastiera che si auto-riaccende se macOS spegne l'event-tap."""

    def _create_event_tap(self):
        self._tap = super()._create_event_tap()
        return self._tap

    def _handle_message(self, proxy, event_type, event, refcon, injected):
        if event_type in _TAP_DISABILITATO:
            Quartz.CGEventTapEnable(self._tap, True)  # riaccendi: nessun buco
            logging.getLogger("voce").warning("event-tap disabilitato da macOS: riacceso")
            return
        return super()._handle_message(proxy, event_type, event, refcon, injected)


def avvia_listener():
    """Crea e avvia il listener globale della tastiera (usato all'avvio e dal
    watchdog se il listener dovesse fermarsi)."""
    lis = ListenerResiliente(on_press=su_pressione, on_release=su_rilascio)
    lis.start()
    return lis


def unica_istanza():
    """Chiude ogni altra istanza di detta.py: l'ultima avviata vince.

    Senza questo, i rilanci dal launcher si accavallano (il vecchio processo
    sopravvive alla chiusura della finestra del Terminale) e le istanze si
    rubano clipboard e microfono a vicenda.
    """
    mio = os.getpid()
    esito = subprocess.run(
        ["pgrep", "-f", r"[Pp]ython.*detta\.py"], capture_output=True, text=True
    )
    for riga in esito.stdout.split():
        pid = int(riga)
        if pid != mio:
            try:
                os.kill(pid, 15)
            except ProcessLookupError:
                pass


def _impara_dagli_errori():
    """Apprendimento automatico, una volta al giorno all'avvio: rilegge le
    ultime dettature grezze dal log, l'agente individua le parole trascritte
    male in modo ricorrente e le aggiunge da solo alle sostituzioni."""
    base = os.path.dirname(os.path.abspath(__file__))
    marcatore = os.path.join(base, "APPRENDIMENTO_ULTIMO")
    oggi = time.strftime("%Y-%m-%d")
    try:
        if open(marcatore).read().strip() == oggi:
            return  # gia' fatto oggi
    except OSError:
        pass
    if not cfg.get("debug_dettature", False):
        return  # senza log dei testi non c'e' niente da cui imparare
    comando = COMANDO_PULIZIA or comando_agente()
    if not comando:
        return
    nuove = impara_sostituzioni(
        os.path.join(base, "voce.log"), os.path.join(base, "config.json"), comando
    )
    if nuove:
        cfg.setdefault("sostituzioni", {}).update(nuove)  # attive da subito
        logging.getLogger("voce").info("imparate sostituzioni: %s", nuove)
    with open(marcatore, "w") as f:
        f.write(oggi)


def _scalda_modello():
    """Scalda Whisper in background: cosi' l'hotkey e' attivo SUBITO e non dopo
    i ~10s di caricamento del modello (prima, in quei secondi, premere il tasto
    non faceva niente e la dettatura sembrava 'non attivarsi')."""
    with _lock_trascrizione:  # niente doppio caricamento se Sal detta mentre scalda
        esegui_sicuro(trascrivi, np.zeros(FREQ, dtype=np.float32))


def _avvisa_se_non_autorizzato():
    """Se macOS non ha autorizzato il monitoraggio tasti, il listener parte ma
    non riceve nulla: l'hotkey sembra 'non attivarsi' senza spiegazione. Qui lo
    diciamo chiaro e apriamo da soli il pannello giusto delle Impostazioni."""
    try:
        from ApplicationServices import AXIsProcessTrusted
    except Exception:
        return
    if AXIsProcessTrusted():
        return
    msg = ("PERMESSO MANCANTE: macOS non autorizza il monitoraggio dei tasti, "
           "quindi il tasto non viene catturato. Impostazioni di Sistema → Privacy "
           "e sicurezza → 'Monitoraggio input' e 'Accessibilita'': attiva il "
           "Terminale (o Python), poi rilancia la dettatura.")
    print(msg)
    logging.getLogger("voce").warning("processo non autorizzato (Accessibility/Input Monitoring)")
    subprocess.Popen(
        ["open", "x-apple.systempreferences:com.apple.preference.security?Privacy_ListenEvent"]
    )


if __name__ == "__main__":
    unica_istanza()
    logging.basicConfig(
        filename=os.path.join(os.path.dirname(os.path.abspath(__file__)), "voce.log"),
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    logging.getLogger("voce").info("avvio dettatura")
    _avvisa_se_non_autorizzato()
    threading.Thread(target=worker_audio, daemon=True).start()  # possiede lo stream audio
    threading.Thread(target=watchdog_audio, daemon=True).start()  # recupera stop persi/CoreAudio bloccato
    listener = avvia_listener()  # hotkey attivo DA SUBITO
    threading.Thread(target=_scalda_modello, daemon=True).start()  # modello in sottofondo
    threading.Thread(target=lambda: esegui_sicuro(_impara_dagli_errori), daemon=True).start()
    print(f"Voce — dettatura attiva (il modello si scalda in sottofondo). "
          f"Tieni premuto [{cfg['hotkey']}] e parla.")
    gestore = GestorePannello.alloc().init()
    AppKit.NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
        0.08, gestore, "tick:", None, True
    )
    AppHelper.runEventLoop()
