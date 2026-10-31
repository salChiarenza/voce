"""P-105: schermate cambiate in un'app longeva, senza avviare Voce o audio."""
import ast
from pathlib import Path
from types import SimpleNamespace

import pytest

DETTA = Path(__file__).resolve().parents[1] / "mac" / "detta.py"


def _carica(spazio):
    albero = ast.parse(DETTA.read_text(encoding="utf-8"))
    nodi = [n for n in albero.body if
            isinstance(n, ast.FunctionDef) and n.name == "_ricrea_pannello"
            or isinstance(n, ast.ClassDef) and n.name == "GestorePannello"]
    exec(compile(ast.Module(body=nodi, type_ignores=[]), str(DETTA), "exec"), spazio)
    return spazio["GestorePannello"]()


def _rect(x, y, w, h):
    return SimpleNamespace(origin=SimpleNamespace(x=x, y=y),
                           size=SimpleNamespace(width=w, height=h))


class _Pannello:
    def __init__(self):
        self.contenuto, self.posizione = object(), None
        self.aperto, self.chiuso, self.alfa = False, False, 0.7
    def initWithContentRect_styleMask_backing_defer_(self, *args): return self
    def frame(self): return _rect(0, 0, 200, 80)
    def contentView(self): return self.contenuto
    def setContentView_(self, contenuto): self.contenuto = contenuto
    def alphaValue(self): return self.alfa
    def setAlphaValue_(self, alfa): self.alfa = alfa
    def orderFrontRegardless(self): self.aperto = True
    def orderOut_(self, _): self.aperto = False
    def close(self): self.chiuso = True
    def setFrameOrigin_(self, p): self.posizione = p
    def setLevel_(self, _): pass
    def setOpaque_(self, _): pass
    def setBackgroundColor_(self, _): pass
    def setIgnoresMouseEvents_(self, _): pass
    def setCollectionBehavior_(self, _): pass
    def setReleasedWhenClosed_(self, _): pass


def _schermo(numero=1, x=0, w=1440, scala=2):
    return SimpleNamespace(deviceDescription=lambda: {"NSScreenNumber": numero},
                           frame=lambda: _rect(x, 0, w, 900),
                           visibleFrame=lambda: _rect(x, 25, w, 875),
                           backingScaleFactor=lambda: scala)


@pytest.fixture
def finestre():
    schermi, mani = [_schermo()], [True]
    originale, mini = _Pannello(), _Pannello()
    originale.aperto = mini.aperto = True
    appkit = SimpleNamespace(
        NSObject=object, NSScreen=SimpleNamespace(screens=lambda: schermi),
        NSPanel=SimpleNamespace(alloc=_Pannello), NSMakeRect=_rect,
        NSWindowStyleMaskBorderless=0, NSWindowStyleMaskNonactivatingPanel=1,
        NSBackingStoreBuffered=2, NSStatusWindowLevel=3,
        NSColor=SimpleNamespace(clearColor=lambda: None),
        NSFont=SimpleNamespace(systemFontOfSize_=lambda n: n),
        NSWindowCollectionBehaviorCanJoinAllSpaces=1,
        NSWindowCollectionBehaviorFullScreenAuxiliary=2)
    spazio = dict(AppKit=appkit, pannello=originale, mini_pannello=mini,
                  mini_label=SimpleNamespace(setFont_=lambda n: None),
                  mani_libere_attive=lambda: mani[0], volume_corrente=0.02)
    spazio["posiziona_pannello"] = lambda: setattr(spazio["pannello"], "posizione", schermi[-1].frame().origin.x)
    spazio["posiziona_mini_pannello"] = lambda: setattr(spazio["mini_pannello"], "posizione", schermi[-1].frame().origin.x)
    ui = _carica(spazio)
    ui.stato, ui._mini_visibile, ui._tick = "trascrivo", True, 6
    return SimpleNamespace(ui=ui, spazio=spazio, schermi=schermi, mani=mani,
                           originale=originale, mini=mini)


@pytest.mark.parametrize("cambio", ["collega", "scollega", "ridimensiona", "scala", "sostituisci", "riordina"])
def test_cambio_schermi_ricrea_entrambi_e_conserva_contenuto_e_stato(finestre, cambio):
    f = finestre
    if cambio in {"scollega", "riordina"}:
        f.schermi.append(_schermo(2, -1920, 1920, 1))
    f.ui._aggiorna_mini()  # baseline: processo gia' in ascolto, poi cambia lo schermo
    assert f.spazio["pannello"] is f.originale
    if cambio == "collega": f.schermi.append(_schermo(2, -1920, 1920, 1))
    elif cambio == "scollega": f.schermi.pop()
    elif cambio == "ridimensiona": f.schermi[0] = _schermo(w=1280)
    elif cambio == "scala": f.schermi[0] = _schermo(scala=1)
    elif cambio == "sostituisci": f.schermi[0] = _schermo(numero=3)
    elif cambio == "riordina": f.schermi.reverse()
    f.ui._aggiorna_mini()  # percorso vero del timer, non un callback scollegato
    nuovo, mini = f.spazio["pannello"], f.spazio["mini_pannello"]
    assert nuovo is not f.originale and mini is not f.mini
    assert nuovo.contenuto is f.originale.contenuto and mini.contenuto is f.mini.contenuto
    assert f.originale.chiuso and f.mini.chiuso
    assert nuovo.aperto and mini.aperto
    assert nuovo.posizione == mini.posizione == f.schermi[-1].frame().origin.x
    assert nuovo.alfa == 0.7 and f.ui.stato == "trascrivo" and f.ui._mini_visibile
    f.ui._aggiorna_mini()
    assert f.spazio["pannello"] is nuovo  # nessun riciclo continuo


