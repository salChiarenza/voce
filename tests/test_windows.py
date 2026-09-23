import ast
import importlib.util
import json
import logging
import re
import time
from pathlib import Path
from types import SimpleNamespace


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "windows" / "voce_hook.py"
SPEC = importlib.util.spec_from_file_location("voce_windows_hook", MODULE_PATH)
voce_windows = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(voce_windows)


def _funzioni_pure_app(*nomi):
    path = REPO_ROOT / "windows" / "voice_dettatura_windows.py"
    albero = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    nodi = [
        nodo
        for nodo in albero.body
        if isinstance(nodo, (ast.FunctionDef, ast.Assign, ast.AnnAssign))
        and (
            isinstance(nodo, ast.FunctionDef)
            and nodo.name in nomi
            or isinstance(nodo, ast.Assign)
            and any(
                isinstance(target, ast.Name)
                and target.id in ("_FRASI_FANTASMA", "_CSHARP_MIC",
                                  "GUADAGNO_INGRESSO_MINIMO", "GUADAGNO_INGRESSO_TARGET",
                                  "SOGLIA_GUASTI_CORSIA", "RIPOSO_CORSIA_SEC", "_VK_TASTI")
                for target in nodo.targets
            )
        )
    ]
    spazio = {"re": re}
    exec(compile(ast.Module(body=nodi, type_ignores=[]), str(path), "exec"), spazio)
    return spazio


def test_script_tts_usa_la_voce_scelta_e_fallback_italiano():
    script = voce_windows.script_tts(-1, "Microsoft Elsa")

    assert "$wanted='Microsoft Elsa'" in script
    assert "VoiceInfo.Name -eq $wanted" in script
    assert "Culture.Name -like 'it*'" in script
    assert "$s.Rate=-1" in script


def test_script_tts_escapa_apostrofi_nel_nome():
    script = voce_windows.script_tts(0, "Voce d'Italia")
    assert "$wanted='Voce d''Italia'" in script


def test_windows_tts_rende_ascoltabili_paragrafi_tabelle_e_percorsi():
    pulisci_app = _funzioni_pure_app("pulisci_per_voce")["pulisci_per_voce"]
    casi = [
        ("# Risultati\n\n- Primo\n- Secondo\n\nParagrafo uno.\n\nParagrafo due.",
         "Risultati. Primo. Secondo. Paragrafo uno. Paragrafo due."),
        ("| Attività | Stato |\n| --- | --- |\n| Voce | Pronta |\n| Test | Passati |",
         "Attività: Voce; Stato: Pronta. Attività: Test; Stato: Passati."),
        ("Apri [report.md](/Users/sal/cliente/report.md:12) e `C:\\Lavoro\\Cliente\\dati.csv`.",
         "Apri report.md, riga 12 e dati.csv."),
    ]
    for pulisci in (voce_windows.pulisci_per_voce, pulisci_app):
        for testo, atteso in casi:
            assert pulisci(testo) == atteso
            assert pulisci(atteso) == atteso  # hook e lettore preparano lo stesso testo


def test_tts_windows_espone_il_pid_mentre_legge_e_lo_rimuove_dopo(tmp_path, monkeypatch):
    """Lo stop dell'app deve poter trovare anche la voce avviata dall'hook."""
    from io import BytesIO

    pid_file = tmp_path / "voce_pid"
    pid_durante = []

    class Processo:
        pid = 4321
        stdin = BytesIO()

        def wait(self, timeout=None):
            pid_durante.append(pid_file.read_text())
            return 0

    monkeypatch.setattr(voce_windows, "PID_FILE", pid_file, raising=False)
    monkeypatch.setattr(voce_windows, "CFG_PATH", tmp_path / "config.json")
    monkeypatch.setattr(voce_windows.subprocess, "Popen", lambda *a, **k: Processo())

    voce_windows.parla("Risposta da leggere", attendi=True, tetto_sec=60)

    assert pid_durante == ["4321"]
    assert not pid_file.exists()


def test_lista_voci_normalizza_un_solo_risultato(monkeypatch):
    class Esito:
        returncode = 0
        stdout = '{"name":"Microsoft Elsa","culture":"it-IT"}'

    monkeypatch.setattr(voce_windows.subprocess, "run", lambda *_args, **_kwargs: Esito())
    assert voce_windows.voci_italiane() == [
        {"name": "Microsoft Elsa", "culture": "it-IT"}
    ]


def test_selezione_voce_salva_solo_una_voce_installata(tmp_path, monkeypatch):
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"voce_nome": "", "voce_rate": 0}), encoding="utf-8")
    monkeypatch.setattr(voce_windows, "CFG_PATH", config)
    monkeypatch.setattr(
        voce_windows,
        "voci_italiane",
        lambda: [{"name": "Microsoft Elsa", "culture": "it-IT"}],
    )

    voce_windows.seleziona_voce("Microsoft Elsa")

    assert json.loads(config.read_text(encoding="utf-8"))["voce_nome"] == "Microsoft Elsa"


def test_selezione_voce_rifiuta_nome_non_installato(tmp_path, monkeypatch):
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"voce_nome": ""}), encoding="utf-8")
    monkeypatch.setattr(voce_windows, "CFG_PATH", config)
    monkeypatch.setattr(voce_windows, "voci_italiane", lambda: [])

    try:
        voce_windows.seleziona_voce("Voce inesistente")
    except ValueError as exc:
        assert "non installata" in str(exc)
    else:
        raise AssertionError("Una voce non installata non deve essere salvata")


def test_aggiornamento_conserva_preferenze_e_aggiunge_nuovi_default(tmp_path):
    defaults = tmp_path / "defaults.json"
    current = tmp_path / "config.json"
    defaults.write_text(
        json.dumps(
            {
                "brand": "salchiarenza.ai",
                "voce_nome": "",
                "detta_pulito": True,
                "invio_automatico_ritardo_conversazione_sec": 0.3,
                "nuovo_default": "entra",
            }
        ),
        encoding="utf-8",
    )
    current.write_text(
        json.dumps(
            {
                "brand": "vecchio-brand",
                "voce_nome": "Microsoft Elsa",
                "detta_pulito": False,
                "invio_automatico_ritardo_conversazione_sec": 1.1,
            }
        ),
        encoding="utf-8",
    )

    voce_windows.unisci_config(str(defaults), str(current))
    merged = json.loads(current.read_text(encoding="utf-8"))

    assert merged["brand"] == "salchiarenza.ai"
    assert merged["voce_nome"] == "Microsoft Elsa"
    assert merged["detta_pulito"] is False
    assert merged["invio_automatico_ritardo_conversazione_sec"] == 1.1
    assert merged["nuovo_default"] == "entra"


def test_windows_scarta_frasi_fantasma_e_collassi_whisper():
    funzioni = _funzioni_pure_app(
        "_normalizza", "_ripetizione_patologica", "e_allucinazione"
    )
    e_allucinazione = funzioni["e_allucinazione"]

    assert e_allucinazione("Grazie.") is True
    assert e_allucinazione(("Pier " * 200).strip()) is True
    assert e_allucinazione("Ecologia" + "版" * 200) is True
    assert e_allucinazione("Grazie mille per la proposta, la rivediamo.") is False


def test_windows_annulla_enter_su_tasto_o_nuova_dettatura():
    funzione = _funzioni_pure_app("invio_da_annullare")["invio_da_annullare"]

    assert funzione(10.1, 10.0, False) is True
    assert funzione(9.9, 10.0, True) is True
    assert funzione(9.9, 10.0, False) is False


def test_destinazione_agente_windows_gemella_del_mac():
    funzione = _funzioni_pure_app("destinazione_agente")["destinazione_agente"]

    assert funzione("ChatGPT - Google Chrome ChatGPT") is True
    assert funzione("Claude - Google Chrome chrome") is True
    assert funzione("claude WindowsTerminal") is True
    assert funzione("Google Chrome", "https://chatgpt.com/c/123") is True
    assert funzione("Documento1 - Word WINWORD") is False
    assert funzione("") is False


def test_ritardo_invio_windows_gemello_del_mac():
    funzione = _funzioni_pure_app("ritardo_invio")["ritardo_invio"]
    cfg = {
        "invio_automatico_ritardo_sec": 2.5,
        "invio_automatico_ritardo_conversazione_sec": 0.4,
        "invio_automatico_ritardo_chat_ai_sec": 1.0,
    }
    assert funzione(cfg, True, True) == 0.4
    assert funzione(cfg, True, False) == 0.4
    assert funzione(cfg, False, True) == 1.0
    assert funzione(cfg, False, False) == 2.5
    assert funzione({}, True, False) == 0.3
    assert funzione({}, False, True) == 2.0
    assert funzione({}, False, False) == 2.5


