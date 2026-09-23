"""Dettatura locale hold-to-talk.

Tieni premuto il tasto configurato (default: Cmd sinistro), parla, rilascia:
il testo trascritto da Whisper (in locale) viene incollato dove sta il cursore.
Un pannello nativo non-attivante (non ruba mai il focus) mostra le lineette
che si muovono col volume mentre parli. Per uscire: chiudi la finestra del Terminale.
"""
import collections
import logging
import logging.handlers
import os
import queue
import subprocess
import sys
import threading
import json
import time

import numpy as np
import sounddevice as sd
import mlx_whisper
import AppKit
import ApplicationServices as AX
import Quartz
from PyObjCTools import AppHelper
from pynput import keyboard
from pynput.keyboard import Controller, Key

from voce_lib import (
    carica_config, config_scrivibile, voce_attiva, FLAG_VOICE_ON, FLAG_PARLANDO,
    mani_libere_attive, FLAG_MANI_LIBERE_ON, FLAG_TURNO_UTENTE, BASE, SOURCE_BASE,
    apri_turno_utente, chiudi_turno_utente, CodaDettature,
    c_e_voce, aggiorna_scarti_fuori_scala, e_allucinazione, SOGLIA_VOCE, esegui_sicuro,
    diagnosi_audio_muto, GUADAGNO_INGRESSO_MINIMO, GUADAGNO_INGRESSO_TARGET,
    corsia_utilizzabile, registra_esito_corsia, SOGLIA_GUASTI_CORSIA, RIPOSO_CORSIA_SEC,
    stop_anti_incanto, glossario_iniziale, applica_sostituzioni,
    converti_punteggiatura_dettata,
    serve_pulizia, comando_agente, comandi_agente, destinazione_agente, ritardo_invio,
    shortcut_pulizia_disponibile, pulisci_con_shortcut,
    impara_sostituzioni, ruolo_editabile, scegli_casella, in_zona_scrittura,
    casella_ammissibile, cornice_reale, finestra_credibile, ordina_finestre, chiave_casella, posizione_relativa, punto_da_relativa,
    finestra_su_altro_schermo, schermo_del_punto, schermo_della_finestra, app_sul_monitor, app_ha_finestra_sul_monitor, e_browser_chromium,
    FILE_CASELLE_RICORDATE, caselle_in_json, caselle_da_json,
    salva_audio_recente, rimuovi_eco_glossario,
    trova_taglio, unisci_segmenti, prompt_con_contesto,
    SOGLIA_SILENZIO_PROGRESSIVA, BLOCCO_PROGRESSIVO_SEC,
)
from parla import (
    ferma as ferma_voce, parla as pronuncia, elenco_conversazioni,
    scegli_conversazione, rileggi_ultima,
)

cfg = carica_config()
TASTO = getattr(Key, cfg["hotkey"])
FREQ = 16000  # Whisper lavora a 16 kHz

# Interruttori scelti da Sal (06/07, iterazione definitiva):
# - voce agenti = OPTION + FRECCIA SINISTRA (la freccia attaccata a Option
#   sulla sua tastiera; provato da lui: nessuna interferenza);
# - mani libere = CMD + OPTION tenuti insieme (solo modificatori: niente
#   carattere composto che finirebbe digitato in chat). Lo stato dei
#   modificatori si legge dai flag di sistema Quartz, NON dagli eventi
#   pynput: sulla tastiera fisica di Sal i modificatori premuti insieme
#   non generavano alcun evento (verificato dal log 06/07).
# Option da solo e' NEUTRO.
TASTO_COMBO_VOCE = Key.left  # Option + freccia sinistra = voce agenti on/off

tastiera = Controller()
registrando = False
blocchi = []
stream = None  # aperto una volta sola all'avvio: mai piu' stop()/close() per ogni dettatura
listener = None  # listener globale della tastiera (ricreabile dal watchdog)
eventi = queue.Queue()  # il thread tastiera manda qui i cambi di stato per il pannello
comandi_audio = queue.Queue()  # il thread tastiera mette qui "start"/"stop": li esegue il worker audio
tasto_premuto = False  # stato del tasto-detta, posseduto SOLO dal thread tastiera
combo_voce_scattato = False  # debounce: Option+freccia tenuti = una sola commutazione
combo_mani_libere_scattato = False  # debounce: Cmd+Option tenuti = una sola commutazione
ultima_pressione_utente = 0.0  # qualsiasi tasto: annulla l'Invio automatico in attesa
inizio_registrazione = None
volume_corrente = 0.0  # RMS aggiornato ad ogni callback audio, anche fuori registrazione
# anello di pre-registrazione (~1s): i blocchi audio appena precedenti allo
# start, per non perdere l'attacco della frase quando parte il VAD mani-libere
pre_registrazione = collections.deque(maxlen=32)
# Trascrizione progressiva (04/09): mentre tieni premuto, i segmenti gia'
# chiusi su una pausa vengono trascritti in sottofondo; al rilascio resta
# solo la coda. rms_blocchi corre parallelo a blocchi (un valore per blocco)
# e serve a trovare le pause; sessione_progressiva e' la sessione della
# registrazione in corso (None se spenta o fuori registrazione).
rms_blocchi = []
sessione_progressiva = None
turno_utente_token = None  # resta aperto fino a trascrizione, incolla e Invio
coda_dettature = CodaDettature()
PROGRESSIVA = bool(cfg.get("trascrizione_progressiva", False))
PROGRESSIVA_BLOCCO_SEC = float(cfg.get("trascrizione_progressiva_blocco_sec", BLOCCO_PROGRESSIVO_SEC))
PROGRESSIVA_SOGLIA_SILENZIO = float(cfg.get("trascrizione_progressiva_soglia_silenzio", SOGLIA_SILENZIO_PROGRESSIVA))

BARRE = 18  # quante lineette nel visualizzatore
livelli = collections.deque([0.0] * BARRE, maxlen=BARRE)
MAX_REGISTRAZIONE_SEC = float(cfg.get("max_registrazione_sec", 90))
# Coda al rilascio del tasto-detta: il microfono resta in ascolto ancora un
# attimo, cosi' l'ultima sillaba non si perde se il tasto viene mollato un
# pelo prima di finire la frase. Solo per la dettatura manuale: il VAD
# mani-libere ha gia' la sua pausa di silenzio.
CODA_RILASCIO_SEC = float(cfg.get("coda_rilascio_sec", 0.5))

# tetto DURO: ferma anche col tasto fisicamente giu' (tasto incastrato)
MAX_REGISTRAZIONE_TASTO_SEC = float(cfg.get("max_registrazione_tasto_sec", 300))

# --- pannello di stato nativo (NonactivatingPanel: mai il focus) ---

LARGHEZZA, ALTEZZA = 300, 72
BRAND = cfg.get("brand", "LeaderAI.")

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