def test_cambio_a_riposo_non_accende_indicatori_o_mani_libere(finestre):
    f = finestre
    f.ui.stato, f.ui._mini_visibile, f.mani[0] = "nascosto", False, False
    f.originale.aperto = f.mini.aperto = False
    f.ui._aggiorna_mini()
    f.schermi.append(_schermo(2))
    f.ui._aggiorna_mini()
    assert f.spazio["pannello"] is not f.originale
    assert not f.spazio["pannello"].aperto and not f.spazio["mini_pannello"].aperto
    assert not f.mani[0]


def test_nessuno_schermo_durante_la_transizione_non_perde_la_prova_del_cambio(finestre):
    f = finestre
    f.ui._aggiorna_mini()
    f.schermi.clear()
    f.ui._aggiorna_mini()
    assert f.spazio["pannello"] is f.originale
    f.schermi.append(_schermo(2))
    f.ui._aggiorna_mini()
    assert f.spazio["pannello"] is not f.originale


def test_notifica_di_ricollegamento_rigenera_anche_se_la_geometria_finale_e_identica(finestre):
    f = finestre
    f.ui._aggiorna_mini()
    assert hasattr(f.ui, "schermiCambiati_"), "Manca l'osservatore dei cambi schermo"
    f.ui.schermiCambiati_(None)
    f.ui._aggiorna_mini()
    assert f.spazio["pannello"] is not f.originale


def test_l_avvio_collega_la_notifica_al_gestore_del_timer(finestre):
    f = finestre
    registrati = []
    centro = SimpleNamespace(addObserver_selector_name_object_=lambda *a: registrati.append(a))
    f.spazio["AppKit"].NSNotificationCenter = SimpleNamespace(defaultCenter=lambda: centro)
    f.spazio["AppKit"].NSApplicationDidChangeScreenParametersNotification = "cambio-schermi"
    f.spazio["gestore"] = f.ui
    albero = ast.parse(DETTA.read_text(encoding="utf-8"))
    ingressi = [n for n in ast.walk(albero) if isinstance(n, ast.Expr)
                and isinstance(n.value, ast.Call)
                and getattr(n.value.func, "attr", "") == "addObserver_selector_name_object_"]
    assert len(ingressi) == 1
    exec(compile(ast.Module(body=ingressi, type_ignores=[]), str(DETTA), "exec"), f.spazio)
    osservatore, selettore, nome, origine = registrati[0]
    assert osservatore is f.ui and nome == "cambio-schermi" and origine is None
    f.ui._aggiorna_mini()
    getattr(osservatore, selettore.replace(":", "_"))(None)
    f.ui._aggiorna_mini()
    assert f.spazio["pannello"] is not f.originale


def test_ricreazione_nativa_conserva_vista_senza_mostrare_finestre_o_avviare_voce():
    import subprocess
    import sys
    pytest.importorskip("AppKit")
    sessione = subprocess.run([sys.executable, "-c", "import AppKit; AppKit.NSApplication.sharedApplication()"],
                             capture_output=True, text=True)
    if sessione.returncode != 0:
        pytest.skip(f"Sessione grafica AppKit non disponibile (preflight {sessione.returncode})")
    codice = '''
import ast, sys, AppKit
from pathlib import Path
AppKit.NSApplication.sharedApplication()
albero = ast.parse(Path(sys.argv[1]).read_text(encoding="utf-8"))
nodi = [n for n in albero.body if isinstance(n, ast.FunctionDef) and n.name == "_ricrea_pannello"]
assert nodi, "Manca la ricreazione del pannello"
exec(compile(ast.Module(body=nodi, type_ignores=[]), sys.argv[1], "exec"))
vecchio = AppKit.NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
        AppKit.NSMakeRect(0, 0, 200, 80), 0, AppKit.NSBackingStoreBuffered, False)
vecchio.setReleasedWhenClosed_(False)
vista = vecchio.contentView()
vecchio.setAlphaValue_(0.7)
nuovo = None
try:
    nuovo = _ricrea_pannello(vecchio)
    assert nuovo.contentView() == vista
    assert nuovo.frame().size.width == 200 and nuovo.frame().size.height == 80
    assert abs(nuovo.alphaValue() - 0.7) < 0.01
    assert not nuovo.isVisible()
    assert nuovo.ignoresMouseEvents()
    assert nuovo.collectionBehavior() & AppKit.NSWindowCollectionBehaviorCanJoinAllSpaces
finally:
    vecchio.close()
    if nuovo is not None:
        nuovo.close()
'''
    prova = subprocess.run([sys.executable, "-c", codice, str(DETTA)], capture_output=True, text=True)
    assert prova.returncode == 0, prova.stdout + prova.stderr