def test_invio_automatico_windows_usa_il_ritardo_di_contesto():
    sorgente = (REPO_ROOT / "windows" / "voice_dettatura_windows.py").read_text(encoding="utf-8")
    corpo = sorgente.split("def _incolla_messaggio", 1)[1].split("\ndef ", 1)[0]
    assert "chat_agente = destinazione_agente(nome_finestra(finestra_bersaglio))" in corpo
    assert "ritardo_invio(CFG, voce_attiva(), chat_agente)" in corpo
    assert "invio automatico ANNULLATO" in corpo


# --- audio muto: guadagno d'ingresso abbassato vs stream morto (gemello Mac) ---
# Caso 01/08/2026: su Mac il volume d'ingresso di sistema e' sceso da solo a
# 36/100 e l'app e' diventata muta senza diagnosi. Stessa rete su Windows.

def test_diagnosi_audio_muto_windows_riconosce_il_guadagno_abbassato():
    spazio = _funzioni_pure_app("diagnosi_audio_muto")
    causa, target = spazio["diagnosi_audio_muto"](0.0014, 36)
    assert causa == "guadagno_basso"
    assert target == spazio["GUADAGNO_INGRESSO_TARGET"]


def test_diagnosi_audio_muto_windows_col_guadagno_giusto_incolpa_lo_stream():
    spazio = _funzioni_pure_app("diagnosi_audio_muto")
    assert spazio["diagnosi_audio_muto"](0.0014, 75) == ("stream_muto", None)


def test_diagnosi_audio_muto_windows_senza_lettura_ricade_sullo_stream():
    spazio = _funzioni_pure_app("diagnosi_audio_muto")
    assert spazio["diagnosi_audio_muto"](0.0014, None) == ("stream_muto", None)


def test_diagnosi_audio_muto_windows_audio_sano_non_e_un_guasto():
    spazio = _funzioni_pure_app("diagnosi_audio_muto")
    assert spazio["diagnosi_audio_muto"](0.0128, 36) == ("ok", None)