def colore_da_hex(hex_str):
    """Da '#RRGGBB' a NSColor."""
    hex_str = hex_str.lstrip("#")
    r, g, b = (int(hex_str[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(r, g, b, 1.0)


COLORE_BARRE = colore_da_hex(cfg.get("colore", "#32D74B"))
VERDE_FIRMA = colore_da_hex("#56C842")  # il punto del logo "LeaderAI."


def font_marchio(dimensione):
    """Onest Bold, il carattere del logo LeaderAI, dal file accanto all'app e
    solo per questo processo; se manca, il grassetto di sistema."""
    try:
        import CoreText
        url = AppKit.NSURL.fileURLWithPath_(str(SOURCE_BASE / "Onest.ttf"))
        CoreText.CTFontManagerRegisterFontsForURL(url, CoreText.kCTFontManagerScopeProcess, None)
        font = AppKit.NSFontManager.sharedFontManager().fontWithFamily_traits_weight_size_(
            "Onest", 0, 9, dimensione)
        if font is not None:
            return font
    except Exception:
        pass
    return AppKit.NSFont.systemFontOfSize_weight_(dimensione, AppKit.NSFontWeightBold)


# "LeaderAI." come nel logo: il punto finale diventa un punto verde vivo, che
# cresce e si accende con la voce mentre parli e pulsa mentre trascrive.
# Un marchio senza punto finale resta testo semplice.
PUNTO_VIVO = BRAND.endswith(".")
TESTO_MARCHIO = BRAND[:-1] if PUNTO_VIVO else BRAND
FONT_MARCHIO = font_marchio(16)
TESTO_BRAND = AppKit.NSAttributedString.alloc().initWithString_attributes_(TESTO_MARCHIO, {
    AppKit.NSFontAttributeName: FONT_MARCHIO,
    AppKit.NSForegroundColorAttributeName: AppKit.NSColor.colorWithCalibratedWhite_alpha_(0.97, 1.0),
})
LATO_PUNTO = round(FONT_MARCHIO.capHeight() * 0.34, 1)  # un po' piu' del logo: si vede meglio
SPAZIO_PUNTO = round(FONT_MARCHIO.capHeight() * 0.12, 1)
_larghezza_marchio = TESTO_BRAND.size().width + ((SPAZIO_PUNTO + LATO_PUNTO) if PUNTO_VIVO else 0)
X_MARCHIO = round((LARGHEZZA - _larghezza_marchio) / 2)
Y_BASE_MARCHIO = 9  # linea di base del testo dentro la fascia del marchio
# Mentre trascrive LeaderAI resta protagonista: si ingrandisce al centro della
# pill e la scritta di stato, piccola, sta sotto (Sal, 23/09/2026).
SCALA_EVIDENZA = 1.35
Y_BASE_EVIDENZA = 39  # linea di base del marchio ingrandito, nella pill

# Una vista che ospita gli strati Core Animation del logo: testo, firma e punto
# si animano da soli, fluidi, senza ridisegnare la pill a ogni tick.
brand = AppKit.NSView.alloc().initWithFrame_(vista.bounds())
brand.setLayer_(Quartz.CALayer.layer())
brand.setWantsLayer_(True)
vista.addSubview_(brand)
marchio = Quartz.CALayer.layer()  # la fascia in alto: si sposta e si ingrandisce tutta insieme
marchio.setFrame_(((0, 44), (LARGHEZZA, 28)))
brand.layer().addSublayer_(marchio)
testo_marchio = Quartz.CATextLayer.layer()
testo_marchio.setString_(TESTO_BRAND)
testo_marchio.setContentsScale_(3.0)  # nitido anche ingrandito sugli schermi Retina
_dim = TESTO_BRAND.size()
testo_marchio.setFrame_(((X_MARCHIO, Y_BASE_MARCHIO - (_dim.height - FONT_MARCHIO.ascender())),
                         (_dim.width, _dim.height)))
marchio.addSublayer_(testo_marchio)

punto = firma = None
if PUNTO_VIVO:
    # la firma del sito: la sottolineatura verde che si disegna da sinistra
    firma = Quartz.CALayer.layer()
    firma.setAnchorPoint_((0, 0.5))
    firma.setBounds_(((0, 0), (TESTO_BRAND.size().width, round(FONT_MARCHIO.capHeight() * 0.18, 1))))
    firma.setPosition_((X_MARCHIO, Y_BASE_MARCHIO - FONT_MARCHIO.capHeight() * 0.34))
    firma.setBackgroundColor_(VERDE_FIRMA.CGColor())
    marchio.addSublayer_(firma)
    punto = Quartz.CALayer.layer()
    punto.setBounds_(((0, 0), (LATO_PUNTO, LATO_PUNTO)))
    punto.setPosition_((X_MARCHIO + TESTO_BRAND.size().width + SPAZIO_PUNTO + LATO_PUNTO / 2,
                        Y_BASE_MARCHIO + LATO_PUNTO / 2))
    punto.setCornerRadius_(LATO_PUNTO / 2)
    punto.setBackgroundColor_(VERDE_FIRMA.CGColor())
    punto.setShadowColor_(VERDE_FIRMA.CGColor())
    punto.setShadowOffset_((0, 0))
    punto.setShadowRadius_(5.0)
    punto.setShadowOpacity_(0.0)
    marchio.addSublayer_(punto)


def marchio_in_evidenza(acceso, subito=False):
    """Con una scritta di stato (trascrivo, sistemo, microfono) il marchio si
    ingrandisce al centro; mentre parli torna in alto sopra le lineette."""
    if acceso:
        centro, base = 44 + 14, 44 + Y_BASE_MARCHIO
        spostamento = Y_BASE_EVIDENZA - (centro + SCALA_EVIDENZA * (base - centro))
        forma = Quartz.CATransform3DConcat(
            Quartz.CATransform3DMakeScale(SCALA_EVIDENZA, SCALA_EVIDENZA, 1.0),
            Quartz.CATransform3DMakeTranslation(0, spostamento, 0))
    else:
        forma = Quartz.CATransform3DIdentity
    Quartz.CATransaction.begin()
    Quartz.CATransaction.setDisableActions_(subito)
    Quartz.CATransaction.setAnimationDuration_(0.25)
    marchio.setTransform_(forma)
    Quartz.CATransaction.commit()


def marchio_entra():
    """Alla comparsa della pill il punto 'si accende' con un piccolo scatto e
    la firma si disegna da sinistra, con la curva della home del sito."""
    if punto is None:
        return
    punto.removeAnimationForKey_("pulsa")
    scatto = Quartz.CAKeyframeAnimation.animationWithKeyPath_("transform.scale")
    scatto.setValues_([0.2, 1.6, 1.0])
    scatto.setKeyTimes_([0.0, 0.55, 1.0])
    scatto.setDuration_(0.35)
    punto.addAnimation_forKey_(scatto, "entra")
    disegna = Quartz.CABasicAnimation.animationWithKeyPath_("transform.scale.x")
    disegna.setFromValue_(0.0)
    disegna.setToValue_(1.0)
    disegna.setDuration_(0.75)
    disegna.setTimingFunction_(Quartz.CAMediaTimingFunction.functionWithControlPoints____(0.65, 0.0, 0.35, 1.0))
    firma.addAnimation_forKey_(disegna, "disegna")


def punto_segue_voce(volume):
    """Mentre parli il punto cresce e si illumina col volume della voce."""
    if punto is None:
        return
    Quartz.CATransaction.begin()
    Quartz.CATransaction.setAnimationDuration_(0.12)
    s = 1.0 + min(0.9, volume * 15)
    punto.setTransform_(Quartz.CATransform3DMakeScale(s, s, 1.0))
    punto.setShadowOpacity_(min(0.9, volume * 20))
    Quartz.CATransaction.commit()


def punto_pulsa(acceso):
    """Mentre trascrive il punto pulsa, come un cuore che lavora."""
    if punto is None:
        return
    if not acceso:
        punto.removeAnimationForKey_("pulsa")
        return
    if punto.animationForKey_("pulsa") is not None:
        return
    Quartz.CATransaction.begin()
    Quartz.CATransaction.setDisableActions_(True)
    punto.setTransform_(Quartz.CATransform3DIdentity)
    punto.setShadowOpacity_(0.0)
    Quartz.CATransaction.commit()
    scala = Quartz.CABasicAnimation.animationWithKeyPath_("transform.scale")
    scala.setFromValue_(1.0)
    scala.setToValue_(1.7)
    luce = Quartz.CABasicAnimation.animationWithKeyPath_("shadowOpacity")
    luce.setFromValue_(0.1)
    luce.setToValue_(0.9)
    battito = Quartz.CAAnimationGroup.animation()
    battito.setAnimations_([scala, luce])
    battito.setDuration_(0.5)
    battito.setAutoreverses_(True)
    battito.setRepeatCount_(1e9)
    battito.setTimingFunction_(Quartz.CAMediaTimingFunction.functionWithName_(Quartz.kCAMediaTimingFunctionEaseInEaseOut))
    punto.addAnimation_forKey_(battito, "pulsa")


# scritta di stato piccola e grigia: in risalto resta LeaderAI
etichetta = AppKit.NSTextField.labelWithString_("")
etichetta.setFrame_(AppKit.NSMakeRect(0, 12, LARGHEZZA, 16))
etichetta.setAlignment_(AppKit.NSTextAlignmentCenter)
etichetta.setTextColor_(AppKit.NSColor.colorWithCalibratedWhite_alpha_(0.72, 1.0))
etichetta.setFont_(AppKit.NSFont.systemFontOfSize_weight_(11, AppKit.NSFontWeightMedium))
etichetta.setHidden_(True)
vista.addSubview_(etichetta)

indicatore_voce = AppKit.NSTextField.labelWithString_("● AI")
indicatore_voce.setFrame_(AppKit.NSMakeRect(LARGHEZZA - 54, 49, 42, 16))
indicatore_voce.setAlignment_(AppKit.NSTextAlignmentRight)
indicatore_voce.setTextColor_(COLORE_BARRE)
indicatore_voce.setFont_(AppKit.NSFont.monospacedSystemFontOfSize_weight_(11, AppKit.NSFontWeightSemibold))
indicatore_voce.setHidden_(True)
vista.addSubview_(indicatore_voce)


def aggiorna_indicatore_voce():
    """Due cose distinte sulla pill, non piu' una sola:
    - bordo verde = stile della pill quando l'invio automatico e' attivo
      (quasi sempre, e' di config): Sal lo vuole sempre, non solo a voce ON;
    - etichetta '● AI' = il tasto voce agenti (TTS) e' DAVVERO acceso: deve
      dire il vero, altrimenti sembra sempre ON anche a voce spenta."""
    stile_attivo = cfg.get("invio_automatico", True)
    vista.layer().setBorderWidth_(1.0 if stile_attivo else 0.0)
    vista.layer().setBorderColor_(COLORE_BARRE.CGColor())
    indicatore_voce.setHidden_(not voce_attiva())


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

# --- microfonino mani-libere: piccolo, sempre visibile quando la modalita'
# e' attiva e a riposo, pulsa col volume mentre Sal parla (richiesta 06/07:
# "un'emoji microfono piccola da vedere che si muove quando io parlo") ---

MINI_LATO = 44
mini_pannello = AppKit.NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
    AppKit.NSMakeRect(0, 0, MINI_LATO, MINI_LATO),
    AppKit.NSWindowStyleMaskBorderless | AppKit.NSWindowStyleMaskNonactivatingPanel,
    AppKit.NSBackingStoreBuffered,
    False,
)
mini_pannello.setLevel_(AppKit.NSStatusWindowLevel)
mini_pannello.setOpaque_(False)
mini_pannello.setBackgroundColor_(AppKit.NSColor.clearColor())
mini_pannello.setIgnoresMouseEvents_(True)
mini_pannello.setCollectionBehavior_(
    AppKit.NSWindowCollectionBehaviorCanJoinAllSpaces
    | AppKit.NSWindowCollectionBehaviorFullScreenAuxiliary
)
mini_label = AppKit.NSTextField.labelWithString_("🎙️")
mini_label.setFrame_(AppKit.NSMakeRect(0, 0, MINI_LATO, MINI_LATO))
mini_label.setAlignment_(AppKit.NSTextAlignmentCenter)
mini_label.setFont_(AppKit.NSFont.systemFontOfSize_(22))
mini_pannello.contentView().addSubview_(mini_label)


def posiziona_mini_pannello():
    """Microfonino in basso, poco a destra del centro (stessa fascia della
    pill ma fuori dal suo ingombro), sul monitor dove sta il mouse."""
    area = schermo_attivo().visibleFrame()
    x = area.origin.x + (area.size.width - MINI_LATO) / 2 + LARGHEZZA / 2 + 24
    margine_basso = min(80, max(16, area.size.height * 0.10))
    y = area.origin.y + margine_basso
    mini_pannello.setFrameOrigin_(AppKit.NSMakePoint(x, y))


def _tasto_detta_giu():
    """True se la dettatura e' MANUALE (tasto-detta premuto per l'app) E il
    tasto e' ancora fisicamente giu' secondo il sistema (Quartz, non pynput).
    Nel VAD mani-libere tasto_premuto e' False: qui torna False e il tetto
    soft vale come prima. Se Quartz non risponde si assume tasto su: meglio
    un tetto in piu' che una registrazione infinita."""
    if not tasto_premuto:
        return False
    try:
        return _cmd_giu()
    except Exception:
        return False


def stop_se_registrazione_troppo_lunga():
    """Airbag anti-incanto: non ferma mai subito, solo se resta aperta troppo.
    Col tasto-detta ancora fisicamente giu' (caso 04/09: monologo di 90s+)
    NON ferma: vale solo il tetto duro."""
    global tasto_premuto
    ora = time.monotonic()
    tasto_giu = _tasto_detta_giu()
    if stop_anti_incanto(registrando, inizio_registrazione, ora, tasto_giu,
                         MAX_REGISTRAZIONE_SEC, MAX_REGISTRAZIONE_TASTO_SEC):
        durata = ora - inizio_registrazione
        logging.getLogger("voce").warning(
            "registrazione oltre %.1fs: stop anti-incanto (tasto giu': %s)", durata, tasto_giu
        )
        tasto_premuto = False
        comandi_audio.put("stop")


# Indicatore di stato SEMPRE visibile ma discreto, nella barra dei menu in
# alto: la pillola e' un lampo che sparisce, quindi senza questo Sal non ha
# modo di sapere se mani libere/voce sono accese senza provare a parlare.
indicatore_menu = AppKit.NSStatusBar.systemStatusBar().statusItemWithLength_(
    AppKit.NSVariableStatusItemLength
)
indicatore_menu.setVisible_(True)
_stato_menu = None


def aggiorna_indicatore_menu(gestore):
    """Accesso stabile al riascolto e alla scelta esplicita della conversazione."""
    global _stato_menu
    stato = elenco_conversazioni()
    titolo = ("🎙️ " if mani_libere_attive() else "") + ("🔊 AI · Voce" if voce_attiva() else "Voce")
    firma = (titolo, json.dumps(stato, sort_keys=True, ensure_ascii=False))
    if firma == _stato_menu:
        return
    indicatore_menu.button().setTitle_(titolo)
    menu = AppKit.NSMenu.alloc().initWithTitle_("Voce")
    menu.setAutoenablesItems_(False)

    def aggiungi(testo, azione, valore=None, scelto=False, attivo=True):
        voce = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(testo, azione, "")
        voce.setTarget_(gestore)
        voce.setRepresentedObject_(valore)
        voce.setEnabled_(attivo)
        voce.setState_(1 if scelto else 0)
        menu.addItem_(voce)

    aggiungi("Rileggi l’ultima risposta", "rileggiVoce:", attivo=stato["rileggibile"])
    menu.addItem_(AppKit.NSMenuItem.separatorItem())
    aggiungi("Ascolta tutte le conversazioni", "scegliConversazione:",
             scelto=stato["preferita"] is None)
    for fonte in stato["conversazioni"]:
        anteprima = " ".join(fonte["anteprima"].split())[:64]
        etichetta = fonte["nome"] or "Agente"
        if anteprima:
            etichetta += " · " + anteprima
        if fonte["in_attesa"]:
            etichetta += " (in attesa)"
        aggiungi(etichetta, "scegliConversazione:", fonte["id"],
                 scelto=stato["preferita"] == fonte["id"])
    indicatore_menu.setMenu_(menu)
    _stato_menu = firma


class GestorePannello(AppKit.NSObject):
    """Vive nel thread principale: applica gli stati e anima le lineette."""

    stato = "nascosto"
    _tick = 0
    _mini_visibile = False

    def rileggiVoce_(self, sender):
        threading.Thread(target=rileggi_ultima, daemon=True).start()

    def scegliConversazione_(self, sender):
        identita = sender.representedObject()
        threading.Thread(target=scegli_conversazione, args=(identita,), daemon=True).start()

    def _aggiorna_mini(self):
        """Microfonino mani-libere: visibile finche' la modalita' e' ON,
        pulsa col volume (piu' forte parli, piu' grande e opaco)."""
        attiva = mani_libere_attive()
        if attiva and not self._mini_visibile:
            posiziona_mini_pannello()
            mini_pannello.orderFrontRegardless()
            self._mini_visibile = True
        elif not attiva and self._mini_visibile:
            mini_pannello.orderOut_(None)
            self._mini_visibile = False
        if self._mini_visibile:
            mini_pannello.setAlphaValue_(0.45 + min(0.55, volume_corrente * 18))
            mini_label.setFont_(AppKit.NSFont.systemFontOfSize_(22 + min(10.0, volume_corrente * 250)))

    def tick_(self, timer):
        try:
            while True:
                nuovo = eventi.get_nowait()
                if registrando and nuovo in ("trascrivo", "sistemo", "nascosto"):
                    continue
                self.stato = nuovo
                if nuovo == "ascolto":
                    posiziona_pannello()
                    aggiorna_indicatore_voce()
                    brand.setHidden_(False)
                    etichetta.setHidden_(True)
                    onda.setHidden_(False)
                    pannello.orderFrontRegardless()  # mostra SENZA attivare l'app
                    marchio_in_evidenza(False)
                    marchio_entra()
                elif nuovo == "trascrivo":
                    aggiorna_indicatore_voce()
                    onda.setHidden_(True)
                    brand.setHidden_(False)
                    etichetta.setStringValue_("⏳ Trascrivo…")
                    etichetta.setHidden_(False)
                    marchio_in_evidenza(True)
                    punto_pulsa(True)
                elif nuovo == "sistemo":
                    etichetta.setStringValue_("✨ Sistemo…")
                    etichetta.setHidden_(False)
                    marchio_in_evidenza(True)
                    punto_pulsa(True)
                elif nuovo == "mic_basso":
                    # la pill qui e' gia' stata nascosta: va rimessa davanti,
                    # altrimenti l'utente non vedrebbe mai perche' e' saltata
                    # la dettatura (era il vero difetto del caso 01/08).
                    posiziona_pannello()
                    onda.setHidden_(True)
                    brand.setHidden_(False)
                    etichetta.setStringValue_("🎤 Alzo il microfono…")
                    etichetta.setHidden_(False)
                    marchio_in_evidenza(True, subito=True)
                    punto_pulsa(False)
                    pannello.orderFrontRegardless()
                elif nuovo == "nascosto":
                    pannello.orderOut_(None)
                    punto_pulsa(False)
                    marchio_in_evidenza(False, subito=True)
        except queue.Empty:
            pass
        if self.stato == "ascolto":
            stop_se_registrazione_troppo_lunga()
            onda.setNeedsDisplay_(True)  # ridisegna il sorriso col volume nuovo
            punto_segue_voce(volume_corrente)
        # watchdog dell'hotkey: se il listener della tastiera si fosse fermato,
        # lo riaccendo (controllo ogni ~2s, non a ogni tick).
        self._tick += 1
        esegui_sicuro(self._aggiorna_mini)  # microfonino mani-libere: pulsa a ogni tick
        if self._tick % 6 == 0:  # ogni ~0.5s: icona di stato nella barra menu
            esegui_sicuro(lambda: aggiorna_indicatore_menu(self))
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
# Detta pulito usa soltanto il modello Apple via Comando Rapido. L'agente non
# e' piu' una riserva interattiva: un suo timeout bloccava il testo per 20s.
# Nelle chat ChatGPT/Claude/Codex si usa sempre il grezzo immediato.
SHORTCUT_PULIZIA = cfg.get("pulizia_shortcut", "Voce Pulita") if cfg.get("detta_pulito", False) else None
# L'interruttore della corsia Apple non e' definitivo: si
# riprova dopo RIPOSO_CORSIA_SEC (vedi corsia_utilizzabile). Con un processo che
# vive giorni, "spento" senza ritorno significava spento per sempre.
_guasti_shortcut = 0          # fallimenti consecutivi della corsia veloce Apple
_ultimo_guasto_shortcut = None
if SHORTCUT_PULIZIA and not shortcut_pulizia_disponibile(SHORTCUT_PULIZIA):
    # Non c'e' adesso: si parte in pausa invece di spegnerla per sempre. Il
    # Comando Rapido puo' comparire dopo (importato a mano, iCloud che
    # sincronizza, Shortcuts non ancora pronto all'avvio) e l'app deve
    # accorgersene da sola. Caso 25-26-28/07/2026: tre giornate intere con
    # ZERO uso della corsia veloce e 123 pulizie tutte sull'agente lento,
    # perche' l'unico controllo era quello all'avvio.
    _guasti_shortcut, _ultimo_guasto_shortcut = SOGLIA_GUASTI_CORSIA, time.monotonic()
COMANDO_APPRENDIMENTO = comandi_agente() if cfg.get("debug_dettature", False) else None


def _whisper_grezzo(audio, prompt=None):
    """Un passaggio di Whisper: solo il modello e la sua guardia
    anti-non-parlato. Nessuna rifinitura del testo (vedi _rifinisci)."""
    esito = mlx_whisper.transcribe(
        audio, path_or_hf_repo=cfg["modello"], language=cfg["lingua"],
        initial_prompt=prompt,
    )
    # Filtro anti-non-parlato (06/07): Whisper dichiara per ogni segmento
    # quanto e' sicuro che sia voce vera. Musica, rumori e audio di
    # sottofondo (video, telefono in vivavoce) producono no_speech_prob
    # alta o confidenza bassissima: si scartano qui, prima che diventino
    # testo allucinato incollato in chat. Soglie regolabili in config.
    segmenti = esito.get("segments") or []
    if segmenti:
        no_speech = sum(s.get("no_speech_prob", 0.0) for s in segmenti) / len(segmenti)
        confidenza = sum(s.get("avg_logprob", 0.0) for s in segmenti) / len(segmenti)
        if no_speech > float(cfg.get("soglia_no_speech", 0.6)) and confidenza < float(cfg.get("soglia_confidenza", -1.0)):
            logging.getLogger("voce").info(
                "scartato: non sembra parlato (no_speech %.2f, confidenza %.2f)",
                no_speech, confidenza,
            )
            return ""
    return esito["text"].strip()


def _rifinisci(testo):
    """Post-processing del testo trascritto, UNA volta sola per dettatura:
    eco del glossario, sostituzioni, punteggiatura dettata."""
    testo = rimuovi_eco_glossario(testo, cfg.get("glossario", []))
    testo = applica_sostituzioni(testo, cfg.get("sostituzioni", {}))
    return converti_punteggiatura_dettata(testo)


def trascrivi(audio):
    """Percorso classico: un solo passaggio Whisper sull'intero audio."""
    return _rifinisci(_whisper_grezzo(audio, GLOSSARIO_PROMPT))


def _finestre_sullo_schermo():
    """Le finestre visibili di tutte le app, dalla piu' avanti alla piu'
    indietro: [(pid, (x, y, larghezza, altezza))] in coordinate Accessibility.
    Restano fuori pannelli e strisce (livello diverso da zero, altezza sotto
    i 200 punti): la pill, la barra menu, le tendine."""
    elenco = Quartz.CGWindowListCopyWindowInfo(
        Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements,
        Quartz.kCGNullWindowID,
    ) or []
    finestre = []
    for finestra in elenco:
        if finestra.get("kCGWindowLayer", 1) != 0:
            continue
        bordi = finestra.get("kCGWindowBounds") or {}
        geometria = (bordi.get("X", 0), bordi.get("Y", 0), bordi.get("Width", 0), bordi.get("Height", 0))
        if not finestra_credibile(geometria, _altezza_schermo_massima()):
            continue
        finestre.append((finestra.get("kCGWindowOwnerPID"), geometria))
    return finestre


def _app_sul_monitor_del_mouse(davanti):
    """Con due monitor il bersaglio e' l'app che sta sul monitor della pill
    (il mouse), non quella con il focus della tastiera. Caso reale 20/09/2026
    15:06: Chrome sul Samsung, l'app Claude sul monitor piccolo con il focus;
    Sal detta guardando il Samsung e il testo compare nel piccolo. Torna
    l'app da usare al posto di quella davanti, o None se non cambia niente."""
    schermi = _schermi_ax()
    if len(schermi) < 2:
        return None
    monitor = schermo_del_punto(_posizione_mouse(), schermi)
    pid_davanti = davanti.processIdentifier() if davanti is not None else None
    pid = app_sul_monitor(_finestre_sullo_schermo(), pid_davanti, monitor, schermi, os.getpid())
    if pid is None:
        return None
    return AppKit.NSRunningApplication.runningApplicationWithProcessIdentifier_(pid)


def app_frontale():
    """Il bersaglio del testo dettato: l'app davanti in questo momento, oppure,
    con due monitor, l'app che sta sul monitor della pill se quella davanti
    non ha finestre li' (vedi _app_sul_monitor_del_mouse)."""
    davanti = AppKit.NSWorkspace.sharedWorkspace().frontmostApplication()
    try:
        altra = _app_sul_monitor_del_mouse(davanti)
    except Exception:
        logging.getLogger("voce").debug("app sul monitor del mouse non letta", exc_info=True)
        altra = None
    if altra is None:
        return davanti
    logging.getLogger("voce").info(
        "bersaglio: %s sul monitor del mouse (davanti c'era %s)",
        altra.localizedName(), davanti.localizedName() if davanti is not None else "nessuna app",
    )
    return altra


# Riattivare l'app non basta se il bersaglio e' una SCHEDA di un browser:
# Instagram e ChatGPT nella stessa finestra Chrome sono la stessa app, quindi
# activateWithOptions_ non se ne accorge. Per i browser che sanno rispondere
# via AppleScript teniamo anche l'URL della scheda attiva e la ripristiniamo.
_SCRIPT_SCHEDA = {
    "com.google.Chrome": {
        "leggi": 'tell application "Google Chrome" to get URL of active tab of front window',
        "scrivi": '''
            tell application "Google Chrome"
                repeat with w in windows
                    set i to 1
                    repeat with t in tabs of w
                        if URL of t is "{url}" then
                            set active tab index of w to i
                            set index of w to 1
                            return
                        end if
                        set i to i + 1
                    end repeat
                end repeat
            end tell
        ''',
    },
    "com.apple.Safari": {
        "leggi": 'tell application "Safari" to get URL of front document',
        "scrivi": '''
            tell application "Safari"
                repeat with w in windows
                    repeat with t in tabs of w
                        if URL of t is "{url}" then
                            set current tab of w to t
                            set index of w to 1
                            return
                        end if
                    end repeat
                end repeat
            end tell
        ''',
    },
}


def _url_finestra_a_fuoco(app):
    """L'indirizzo della pagina nella finestra col focus, letto da
    Accessibility (AXDocument). Caso 20/09/2026: AppleScript rispondeva
    «about:blank» per la finestra davanti mentre Sal stava su ChatGPT in
    un'altra finestra Chrome; AXDocument diceva il vero. None se non c'e'."""
    try:
        ax_app = AX.AXUIElementCreateApplication(app.processIdentifier())
        finestra = _ax_valore(ax_app, AX.kAXFocusedWindowAttribute)
        if finestra is None:
            return None
        url = _ax_valore(finestra, "AXDocument")
        url = str(url).strip() if url else ""
        return url if url.startswith(("http://", "https://")) else None
    except Exception:
        return None


def scheda_browser_frontale(app):
    """URL della scheda attiva ORA, solo per i browser che sappiamo pilotare
    (None per tutto il resto: allora il bersaglio resta solo l'app).
    Prima la finestra col focus via Accessibility, poi AppleScript."""
    script = app is not None and _SCRIPT_SCHEDA.get(app.bundleIdentifier())
    if not script:
        return None
    url = _url_finestra_a_fuoco(app)
    if url:
        return url
    try:
        esito = subprocess.run(
            ["osascript", "-e", script["leggi"]], capture_output=True, text=True, timeout=3
        )
        return esito.stdout.strip() or None
    except Exception:
        return None


def riattiva_scheda_browser(app, url):
    """Riporta avanti la scheda esatta (per URL) dove Sal stava dettando,
    dentro l'app-browser gia' riattivata."""
    script = _SCRIPT_SCHEDA.get(app.bundleIdentifier())
    if not script or scheda_browser_frontale(app) == url:
        return
    comando = script["scrivi"].format(url=url.replace('\\', '\\\\').replace('"', '\\"'))
    try:
        subprocess.run(["osascript", "-e", comando], capture_output=True, timeout=3)
        time.sleep(0.2)
    except Exception:
        logging.getLogger("voce").exception("impossibile riattivare la scheda del browser")


def riattiva_bersaglio(app, scheda_url=None):
    """Se nel frattempo Sal ha cambiato pagina/app/scheda (dettatura lunga +
    pulizia), il testo deve arrivare comunque dove stava parlando, non dove
    si trova ora il focus. Riporta avanti l'app-bersaglio (e la scheda, se
    era un browser) prima di incollare."""
    if app is None:
        return
    corrente = AppKit.NSWorkspace.sharedWorkspace().frontmostApplication()
    if corrente is None or corrente.processIdentifier() != app.processIdentifier():
        app.activateWithOptions_(AppKit.NSApplicationActivateIgnoringOtherApps)
        time.sleep(0.2)  # tempo al focus di spostarsi davvero prima del Cmd+V
    if scheda_url:
        riattiva_scheda_browser(app, scheda_url)


# --- se davanti non c'e' dove scrivere, il testo torna nell'ultima chat AI ---
# Sal, 18/09/2026 11:36: due dettature per Claude fatte con Gmail davanti
# (Chrome, nessuna casella) sono finite alla cieca e perse. «Io non devo
# mettere per forza il cursore all'interno della chat in modo tale che la
# voce capisca dove devo andare. Perché passo da una pagina all'altra.»
# L'ultima chat AI dove una dettatura e' arrivata e' la base di chi parla con
# un agente: se l'app davanti e' leggibile e non ha nessuna casella, si torna
# li' invece di incollare nel vuoto.
_ultima_chat_ai = None  # (app, scheda) dell'ultima chat AI dove il testo e' arrivato


def _fuori_dal_monitor_del_mouse(app):
    """True se, con due monitor, l'app non ha nessuna finestra sul monitor
    del mouse (dove sta la pill). Caso reale 20/09/2026 15:41: Chrome sul
    Samsung per un attimo senza casella leggibile, e il ritorno alla chat
    Claude tirava il testo sul monitor piccolo: «continua a mettermi dove
    vuole». Il testo non cambia mai monitor da solo."""
    if app is None:
        return False
    schermi = _schermi_ax()
    if len(schermi) < 2:
        return False
    monitor = schermo_del_punto(_posizione_mouse(), schermi)
    return not app_ha_finestra_sul_monitor(_finestre_sullo_schermo(), app.processIdentifier(), monitor, schermi)


def _bersaglio_di_riserva(bersaglio, chat_agente):
    """L'ultima chat AI usata, se e' un altro posto da `bersaglio` ed e' ancora
    aperta; None se non c'e' o se il bersaglio e' gia' una chat AI (li' il
    testo arriva comunque, anche senza casella leggibile: Antigravity 13/09)."""
    if chat_agente or _ultima_chat_ai is None:
        return None
    app, scheda = _ultima_chat_ai
    app_ora, scheda_ora = bersaglio
    if app is None or app.isTerminated():
        return None
    if (app_ora is not None and app_ora.processIdentifier() == app.processIdentifier()
            and scheda_ora == scheda):
        return None
    return _ultima_chat_ai


# --- cursore automatico nella casella (richiesta 29/08/2026) ---
# Sal passa di finestra in finestra e detta al volo: riattivare l'app non
# basta se dentro la finestra nessuna casella di testo ha il focus, perche'
# il Cmd+V cadrebbe nel vuoto e lui dovrebbe prendere il mouse e cliccare
# nella "barretta". Qui, via Accessibility, si guarda dove sta il focus e,
# se non e' una casella, il click nella casella di scrittura lo fa l'app.

AX_BUDGET_SEC = 0.5      # tempo massimo di ricerca nella finestra
# Le pagine web sono foreste: 600 elementi si esaurivano nella struttura di
# Chrome prima di arrivare alla casella (caso reale 29/08 13:17, "nessuna
# casella di testo nella finestra"). Misurato ~15.000 elementi/secondo: 4000
# stanno comodi nel budget di tempo, che resta la vera cintura di sicurezza.
AX_MAX_ELEMENTI = 4000
# Le app Electron (Claude 2.110.x, misurato 17/09/2026) costruiscono l'albero
# Accessibility del contenuto solo DOPO il primo tocco, circa mezzo secondo
# dopo: al primo giro si vede un guscio di pochi gruppi senza caselle. Prima
# di dire "caselle non ce ne sono" si aspetta questo tempo e si riguarda una
# volta. Mezzo secondo, non uno: si paga solo quando il primo giro e' vuoto.
AX_ATTESA_RISVEGLIO_SEC = 0.5
AX_GIRI_RISVEGLIO = 5    # giri di ricerca in tutto: al massimo due secondi in piu'
# Dove stava la casella l'ultima volta, per app e taglia di finestra: se
# l'albero resta addormentato dopo tutti i giri si clicca li' (Sal, 17/09/2026:
# "deve trovare da solo dove scrivere e deve scrivere"). Vive anche su file
# accanto all'app (FILE_CASELLE_RICORDATE): a ogni riavvio riparte gia' istruita.
_caselle_ricordate = {}


def _carica_caselle_ricordate():
    try:
        _caselle_ricordate.update(caselle_da_json(FILE_CASELLE_RICORDATE.read_text(encoding="utf-8")))
    except OSError:
        pass  # prima volta: nessuna memoria


def _salva_caselle_ricordate():
    try:
        FILE_CASELLE_RICORDATE.write_text(caselle_in_json(_caselle_ricordate), encoding="utf-8")
    except OSError:
        logging.getLogger("voce").warning("memoria delle caselle non salvata: %s", FILE_CASELLE_RICORDATE)


_carica_caselle_ricordate()


def _ax_valore(elemento, attributo):
    """Un attributo Accessibility, o None se l'elemento non ce l'ha."""
    err, valore = AX.AXUIElementCopyAttributeValue(elemento, attributo, None)
    return valore if err == 0 else None


def _altezza_schermo_massima():
    """L'altezza del monitor piu' alto: oltre quella non c'e' una finestra,
    c'e' la scrivania (il Finder la espone come finestra)."""
    schermi = AppKit.NSScreen.screens()
    return max((s.frame().size.height for s in schermi), default=float("inf"))


def _schermi_ax():
    """I monitor come rettangoli (x, y, larghezza, altezza) nelle coordinate
    Accessibility: origine in alto a sinistra del monitor principale, y verso
    il basso. Le stesse coordinate delle finestre e del mouse letti da AX."""
    schermi = AppKit.NSScreen.screens()
    if not schermi:
        return []
    altezza_principale = schermi[0].frame().size.height
    rettangoli = []
    for schermo in schermi:
        cornice = schermo.frame()
        rettangoli.append((
            cornice.origin.x,
            altezza_principale - (cornice.origin.y + cornice.size.height),
            cornice.size.width,
            cornice.size.height,
        ))
    return rettangoli


def _posizione_mouse():
    """Dove sta il puntatore ORA, in coordinate Accessibility (y verso il
    basso). Serve solo come spareggio fra finestre, mai come condizione."""
    punto = Quartz.CGEventGetLocation(Quartz.CGEventCreate(None))
    return punto.x, punto.y


def _finestre_bersaglio(ax_app):
    """Le finestre dove provare a mettere il cursore, in ordine di tentativo.

    Prima quella col focus, poi la principale, poi le altre. Le app Electron
    sotto carico a volte non rispondono alla prima lettura (caso reale 29/08
    13:42: tre dettature con 'finestra frontale non leggibile' su app con
    finestre sane): una lettura fallita non deve spegnere la funzione.

    Dal 08/09/2026 non ci si ferma alla prima: se li' dentro caselle non ce
    ne sono, si provano le altre finestre dell'app. Le finte (la striscia da
    33 punti di Claude, la scrivania del Finder) restano fuori, e il mouse,
    se sta dentro una di queste finestre, sposta solo la precedenza.
    Torna (finestre credibili, errore di lettura del focus, finestre lette
    in tutto): l'ultimo numero distingue "non ho potuto guardare" da "ho
    guardato e non c'e' posto dove scrivere"."""
    finestre, primo_err = [], 0
    err, focalizzata = AX.AXUIElementCopyAttributeValue(ax_app, AX.kAXFocusedWindowAttribute, None)
    if err == 0 and focalizzata is not None:
        finestre.append(focalizzata)
    else:
        primo_err = err
    for attributo in (AX.kAXMainWindowAttribute, "AXWindows"):
        valore = _ax_valore(ax_app, attributo)
        if valore is None:
            continue
        elenco = list(valore) if attributo == "AXWindows" else [valore]
        finestre.extend(el for el in elenco if el is not None)

    massima = _altezza_schermo_massima()
    viste, candidate, geometrie = set(), [], []
    for finestra in finestre:
        geometria = _ax_geometria(finestra)
        if not finestra_credibile(geometria, massima):
            continue
        if geometria in viste:  # la stessa finestra torna da piu' attributi
            continue
        viste.add(geometria)
        candidate.append(finestra)
        geometrie.append(geometria)
    ordine = ordina_finestre(geometrie, _posizione_mouse(), _schermi_ax())
    return ([(candidate[i], geometrie[i]) for i in ordine], primo_err, len(finestre))


def _ax_geometria(elemento):
    """(x, y, larghezza, altezza) in coordinate globali (origine in alto a
    sinistra: y piu' grande = piu' in basso), o None se illeggibile."""
    pos = _ax_valore(elemento, AX.kAXPositionAttribute)
    dim = _ax_valore(elemento, AX.kAXSizeAttribute)
    if pos is None or dim is None:
        return None
    ok_p, punto = AX.AXValueGetValue(pos, AX.kAXValueCGPointType, None)
    ok_d, taglia = AX.AXValueGetValue(dim, AX.kAXValueCGSizeType, None)
    if not (ok_p and ok_d):
        return None
    return punto.x, punto.y, taglia.width, taglia.height


def _focus_in_casella(ax_app):
    """True se l'elemento col focus nell'app e' gia' una casella di testo."""
    focalizzato = _ax_valore(ax_app, AX.kAXFocusedUIElementAttribute)
    if focalizzato is None:
        return False
    return ruolo_editabile(_ax_valore(focalizzato, AX.kAXRoleAttribute))


def _caselle_nella_finestra(finestra):
    """Tutte le caselle di testo della finestra, con la loro geometria.
    Visita in ampiezza con tetto di tempo ed elementi: meglio rinunciare
    (comportamento di prima) che tenere il testo in ostaggio."""
    da_visitare = collections.deque([finestra])
    inizio = time.monotonic()
    visitati = 0
    caselle = []
    while da_visitare and visitati < AX_MAX_ELEMENTI and time.monotonic() - inizio < AX_BUDGET_SEC:
        elemento = da_visitare.popleft()
        visitati += 1
        if ruolo_editabile(_ax_valore(elemento, AX.kAXRoleAttribute)):
            geometria = _ax_geometria(elemento)
            if geometria:
                caselle.append((elemento, geometria))
            continue  # dentro una casella non serve scendere
        da_visitare.extend(_ax_valore(elemento, AX.kAXChildrenAttribute) or [])
    return caselle


def _click_sintetico(geometria):
    """Click del programma al centro della casella; poi il puntatore torna
    dov'era, cosi' Sal non se ne accorge nemmeno."""
    x, y, larghezza, altezza = geometria
    centro = (x + larghezza / 2, y + altezza / 2)
    posizione_prima = Quartz.CGEventGetLocation(Quartz.CGEventCreate(None))
    for tipo in (Quartz.kCGEventLeftMouseDown, Quartz.kCGEventLeftMouseUp):
        evento = Quartz.CGEventCreateMouseEvent(None, tipo, centro, Quartz.kCGMouseButtonLeft)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, evento)
        time.sleep(0.03)
    Quartz.CGWarpMouseCursorPosition(posizione_prima)


def _cerca_casella(ax_app, finestra, geo_dichiarata, con_pagina):
    """La casella dove scrivere dentro UNA finestra: (elemento, geometria)
    oppure None. Nei browser il focus sta spesso sulla pagina (AXWebArea):
    si cerca prima DENTRO la pagina, saltando la struttura del browser; la
    finestra intera resta il secondo giro."""
    radici = []
    if con_pagina:
        focalizzato = _ax_valore(ax_app, AX.kAXFocusedUIElementAttribute)
        if focalizzato is not None and _ax_valore(focalizzato, AX.kAXRoleAttribute) == "AXWebArea":
            radici.append(focalizzato)
    radici.append(finestra)
    for radice in radici:
        trovate = _caselle_nella_finestra(radice)
        # la finestra dichiarata da Chrome non copre i suoi stessi pezzi:
        # la fascia di scrittura si misura sul rettangolo vero
        cornice = cornice_reale(geo_dichiarata, [g for _, g in trovate])
        # parte bassa della finestra (chat) o area alta almeno meta' finestra
        # (documento): mai le barre in alto, che sono alte poco
        caselle = [
            (el, g) for el, g in trovate
            if casella_ammissibile(g[1], g[3], cornice[1], cornice[3])
        ]
        scelta = scegli_casella([(g[1], g[2]) for _, g in caselle])
        if scelta is not None:
            return caselle[scelta]
    return None


def _chiedi_albero_electron(ax_app):
    """Le app Electron accendono l'albero Accessibility del contenuto quando un
    programma glielo chiede con AXManualAccessibility (documentato da Electron).
    Nessun effetto sulle altre app, che non hanno l'attributo."""
    valore = _ax_valore(ax_app, "AXManualAccessibility")
    if valore is not None and not valore:
        AX.AXUIElementSetAttributeValue(ax_app, "AXManualAccessibility", True)


def _chiedi_pagina_browser(app, ax_app):
    """I browser della famiglia Chrome espongono la pagina ad Accessibility
    solo se un programma chiede l'interfaccia estesa: senza, la casella di
    ChatGPT non esiste nell'albero (20/09/2026, 44 incolla alla cieca in un
    giorno). Si chiede una volta e resta accesa finche' Voce gira; la pagina
    compare in circa due secondi, dentro i giri di risveglio."""
    if app is None or not e_browser_chromium(app.bundleIdentifier()):
        return
    if _ax_valore(ax_app, "AXEnhancedUserInterface"):
        return
    AX.AXUIElementSetAttributeValue(ax_app, "AXEnhancedUserInterface", True)


def _sveglia_accessibilita(app):
    """Al tasto premuto: tocca l'albero Accessibility dell'app davanti e, se e'
    un'app Electron, chiede di accenderlo. Le app Electron lo costruiscono solo
    dopo il primo tocco e ci mettono da mezzo secondo a tre secondi e mezzo
    (Antigravity, misurato 17/09/2026 alle 14:14): fatto qui, mentre si parla,
    al rilascio la casella e' gia' visibile. Gira in un thread a parte e non
    tocca niente sullo schermo."""
    if app is None or not cfg.get("cursore_automatico", True):
        return
    try:
        ax_app = AX.AXUIElementCreateApplication(app.processIdentifier())
        _chiedi_albero_electron(ax_app)
        _chiedi_pagina_browser(app, ax_app)
        if _focus_in_casella(ax_app):
            return
        finestre, _, _ = _finestre_bersaglio(ax_app)
        if finestre:
            _cerca_casella(ax_app, finestre[0][0], finestre[0][1], con_pagina=True)
    except Exception:
        logging.getLogger("voce").debug("sveglia accessibilita' fallita", exc_info=True)


def _geometria_finestra_a_fuoco(ax_app):
    finestra = _ax_valore(ax_app, AX.kAXFocusedWindowAttribute)
    return _ax_geometria(finestra) if finestra is not None else None


def _ricorda_casella(app, ax_app, geometria=None, geo_finestra=None):
    """Segna dove sta la casella di scrittura in questa finestra (app e
    taglia): se l'albero Accessibility dell'app si addormenta (Claude
    2.110.x, 17/09/2026) la volta dopo si clicca li' invece di incollare alla
    cieca. Senza geometria si legge quella dell'elemento col focus."""
    if geo_finestra is None:
        geo_finestra = _geometria_finestra_a_fuoco(ax_app)
    if geometria is None:
        focalizzato = _ax_valore(ax_app, AX.kAXFocusedUIElementAttribute)
        geometria = _ax_geometria(focalizzato) if focalizzato is not None else None
    chiave = chiave_casella(app.localizedName(), geo_finestra)
    relativa = posizione_relativa(geo_finestra, geometria) if geo_finestra and geometria else None
    if chiave is None or relativa is None:
        return
    nuova = chiave not in _caselle_ricordate
    if nuova:
        logging.getLogger("voce").info("cursore automatico: casella ricordata per %s (finestra %sx%s)", *chiave)
    if nuova or _caselle_ricordate[chiave] != relativa:
        _caselle_ricordate[chiave] = relativa
        _salva_caselle_ricordate()


def _punto_ricordato(app, geo_finestra):
    """Dove cliccare per la casella di questa finestra, se la si e' gia' vista."""
    relativa = _caselle_ricordate.get(chiave_casella(app.localizedName(), geo_finestra))
    return punto_da_relativa(geo_finestra, relativa) if relativa else None


def _casella_nelle_finestre(ax_app, finestre, log):
    """La prima casella di scrittura provando le finestre nell'ordine dato:
    (elemento, geometria, geometria della sua finestra) oppure None."""
    for indice, (finestra, geo_finestra) in enumerate(finestre):
        trovata = _cerca_casella(ax_app, finestra, geo_finestra, con_pagina=(indice == 0))
        if trovata is not None:
            if indice:
                log.info("cursore automatico: casella trovata nella finestra %s di %s",
                         indice + 1, len(finestre))
            return trovata[0], trovata[1], geo_finestra
    return None


def _porta_sul_monitor_del_mouse(ax_app, log):
    """Il focus sta gia' in una casella, ma in una finestra su un altro
    monitor rispetto al mouse: la pill (che segue il mouse) e' su uno
    schermo e il testo andrebbe sull'altro. Caso reale 20/09/2026, monitor
    Samsung collegato: Sal vede la pill sul Samsung e la dettatura finisce
    nella chat rimasta sul monitor piccolo. Se la stessa app ha una finestra
    con una casella sul monitor del mouse, il cursore va li'. Con un solo
    monitor, o senza una finestra adatta di la', non tocca niente.
    Torna True se il cursore e' stato spostato."""
    schermi = _schermi_ax()
    if len(schermi) < 2:
        return False
    mouse = _posizione_mouse()
    geo_fuoco = _geometria_finestra_a_fuoco(ax_app)
    if not finestra_su_altro_schermo(geo_fuoco, mouse, schermi):
        return False
    monitor_mouse = schermo_del_punto(mouse, schermi)
    finestre, _, _ = _finestre_bersaglio(ax_app)
    di_la = [(f, g) for f, g in finestre if schermo_della_finestra(g, schermi) == monitor_mouse]
    if not di_la:
        return False
    trovata = _casella_nelle_finestre(ax_app, di_la, log)
    if trovata is None:
        return False
    elemento, geometria, geo_finestra = trovata
    AX.AXUIElementSetAttributeValue(elemento, AX.kAXFocusedAttribute, True)
    time.sleep(0.1)
    if _geometria_finestra_a_fuoco(ax_app) != geo_finestra or not _focus_in_casella(ax_app):
        _click_sintetico(geometria)  # il focus gentile non cambia finestra: click
        time.sleep(0.15)
    log.info("cursore automatico: casella spostata sul monitor del mouse")
    return True


def metti_cursore_in_casella(app):
    """Se nell'app bersaglio nessuna casella di testo ha il focus, mette il
    cursore nella casella di scrittura (nelle chat sta in fondo). Prima per
    via gentile (focus Accessibility), poi con un click fatto dal programma.
    Se non trova caselle non tocca niente.

    Si provano tutte le finestre credibili dell'app, non solo la prima:
    quella dichiarata col focus a volte e' una striscia vuota o la scrivania
    (08/09/2026), e li' la dettatura finiva nel vuoto.

    Se al primo giro caselle non se ne vedono si aspetta AX_ATTESA_RISVEGLIO_SEC
    e si riguarda, fino a AX_GIRI_RISVEGLIO giri: le app Electron (Claude
    2.110.x, 17/09/2026) espongono il contenuto solo dopo il primo tocco
    Accessibility, e la dettatura finiva "alla cieca" con l'avviso sonoro
    anche se il cursore stava gia' nella chat. Se la finestra resta
    addormentata si clicca dove stava la casella l'ultima volta in una
    finestra di questa taglia (memoria aggiornata a ogni dettatura riuscita).

    Torna True se un posto dove scrivere c'e' (focus gia' giusto, o messo);
    False SOLO quando le finestre sono leggibili e di caselle non ce n'e'
    proprio (li' l'incolla andrebbe nel vuoto); None quando non si sa
    (cursore automatico spento, finestre AX illeggibili: la casella puo'
    esserci comunque e si incolla come sempre)."""
    if app is None or not cfg.get("cursore_automatico", True):
        return None
    log = logging.getLogger("voce")
    ax_app = AX.AXUIElementCreateApplication(app.processIdentifier())
    if _focus_in_casella(ax_app):
        _porta_sul_monitor_del_mouse(ax_app, log)
        _ricorda_casella(app, ax_app)
        return True  # il cursore e' gia' al posto giusto
    finestre, err_focus, lette = _finestre_bersaglio(ax_app)
    if not finestre:
        if lette:
            # finestre ce n'erano, ma solo finte (striscia vuota, scrivania):
            # un posto dove scrivere qui non c'e', e il testo va tenuto
            log.info("cursore automatico: %s finestre, nessuna dove si possa scrivere", lette)
            return False
        log.info("cursore automatico: nessuna finestra leggibile (errore AX %s)", err_focus)
        return None
    trovata = _casella_nelle_finestre(ax_app, finestre, log)
    giri = 1
    if trovata is None:
        _chiedi_albero_electron(ax_app)  # seconda richiesta: la prima era al tasto premuto
        _chiedi_pagina_browser(app, ax_app)
    while trovata is None and giri < AX_GIRI_RISVEGLIO:
        # guscio vuoto di un'app Electron appena toccata? si aspetta che
        # l'albero si accenda e si riguarda (vedi AX_ATTESA_RISVEGLIO_SEC)
        time.sleep(AX_ATTESA_RISVEGLIO_SEC)
        giri += 1
        if _focus_in_casella(ax_app):
            log.info("cursore automatico: casella gia' a fuoco, vista al giro %s", giri)
            _ricorda_casella(app, ax_app)
            return True
        finestre_dopo, _, _ = _finestre_bersaglio(ax_app)
        if finestre_dopo:
            finestre = finestre_dopo
            trovata = _casella_nelle_finestre(ax_app, finestre, log)
        if trovata is not None:
            log.info("cursore automatico: casella trovata al giro %s", giri)
    if trovata is None:
        # finestra ancora addormentata: si clicca dove stava la casella
        # l'ultima volta in una finestra di questa taglia, se la si e' vista
        punto = _punto_ricordato(app, finestre[0][1])
        if punto is not None:
            log.info("cursore automatico: finestra addormentata dopo %s giri, "
                     "click dove stava la casella l'ultima volta", giri)
            _click_sintetico((punto[0], punto[1], 0, 0))
            time.sleep(0.15)
            return True
        log.info("cursore automatico: nessuna casella di testo nelle %s finestre dell'app (%s giri)",
                 len(finestre), giri)
        return False
    elemento, geometria, geo_finestra = trovata
    _ricorda_casella(app, ax_app, geometria, geo_finestra)
    AX.AXUIElementSetAttributeValue(elemento, AX.kAXFocusedAttribute, True)
    time.sleep(0.1)
    if _focus_in_casella(ax_app):
        log.info("cursore automatico: messo nella casella di scrittura")
        return True
    _click_sintetico(geometria)
    time.sleep(0.15)
    log.info("cursore automatico: click nella casella di scrittura")
    return True


def incolla(testo, conserva_appunti=False):
    """Mette il testo in clipboard, simula Cmd+V, poi ripristina la clipboard.

    Con conserva_appunti=True il ripristino si salta: quando l'incolla parte
    alla cieca (nessuna casella trovata) il testo deve restare negli Appunti,
    altrimenti la frase dettata sparisce del tutto (caso reale 30/08/2026)."""
    vecchia = subprocess.run(["pbpaste"], capture_output=True).stdout
    subprocess.run(["pbcopy"], input=testo.encode())
    time.sleep(0.15)
    with tastiera.pressed(Key.cmd):
        tastiera.press("v")
        tastiera.release("v")
    time.sleep(0.4)
    if not conserva_appunti:
        subprocess.run(["pbcopy"], input=vecchia)


def su_callback(indata, frames, t, status):
    global volume_corrente
    volume_corrente = float(np.sqrt(np.mean(indata ** 2)))  # serve al VAD mani-libere anche fuori registrazione
    if not registrando:
        # stream sempre aperto: fuori registrazione teniamo solo un piccolo
        # anello di pre-registrazione (~1s). Serve alle mani libere: il VAD
        # parte DOPO che hai iniziato a parlare, senza questo la prima
        # parola andrebbe persa ("mi ha preso solo una parte", 06/07).
        pre_registrazione.append(indata.copy())
        return
    blocchi.append(indata.copy())
    rms_blocchi.append(volume_corrente)  # parallelo a blocchi: serve a trovare le pause
    livelli.append(volume_corrente)


def nome_device_input():
    """Nome del device di input di sistema in questo momento (None se non
    determinabile: mai far esplodere il watchdog per questo)."""
    try:
        return sd.query_devices(kind="input")["name"]
    except Exception:
        return None


def volume_ingresso_sistema():
    """Volume d'ingresso del microfono di sistema, 0-100 (None se illeggibile:
    mai far esplodere il chiamante per questo). E' il guadagno che il Mac
    applica PRIMA dello stream, quindi lo vede anche un processo gia' avviato:
    rialzarlo ha effetto subito, senza riaprire il device."""
    try:
        letto = subprocess.run(
            ["osascript", "-e", "input volume of (get volume settings)"],
            capture_output=True, text=True, timeout=5,
        )
        return int(letto.stdout.strip())
    except Exception:
        return None


def imposta_volume_ingresso(valore):
    """Rialza il volume d'ingresso di sistema e torna il valore RILETTO (None se
    non riuscito). Si rilegge sempre invece di fidarsi: il Mac quantizza il
    livello a passi suoi e su alcuni device l'ingresso non e' regolabile."""
    try:
        subprocess.run(
            ["osascript", "-e", f"set volume input volume {int(valore)}"],
            capture_output=True, text=True, timeout=5, check=True,
        )
    except Exception:
        return None
    return volume_ingresso_sistema()


def ripara_guadagno_ingresso(rms):
    """Audio sotto soglia mentre il volume d'ingresso di sistema e' abbassato:
    il guasto e' quello, non lo stream. Lo rialza e torna True perche' il
    chiamante NON riavvii il processo: il guadagno resterebbe basso anche dopo,
    e si otterrebbe solo un ciclo di riavvii inutili.

    Caso 01/08/2026: ingresso sceso da solo a 36/100 mentre Sal dettava, parlato
    a rms 0.0014 contro una soglia di 0.004, ogni dettatura scartata in
    silenzio. airbag_stream_muto non poteva vederlo: guarda solo le dettature
    oltre i 3 secondi, e le prove di Sal erano da 0,5 e 1,2 secondi."""
    causa, target = diagnosi_audio_muto(
        rms, volume_ingresso_sistema(), cfg.get("soglia_voce", SOGLIA_VOCE)
    )
    if causa != "guadagno_basso":
        return False
    eventi.put("mic_basso")
    nascondi = threading.Timer(2.5, lambda: eventi.put("nascosto"))
    nascondi.daemon = True  # non trattenere l'uscita del processo
    nascondi.start()
    riletto = imposta_volume_ingresso(target)
    if riletto is None:
        logging.getLogger("voce").error(
            "volume d'ingresso del microfono basso e non rialzabile da qui: "
            "alzalo da Impostazioni di Sistema > Suono > Ingresso"
        )
    else:
        logging.getLogger("voce").warning(
            "volume d'ingresso del microfono era basso: rialzato a %s", riletto
        )
    return True


def allinea_volume_ingresso():
    """All'avvio: con l'ingresso sotto il minimo l'app nasce muta e sembra
    rotta. Meglio scoprirlo qui che alla prima dettatura persa."""
    attuale = volume_ingresso_sistema()
    if attuale is None or attuale >= GUADAGNO_INGRESSO_MINIMO:
        return
    riletto = imposta_volume_ingresso(GUADAGNO_INGRESSO_TARGET)
    logging.getLogger("voce").warning(
        "volume d'ingresso del microfono a %s all'avvio: rialzato a %s", attuale, riletto
    )


device_input_apertura = None  # device che avevamo quando lo stream e' stato aperto


def avvia_stream():
    """Apre il microfono UNA sola volta per tutta la vita del processo.

    Aprire/chiudere lo stream a ogni dettatura e' quello che faceva incantare
    CoreAudio (deadlock nel mutex della HAL allo stop, vedi git history):
    tenerlo sempre acceso elimina la causa invece di limitarsi a riavviare
    il processo quando succede. Contropartita: se il device di input cambia
    (es. colleghi AirPods, disconnetti un mic USB) questo processo resta
    agganciato al vecchio finche' non riparte: watchdog_audio se ne accorge
    e si riavvia da solo (vedi riavvia_processo); se invece il device resta
    uguale di nome ma lo stream consegna aria morta (Continuity iPhone),
    interviene airbag_stream_muto alla prima dettatura lunga scartata."""
    global stream, device_input_apertura
    stream = sd.InputStream(
        samplerate=FREQ, channels=1, dtype="float32", callback=su_callback
    )
    stream.start()
    device_input_apertura = nome_device_input()


def _nascondi_o_arma():
    """Fine ciclo pill: nasconde. (Lo stato ON/OFF di mani libere ora lo
    dice l'icona nella barra menu: la vecchia pillola-lampo che ricompariva
    a ogni fine turno era ridondante e disturbava.)"""
    eventi.put("nascosto")


def avvia_registrazione():
    global blocchi, rms_blocchi, registrando, inizio_registrazione
    global sessione_progressiva, turno_utente_token
    if registrando:
        coda_dettature.annulla_avvio()
        return
    turno_utente_token = apri_turno_utente()
    coda_dettature.apri(turno_utente_token)
    try:
        ferma_voce()  # ti zittisco se parlo io: tocca a te
        # si parte dall'anello di pre-registrazione: il VAD scatta quando gia'
        # stai parlando, senza questi blocchi la prima parola andrebbe persa
        blocchi = list(pre_registrazione)
        rms_blocchi = [float(np.sqrt(np.mean(b ** 2))) for b in blocchi]
        pre_registrazione.clear()
        livelli.extend([0.0] * BARRE)
        registrando = True
        inizio_registrazione = time.monotonic()
        logging.getLogger("voce").info("registrazione avviata")
        # mentre si parla, l'app davanti accende il suo albero Accessibility:
        # al rilascio la casella di scrittura e' gia' visibile (vedi _sveglia_accessibilita)
        threading.Thread(target=_sveglia_accessibilita, args=(app_frontale(),), daemon=True).start()
        suono("Pop")
        eventi.put("ascolto")
        if PROGRESSIVA:
            sessione_progressiva = SessioneProgressiva(blocchi, rms_blocchi)
            sessione_progressiva.avvia()
    except Exception:
        _concludi_dettatura(turno_utente_token)
        turno_utente_token = None
        raise


_lock_trascrizione = threading.Lock()


class SessioneProgressiva:
    """Trascrizione a segmenti MENTRE si registra (04/09/2026).

    Un thread di sottofondo guarda i volumi per blocco (rms_blocchi) e, ogni
    volta che il segmento aperto supera trascrizione_progressiva_blocco_sec
    e cade su una pausa di 0,5s (trova_taglio), trascrive quel segmento sotto
    _lock_trascrizione, passando a Whisper glossario + coda del testo
    precedente. Non tocca mai il callback audio ne' il thread tastiera: legge
    solo fette della lista blocchi per indice. Al rilascio
    _trascrivi_con_sessione aspetta il segmento in corso, trascrive solo la
    coda e rincolla. Un errore in sottofondo alza `guasta`: si torna al
    passaggio unico su tutto l'audio, come oggi."""

    def __init__(self, blocchi_ref, rms_ref):
        self.blocchi = blocchi_ref
        self.rms = rms_ref
        self.campioni = []      # numero di campioni per blocco (cresce con blocchi)
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
        log = logging.getLogger("voce")
        while not self.fermata.is_set():
            time.sleep(0.2)
            n = min(len(self.blocchi), len(self.rms))
            for b in self.blocchi[len(self.campioni):n]:
                self.campioni.append(len(b))
            taglio = trova_taglio(
                self.rms, self.campioni, self.inizio_segmento, FREQ,
                PROGRESSIVA_SOGLIA_SILENZIO, blocco_min_sec=PROGRESSIVA_BLOCCO_SEC,
            )
            if taglio is None or self.fermata.is_set():
                continue
            inizio, self.inizio_segmento = self.inizio_segmento, taglio
            try:
                segmento = np.concatenate(self.blocchi[inizio:taglio])[:, 0]
                prompt = prompt_con_contesto(GLOSSARIO_PROMPT, self.pezzi[-1] if self.pezzi else "")
                partenza = time.monotonic()
                with _lock_trascrizione:
                    testo = _whisper_grezzo(segmento, prompt)
                testo = rimuovi_eco_glossario(testo, cfg.get("glossario", []))
                self.pezzi.append(testo)
                log.info(
                    "progressiva: segmento %d (%.1fs) trascritto in %.1fs, %d parole",
                    len(self.pezzi), len(segmento) / FREQ, time.monotonic() - partenza,
                    len(testo.split()),
                )
            except Exception:
                log.exception("progressiva: errore sul segmento, torno al passaggio unico")
                self.guasta = True
                return


def _trascrivi_con_sessione(audio, sessione):
    """Testo rifinito dell'audio intero. Senza sessione (interruttore spento,
    o nessun segmento chiuso: dettature sotto ~12s) e' il percorso di sempre,
    un solo passaggio Whisper. Con segmenti gia' trascritti si trascrive solo
    la coda dall'ultimo taglio, si rincolla e si rifinisce una volta sola."""
    log = logging.getLogger("voce")
    if sessione is not None:
        sessione.ferma()
        sessione.thread.join(timeout=120)  # FUORI dal lock: il segmento in corso lo vuole
    if sessione is None or sessione.guasta or not sessione.pezzi or sessione.thread.is_alive():
        with _lock_trascrizione:  # una trascrizione per volta
            eventi.put("trascrivo")
            return trascrivi(audio)
    coperti = sum(sessione.campioni[:sessione.inizio_segmento])
    if coperti > len(audio):
        log.warning("progressiva: segmenti oltre l'audio (%d > %d), passaggio unico", coperti, len(audio))
        with _lock_trascrizione:
            eventi.put("trascrivo")
            return trascrivi(audio)
    coda = audio[coperti:]
    pezzi = list(sessione.pezzi)
    partenza = time.monotonic()
    with _lock_trascrizione:
        eventi.put("trascrivo")
        if len(coda) >= FREQ * 0.2 and c_e_voce(coda, cfg.get("soglia_voce", SOGLIA_VOCE)):
            prompt = prompt_con_contesto(GLOSSARIO_PROMPT, pezzi[-1])
            pezzi.append(rimuovi_eco_glossario(_whisper_grezzo(coda, prompt), cfg.get("glossario", [])))
    # frase-fantasma su un pezzo (tipico: coda cortissima) = pezzo scartato
    pezzi = [p for p in pezzi if not e_allucinazione(p)]
    log.info(
        "progressiva: %d segmenti in sottofondo, coda %.1fs trascritta in %.1fs",
        len(sessione.pezzi), len(coda) / FREQ, time.monotonic() - partenza,
    )
    return _rifinisci(unisci_segmenti(pezzi, cfg.get("glossario", [])))


def _trascrivi_e_incolla(
    audio, app_bersaglio, scheda_bersaglio, sessione=None, token_turno=None,
):
    """Parte pesante (Whisper ~2-3s + incolla): gira su un thread a parte e
    blindata. Se girasse sul thread della tastiera, macOS la vedrebbe "appesa"
    e disabiliterebbe l'hotkey; e un suo errore ucciderebbe il listener.

    app_bersaglio e' l'app (e scheda_bersaglio l'URL, se browser noto) che
    erano davanti al momento dello stop: se nel frattempo (pulizia inclusa)
    Sal cambia pagina o scheda, il testo deve arrivare comunque li', non dove
    si trova ora il focus."""
    log = logging.getLogger("voce")
    fallita = False
    try:
        conservato = esegui_sicuro(
            salva_audio_recente, audio, BASE / "audio_recenti",
            cfg.get("conserva_audio_n", 0),
        )
        if conservato:  # percorso intero: la cartella operativa, non quella sorgente
            log.info("audio conservato: %s", conservato)
        testo = _trascrivi_con_sessione(audio, sessione)
        debug = cfg.get("debug_dettature", False)
        allucinato = e_allucinazione(testo)
        if allucinato:  # frase-fantasma di Whisper sul non-parlato: scarta
            log.info("scartato come allucinazione (%d caratteri)", len(testo))
            testo = ""
        nome_bersaglio = app_bersaglio.localizedName() if app_bersaglio else ""
        chat_agente = destinazione_agente(nome_bersaglio, scheda_bersaglio)
        log.info(
            "trascritto: %d parole%s",
            len(testo.split()),
            " (grezzo, chat agente)" if testo and chat_agente else "",
        )
        if debug and testo and not allucinato:
            log.info("grezzo: %s", testo)
        # In conversazione con l'agente (voce ON *o* mani libere ON) la
        # pulizia si salta: costa 1-3s a turno e — caso reale 06/07 — il
        # modello Apple a volte RIASSUME invece di correggere (35 parole
        # grezze intere ridotte a meta': "si e' mangiato le parole" era la
        # pulizia, non il microfono). L'agente capisce benissimo il grezzo.
        in_conversazione = voce_attiva() or mani_libere_attive()
        salta_per_conversazione = (
            chat_agente
            or (in_conversazione and not cfg.get("pulizia_in_conversazione", False))
        )
        if testo and not salta_per_conversazione and SHORTCUT_PULIZIA and serve_pulizia(testo, cfg):
            eventi.put("sistemo")
            glossario = cfg.get("glossario", [])
            inizio_pulizia = time.monotonic()
            pulito = None
            global _guasti_shortcut, _ultimo_guasto_shortcut
            # corsia veloce Apple (~1.3s di mediana misurata)
            if SHORTCUT_PULIZIA and corsia_utilizzabile(
                    _guasti_shortcut, _ultimo_guasto_shortcut, inizio_pulizia):
                pulito = pulisci_con_shortcut(
                    testo, SHORTCUT_PULIZIA,
                    timeout=float(cfg.get("pulizia_timeout_shortcut_sec", 2)),
                    glossario=glossario,
                )
                log.info("pulizia shortcut %.1fs: %s", time.monotonic() - inizio_pulizia,
                         "ok" if pulito else "FALLITA")
                # 2 incanti di fila = pausa, non spegnimento: Apple Intelligence
                # appesa non deve regalare 10s morti a ogni dettatura, ma quando
                # torna a funzionare l'app deve accorgersene da sola.
                prima = _guasti_shortcut
                _guasti_shortcut, _ultimo_guasto_shortcut = registra_esito_corsia(
                    _guasti_shortcut, bool(pulito), inizio_pulizia)
                if prima < SOGLIA_GUASTI_CORSIA <= _guasti_shortcut:
                    log.warning("corsia veloce in pausa %d minuti (2 fallimenti di fila)",
                                RIPOSO_CORSIA_SEC // 60)
                if debug and pulito:
                    log.info("pulito: %s", pulito)
            if pulito is None:
                log.info("pulizia veloce non riuscita: uso subito il grezzo")
            testo = pulito or testo
    except Exception:
        log.exception("errore in trascrizione")
        testo = ""
        fallita = True
    finally:
        _concludi_dettatura(token_turno, testo, (app_bersaglio, scheda_bersaglio), fallita)


def _concludi_dettatura(token, testo="", bersaglio=None, fallita=False):
    coda_dettature.completa(token, testo, bersaglio, fallita)
    # Anche scarti e silenzi passano qui: nessun pezzo puo' lasciare la coda appesa.
    threading.Thread(target=_consegna_dettature, daemon=True).start()


def _consegna_dettature():
    coda_dettature.consegna_pronte(_incolla_messaggio, chiudi_turno_utente)
    if not registrando and not coda_dettature.occupata():
        _nascondi_o_arma()


def _incolla_messaggio(testo, bersaglio, revisione):
    global _ultima_chat_ai
    app_bersaglio, scheda_bersaglio = bersaglio
    chat_agente = destinazione_agente(
        app_bersaglio.localizedName() if app_bersaglio else "", scheda_bersaglio,
    )
    log = logging.getLogger("voce")
    try:
        riattiva_bersaglio(app_bersaglio, scheda_bersaglio)
        casella = esegui_sicuro(metti_cursore_in_casella, app_bersaglio)
        riserva = _bersaglio_di_riserva(bersaglio, chat_agente) if casella is False else None
        if riserva is not None and esegui_sicuro(_fuori_dal_monitor_del_mouse, riserva[0]):
            log.info("cursore automatico: la chat %s sta su un altro monitor, il testo resta qui",
                     riserva[0].localizedName())
            riserva = None
        if riserva is not None:
            # davanti non c'e' dove scrivere (Gmail in Chrome, Finder, Anteprima):
            # il testo torna nell'ultima chat AI, dove Sal stava parlando
            app_bersaglio, scheda_bersaglio = riserva
            chat_agente = True  # e' una chat AI per costruzione (vedi _ultima_chat_ai)
            log.info("cursore automatico: davanti non c'e' dove scrivere, torno alla chat %s",
                     app_bersaglio.localizedName())
            riattiva_bersaglio(app_bersaglio, scheda_bersaglio)
            casella = esegui_sicuro(metti_cursore_in_casella, app_bersaglio)
        senza_casella = casella is False  # finestra letta: di caselle non ce n'e'
        if testo:
            incolla(testo + " ", conserva_appunti=senza_casella)
        if senza_casella:
            # l'incolla e' partito alla cieca: il testo resta negli
            # Appunti (Cmd+V dove serve) e il suono diverso avvisa che
            # la frase NON e' arrivata (caso 30/08: frase incollata nel
            # vuoto e persa col ripristino degli Appunti)
            suono("Basso")
            log.info("incollato alla cieca: testo conservato negli Appunti")
        if chat_agente:
            _ultima_chat_ai = (app_bersaglio, scheda_bersaglio)
        log.info("incollato (app bersaglio: %s)", app_bersaglio.localizedName() if app_bersaglio else "nessuna")
        # il testo e' arrivato: la pill si chiude adesso, non dopo l'Invio
        # (caso 23/09/2026: «Trascrivo…» restava 2 secondi sul testo gia'
        # pronto). Se un altro pezzo e' in arrivo resta aperta per lui.
        if not registrando and not coda_dettature.occupata():
            _nascondi_o_arma()
        # invio automatico: parte sempre (indipendente dal toggle voce
        # agenti). La PAUSA prima dell'Invio dipende dal contesto: a voce
        # ON e' botta e risposta (breve); in una chat AI a voce OFF il
        # testo si vede e parte quasi subito (dati 30/08→04/09: con la
        # pausa dei documenti il 40% degli Invii veniva annullato da Sal
        # che premeva Invio a mano; con un secondo solo, 17/09, non faceva
        # in tempo a bloccarlo con uno spazio: ora due); nei documenti
        # serve tempo per correggere. Durante l'attesa, QUALSIASI tasto premuto da Sal o
        # una nuova registrazione gia' in corso ANNULLANO l'Invio
        # (richiesta 06/07: "se clicco un tasto l'invio si deve
        # bloccare" — stava aggiungendo una seconda frase e la prima e'
        # partita da sola). La frase resta incollata: partira' con
        # l'Invio del turno successivo, tutto insieme.
        if cfg.get("invio_automatico", True) and (not senza_casella or chat_agente):
            # senza una casella vera l'Invio andrebbe su un focus ignoto:
            # in una pagina puo' essere un bottone qualunque. In una chat AI
            # riconosciuta no: il Cmd+V e' gia' partito in quel punto, quindi
            # o il testo e' nella casella e l'Invio lo manda, o non c'e'
            # niente da mandare. Caso reale 13/09/2026: Antigravity non
            # espone nessuna casella all'accessibilita' (finestra muta,
            # zero elementi) e Sal doveva premere Invio a mano dopo ogni
            # dettatura; una frase incollata e mai inviata si e' persa,
            # sostituita dalla dettatura successiva.
            attesa = ritardo_invio(cfg, voce_attiva(), chat_agente)
            time.sleep(0.15)  # margine: il Cmd+V dell'incolla non deve contare come "tasto di Sal"
            riferimento = time.monotonic()
            trascorso = 0.0
            annullato = (tasto_premuto or registrando
                         or not coda_dettature.puo_inviare(revisione))
            while not annullato and trascorso < attesa:
                time.sleep(min(0.1, attesa - trascorso))
                trascorso = time.monotonic() - riferimento
                if (ultima_pressione_utente > riferimento or registrando
                        or tasto_premuto or not coda_dettature.puo_inviare(revisione)):
                    annullato = True
                    break
            annullato = (annullato or tasto_premuto or registrando
                         or not coda_dettature.puo_inviare(revisione))
            if annullato:
                log.info("invio automatico ANNULLATO (tasto premuto o nuova dettatura in corso)")
                return revisione >= 0 and not coda_dettature.puo_inviare(revisione)
            else:
                tastiera.press(Key.enter)
                tastiera.release(Key.enter)
                log.info("invio automatico premuto (attesa %.1fs%s%s)",
                         attesa, ", chat AI" if chat_agente else "",
                         ", alla cieca" if senza_casella else "")
    except Exception:
        log.exception("errore in consegna dettatura")


scarti_fuori_scala = 0  # dettature di fila con sample fuori [-1,1]: al 2° si riavvia lo stream


def ferma_e_trascrivi():
    """Chiude la registrazione (il microfono resta aperto: vedi avvia_stream)
    e lancia la trascrizione su un thread a parte."""
    global registrando, inizio_registrazione, scarti_fuori_scala
    global sessione_progressiva, turno_utente_token
    token_turno, turno_utente_token = turno_utente_token, None
    try:
        if not registrando:
            _concludi_dettatura(token_turno)
            _nascondi_o_arma()
            return
        app_bersaglio = app_frontale()  # bersaglio del testo: l'app davanti ORA, non a fine pulizia
        scheda_bersaglio = scheda_browser_frontale(app_bersaglio)  # idem, la scheda se e' un browser noto
        registrando = False
        inizio_registrazione = None
        sessione, sessione_progressiva = sessione_progressiva, None
        if sessione is not None:
            sessione.ferma()  # niente nuovi tagli: la coda la fa il thread di incolla
        logging.getLogger("voce").info("registrazione fermata")
        suono("Bottle")
        if not blocchi:
            _concludi_dettatura(token_turno)
            _nascondi_o_arma()
            return
        audio = np.concatenate(blocchi)[:, 0]
        if len(audio) < FREQ * 0.4:  # sotto 0,4 s: pressione accidentale
            _concludi_dettatura(token_turno)
            _nascondi_o_arma()
            return
        rms = float(np.sqrt(np.mean(audio ** 2)))
        logging.getLogger("voce").info("audio: %.1fs, volume rms %.4f", len(audio) / FREQ, rms)
        scarti_fuori_scala, scarta, riavvia = aggiorna_scarti_fuori_scala(scarti_fuori_scala, rms)
        if scarta:  # sample fuori [-1,1]: stream corrotto, Whisper allucinerebbe
            logging.getLogger("voce").warning(
                "scartato: audio fuori scala (rms %.2f > 1), stream corrotto — riprova tra qualche secondo", rms
            )
            _concludi_dettatura(token_turno)
            _nascondi_o_arma()
            if riavvia:
                riavvia_processo(
                    f"audio fuori scala persistente (rms {rms:.2f}, {scarti_fuori_scala} scarti di fila)"
                )
            return
        if not c_e_voce(audio, cfg.get("soglia_voce", SOGLIA_VOCE)):  # silenzio/respiro: niente parlato
            logging.getLogger("voce").info("scartato: volume sotto soglia (mic muto/occupato?)")
            _concludi_dettatura(token_turno)
            _nascondi_o_arma()
            # prima si controlla il guadagno d'ingresso: se e' lui, riavviare il
            # processo non risolverebbe nulla (vedi ripara_guadagno_ingresso).
            if not ripara_guadagno_ingresso(rms):
                airbag_stream_muto(len(audio) / FREQ)
            return
        threading.Thread(
            target=_trascrivi_e_incolla,
            args=(audio, app_bersaglio, scheda_bersaglio, sessione, token_turno),
            daemon=True,
        ).start()
    except Exception:
        logging.getLogger("voce").exception("errore chiusura registrazione")
        registrando = False
        inizio_registrazione = None
        if sessione_progressiva is not None:
            sessione_progressiva.ferma()
            sessione_progressiva = None
        _concludi_dettatura(token_turno, fallita=True)


def commuta_voce():
    """Tasto on/off della voce agenti, con conferma parlata."""
    if FLAG_VOICE_ON.exists():
        FLAG_VOICE_ON.unlink()
        stato = "Voce AI spenta"
    else:
        FLAG_VOICE_ON.touch()
        stato = "Voce AI accesa. Le risposte dell'agente sono audio sintetico."
    logging.getLogger("voce").info("combo voce: %s", stato)
    # l'annuncio di stato non si mette in coda dietro una lettura lunga:
    # zittisce e parla subito (spegnere la voce DEVE fare silenzio ora)
    ferma_voce()
    pronuncia(stato)


def commuta_mani_libere():
    """Tasto on/off della modalita' mani libere: ascolto continuo a soglia di
    volume (vedi worker_mani_libere), senza dover tenere premuto il tasto.

    Su file (FLAG_MANI_LIBERE_ON), non variabile in memoria: cosi' anche il
    lanciatore sul Desktop puo' accenderla insieme alla voce con un click."""
    # Feedback con SUONI immediati, non TTS: l'annuncio parlato ("Mani
    # libere attivate", via Shortcuts/Siri) teneva il microfono sordo per
    # ~4s (latenza + durata + grazia) e quello che Sal diceva subito dopo
    # il combo andava perso (caso reale 06/07: il suo "Ok" ignorato).
    # Lo stato visivo lo danno il microfonino e l'icona nella barra menu.
    if FLAG_MANI_LIBERE_ON.exists():
        FLAG_MANI_LIBERE_ON.unlink()
        logging.getLogger("voce").info("combo mani libere: OFF")
        suono("Bottle")
    else:
        logging.getLogger("voce").info("combo mani libere: ON")
        suono("Glass")
        FLAG_MANI_LIBERE_ON.touch()


def worker_mani_libere():
    """Ascolto continuo, SOLO quando mani_libere_attive(): quando il volume sale
    sopra soglia per un po' parte la registrazione (stessa pill, stesso
    avvia_registrazione del tasto manuale), quando scende sotto soglia per un
    po' si ferma e trascrive da sola. In pausa mentre l'agente parla (altrimenti
    si "sentirebbe da sola" e si incepperebbe) e mentre il tasto manuale e' gia'
    in uso (non interferisce)."""
    IDLE, ASCOLTO = "idle", "ascolto"
    stato = IDLE
    frame_sopra = frame_sotto = 0
    intervallo = 0.05
    # ISTERESI a due soglie (06/07, "mi ha preso solo una parte"): Sal a
    # volte parla piano (rms 0.012-0.015, vicino alla soglia d'innesco) e
    # con una soglia sola il VAD si fermava nelle sue pause naturali,
    # spezzando la frase. Innesco a soglia piena (sopra il rumore ambiente
    # 0.004-0.009), STOP solo quando si scende sotto una soglia piu' bassa
    # (meta') per un silenzio piu' lungo.
    soglia_start = float(cfg.get("mani_libere_soglia_voce", 0.010))
    soglia_stop = float(cfg.get("mani_libere_soglia_stop", soglia_start / 2))
    frame_attivazione = max(1, round(cfg.get("mani_libere_attivazione_sec", 0.2) / intervallo))
    frame_silenzio = max(1, round(cfg.get("mani_libere_silenzio_sec", 1.4) / intervallo))
    fine_voce = 0.0  # quando l'agente ha smesso di parlare: piccolo periodo di grazia
    grazia_sec = float(cfg.get("mani_libere_grazia_dopo_voce_sec", 0.7))
    # Auto-spegnimento: mani libere dimenticata accesa = tutto quello che
    # suona nella stanza (telefonate, persone, video) finisce in chat con
    # Invio automatico. Dopo N minuti senza nessuna dettatura si spegne da
    # sola, con suono di conferma.
    autospegnimento_sec = float(cfg.get("mani_libere_autospegnimento_min", 10)) * 60
    ultima_attivita = time.monotonic()
    era_attiva = False
    while True:
        time.sleep(intervallo)
        if not mani_libere_attive():
            if stato == ASCOLTO:
                # la modalita' e' stata spenta MENTRE il VAD registrava: la
                # registrazione va chiusa, altrimenti resta aperta (pill
                # fissa sullo schermo) finche' non scatta l'anti-incanto.
                comandi_audio.put("stop")
            stato, frame_sopra, frame_sotto = IDLE, 0, 0
            era_attiva = False
            continue
        if not era_attiva:  # appena accesa: il conto dell'inattivita' riparte
            era_attiva = True
            ultima_attivita = time.monotonic()
        if registrando or stato == ASCOLTO:
            ultima_attivita = time.monotonic()  # sta lavorando: niente conto alla rovescia
        elif autospegnimento_sec > 0 and time.monotonic() - ultima_attivita > autospegnimento_sec:
            logging.getLogger("voce").info(
                "mani libere: auto-spegnimento dopo %.0f minuti di inattivita'",
                autospegnimento_sec / 60,
            )
            FLAG_MANI_LIBERE_ON.unlink(missing_ok=True)
            suono("Bottle")
            continue
        if FLAG_PARLANDO.exists():  # l'agente sta leggendo la risposta: si aspetta
            fine_voce = time.monotonic()
            frame_sopra = 0
            continue
        if time.monotonic() - fine_voce < grazia_sec:
            continue  # coda audio delle casse appena spente: non scambiarla per Sal
        if stato == IDLE:
            if registrando:  # gia' in corso (es. tasto manuale): non toccare
                continue
            if volume_corrente >= soglia_start:
                frame_sopra += 1
                if frame_sopra >= frame_attivazione:
                    frame_sopra = 0
                    stato = ASCOLTO
                    comandi_audio.put("start")
            else:
                frame_sopra = 0
        elif stato == ASCOLTO:
            if volume_corrente < soglia_stop:
                frame_sotto += 1
                if frame_sotto >= frame_silenzio:
                    frame_sotto = 0
                    stato = IDLE
                    comandi_audio.put("stop")
            else:
                frame_sotto = 0


def worker_audio():
    """Esegue avvio/stop registrazione FUORI dal thread della tastiera (che deve
    solo mettere "start"/"stop" in coda e tornare subito: qualunque lavoro più
    lento fatto li' dentro incastrerebbe l'event-tap). Lo stream resta aperto
    per tutta la vita del processo (vedi avvia_stream): qui non si apre ne'
    si chiude piu' microfono a ogni dettatura."""
    while True:
        cmd = comandi_audio.get()
        if cmd == "start":
            esegui_sicuro(avvia_registrazione)
        elif cmd == "stop":
            esegui_sicuro(ferma_e_trascrivi)
        elif cmd == "stop_coda":
            # rilascio del tasto: il callback audio continua ad accodare
            # blocchi finche' registrando e' True, quindi basta aspettare
            # qui (mai nel thread tastiera) prima di chiudere.
            if registrando and CODA_RILASCIO_SEC > 0:
                time.sleep(CODA_RILASCIO_SEC)
            esegui_sicuro(ferma_e_trascrivi)


def riavvia_processo(motivo):
    """L'audio e' compromesso sotto lo stream sempre-aperto (device cambiato o
    stream incantato): invece di chiamare stream.stop()/close() (il deadlock
    che abbiamo appena eliminato), usciamo e ripartiamo da zero. L'uscita del
    processo chiude il device per conto dell'OS, senza passare dal mutex
    CoreAudio che si incantava."""
    logging.getLogger("voce").warning("riavvio processo audio: %s", motivo)
    cartella = os.path.dirname(os.path.abspath(__file__))
    subprocess.Popen([sys.executable, os.path.abspath(__file__)], cwd=cartella, start_new_session=True)
    os._exit(0)


FILE_ULTIMO_RIAVVIO_MUTO = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), ".ultimo_riavvio_muto"
)


def airbag_stream_muto(durata):
    """Dettatura lunga ma quasi muta = quasi sempre stream CoreAudio incantato
    (caso 08/07: 12s di parlato a rms 0.0016 dopo la comparsa del Microfono di
    iPhone). Il watchdog per nome-device non se ne accorge: PortAudio congela
    la lista device all'avvio, quindi il confronto non cambia mai. Rimedio:
    lo stesso riavvio pulito del cambio device. Cooldown su file: se il
    riavvio non risolve (mic muto davvero), niente loop di riavvii."""
    if durata < 3.0:
        return  # tocco corto senza parlato: silenzio legittimo, non un guasto
    try:
        if time.time() - os.path.getmtime(FILE_ULTIMO_RIAVVIO_MUTO) < 600:
            logging.getLogger("voce").warning(
                "stream ancora muto dopo riavvio recente: mic muto/occupato davvero, non riavvio"
            )
            return
    except OSError:
        pass  # mai riavviato prima: si procede
    with open(FILE_ULTIMO_RIAVVIO_MUTO, "w") as f:
        f.write(str(time.time()))
    riavvia_processo(f"dettatura {durata:.1f}s quasi muta (stream incantato?)")


def watchdog_audio():
    """Airbag fuori dal pannello: interviene anche se l'UI resta viva ma l'audio no."""
    global tasto_premuto
    tick = 0
    while True:
        time.sleep(0.5)
        ora = time.monotonic()
        tasto_giu = _tasto_detta_giu()
        if stop_anti_incanto(registrando, inizio_registrazione, ora, tasto_giu,
                             MAX_REGISTRAZIONE_SEC, MAX_REGISTRAZIONE_TASTO_SEC):
            durata = ora - inizio_registrazione
            logging.getLogger("voce").warning(
                "registrazione oltre %.1fs: stop anti-incanto watchdog (tasto giu': %s)",
                durata, tasto_giu,
            )
            tasto_premuto = False
            comandi_audio.put("stop")
        tick += 1
        if tick % 10 == 0 and not registrando:  # ogni ~5s, mai a meta' di una dettatura
            attuale = nome_device_input()
            if attuale is not None and attuale != device_input_apertura:
                riavvia_processo(f"cambio microfono: {device_input_apertura!r} -> {attuale!r}")