def test_diagnosi_audio_muto_gemella_del_mac():
    """Le due app devono decidere allo stesso modo: regola di parita' Mac<->Windows."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(REPO_ROOT / "mac"))
    import voce_lib

    spazio = _funzioni_pure_app("diagnosi_audio_muto")
    assert spazio["GUADAGNO_INGRESSO_MINIMO"] == voce_lib.GUADAGNO_INGRESSO_MINIMO
    assert spazio["GUADAGNO_INGRESSO_TARGET"] == voce_lib.GUADAGNO_INGRESSO_TARGET
    for rms, guadagno in [(0.0014, 36), (0.0014, 75), (0.0014, None), (0.0128, 36)]:
        assert spazio["diagnosi_audio_muto"](rms, guadagno) == \
            voce_lib.diagnosi_audio_muto(rms, guadagno), (rms, guadagno)


def test_script_volume_ingresso_legge_e_scrive_la_percentuale():
    spazio = _funzioni_pure_app("script_volume_ingresso")
    lettura = spazio["script_volume_ingresso"]()
    assert "[Mic]::Set" not in lettura          # sola lettura: non tocca nulla
    assert "[Math]::Round([Mic]::Get()*100)" in lettura
    assert "eCapture" in lettura or "GetDefaultAudioEndpoint(1,1" in lettura

    scrittura = spazio["script_volume_ingresso"](75)
    assert "[Mic]::Set(0.75)" in scrittura
    assert scrittura.rstrip().endswith("[Math]::Round([Mic]::Get()*100)")  # rilegge sempre


def test_script_volume_ingresso_non_esce_dai_limiti():
    spazio = _funzioni_pure_app("script_volume_ingresso")
    assert "[Mic]::Set(1.0)" in spazio["script_volume_ingresso"](250)
    assert "[Mic]::Set(0.0)" in spazio["script_volume_ingresso"](-40)


def test_corsia_pulizia_windows_gemella_del_mac():
    """Pausa e ritorno devono decidere come sul Mac (regola di parita')."""
    import sys
    sys.path.insert(0, str(REPO_ROOT / "mac"))
    import voce_lib

    spazio = _funzioni_pure_app("corsia_utilizzabile", "registra_esito_corsia")
    assert spazio["SOGLIA_GUASTI_CORSIA"] == voce_lib.SOGLIA_GUASTI_CORSIA
    assert spazio["RIPOSO_CORSIA_SEC"] == voce_lib.RIPOSO_CORSIA_SEC
    casi = [(0, None, 1000), (1, 900, 1000), (2, 1000, 1000),
            (2, 1000, 1000 + voce_lib.RIPOSO_CORSIA_SEC)]
    for guasti, ultimo, ora in casi:
        assert spazio["corsia_utilizzabile"](guasti, ultimo, ora) == \
            voce_lib.corsia_utilizzabile(guasti, ultimo, ora), (guasti, ultimo, ora)
    assert spazio["registra_esito_corsia"](1, True, 500) == voce_lib.registra_esito_corsia(1, True, 500)
    assert spazio["registra_esito_corsia"](1, False, 500) == voce_lib.registra_esito_corsia(1, False, 500)


def test_guardia_pulizia_windows_gemella_del_mac():
    import sys
    sys.path.insert(0, str(REPO_ROOT / "mac"))
    import voce_lib

    spazio = _funzioni_pure_app("pulizia_inventa_nomi", "pulizia_sospetta")
    glossario = ["LeaderAI", "AI con Sal"]
    casi = [
        ("Apri OpenAI e controlla", "Apri LeaderAI e controlla"),
        ("scrivilo su leader ai", "Scrivilo su LeaderAI"),
        (
            "Questo messaggio contiene abbastanza parole per verificare che la pulizia non cancelli una parte importante del significato originale",
            "Questo messaggio verifica la pulizia",
        ),
    ]
    for grezzo, pulito in casi:
        assert spazio["pulizia_inventa_nomi"](grezzo, pulito, glossario) == \
            voce_lib.pulizia_inventa_nomi(grezzo, pulito, glossario)
        assert spazio["pulizia_sospetta"](grezzo, pulito, glossario) == \
            voce_lib.pulizia_sospetta(grezzo, pulito, glossario)


def test_tetto_anti_incanto_windows_gemello_del_mac():
    import sys
    sys.path.insert(0, str(REPO_ROOT / "mac"))
    import voce_lib
    win = _funzioni_pure_app("stop_anti_incanto")["stop_anti_incanto"]
    casi = [
        (True, 0.0, 91.0, True, 90.0, 300.0),    # tasto giu' oltre il soft: non ferma
        (True, 0.0, 91.0, False, 90.0, 300.0),   # tasto su oltre il soft: ferma
        (True, 0.0, 89.0, False, 90.0, 300.0),   # sotto il soft: non ferma
        (True, 0.0, 301.0, True, 90.0, 300.0),   # tasto incastrato oltre il duro: ferma
        (False, 0.0, 500.0, False, 90.0, 300.0),  # non registra
        (True, None, 500.0, False, 90.0, 300.0),  # senza inizio
    ]
    for caso in casi:
        assert win(*caso) is voce_lib.stop_anti_incanto(*caso), caso
    assert win(True, 0.0, 91.0, True, 90.0, 300.0) is False
    assert win(True, 0.0, 301.0, True, 90.0, 300.0) is True


def test_vk_del_tasto_windows_mappa_il_tasto_configurato():
    spazio = _funzioni_pure_app("vk_del_tasto")
    vk = spazio["vk_del_tasto"]
    assert vk("ctrl_r") == 0xA3
    assert vk("ctrl_l") == 0xA2
    assert vk("menu") == 0x5D
    assert vk("f8") == 0x77
    assert vk("tasto_inesistente") is None
    assert vk(None) is None
    cfg = json.loads((REPO_ROOT / "windows" / "config.json").read_text(encoding="utf-8"))
    assert vk(cfg["hotkey"]) is not None  # il tasto-detta di prodotto e' leggibile


def test_watchdog_windows_legge_il_tasto_fisico_in_modo_portabile():
    sorgente = (REPO_ROOT / "windows" / "voice_dettatura_windows.py").read_text(encoding="utf-8")
    corpo = sorgente.split("def watchdog", 1)[1].split("\ndef ", 1)[0]
    assert "stop_anti_incanto(" in corpo
    assert "MAX_RECORDING_TASTO_SEC" in corpo
    assert 'CFG.get("max_registrazione_tasto_sec", 300)' in sorgente
    lettura = sorgente.split("def tasto_detta_giu", 1)[1].split("\ndef ", 1)[0]
    assert "GetAsyncKeyState" in lettura
    assert 'getattr(ctypes, "windll", None)' in lettura  # importabile anche su Mac


def test_percorso_interattivo_windows_non_chiama_un_agente():
    sorgente = (REPO_ROOT / "windows" / "voice_dettatura_windows.py").read_text(encoding="utf-8")
    corpo = sorgente.split("def transcribe_and_paste", 1)[1].split("\ndef ", 1)[0]
    assert "pulisci_con_agente" not in corpo
    assert "pulizia agente" not in corpo


def test_scegli_casella_e_rotazione_audio_gemelle_del_mac():
    import sys
    sys.path.insert(0, str(REPO_ROOT / "mac"))
    import voce_lib

    spazio = _funzioni_pure_app("scegli_casella", "file_audio_da_eliminare", "in_zona_scrittura")
    for caso in ((50, 0, 1000), (900, 0, 1000), (-45, -100, 100), (-20, -100, 100)):
        assert spazio["in_zona_scrittura"](*caso) == voce_lib.in_zona_scrittura(*caso)
    casi_caselle = [[], [(100, 500), (700, 300)], [(700, 200), (700, 600)]]
    for candidati in casi_caselle:
        assert spazio["scegli_casella"](candidati) == voce_lib.scegli_casella(candidati)
    nomi = ["a.wav", "b.wav", "c.wav"]
    for massimo in (0, 2, 10):
        assert spazio["file_audio_da_eliminare"](nomi, massimo) == \
            voce_lib.file_audio_da_eliminare(nomi, massimo)


def test_cursore_automatico_windows_non_blocca_mai_l_incolla():
    sorgente = (REPO_ROOT / "windows" / "voice_dettatura_windows.py").read_text(encoding="utf-8")
    corpo = sorgente.split("def metti_cursore_in_casella", 1)[1].split("\ndef ", 1)[0]
    # tutto il lavoro UI Automation sta dentro un try: un intoppo non deve
    # mai impedire l'incolla (comportamento di prima)
    assert "try:" in corpo
    assert "except Exception:" in corpo


def _cursore_automatico_windows():
    """Carica metti_cursore_in_casella di Windows con UI Automation finta
    (gemella di _cursore_automatico_mac). chiama(passate, focus_dopo_attesa, focus):
    passate = caselle trovate da FindAll a ogni giro (None = nessuna)."""
    import sys
    sys.path.insert(0, str(REPO_ROOT / "mac"))
    import voce_lib

    stato = SimpleNamespace(attese=[], giri=[], click=[], salvataggi=[], focus=False, focus_dopo_attesa=False,
                            passate=[None], finestra=(0, 33, 1512, 982), casella_a_fuoco=(100, 900, 1400, 960))

    def rett(left, top, right, bottom):
        return SimpleNamespace(left=left, top=top, right=right, bottom=bottom)

    class Trovate:
        def __init__(self, elementi):
            self.elementi, self.Length = elementi, len(elementi)

        def GetElement(self, i):
            return self.elementi[i]

    def find_all(scope, condizione):
        stato.giri.append(scope)
        esito = stato.passate[min(len(stato.giri) - 1, len(stato.passate) - 1)]
        if esito is None:
            return Trovate([])
        left, top, right, bottom = esito
        return Trovate([SimpleNamespace(CurrentBoundingRectangle=rett(left, top, right, bottom), SetFocus=lambda: None)])

    def radice():
        left, top, right, bottom = stato.finestra
        return SimpleNamespace(FindAll=find_all, CurrentBoundingRectangle=rett(left, top, right, bottom))

    def a_fuoco():
        if not stato.focus:
            return None
        left, top, right, bottom = stato.casella_a_fuoco
        return SimpleNamespace(CurrentControlType=50004, CurrentBoundingRectangle=rett(left, top, right, bottom))

    uia = SimpleNamespace(
        GetFocusedElement=a_fuoco, ElementFromHandle=lambda hwnd: radice(),
        CreateOrCondition=lambda a, b: "oppure", CreatePropertyCondition=lambda p, v: "condizione",
    )

    def dormi(secondi):
        stato.attese.append(secondi)
        if stato.focus_dopo_attesa:
            stato.focus = True

    spazio = dict(
        CFG={"cursore_automatico": True}, _client_uia=lambda: uia, logging=logging,
        nome_finestra=lambda hwnd: "Claude", _click_sintetico=lambda x, y: stato.click.append((x, y)),
        _salva_caselle_ricordate=lambda: stato.salvataggi.append(dict(spazio["_caselle_ricordate"])),
        _UIA_EDIT=50004, _UIA_DOCUMENT=50030, _UIA_PROP_CONTROLTYPE=30003, _UIA_SCOPE_DISCENDENTI=4,
        casella_ammissibile=voce_lib.casella_ammissibile, scegli_casella=voce_lib.scegli_casella,
        time=SimpleNamespace(sleep=dormi),
    )
    path = REPO_ROOT / "windows" / "voice_dettatura_windows.py"
    nodi = [
        n for n in ast.parse(path.read_text(encoding="utf-8")).body
        if (isinstance(n, ast.FunctionDef)
            and n.name in ("metti_cursore_in_casella", "_geo_rett", "_ricorda_casella", "_punto_ricordato",
                           "chiave_casella", "posizione_relativa", "punto_da_relativa"))
        or (isinstance(n, ast.Assign)
            and any(getattr(t, "id", "") in ("ATTESA_RISVEGLIO_SEC", "GIRI_RISVEGLIO", "_caselle_ricordate")
                    for t in n.targets))
    ]
    exec(compile(ast.Module(body=nodi, type_ignores=[]), str(path), "exec"), spazio)

    def chiama(passate, focus_dopo_attesa=False, focus=False):
        stato.passate, stato.focus_dopo_attesa, stato.focus = passate, focus_dopo_attesa, focus
        stato.attese, stato.giri, stato.click = [], [], []
        return spazio["metti_cursore_in_casella"](12345)

    stato.chiama = chiama
    stato.attesa = spazio["ATTESA_RISVEGLIO_SEC"]
    stato.giri_massimi = spazio["GIRI_RISVEGLIO"]
    stato.memoria = spazio["_caselle_ricordate"]
    return stato


def test_cursore_automatico_windows_riprova_quando_l_albero_e_addormentato():
    s = _cursore_automatico_windows()
    assert s.chiama([None], focus_dopo_attesa=True) is True
    assert s.attesa in s.attese and s.attesa <= 0.5
    assert len(s.giri) == 1 and s.click == []


def test_cursore_automatico_windows_al_secondo_giro_trova_la_casella():
    s = _cursore_automatico_windows()
    casella = (100, 800, 1400, 860)  # left, top, right, bottom: in fondo alla finestra
    assert s.chiama([None, casella]) is True
    assert s.attese.count(s.attesa) == 1 and len(s.giri) == 2


def test_cursore_automatico_windows_dopo_tutti_i_giri_senza_memoria_dice_che_caselle_non_ce_ne_sono():
    s = _cursore_automatico_windows()
    assert s.chiama([None]) is False
    assert s.giri_massimi == 5 and len(s.giri) == s.giri_massimi
    assert s.attese.count(s.attesa) == s.giri_massimi - 1 and s.click == []


def test_cursore_automatico_windows_non_aspetta_se_la_casella_c_e_subito():
    s = _cursore_automatico_windows()
    casella = (100, 800, 1400, 860)
    assert s.chiama([casella]) is True
    assert s.attesa not in s.attese and len(s.giri) == 1


def test_cursore_automatico_windows_ricorda_la_casella_e_ci_clicca_quando_la_finestra_dorme():
    s = _cursore_automatico_windows()
    assert s.chiama([None], focus=True) is True
    assert ("Claude", 1512, 949) in s.memoria
    assert s.chiama([None]) is True
    assert len(s.giri) == s.giri_massimi and len(s.click) == 1
    x, y = s.click[0]
    assert 100 <= x <= 200 and 900 <= y <= 960


def test_cursore_automatico_windows_la_memoria_vale_solo_per_la_stessa_finestra():
    s = _cursore_automatico_windows()
    assert s.chiama([(100, 800, 1400, 860)]) is True
    s.finestra = (0, 33, 1000, 733)
    assert s.chiama([None]) is False and s.click == []


def test_sveglia_accessibilita_windows_gemella_del_mac():
    sorgente = (REPO_ROOT / "windows" / "voice_dettatura_windows.py").read_text(encoding="utf-8")
    corpo = sorgente.split("def start_recording", 1)[1].split("\ndef ", 1)[0]
    assert "threading.Thread(target=_sveglia_accessibilita" in corpo and "daemon=True" in corpo
    corpo = sorgente.split("def _sveglia_accessibilita", 1)[1].split("\ndef ", 1)[0]
    assert "CoInitialize" in corpo and "FindAll" in corpo and "except Exception:" in corpo
    # comportamento con UI Automation finta: tocca l'albero solo se il focus non e' gia' in una casella
    cercate = []
    radice = SimpleNamespace(FindAll=lambda scope, cond: cercate.append(scope) or SimpleNamespace(Length=0))
    focus = {"casella": False}
    uia = SimpleNamespace(
        GetFocusedElement=lambda: SimpleNamespace(CurrentControlType=50004) if focus["casella"] else None,
        ElementFromHandle=lambda hwnd: radice,
        CreateOrCondition=lambda a, b: "oppure", CreatePropertyCondition=lambda p, v: "condizione",
    )
    spazio = dict(CFG={"cursore_automatico": True}, _client_uia=lambda: uia, logging=logging,
                  _UIA_EDIT=50004, _UIA_DOCUMENT=50030, _UIA_PROP_CONTROLTYPE=30003, _UIA_SCOPE_DISCENDENTI=4)
    path = REPO_ROOT / "windows" / "voice_dettatura_windows.py"
    nodi = [n for n in ast.parse(path.read_text(encoding="utf-8")).body
            if isinstance(n, ast.FunctionDef) and n.name == "_sveglia_accessibilita"]
    exec(compile(ast.Module(body=nodi, type_ignores=[]), str(path), "exec"), spazio)
    spazio["_sveglia_accessibilita"](12345)
    assert cercate == [4]
    focus["casella"] = True
    spazio["_sveglia_accessibilita"](12345)
    assert cercate == [4]
    spazio["_sveglia_accessibilita"](0)
    assert cercate == [4]


def test_memoria_caselle_windows_salvata_a_ogni_novita():
    s = _cursore_automatico_windows()
    assert s.chiama([(100, 800, 1400, 860)]) is True
    assert len(s.salvataggi) == 1 and ("Claude", 1512, 949) in s.salvataggi[0]
    assert s.chiama([(100, 800, 1400, 860)]) is True  # stessa posizione: niente riscrittura
    assert len(s.salvataggi) == 1


def test_memoria_caselle_json_windows_gemella_del_mac():
    import json
    import sys
    sys.path.insert(0, str(REPO_ROOT / "mac"))
    import voce_lib

    path = REPO_ROOT / "windows" / "voice_dettatura_windows.py"
    nodi = [n for n in ast.parse(path.read_text(encoding="utf-8")).body
            if isinstance(n, ast.FunctionDef) and n.name in ("caselle_in_json", "caselle_da_json")]
    spazio = {"json": json}
    exec(compile(ast.Module(body=nodi, type_ignores=[]), str(path), "exec"), spazio)
    memoria = {("Claude", 1512, 949): (0.09, 42.0)}
    testo = spazio["caselle_in_json"](memoria)
    assert testo == voce_lib.caselle_in_json(memoria)
    assert spazio["caselle_da_json"](testo) == voce_lib.caselle_da_json(testo) == memoria
    assert spazio["caselle_da_json"]("{rotto") == {}


def test_memoria_caselle_windows_gemella_del_mac():
    import sys
    sys.path.insert(0, str(REPO_ROOT / "mac"))
    import voce_lib

    spazio = _funzioni_pure_app("chiave_casella", "posizione_relativa", "punto_da_relativa")
    finestra, casella = (0, 33, 1512, 949), (100, 900, 1300, 60)
    relativa = spazio["posizione_relativa"](finestra, casella)
    assert relativa == voce_lib.posizione_relativa(finestra, casella)
    assert spazio["punto_da_relativa"](finestra, relativa) == voce_lib.punto_da_relativa(finestra, relativa)
    assert spazio["chiave_casella"]("Claude", finestra) == voce_lib.chiave_casella("Claude", finestra)


def test_rimuovi_eco_glossario_gemella_del_mac():
    import sys
    sys.path.insert(0, str(REPO_ROOT / "mac"))
    import voce_lib

    spazio = _funzioni_pure_app("rimuovi_eco_glossario")
    glossario = ["Claude Code", "LeaderAI"]
    casi = [
        "Glossario, mi arrendo.",
        "Glossario: Claude Code, LeaderAI. Ciao a te.",
        "Glossario: LeaderAI.",
        "Aggiungi al glossario la parola LeaderAI",
        "Glossario aggiornato bene",
        "Mi arrendo.",
    ]
    for testo in casi:
        assert spazio["rimuovi_eco_glossario"](testo, glossario) == \
            voce_lib.rimuovi_eco_glossario(testo, glossario), testo


def test_lettura_doppia_windows_gemella_del_mac(tmp_path, monkeypatch):
    """Il doppio evento di fine risposta si scarta anche su Windows."""
    monkeypatch.setattr(voce_windows, "ULTIMA_LETTURA", tmp_path / "ULTIMA_LETTURA")

    assert voce_windows.gia_letto_da_poco("stessa risposta") is False
    assert voce_windows.gia_letto_da_poco("stessa risposta") is True
    assert voce_windows.gia_letto_da_poco("risposta diversa") is False


def test_windows_origine_usa_la_sessione_senza_fondere_task_nella_stessa_cartella():
    origine = voce_windows.origine_risposta
    dati = {"session_id": "sessione-a", "cwd": r"C:\Lavoro\Cliente",
            "transcript_path": r"C:\Utente\.codex\sessions\uno.jsonl"}
    a = origine(dati)
    b = origine({**dati, "session_id": "sessione-b"})
    assert a["id"] != b["id"]
    assert a == origine(dati)
    assert a["nome"] == "ChatGPT"
    assert origine({"cwd": "C:/Lavoro/Cliente"})["id"] != origine({"cwd": "C:/Lavoro/Cliente"})["id"]


def test_windows_doppioni_sono_distinti_per_conversazione(tmp_path, monkeypatch):
    monkeypatch.setattr(voce_windows, "ULTIMA_LETTURA", tmp_path / "ULTIMA_LETTURA")
    a, b = {"id": "a", "nome": "Claude A"}, {"id": "b", "nome": "Claude B"}
    assert voce_windows.gia_letto_da_poco("Stessa risposta", a) is False
    assert voce_windows.gia_letto_da_poco("Stessa risposta", b) is False
    assert voce_windows.gia_letto_da_poco("Stessa risposta", a) is True


def test_windows_hook_porta_i_metadati_fino_alla_coda(tmp_path, monkeypatch):
    from io import StringIO

    _isola_coda_windows(tmp_path, monkeypatch)
    attiva = tmp_path / "VOICE_ON"
    attiva.touch()
    monkeypatch.setattr(voce_windows, "FLAG_VOICE_ON", attiva)
    monkeypatch.setattr(voce_windows, "ULTIMA_LETTURA", tmp_path / "ULTIMA_LETTURA")
    for identita in ("a", "b", "a"):
        dati = {"session_id": identita, "last_assistant_message": "Risposta identica",
                "cwd": r"C:\Lavoro\Cliente", "model": "modello", "turn_id": "turno"}
        monkeypatch.setattr(voce_windows.sys, "stdin", StringIO(json.dumps(dati)))
        voce_windows.main()

    prima = voce_windows.prendi_pendente(con_origine=True)
    seconda = voce_windows.prendi_pendente(con_origine=True)
    assert prima == {"id": "a", "nome": "ChatGPT", "testo": "Risposta identica"}
    assert seconda == {"id": "b", "nome": "ChatGPT", "testo": "Risposta identica"}
    assert voce_windows.prendi_pendente() is None


def test_attesa_windows_vince_l_ultima(tmp_path):
    pendente = tmp_path / "LETTURA_PENDENTE"
    voce_windows.scrivi_pendente("risposta vecchia", pendente)
    voce_windows.scrivi_pendente("risposta nuova", pendente)

    assert voce_windows.prendi_pendente(pendente) == "risposta nuova"
    assert voce_windows.prendi_pendente(pendente) is None


def test_lettore_windows_legge_in_fila_e_pulisce(tmp_path, monkeypatch):
    """La lettura in corso si finisce sempre (attendi=True), poi si passa a
    cio' che e' arrivato nel frattempo; alla fine il lock sparisce."""
    pendente = tmp_path / "LETTURA_PENDENTE"
    lette = []

    def parla_finta(testo, voice_name=None, attendi=False, tetto_sec=None):
        assert attendi is True       # mai fire-and-forget dentro il lettore
        assert tetto_sec >= 60       # una voce incantata non tiene il lock per sempre
        lette.append(testo)
        if testo == "prima":
            voce_windows.scrivi_pendente("arrivata durante", pendente)

    monkeypatch.setattr(voce_windows, "LETTURA_PENDENTE", pendente)
    monkeypatch.setattr(voce_windows, "LETTORE_LOCK", tmp_path / "LETTORE_LOCK")
    monkeypatch.setattr(voce_windows, "parla", parla_finta)
    voce_windows.scrivi_pendente("prima", pendente)

    voce_windows.lettore()

    assert lette == ["prima", "arrivata durante"]
    assert voce_windows._lettore_in_corsa() is False  # lock rilasciato


def test_metti_in_lettura_windows_non_avvia_un_secondo_lettore(tmp_path, monkeypatch):
    pendente = tmp_path / "LETTURA_PENDENTE"
    avvii = []
    monkeypatch.setattr(voce_windows, "LETTURA_PENDENTE", pendente)
    monkeypatch.setattr(voce_windows, "_lettore_in_corsa", lambda: True)
    monkeypatch.setattr(voce_windows.subprocess, "Popen", lambda *a, **k: avvii.append(a))

    voce_windows.metti_in_lettura("testo da leggere")

    assert voce_windows.prendi_pendente(pendente) == "testo da leggere"
    assert avvii == []  # il lettore vivo passera' da solo al nuovo testo


def test_windows_scartata_se_arriva_mentre_sal_sta_dettando(tmp_path, monkeypatch):
    pendente = tmp_path / "LETTURA_PENDENTE"
    turno_utente = tmp_path / "TURNO_UTENTE"
    turno_utente.touch()
    avvii = []
    monkeypatch.setattr(voce_windows, "LETTURA_PENDENTE", pendente)
    monkeypatch.setattr(voce_windows, "FLAG_TURNO_UTENTE", turno_utente, raising=False)
    monkeypatch.setattr(voce_windows, "_avvia_lettore_se_serve", lambda: avvii.append(True))

    voce_windows.metti_in_lettura("Risposta del turno precedente")

    assert voce_windows.prendi_pendente(pendente) is None
    assert avvii == []


def test_lettore_windows_non_parte_se_sal_inizia_a_dettare_dopo_la_coda(tmp_path, monkeypatch):
    lette = []
    turno_utente = tmp_path / "TURNO_UTENTE"
    monkeypatch.setattr(voce_windows, "LETTURA_PENDENTE", tmp_path / "LETTURA_PENDENTE")
    monkeypatch.setattr(voce_windows, "LETTORE_LOCK", tmp_path / "LETTORE_LOCK")
    monkeypatch.setattr(voce_windows, "FLAG_TURNO_UTENTE", turno_utente, raising=False)
    monkeypatch.setattr(voce_windows, "parla", lambda testo, **kwargs: lette.append(testo))
    voce_windows.scrivi_pendente("Risposta gia' accodata")
    turno_utente.touch()

    voce_windows.lettore()

    assert lette == []
    assert voce_windows.prendi_pendente() is None


def _isola_coda_windows(tmp_path, monkeypatch):
    monkeypatch.setattr(voce_windows, "LETTURA_PENDENTE", tmp_path / "LETTURA_PENDENTE")
    monkeypatch.setattr(voce_windows, "LETTORE_LOCK", tmp_path / "LETTORE_LOCK")
    avvii = []
    monkeypatch.setattr(voce_windows.subprocess, "Popen", lambda *a, **k: avvii.append(a))
    return avvii


def test_windows_coda_tiene_separate_le_conversazioni(tmp_path, monkeypatch):
    _isola_coda_windows(tmp_path, monkeypatch)
    prima = {"id": "sessione-a", "nome": "Claude · Cliente A"}
    seconda = {"id": "sessione-b", "nome": "Codex · Cliente B"}
    voce_windows.scrivi_pendente("A vecchia", origine=prima)
    voce_windows.scrivi_pendente("B da conservare", origine=seconda)
    voce_windows.scrivi_pendente("A aggiornata", origine=prima)

    assert voce_windows.prendi_pendente(con_origine=True) == {**prima, "testo": "A aggiornata"}
    assert voce_windows.prendi_pendente(con_origine=True) == {**seconda, "testo": "B da conservare"}
    assert voce_windows.ha_pendenti() is False


def test_windows_preferita_legge_solo_quella_e_conserva_le_altre(tmp_path, monkeypatch):
    _isola_coda_windows(tmp_path, monkeypatch)
    voce_windows.scrivi_pendente("Risposta A", origine={"id": "a", "nome": "Claude A"})
    voce_windows.scrivi_pendente("Risposta B", origine={"id": "b", "nome": "Codex B"})

    assert voce_windows.scegli_conversazione("b") is True
    assert voce_windows.prendi_pendente() == "Risposta B"
    assert voce_windows.ha_pendenti() is False  # A resta in attesa della scelta
    elenco = voce_windows.elenco_conversazioni()
    assert elenco["preferita"] == "b"
    assert {c["id"]: c["in_attesa"] for c in elenco["conversazioni"]} == {"a": True, "b": False}

    assert voce_windows.scegli_conversazione(None) is True
    assert voce_windows.prendi_pendente() == "Risposta A"
    assert voce_windows.scegli_conversazione("inesistente") is False


def test_windows_stop_conserva_ultima_risposta_per_rilettura(tmp_path, monkeypatch):
    avvii = _isola_coda_windows(tmp_path, monkeypatch)
    assert voce_windows.rileggi_ultima() is False
    origine = {"id": "a", "nome": "Claude A"}
    voce_windows.scrivi_pendente("Risposta già iniziata", origine=origine)
    assert voce_windows.prendi_pendente() == "Risposta già iniziata"
    voce_windows.scrivi_pendente("Altra risposta in attesa", origine={"id": "b", "nome": "Codex B"})

    voce_windows.svuota_pendenti()

    assert voce_windows.ha_pendenti() is False
    assert voce_windows.elenco_conversazioni()["rileggibile"] is True
    assert voce_windows.rileggi_ultima() is True
    assert len(avvii) == 1
    assert voce_windows.prendi_pendente(con_origine=True) == {**origine, "testo": "Risposta già iniziata"}
    assert voce_windows.ha_pendenti() is False


def test_windows_rileggi_rispetta_la_conversazione_scelta(tmp_path, monkeypatch):
    _isola_coda_windows(tmp_path, monkeypatch)
    voce_windows.scrivi_pendente("Risposta A", origine={"id": "a", "nome": "Claude A"})
    assert voce_windows.prendi_pendente() == "Risposta A"
    voce_windows.scrivi_pendente("Risposta B", origine={"id": "b", "nome": "Codex B"})
    assert voce_windows.prendi_pendente() == "Risposta B"

    assert voce_windows.scegli_conversazione("a") is True
    assert voce_windows.rileggi_ultima() is True
    assert voce_windows.prendi_pendente() == "Risposta A"


def test_windows_rilettura_non_duplica_la_stessa_risposta_ancora_in_attesa(tmp_path, monkeypatch):
    _isola_coda_windows(tmp_path, monkeypatch)
    voce_windows.scrivi_pendente("Da rileggere", origine={"id": "a", "nome": "Claude A"})
    assert voce_windows.scegli_conversazione("a") is True
    assert voce_windows.rileggi_ultima() is True
    assert voce_windows.prendi_pendente() == "Da rileggere"
    assert voce_windows.prendi_pendente() is None


def test_windows_annuncio_sistema_non_diventa_conversazione_ne_sostituisce_replay(tmp_path, monkeypatch):
    _isola_coda_windows(tmp_path, monkeypatch)
    voce_windows.scrivi_pendente("Risposta vera", origine={"id": "a", "nome": "Claude A"})
    assert voce_windows.prendi_pendente() == "Risposta vera"
    assert voce_windows.scegli_conversazione("a") is True
    voce_windows.scrivi_pendente("Voce AI accesa")
    assert voce_windows.prendi_pendente() == "Voce AI accesa"
    assert [c["id"] for c in voce_windows.elenco_conversazioni()["conversazioni"]] == ["a"]
    assert voce_windows.scegli_conversazione(None) is True
    assert voce_windows.rileggi_ultima() is True
    assert voce_windows.prendi_pendente() == "Risposta vera"


def test_windows_lettore_annuncia_i_cambi_di_conversazione_senza_id(tmp_path, monkeypatch):
    _isola_coda_windows(tmp_path, monkeypatch)
    lette = []
    voce_windows.scrivi_pendente(
        "Prima risposta", origine={"id": "id-privato-a", "nome": "Claude · Cliente A"},
    )
    voce_windows.scrivi_pendente(
        "Seconda risposta", origine={"id": "id-privato-b", "nome": "Codex · Cliente B"},
    )

    def parla_finta(testo, voice_name=None, attendi=False, tetto_sec=None):
        assert attendi is True
        lette.append(testo)

    monkeypatch.setattr(voce_windows, "parla", parla_finta)
    voce_windows.lettore()

    assert len(lette) == 2
    assert "Claude · Cliente A" in lette[0] and lette[0].endswith("Prima risposta")
    assert "Codex · Cliente B" in lette[1] and lette[1].endswith("Seconda risposta")
    assert "id-privato" not in " ".join(lette)
    assert voce_windows._lettore_in_corsa() is False


def test_windows_ferma_svuota_solo_attesa_e_conserva_replay(tmp_path, monkeypatch):
    _isola_coda_windows(tmp_path, monkeypatch)
    voce_windows.scrivi_pendente("Risposta interrotta", origine={"id": "a", "nome": "Claude A"})
    assert voce_windows.prendi_pendente() == "Risposta interrotta"
    voce_windows.scrivi_pendente("Risposta in coda", origine={"id": "a", "nome": "Claude A"})
    spazio = _funzioni_pure_app("ferma_voce")
    spazio.update(
        voce_agenti=voce_windows,
        PID_FILE=tmp_path / "voce_pid", logging=logging,
    )

    spazio["ferma_voce"]()  # senza PID c'e' comunque una coda da svuotare

    assert voce_windows.ha_pendenti() is False
    assert voce_windows.rileggi_ultima() is True
    assert voce_windows.prendi_pendente() == "Risposta interrotta"


def test_windows_rilettura_durante_stop_riparte_col_lettore_superstite(tmp_path, monkeypatch):
    """Lo stop termina PowerShell, non il lettore: il replay arriva prima
    che PowerShell finisca e viene preso al giro successivo, una volta sola."""
    _isola_coda_windows(tmp_path, monkeypatch)
    pid_file = tmp_path / "voce_pid"
    monkeypatch.setattr(voce_windows, "PID_FILE", pid_file)
    monkeypatch.setattr(voce_windows, "CFG_PATH", tmp_path / "config.json")
    testi, terminati = [], []
    spazio = _funzioni_pure_app("ferma_voce")
    spazio.update(
        voce_agenti=voce_windows, PID_FILE=pid_file, logging=logging,
        subprocess=voce_windows.subprocess,
    )

    class Processo:
        def __init__(self, numero):
            self.numero, self.pid = numero, 8000 + numero
            self.stdin = SimpleNamespace(write=self.ricevi, close=lambda: None)

        def ricevi(self, dati):
            testi.append(dati.decode("utf-8"))

        def wait(self, timeout=None):
            if self.numero == 1:
                spazio["ferma_voce"]()
                assert voce_windows.rileggi_ultima() is True
            return 0

    processi = []

    def avvia(comando, **kwargs):
        assert comando[0] == "powershell"  # il lettore esistente resta l'unico
        processo = Processo(len(processi) + 1)
        processi.append(processo)
        return processo

    monkeypatch.setattr(voce_windows.subprocess, "Popen", avvia)
    monkeypatch.setattr(voce_windows.subprocess, "run", lambda cmd, **kwargs: terminati.append(cmd))
    voce_windows.scrivi_pendente("Risposta interrotta", origine={"id": "a", "nome": "Claude A"})

    voce_windows.lettore()

    assert terminati == [["taskkill", "/PID", "8001", "/T", "/F"]]
    assert len(testi) == 2
    assert testi[0].endswith("Risposta interrotta")
    assert testi[1] == "Risposta interrotta"
    assert not pid_file.exists()
    assert voce_windows.ha_pendenti() is False


def test_windows_toggle_e_rilettura_usano_lo_stesso_lettore_senza_audio_sovrapposto(tmp_path, monkeypatch):
    """Il toggle prima partiva fuori lock: Rileggi avviava una seconda voce
    mentre la prima era viva, poi cancellava il PID necessario a fermarla."""
    _isola_coda_windows(tmp_path, monkeypatch)
    pid_file = tmp_path / "voce_pid"
    monkeypatch.setattr(voce_windows, "PID_FILE", pid_file)
    monkeypatch.setattr(voce_windows, "CFG_PATH", tmp_path / "config.json")
    spazio = _funzioni_pure_app("pronuncia", "ferma_voce", "pulisci_per_voce", "_ps_voce", "_ps_string")
    spazio.update(
        voce_agenti=voce_windows, PID_FILE=pid_file, logging=logging,
        subprocess=voce_windows.subprocess, VOCE_RATE=0, VOCE_NOME="",
    )
    vivi, avvii_audio, testi = set(), [], []

    class Processo:
        def __init__(self, pid):
            self.pid = pid
            self.stdin = SimpleNamespace(
                write=lambda dati: testi.append(dati.decode("utf-8")), close=lambda: None,
            )

        def wait(self, timeout=None):
            vivi.discard(self.pid)
            return 0

    def avvia(comando, **kwargs):
        if comando[0] != "powershell":
            assert comando[-1] == "--lettore"
            return SimpleNamespace(pid=9000)  # avvio child simulato, eseguito sotto
        pid = 5000 + len(avvii_audio)
        avvii_audio.append((pid, sorted(vivi)))
        vivi.add(pid)
        return Processo(pid)

    def termina(comando, **kwargs):
        assert comando[:2] == ["taskkill", "/PID"]
        vivi.discard(int(comando[2]))

    monkeypatch.setattr(voce_windows.subprocess, "Popen", avvia)
    monkeypatch.setattr(voce_windows.subprocess, "run", termina)
    voce_windows.scrivi_pendente("Risposta A", origine={"id": "a", "nome": "Claude A"})
    assert voce_windows.prendi_pendente() == "Risposta A"

    spazio["pronuncia"]("Voce AI accesa. Le risposte sono audio sintetico.")
    assert voce_windows.rileggi_ultima() is True
    voce_windows.lettore()

    assert len(avvii_audio) == 2
    assert all(not altri for _, altri in avvii_audio), avvii_audio
    assert vivi == set()
    assert not pid_file.exists()
    assert any("Voce AI accesa" in testo for testo in testi)
    assert any("Risposta A" in testo for testo in testi)
    assert voce_windows.rileggi_ultima() is True
    assert voce_windows.prendi_pendente() == "Risposta A"  # toggle non sovrascrive recupero


def test_punteggiatura_dettata_windows_gemella_del_mac():
    spazio = _funzioni_pure_app("converti_punteggiatura_dettata")
    f = spazio["converti_punteggiatura_dettata"]

    assert f("Domani si parte punto esclamativo") == "Domani si parte!"
    assert f("Hai capito punto interrogativo") == "Hai capito?"
    assert f("prima riga a capo seconda riga") == "prima riga\nSeconda riga"
    assert f("Il punto esclamativo non me lo becca") == "Il punto esclamativo non me lo becca"
    assert f("Non ne vengo a capo") == "Non ne vengo a capo"


def test_ripasso_windows_gemello_del_mac():
    spazio = _funzioni_pure_app(
        "estrai_grezzi_con_orario", "abbina_audio_a_grezzo", "disaccordi_parole")
    grezzi = spazio["estrai_grezzi_con_orario"](
        ["2026-08-30 14:19:32,192 INFO grezzo: Dalle colle è emerso questo."])
    assert spazio["abbina_audio_a_grezzo"](
        "dettatura_20260830_141931.wav", grezzi) == "Dalle colle è emerso questo."
    assert spazio["disaccordi_parole"](
        "Dalle colle è emerso questo.", "Dalle call è emerso questo."
    ) == [("colle", "call")]


def test_risposta_arbitro_windows_gemella_del_mac():
    spazio = _funzioni_pure_app("estrai_json", "risposta_arbitro")
    spazio["json"] = json  # estrai_json ne ha bisogno: nel modulo vero c'e' gia'
    f = spazio["risposta_arbitro"]
    proposte, errore = f(1, "Failed to authenticate: OAuth session expired\n")
    assert proposte == {} and "codice 1" in errore and "OAuth" in errore
    proposte, errore = f(0, "Non posso rispondere.")
    assert proposte == {} and "senza JSON" in errore
    assert f(0, 'Ecco: {"colle": "call"}') == ({"colle": "call"}, None)
    assert f(0, "{}") == ({}, None)


def _apprendimento_windows(tmp_path, proposte):
    """Esegue le funzioni vere senza avviare app, microfono o agenti."""
    spazio = _funzioni_pure_app(
        "estrai_grezzi_dal_log", "unisci_sostituzioni", "estrai_json",
        "risposta_arbitro", "_catena_arbitri", "chiedi_arbitro",
        "prompt_apprendimento", "impara_sostituzioni",
        "impara_dagli_errori_giornaliero", "estrai_grezzi_con_orario",
        "abbina_audio_a_grezzo", "disaccordi_parole", "prompt_arbitro_ripasso",
        "ripassa_audio_conservati", "glossario_iniziale", "rimuovi_eco_glossario",
        "applica_sostituzioni", "converti_punteggiatura_dettata",
    )
    cfg = {
        "sostituzioni": {"leader ai": "LeaderAI"},
        "debug_dettature": True,
        "conserva_audio_n": 0,
    }
    config = tmp_path / "config.json"
    config.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    log = tmp_path / "voce.log"
    log.write_text(
        "2026-09-05 10:00:01,000 INFO grezzo: "
        "vi mando il documento al cliente con consegna programmata\n",
        encoding="utf-8",
    )
    chiamate = []

    def run(comando, **kwargs):
        chiamate.append(comando)
        return SimpleNamespace(returncode=0, stdout=json.dumps(proposte), stderr="")

    spazio.update(
        Path=Path, json=json, logging=logging, time=time,
        subprocess=SimpleNamespace(run=run), CFG=cfg,
        BASE=tmp_path, LOG=log, COMANDO_APPRENDIMENTO=["arbitro-di-prova"],
    )
    return spazio, config, log, chiamate


def test_windows_apprendimento_propone_senza_modificare_config_o_memoria(tmp_path, caplog):
    proposte = {"vi": "mi", "al": "il", "programmata": "programmato"}
    spazio, config, log, chiamate = _apprendimento_windows(tmp_path, proposte)
    prima = config.read_bytes()
    cfg_prima = json.loads(prima)

    with caplog.at_level(logging.INFO):
        risultato = spazio["impara_sostituzioni"](log, config, ["arbitro-di-prova"])

    assert len(chiamate) == 1  # l'arbitro propone ancora
    assert risultato == proposte
    assert config.read_bytes() == prima
    assert spazio["CFG"] == cfg_prima
    assert "proposte da verificare, non applicate" in caplog.text
    assert json.dumps(proposte, ensure_ascii=False) in caplog.text
    assert spazio["applica_sostituzioni"](
        "Vi mando il documento al cliente", spazio["CFG"]["sostituzioni"]
    ) == "Vi mando il documento al cliente"


def test_windows_avvio_giornaliero_non_attiva_le_proposte(tmp_path, caplog):
    proposte = {"vi": "mi", "al": "il", "programmata": "programmato"}
    spazio, config, _, chiamate = _apprendimento_windows(tmp_path, proposte)
    prima = config.read_bytes()
    cfg_prima = json.loads(prima)

    with caplog.at_level(logging.INFO):
        spazio["impara_dagli_errori_giornaliero"]()

    assert len(chiamate) == 1
    assert (tmp_path / "APPRENDIMENTO_ULTIMO").read_text() == time.strftime("%Y-%m-%d")
    assert (config.read_bytes(), spazio["CFG"]) == (prima, cfg_prima)
    assert "proposte da verificare, non applicate" in caplog.text
    assert "imparate sostituzioni" not in caplog.text


def test_windows_ripasso_propone_senza_modificare_config_o_memoria(tmp_path, caplog):
    proposte = {"vi": "mi", "al": "il", "programmata": "programmato"}
    spazio, config, log, chiamate = _apprendimento_windows(tmp_path, proposte)
    prima = config.read_bytes()
    cfg_prima = json.loads(prima)
    wav = tmp_path / "dettatura_20260905_100000.wav"
    wav.write_bytes(b"audio passato soltanto al modello simulato")
    audio_letti = []

    class Modello:
        def __init__(self, nome, **kwargs):
            assert nome == "modello-di-prova"

        def transcribe(self, percorso, **kwargs):
            audio_letti.append(percorso)
            return [SimpleNamespace(
                text="mi mando il documento il cliente con consegna programmato"
            )], None

    spazio["WhisperModel"] = Modello
    with caplog.at_level(logging.INFO):
        risultato = spazio["ripassa_audio_conservati"](
            tmp_path, [log], config, ["arbitro-di-prova"], "modello-di-prova"
        )

    assert audio_letti == [str(wav)]
    assert len(chiamate) == 1
    assert risultato == proposte
    assert config.read_bytes() == prima
    assert spazio["CFG"] == cfg_prima
    assert "proposte da verificare, non applicate" in caplog.text
    assert json.dumps(proposte, ensure_ascii=False) in caplog.text
    assert "imparate" not in caplog.text


def test_windows_proposte_accettano_solo_coppie_di_stringhe_valide():
    unisci = _funzioni_pure_app("unisci_sostituzioni")["unisci_sostituzioni"]
    assert unisci({"Leader AI": "LeaderAI"}, {
        "leader ai": "altro", "numero": 42, "lista": ["call"],
        "oggetto": {"parola": "call"}, "vuota": "  ", "": "call",
        42: "call", "identica": "IDENTICA", "troppo lunga": "x" * 41,
        "  clawde  ": "  Claude  ",
    }) == {"clawde": "Claude"}


def test_casella_ammissibile_windows_gemella_del_mac():
    spazio = _funzioni_pure_app("in_zona_scrittura", "casella_ammissibile")
    f = spazio["casella_ammissibile"]
    assert f(700, 40, 0, 800) is True    # chat in fondo
    assert f(60, 700, 0, 800) is True    # documento a tutta finestra
    assert f(40, 28, 0, 800) is False    # barra degli indirizzi


# --- trascrizione progressiva (gemella Mac, 04/09/2026) ---

def _blocchi_windows(*tratti):
    rms, campioni = [], []
    for secondi, volume in tratti:
        for _ in range(int(round(secondi * 40))):
            rms.append(volume)
            campioni.append(400)
    return rms, campioni


def test_windows_trova_taglio_solo_su_pausa_dopo_i_12_secondi():
    trova_taglio = _funzioni_pure_app("trova_taglio")["trova_taglio"]
    rms, campioni = _blocchi_windows((5, 0.02), (1, 0.005), (5, 0.02))
    assert trova_taglio(rms, campioni, 0) is None
    rms, campioni = _blocchi_windows((13, 0.02), (1, 0.005), (13, 0.02), (1, 0.005))
    primo = trova_taglio(rms, campioni, 0)
    assert primo == 13 * 40 + 20
    assert trova_taglio(rms, campioni, primo) == primo + 20 + 13 * 40 + 20
    rms, campioni = _blocchi_windows((14, 0.02), (0.2, 0.005), (10, 0.02))
    assert trova_taglio(rms, campioni, 0) is None  # micro-pause: mai a meta' parola


def test_windows_unisci_segmenti_come_il_mac():
    unisci = _funzioni_pure_app("unisci_segmenti")["unisci_segmenti"]
    assert unisci(["Ciao a tutti.", "  oggi parliamo di voce.  "]) == "Ciao a tutti. Oggi parliamo di voce."
    assert unisci(["Prima frase.", ". seconda frase"]) == "Prima frase. Seconda frase"
    assert unisci(["prima parola", ", e poi"]) == "prima parola, e poi"
    assert unisci(["stavo dicendo che", "Il cliente vuole"], ["LeaderAI"]) == "stavo dicendo che il cliente vuole"
    assert unisci(["lo faccio con", "LeaderAI e basta"], ["LeaderAI"]) == "lo faccio con LeaderAI e basta"
    assert unisci(["mando il", "PDF domani"]) == "mando il PDF domani"
    assert unisci(["usa", "Claude Code per questo"], ["Claude Code"]) == "usa Claude Code per questo"
    assert unisci([]) == ""


def test_windows_prompt_con_contesto_come_il_mac():
    prompt_con_contesto = _funzioni_pure_app("prompt_con_contesto")["prompt_con_contesto"]
    glossario = "Glossario: LeaderAI, Codex."
    assert prompt_con_contesto(glossario, "") == glossario
    assert prompt_con_contesto(None, "") is None
    lungo = " ".join(f"parola{i}" for i in range(80))
    prompt = prompt_con_contesto(glossario, lungo)
    assert prompt.startswith(glossario + " parola")
    assert len(prompt) - len(glossario) - 1 <= 200
    assert prompt.endswith("parola79")


def test_windows_progressiva_specchia_il_runtime_mac():
    sorgente = (REPO_ROOT / "windows" / "voice_dettatura_windows.py").read_text(encoding="utf-8")
    for frase in (
        'CFG.get("trascrizione_progressiva", False)',
        'CFG.get("trascrizione_progressiva_blocco_sec", 12)',
        "class SessioneProgressiva",
        "_lock_trascrizione = threading.Lock()",
        "rms_blocks.append(rms)",
        "sessione_progressiva = SessioneProgressiva(blocks, rms_blocks)",
        "text = _trascrivi_con_sessione(audio, sessione)",
        "sessione.thread.join(timeout=120)",
    ):
        assert frase in sorgente, frase
    # la pill dice "trascrivo" solo al rilascio: mai dal thread di sottofondo
    inizio = sorgente.index("class SessioneProgressiva")
    fine = sorgente.index("def _trascrivi_con_sessione")
    assert 'eventi.put("trascrivo")' not in sorgente[inizio:fine]


def test_catena_arbitri_windows_gemella_del_mac():
    """Claude poi Codex, il primo che risponde vince: stesso contratto del Mac."""
    codice = (REPO_ROOT / "windows" / "voice_dettatura_windows.py").read_text(encoding="utf-8")
    assert "def comandi_agente() -> list:" in codice
    assert "def chiedi_arbitro(comando, prompt: str, timeout: int = 60) -> tuple:" in codice
    assert 'comandi.append(["codex", "exec", "--skip-git-repo-check"])' in codice
    # apprendimento e ripasso passano dalla catena, non da un agente solo
    assert codice.count("chiedi_arbitro(comando, prompt_") == 2
    assert "COMANDO_APPRENDIMENTO = comandi_agente()" in codice
    spazio = _funzioni_pure_app("_catena_arbitri")
    catena = spazio["_catena_arbitri"]
    assert catena(["claude", "-p"]) == [["claude", "-p"]]
    assert catena([["claude"], ["codex"]]) == [["claude"], ["codex"]]
    assert catena(None) == [] and catena([]) == []


# --- Pill: logo "LeaderAI." con il punto verde vivo, gemello Mac (23/09/2026) ---

def _crescita_punto():
    import math
    path = REPO_ROOT / "windows" / "voice_dettatura_windows.py"
    albero = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    nodo = next(n for n in albero.body if isinstance(n, ast.FunctionDef) and n.name == "crescita_punto")
    spazio = {"math": math}
    exec(compile(ast.Module(body=[nodo], type_ignores=[]), str(path), "exec"), spazio)
    return spazio["crescita_punto"]


def test_punto_leaderai_si_accende_segue_la_voce_e_pulsa():
    crescita = _crescita_punto()
    assert crescita("ascolto", 0.0, 0.0, 0.0) < -0.5          # compare piccolo...
    assert crescita("ascolto", 0.0, 0.0, 0.19) > 0.5          # ...scatta...
    assert crescita("ascolto", 0.0, 0.0, 0.5) == 0.0          # ...e si posa
    assert abs(crescita("ascolto", 0.05, 0.0, 1.0) - 0.75) < 1e-9   # voce forte: cresce
    assert crescita("ascolto", 1.0, 0.0, 1.0) == 0.9          # con un tetto
    battito = [crescita("trascrivo", 0.0, t / 10, 1.0) for t in range(11)]
    assert battito[0] < 0.01 and abs(battito[5] - 0.7) < 1e-9 and battito[10] < 0.01
    assert crescita("sistemo", 0.0, 0.5, 1.0) == battito[5]
    assert crescita("nascosto", 0.05, 0.5, 1.0) == 0.0


def _marchio_su_canvas(brand, crescita, firma=1.0):
    """Disegna il logo con il metodo vero della pill Windows su un canvas Tk."""
    import tkinter as tk
    import tkinter.font as tkfont
    path = REPO_ROOT / "windows" / "voice_dettatura_windows.py"
    albero = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    classe = next(n for n in albero.body if isinstance(n, ast.ClassDef) and n.name == "Pannello")
    metodo = next(n for n in classe.body if isinstance(n, ast.FunctionDef) and n.name == "_marchio")
    spazio = {"BRAND": brand, "LARGHEZZA": 300, "VERDE_FIRMA": "#56C842",
              "ALONE_PUNTO": ("#1F3A1B", "#2E5A27")}
    exec(compile(ast.Module(body=[metodo], type_ignores=[]), str(path), "exec"), spazio)
    root = tk.Tk()
    try:
        canvas = tk.Canvas(root, width=300, height=72)
        font = tkfont.Font(root=root, family="Segoe UI", size=12, weight="bold")
        spazio["_marchio"](SimpleNamespace(canvas=canvas, font_marchio=font), crescita, firma)
        oggetti = [(canvas.type(i), canvas.coords(i), canvas.itemcget(i, "text") if canvas.type(i) == "text" else None,
                    canvas.bbox(i)) for i in canvas.find_all()]
        return oggetti
    finally:
        root.destroy()


def test_pill_windows_logo_leaderai_col_punto_sulla_riga():
    config = json.loads((REPO_ROOT / "windows" / "config.json").read_text(encoding="utf-8"))
    assert config["brand"] == "LeaderAI."
    oggetti = _marchio_su_canvas(config["brand"], 0.0)
    testo = [o for o in oggetti if o[0] == "text"]
    punti = [o for o in oggetti if o[0] == "oval"]
    assert [t[2] for t in testo] == ["LeaderAI"] and len(punti) == 1   # a riposo: niente alone
    x1, y1, x2, y2 = punti[0][1]
    assert abs(y2 - 21) < 0.01                        # il punto poggia sulla linea di base
    sinistra = testo[0][3][0]
    assert abs((sinistra + x2) / 2 - 150) < 3         # logo centrato nella pill
    firme = [o for o in oggetti if o[0] == "rectangle"]
    assert len(firme) == 1                            # la firma verde sotto il marchio
    fx1, fy1, fx2, fy2 = firme[0][1]
    assert fy1 > 21 and fy2 < 30                      # sotto la linea di base, sopra le lineette
    assert abs(fx1 - sinistra) < 3 and fx2 < x1       # parte col testo, finisce prima del punto
    assert not [o for o in _marchio_su_canvas(config["brand"], 0.0, 0.0) if o[0] == "rectangle"]
    acceso = _marchio_su_canvas(config["brand"], 0.8)
    assert len([o for o in acceso if o[0] == "oval"]) == 3   # voce: punto piu' grande con la sua luce


def test_pill_windows_marchio_senza_punto_finale_resta_testo():
    oggetti = _marchio_su_canvas("Studio Rossi", 0.5)
    assert [o[2] for o in oggetti if o[0] == "text"] == ["Studio Rossi"]
    assert not [o for o in oggetti if o[0] == "oval"]


def test_firma_windows_si_disegna_con_la_curva_del_sito():
    path = REPO_ROOT / "windows" / "voice_dettatura_windows.py"
    albero = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    nodo = next(n for n in albero.body if isinstance(n, ast.FunctionDef) and n.name == "disegno_firma")
    spazio = {}
    exec(compile(ast.Module(body=[nodo], type_ignores=[]), str(path), "exec"), spazio)
    disegno = spazio["disegno_firma"]
    passi = [disegno(t / 100) for t in range(0, 101, 5)]
    assert passi[0] == 0.0 and disegno(0.375) == 0.5 and disegno(0.75) == 1.0 and disegno(3.0) == 1.0
    assert all(a <= b for a, b in zip(passi, passi[1:]))   # cresce sempre, da sinistra a destra