# pynput si e' dimostrato CIECO sui combo di modificatori premuti insieme
# dalla tastiera fisica di Sal (log 06/07: Cmd destro+Option premuti e
# rilasciati, ZERO eventi arrivati al listener; con eventi sintetici invece
# funzionava). Lo stato dei modificatori si legge quindi direttamente dal
# sistema (Quartz), che e' sempre vero qualunque sia la tastiera.

def _option_giu():
    flags = Quartz.CGEventSourceFlagsState(Quartz.kCGEventSourceStateCombinedSessionState)
    return bool(flags & Quartz.kCGEventFlagMaskAlternate)


def _cmd_giu():
    flags = Quartz.CGEventSourceFlagsState(Quartz.kCGEventSourceStateCombinedSessionState)
    return bool(flags & Quartz.kCGEventFlagMaskCommand)


def worker_combo_mani_libere():
    """Cmd + Option tenuti insieme = toggle mani libere. Polling sullo stato
    di sistema dei modificatori (0.05s), NON eventi pynput. Debounce: una
    commutazione per hold. Se la dettatura manuale era appena partita (Cmd
    sceso un attimo prima di Option), la chiude: l'audio di pochi decimi di
    secondo viene scartato dal gate < 0.4s."""
    global combo_mani_libere_scattato
    while True:
        time.sleep(0.05)
        entrambi = _cmd_giu() and _option_giu()
        if entrambi and not combo_mani_libere_scattato:
            combo_mani_libere_scattato = True
            if registrando:
                comandi_audio.put("stop")
            # commuta_* fanno lavoro BLOCCANTE (pkill/shortcuts/say/pipe):
            # su thread dedicato per non bloccare questo poller.
            threading.Thread(target=esegui_sicuro, args=(commuta_mani_libere,), daemon=True).start()
        elif not entrambi:
            combo_mani_libere_scattato = False


def su_pressione(tasto):
    global tasto_premuto, combo_voce_scattato, ultima_pressione_utente
    ultima_pressione_utente = time.monotonic()  # annulla un eventuale Invio in attesa
    if tasto == TASTO:
        if _option_giu():               # Option gia' giu': e' il combo mani libere
            return                      # (lo scatta il poller) — niente dettatura
        if not tasto_premuto:
            coda_dettature.interrompi_invio()  # prima del worker audio
            tasto_premuto = True        # stato sul solo thread tastiera: niente race
            comandi_audio.put("start")  # il lavoro audio (bloccante) lo fa il worker
    elif tasto == TASTO_COMBO_VOCE and not combo_voce_scattato and _option_giu():
        combo_voce_scattato = True      # debounce: un hold = una sola commutazione
        threading.Thread(target=esegui_sicuro, args=(commuta_voce,), daemon=True).start()


def su_rilascio(tasto):
    global tasto_premuto, combo_voce_scattato
    if tasto == TASTO:
        if tasto_premuto:
            tasto_premuto = False
            comandi_audio.put("stop_coda")  # rilascio manuale: coda di CODA_RILASCIO_SEC
    elif tasto == TASTO_COMBO_VOCE:
        combo_voce_scattato = False


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
    """Una volta al giorno cerca possibili correzioni nei dettati recenti.
    Le ipotesi restano nel registro; non diventano sostituzioni attive."""
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
    comando = COMANDO_APPRENDIMENTO or comandi_agente()  # tutti gli agenti presenti, in ordine
    if not comando:
        return
    impara_sostituzioni(
        os.path.join(base, "voce.log"), str(config_scrivibile()), comando
    )
    # Ripasso notturno degli audio conservati: processo a parte, sganciato e
    # a bassa priorita' — carica il secondo modello, propone e muore, cosi' la
    # dettatura in diretta non paga ne' memoria ne' lock di trascrizione.
    if int(cfg.get("conserva_audio_n", 0)) > 0:
        subprocess.Popen(
            [sys.executable, os.path.join(base, "voce_lib.py"), "--ripasso"],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, start_new_session=True,
            preexec_fn=lambda: os.nice(15),
        )
        logging.getLogger("voce").info("ripasso audio avviato in sottofondo")
    with open(marcatore, "w") as f:
        f.write(oggi)


def _apprendimento_periodico():
    """Il processo vive per giorni: l'apprendimento solo all'avvio non
    partiva quasi mai (stesso difetto del Comando Rapido cercato solo
    all'avvio, vedi rc.4). Controllo ogni ora: il gate una-volta-al-giorno
    sta gia' dentro _impara_dagli_errori."""
    while True:
        esegui_sicuro(_impara_dagli_errori)
        time.sleep(3600)


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
    FLAG_TURNO_UTENTE.unlink(missing_ok=True)  # residuo di un arresto durante la dettatura
    # Rotazione a 7 giorni: con debug_dettature=true il log contiene il grezzo
    # di ogni dettatura in chiaro (conversazioni, call, sfoghi) — non deve
    # accumularsi all'infinito. impara_sostituzioni() legge solo le ultime
    # righe, quindi 7 giorni bastano e avanzano per quella funzione.
    gestore_log = logging.handlers.TimedRotatingFileHandler(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "voce.log"),
        when="midnight", backupCount=7, encoding="utf-8",
    )
    logging.basicConfig(
        handlers=[gestore_log],
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    logging.getLogger("voce").info("avvio dettatura")
    _avvisa_se_non_autorizzato()
    allinea_volume_ingresso()  # ingresso basso = app muta senza motivo apparente
    avvia_stream()  # microfono aperto una volta sola, per tutta la vita del processo
    threading.Thread(target=worker_audio, daemon=True).start()  # possiede lo start/stop registrazione
    threading.Thread(target=watchdog_audio, daemon=True).start()  # recupera stop persi/CoreAudio bloccato
    threading.Thread(target=worker_mani_libere, daemon=True).start()  # ascolto continuo, solo se attivato
    threading.Thread(target=worker_combo_mani_libere, daemon=True).start()  # Cmd+Option via flag di sistema
    listener = avvia_listener()  # hotkey attivo DA SUBITO
    threading.Thread(target=_scalda_modello, daemon=True).start()  # modello in sottofondo
    threading.Thread(target=_apprendimento_periodico, daemon=True).start()  # una volta al giorno, anche se il processo vive settimane
    print(f"Voce — dettatura attiva (il modello si scalda in sottofondo). "
          f"Tieni premuto [{cfg['hotkey']}] e parla.")
    gestore = GestorePannello.alloc().init()
    AppKit.NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
        0.08, gestore, "tick:", None, True
    )
    AppHelper.runEventLoop()
