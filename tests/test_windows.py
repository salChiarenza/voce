import ast
import importlib.util
import json
import logging
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "windows" / "voce_hook.py"
SPEC = importlib.util.spec_from_file_location("voce_windows_hook", MODULE_PATH)
voce_windows = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(voce_windows)


@pytest.fixture(autouse=True)
def _gancio_nella_cartella_temporanea(tmp_path, monkeypatch):
    """Il gancio scrive `LETTI_DAL_REGISTRO` nella sua cartella: mai in quella della repo,
    dove un file rimasto da una prova farebbe tacere la prova dopo."""
    casa = tmp_path / "casa-gancio"
    casa.mkdir()
    monkeypatch.setattr(voce_windows, "BASE", casa)


def _funzioni_pure_app(*nomi, **extra):
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
                                  "SOGLIA_GUASTI_CORSIA", "RIPOSO_CORSIA_SEC", "_VK_TASTI",
                                  "_RIFERIMENTI_AL_VIDEO", "_CORTESIE_DI_CHIUSURA",
                                  "_CONNETTIVI_DI_CHIUSURA", "_RE_FORMULE_DI_CHIUSURA",
                                  "SECONDO_PASSAGGIO_MIN_SEC", "SECONDO_PASSAGGIO_ENERGIA")
                for target in nodo.targets
            )
        )
    ]
    spazio = {"re": re, **extra}
    exec(compile(ast.Module(body=nodi, type_ignores=[]), str(path), "exec"), spazio)
    return spazio


@pytest.mark.parametrize('debug', [False, True])
def test_log_windows_whisper_e_correzioni_distinti_solo_debug(debug, caplog, tmp_path):
    """Output originale del motore e testo corretto sono due stadi diversi."""
    import numpy as np
    consegne = []
    class Motore:
        def transcribe(self, audio, **kw):
            return iter([SimpleNamespace(text='Apri cloud code.')]), SimpleNamespace(language='it')
    spazio = _funzioni_pure_app(
        '_whisper_grezzo', 'transcribe_and_paste',
        np=np, logging=logging, BASE=tmp_path, SAMPLE_RATE=16000,
        CFG={'debug_dettature': debug, 'sostituzioni': {'cloud code': 'Claude Code'}},
        load_model=lambda: Motore(), salva_audio_recente=lambda *a, **kw: None,
        e_allucinazione=lambda t: False,
        applica_sostituzioni=_funzioni_pure_app('applica_sostituzioni')['applica_sostituzioni'],
        converti_punteggiatura_dettata=_funzioni_pure_app('converti_punteggiatura_dettata')['converti_punteggiatura_dettata'],
        destinazione_agente=lambda nome: True, nome_finestra=lambda hwnd: 'ChatGPT',
        _concludi_dettatura=lambda *a: consegne.append(a),
        # 31/10/2026: orecchio spento (Whisper come prima), dettatura non buttata con Esc
        ORECCHIO=None, coda_dettature=SimpleNamespace(annullato=lambda token: False),
        ultime_dettature=SimpleNamespace(pezzo=lambda *a: None),
    )
    spazio['_trascrivi_con_sessione'] = lambda audio, sessione: spazio['_whisper_grezzo'](audio, None)
    with caplog.at_level(logging.INFO):
        spazio['transcribe_and_paste'](np.full(16000, 0.04, dtype='float32'), 42, token_turno='turno')
    assert consegne == [('turno', 'Apri Claude Code.', 42, False)]
    if debug:
        assert 'whisper originale: Apri cloud code.' in caplog.text
        assert 'postcorrezioni: Apri Claude Code.' in caplog.text
        assert 'grezzo: Apri Claude Code.' not in caplog.text
    else:
        assert 'cloud code' not in caplog.text and 'Claude Code' not in caplog.text


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
        ("Apri [report.md](/Users/utente/cliente/report.md:12) e `C:\\Lavoro\\Cliente\\dati.csv`.",
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
        "_normalizza", "_ripetizione_patologica", "_solo_formule_di_chiusura",
        "e_allucinazione",
    )
    e_allucinazione = funzioni["e_allucinazione"]

    assert e_allucinazione("Grazie.") is True
    assert e_allucinazione(("Pier " * 200).strip()) is True
    assert e_allucinazione("Ecologia" + "版" * 200) is True
    assert e_allucinazione("Grazie mille per la proposta, la rivediamo.") is False


FRASE_INVENTATA_28_09 = (
    "Grazie a tutti per aver guardato il video, vi ringrazio per avermi seguito, "
    "e vi ringrazio per avermi seguito."
)


def _e_allucinazione_windows():
    return _funzioni_pure_app(
        "_normalizza", "_ripetizione_patologica", "_solo_formule_di_chiusura",
        "e_allucinazione",
    )["e_allucinazione"]


def test_windows_riconosce_la_frase_inventata_del_28_09_e_le_sue_varianti():
    """P-117, gemella del Mac: la rete confronta i pezzi, non solo l'intera stringa."""
    e_allucinazione = _e_allucinazione_windows()
    assert e_allucinazione(FRASE_INVENTATA_28_09) is True
    for f in [
        "Grazie mille per la visione, ci vediamo al prossimo video, ciao a tutti.",
        "Iscrivetevi al canale e alla prossima.",
        "grazie per averci seguito e ci vediamo nel prossimo video",
        "VI RINGRAZIO PER AVERMI SEGUITO!",
        "Grazie a tutti. Grazie a tutti. Grazie a tutti.",
        "Thank you. Thank you. Thank you.",
    ]:
        assert e_allucinazione(f) is True, f


def test_windows_non_scarta_frasi_vere_che_contengono_le_formule():
    e_allucinazione = _e_allucinazione_windows()
    for f in [
        "Grazie a tutti per aver guardato il video che ti ho mandato ieri, fammi sapere cosa ne pensi.",
        "Ti ringrazio per avermi seguito nel progetto, ora passiamo alla seconda fase del lavoro.",
        "Alla prossima riunione porta i numeri del cliente.",
        "Ciao a tutti, oggi parliamo del nuovo listino.",
        "Ci vediamo domani alle nove in ufficio.",
        "Grazie mille, a presto.",
        "Perfetto, grazie. Ci vediamo alla prossima.",
        "Grazie, grazie!",
        "Grazie a tutti. Grazie a tutti.",
    ]:
        assert e_allucinazione(f) is False, f


def _audio_sintetico_windows(secondi, rms):
    import numpy as np

    a = np.random.default_rng(0).standard_normal(int(secondi * 16000)).astype("float32")
    return a * (rms / float(np.sqrt(np.mean(a * a))))


def _passaggio_unico_windows(passaggi, glossario="Glossario: Claude Code."):
    """`_passaggio_unico` dell'app Windows con Whisper finto (le soglie del
    secondo passaggio e `has_voice` sono quelle vere del sorgente)."""
    import numpy as np

    prompt_usati = []
    risposte = iter(passaggi)

    def whisper(audio, prompt=None):
        prompt_usati.append(prompt)
        return next(risposte)

    spazio = _funzioni_pure_app(
        "_normalizza", "_ripetizione_patologica", "_solo_formule_di_chiusura",
        "e_allucinazione", "has_voice", "_passaggio_unico",
        _whisper_grezzo=whisper, rimuovi_eco_glossario=lambda testo, g=(): testo,
        GLOSSARIO_PROMPT=glossario, CFG={"glossario": []}, logging=logging,
        np=np, VOICE_THRESHOLD=0.004, SAMPLE_RATE=16000,
    )
    return spazio["_passaggio_unico"], prompt_usati


def test_windows_riprova_senza_glossario_se_esce_un_fantasma_su_parlato_vero():
    """P-117, gemella del Mac: secondo passaggio senza glossario, una volta, e solo su un parlato."""
    parlato = _audio_sintetico_windows(12.3, 0.052)
    vero = "anche perche' non mi ricordo veramente che dobbiamo fare, vedete"
    passaggio, prompt = _passaggio_unico_windows([FRASE_INVENTATA_28_09, vero])
    assert passaggio(parlato) == vero
    assert prompt == ["Glossario: Claude Code.", None]

    passaggio, prompt = _passaggio_unico_windows(["Apri il file e correggi la funzione."])
    assert passaggio(parlato) == "Apri il file e correggi la funzione."
    assert len(prompt) == 1
    for audio in (_audio_sintetico_windows(1.0, 0.15), _audio_sintetico_windows(8.0, 0.01)):  # colpo, fruscio
        passaggio, prompt = _passaggio_unico_windows(["Grazie."])
        assert passaggio(audio) == "Grazie."
        assert len(prompt) == 1
    for secondi, rms, riprova in ((3.0, 0.021, True), (2.9, 0.05, False), (3.0, 0.019, False)):
        passaggio, prompt = _passaggio_unico_windows([FRASE_INVENTATA_28_09, "ok, vedo che funziona"])
        passaggio(_audio_sintetico_windows(secondi, rms))
        assert (len(prompt) == 2) is riprova, (secondi, rms)
    passaggio, prompt = _passaggio_unico_windows([FRASE_INVENTATA_28_09, "Grazie a tutti."])
    assert _e_allucinazione_windows()(passaggio(parlato)) is True  # ancora fantasma: lo scarta il chiamante
    assert len(prompt) == 2


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


def test_glossario_iniziale_gemella_del_mac():
    """Stesso prompt per Whisper sulle due app: l'elenco nudo dei nomi,
    senza l'etichetta «Glossario:» (banco Mac 11/10/2026)."""
    import sys
    sys.path.insert(0, str(REPO_ROOT / "mac"))
    import voce_lib

    spazio = _funzioni_pure_app("glossario_iniziale")
    for cfg in ({}, {"glossario": []}, {"glossario": ["LeaderAI", " ", "ChatGPT", "Claude Code"]}):
        assert spazio["glossario_iniziale"](cfg) == voce_lib.glossario_iniziale(cfg), cfg
    assert spazio["glossario_iniziale"]({"glossario": ["ChatGPT"]}) == "ChatGPT."


def test_il_glossario_passato_a_whisper_e_scritto_nel_registro_all_avvio_windows():
    """Gemella del Mac (11/10/2026): il registro dice quale glossario gira."""
    sorgente = (REPO_ROOT / 'windows' / 'voice_dettatura_windows.py').read_text(encoding='utf-8')
    corpo = sorgente[sorgente.index('def main() -> None:'):]
    riga = 'logging.getLogger("voce").info("glossario per Whisper: %d nomi: %s", len(CFG.get("glossario", [])), GLOSSARIO_PROMPT)'
    assert riga in corpo
    assert corpo.index('logging.basicConfig(') < corpo.index(riga) < corpo.index('target=load_model')


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
    monkeypatch.setattr(voce_windows, "LOG_GANCIO", tmp_path / "voice_hook.log")  # mai nella cartella della repo
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
    oggetti = _marchio_su_canvas("Studio Bianchi", 0.5)
    assert [o[2] for o in oggetti if o[0] == "text"] == ["Studio Bianchi"]
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


def test_pill_windows_trascrive_con_leaderai_grande_e_scritta_piccola():
    """Sal, 23/09/2026: «deve restare in risalto sempre LeaderAI, anche quando
    trascrivi; le altre scritte piu' piccoline»."""
    import tkinter as tk
    import tkinter.font as tkfont
    path = REPO_ROOT / "windows" / "voice_dettatura_windows.py"
    albero = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    classe = next(n for n in albero.body if isinstance(n, ast.ClassDef) and n.name == "Pannello")
    metodi = [n for n in classe.body if isinstance(n, ast.FunctionDef) and n.name in ("_marchio", "_disegna_trascrivo")]
    spazio = {"BRAND": "LeaderAI.", "LARGHEZZA": 300, "VERDE_FIRMA": "#56C842",
              "ALONE_PUNTO": ("#1F3A1B", "#2E5A27"), "time": time,
              "crescita_punto": lambda *a: 0.0}
    exec(compile(ast.Module(body=metodi, type_ignores=[]), str(path), "exec"), spazio)
    root = tk.Tk()
    try:
        canvas = tk.Canvas(root, width=300, height=72)
        pill = SimpleNamespace(
            canvas=canvas, stato="trascrivo", _pill=lambda: None,
            font_marchio=tkfont.Font(root=root, family="Segoe UI", size=12, weight="bold"),
            font_marchio_grande=tkfont.Font(root=root, family="Segoe UI", size=16, weight="bold"))
        pill._marchio = lambda *a, **k: spazio["_marchio"](pill, *a, **k)
        altezza = lambda i: canvas.bbox(i)[3] - canvas.bbox(i)[1]
        spazio["_marchio"](pill)                                   # mentre parli
        normale = next(i for i in canvas.find_all() if canvas.type(i) == "text")
        altezza_normale = altezza(normale)
        spazio["_disegna_trascrivo"](pill)                          # mentre trascrive
        testi = {canvas.itemcget(i, "text"): i for i in canvas.find_all() if canvas.type(i) == "text"}
        assert set(testi) == {"LeaderAI", "Trascrivo..."}
        assert altezza(testi["LeaderAI"]) > altezza_normale        # il marchio si ingrandisce
        assert altezza(testi["Trascrivo..."]) < 0.75 * altezza(testi["LeaderAI"])  # la scritta resta piccola
        assert canvas.bbox(testi["Trascrivo..."])[1] > canvas.bbox(testi["LeaderAI"])[3] - 2  # e sta sotto
    finally:
        root.destroy()


# --- P-088 su Windows: il modello tiene conto della memoria del PC (sul Mac e' la rc.30) ---

def test_windows_sceglie_il_modello_piccolo_su_un_pc_con_poca_memoria():
    scegli = _funzioni_pure_app("scegli_modello")["scegli_modello"]
    prodotto = json.loads((REPO_ROOT / "windows" / "config.json").read_text(encoding="utf-8"))
    assert prodotto["model_poca_memoria"] != prodotto["model"]
    soglia = prodotto["memoria_minima_modello_gb"]
    assert scegli(prodotto, 4.0)[0] == prodotto["model_poca_memoria"]
    assert scegli(prodotto, soglia - 0.1)[0] == prodotto["model_poca_memoria"]
    for memoria in (soglia, 8.0, 16.0, 32.0):
        assert scegli(prodotto, memoria) == (prodotto["model"], "standard")


def test_windows_modello_memoria_illeggibile_o_regola_spenta_resta_lo_standard():
    scegli = _funzioni_pure_app("scegli_modello")["scegli_modello"]
    base = {"model": "medium", "model_poca_memoria": "small", "memoria_minima_modello_gb": 6}
    assert scegli(base, None)[0] == "medium"
    assert scegli({**base, "memoria_minima_modello_gb": 0}, 2.0)[0] == "medium"
    assert scegli({"model": "medium"}, 2.0)[0] == "medium"          # config senza modello piccolo
    assert scegli({**base, "model_poca_memoria": "medium"}, 2.0)[0] == "medium"


def test_windows_legge_la_memoria_del_pc_o_non_la_sa():
    import ctypes
    from types import SimpleNamespace

    # fuori da Windows (ctypes.windll non esiste): non lo sa, e non si rompe
    assert _funzioni_pure_app("memoria_totale_gb", ctypes=ctypes)["memoria_totale_gb"]() is None

    def memoria_stato(ref):
        ref._obj.ullTotalPhys = 8 * 1024 ** 3
        return 1

    finto = SimpleNamespace(
        Structure=ctypes.Structure, c_ulong=ctypes.c_ulong, c_ulonglong=ctypes.c_ulonglong,
        sizeof=ctypes.sizeof, byref=ctypes.byref,
        windll=SimpleNamespace(kernel32=SimpleNamespace(GlobalMemoryStatusEx=memoria_stato)),
    )
    assert _funzioni_pure_app("memoria_totale_gb", ctypes=finto)["memoria_totale_gb"]() == 8.0


def test_windows_carica_il_modello_scelto_per_memoria():
    codice = (REPO_ROOT / "windows" / "voice_dettatura_windows.py").read_text(encoding="utf-8")
    assert "scegli_modello(CFG, memoria_totale_gb())" in codice
    assert 'WhisperModel(\n            nome,' in codice


# --- P-085 gemella del Mac: il tasto della voce conta solo se TENUTO ---

class _TimerFinto:
    """threading.Timer senza attesa: `scatta()` e' il tempo che passa."""
    creati = []

    def __init__(self, intervallo, funzione):
        self.intervallo, self.funzione = intervallo, funzione
        self.avviato = self.annullato = self.daemon = False
        _TimerFinto.creati.append(self)

    def start(self):
        self.avviato = True

    def cancel(self):
        self.annullato = True

    def scatta(self):
        if self.avviato and not self.annullato:
            self.funzione()


def _tasto_voce_windows():
    _TimerFinto.creati = []
    commutazioni = []
    spazio = _funzioni_pure_app(
        "on_press", "on_release", "_tasto_voce_premuto", "_tasto_voce_rilasciato",
        threading=SimpleNamespace(Timer=_TimerFinto),
        time=SimpleNamespace(monotonic=lambda: 1.0),
        commuta_voce=lambda: commutazioni.append("commutata"), VOCE_TENUTA_SEC=1.0,
        HOTKEY="ctrl_r", TASTO_VOCE="menu", key_down=False, voice_key_down=False,
        voce_timer=None, ultima_pressione_utente=0.0,
        coda_dettature=SimpleNamespace(interrompi_invio=lambda: None),
        commands=SimpleNamespace(put=lambda comando: None),
    )
    return spazio, commutazioni


def test_windows_un_tocco_sul_tasto_voce_non_commuta():
    spazio, commutazioni = _tasto_voce_windows()
    for _ in range(5):                       # cinque tocchi: nessuno commuta
        spazio["on_press"]("menu")
        spazio["on_release"]("menu")
    for timer in _TimerFinto.creati:
        timer.scatta()                       # anche lasciando passare il tempo dopo il rilascio
    assert commutazioni == []


def test_windows_il_tasto_voce_tenuto_commuta_una_volta_sola():
    spazio, commutazioni = _tasto_voce_windows()
    spazio["on_press"]("menu")
    for _ in range(4):                       # il tasto tenuto si ripete: non riparte il conto
        spazio["on_press"]("menu")
    assert len(_TimerFinto.creati) == 1
    assert _TimerFinto.creati[0].intervallo == 1.0
    _TimerFinto.creati[0].scatta()           # e' passato il secondo col tasto ancora giu'
    assert commutazioni == ["commutata"]
    spazio["on_release"]("menu")
    spazio["on_press"]("menu")               # un nuovo gesto tenuto commuta di nuovo
    _TimerFinto.creati[-1].scatta()
    assert commutazioni == ["commutata", "commutata"]


def test_windows_l_aggiornamento_porta_le_chiavi_nuove_e_conserva_le_scelte(tmp_path):
    """P-088 e P-085 arrivano ai clienti con l'aggiornamento: le chiavi nuove
    entrano, le scelte gia' fatte dal proprietario restano."""
    corrente = tmp_path / "config.json"
    corrente.write_text(json.dumps({"model": "large-v3", "voce_nome": "Microsoft Elsa"}), encoding="utf-8")
    voce_windows.unisci_config(str(REPO_ROOT / "windows" / "config.json"), str(corrente))
    unito = json.loads(corrente.read_text(encoding="utf-8"))
    assert unito["model"] == "large-v3" and unito["voce_nome"] == "Microsoft Elsa"
    assert unito["model_poca_memoria"] == "small" and unito["memoria_minima_modello_gb"] == 6
    assert unito["voce_tenuta_sec"] == 1.0


def test_windows_il_prodotto_chiede_la_tenuta_e_l_app_la_legge_da_config():
    codice = (REPO_ROOT / "windows" / "voice_dettatura_windows.py").read_text(encoding="utf-8")
    assert 'VOCE_TENUTA_SEC = max(0.5, float(CFG.get("voce_tenuta_sec", 1.0)))' in codice
    config = json.loads((REPO_ROOT / "windows" / "config.json").read_text(encoding="utf-8"))
    assert config["voce_tenuta_sec"] == 1.0 and config["tasto_voce"] == "menu"


# --- P-078 (22/09/2026): il gancio di fine turno di Windows non e' mai partito ---
# Il comando scritto in ~/.claude/settings.json aveva i percorsi con le barre
# rovesciate e senza virgolette (list2cmdline le mette solo se ci sono spazi);
# Claude Code su Windows lo lancia con Git Bash, che le toglie: 410 volte su
# 410 dal 28/07, e il controllo diceva «configurato» perche' il percorso nel
# file c'era. Ora Claude Code ha la forma senza shell, e il controllo AVVIA il
# comando.

PERCORSI_DI_WINDOWS = [
    r"C:\Users\mario\VoiceDettaturaWindows\.venv\Scripts\python.exe",       # caso del 22/09/2026, P-078
    r"C:\Users\Mario D'Aosta\App (x86)\$HOME\Voce\.venv\Scripts\python.exe",  # spazio, apostrofo, parentesi, dollaro
    r"\\server\condivisa\Voce\python.exe",                               # percorso di rete
]


def _gancio_scritto(settings):
    return json.loads(settings.read_text(encoding="utf-8"))["hooks"]["Stop"][-1]["hooks"][0]


def test_windows_git_bash_toglie_le_barre_rovesciate_della_vecchia_forma():
    """La causa, sulla macchina: un percorso di Windows senza virgolette passato
    a bash perde tutte le barre (Git Bash e' bash)."""
    if shutil.which("bash") is None:
        return  # senza bash non c'e' niente da mostrare
    vecchio = subprocess.list2cmdline([PERCORSI_DI_WINDOWS[0], r"C:\Users\mario\VoiceDettaturaWindows\voce_hook.py"])
    esito = subprocess.run(["bash", "-c", "printf '%s\\n' " + vecchio],
                           capture_output=True, text=True)
    assert "\\" not in esito.stdout
    assert esito.stdout.split()[0] == "C:UsersmarioVoiceDettaturaWindows.venvScriptspython.exe"


def test_windows_il_gancio_di_claude_code_non_passa_dalla_shell(tmp_path, monkeypatch):
    mio = str(Path(voce_windows.__file__).resolve())
    for numero, eseguibile in enumerate(PERCORSI_DI_WINDOWS):
        monkeypatch.setattr(voce_windows.sys, "executable", eseguibile)
        settings = tmp_path / f"settings{numero}.json"
        voce_windows.collega_hook(settings, diretto=True)
        gancio = _gancio_scritto(settings)
        assert gancio["type"] == "command"
        assert gancio["command"] == eseguibile, eseguibile        # il percorso arriva com'e'
        assert gancio["args"] == [mio]
        assert gancio["command"].count(" ") == eseguibile.count(" ")  # niente stringa di shell


def test_windows_l_aggiornamento_sostituisce_il_gancio_rotto_e_conserva_gli_altri(tmp_path):
    rotto = (r"C:\Users\mario\VoiceDettaturaWindows\.venv\Scripts\python.exe "
             r"C:\Users\mario\VoiceDettaturaWindows\voce_hook.py")
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"hooks": {"Stop": [
        {"hooks": [{"type": "command", "command": "echo esistente"}]},
        {"hooks": [{"type": "command", "command": rotto, "timeout": 10}]},
    ]}}), encoding="utf-8")
    for _ in range(2):                           # anche rilanciato: una voce sola
        voce_windows.collega_hook(settings, diretto=True)
        ganci = [h for g in json.loads(settings.read_text(encoding="utf-8"))["hooks"]["Stop"]
                 for h in g["hooks"]]
        nostri = [h for h in ganci if "voce_hook.py" in voce_windows._comando_completo(h)]
        assert len(nostri) == 1 and "args" in nostri[0] and nostri[0]["command"] != rotto
        assert {"type": "command", "command": "echo esistente"} in ganci
    assert settings.with_name("settings.json.pre-voce.bak").exists()


def test_windows_riconosce_il_proprio_gancio_in_tutte_e_due_le_forme(tmp_path):
    a_stringa, diretto, altro = tmp_path / "a.json", tmp_path / "b.json", tmp_path / "c.json"
    voce_windows.collega_hook(a_stringa)
    voce_windows.collega_hook(diretto, diretto=True)
    altro.write_text(json.dumps({"hooks": {"Stop": [
        {"hooks": [{"type": "command", "command": "echo altro"}]}]}}), encoding="utf-8")
    assert voce_windows.hook_collegato(a_stringa) is True
    assert voce_windows.hook_collegato(diretto) is True
    assert voce_windows.hook_collegato(altro) is False
    assert voce_windows.hook_collegato(tmp_path / "manca.json") is False


def test_windows_il_gancio_scritto_dall_installer_parte_davvero(tmp_path):
    settings = tmp_path / "settings.json"
    voce_windows.collega_hook(settings, diretto=True)    # interprete e script veri di questa macchina
    esito = voce_windows.prova_esecuzione_hook(
        voce_windows.trova_hook_voce(settings), diretto_richiesto=True)
    assert esito == (True, "ok")


def test_windows_la_prova_boccia_il_comando_che_non_parte_o_non_risponde():
    # caso del 22/09/2026, P-078: le barre tolte, quindi un eseguibile che non esiste
    rotto = {"type": "command", "args": ["x"],
             "command": "C:UsersmarioVoiceDettaturaWindows.venvScriptspython.exe"}
    ok, dettaglio = voce_windows.prova_esecuzione_hook(rotto)
    assert ok is False and "non parte" in dettaglio
    # su Windows un comando a stringa per Claude Code e' bocciato qualunque cosa dica la shell di prova
    a_stringa = {"type": "command", "command": voce_windows._comando_hook()}
    ok, dettaglio = voce_windows.prova_esecuzione_hook(a_stringa, diretto_richiesto=True)
    assert ok is False and "Git Bash" in dettaglio
    # parte ma non e' il nostro gancio (esce 0 senza il segnale), o muore: bocciato, col motivo
    muto = {"type": "command", "command": sys.executable, "args": ["-c", "pass"]}
    assert voce_windows.prova_esecuzione_hook(muto)[0] is False
    muore = {"type": "command", "command": sys.executable,
             "args": ["-c", "import sys; sys.stderr.write('boom\\n'); sys.exit(3)"]}
    ok, dettaglio = voce_windows.prova_esecuzione_hook(muore)
    assert ok is False and "codice 3" in dettaglio and "boom" in dettaglio


def _casa_finta(tmp_path, monkeypatch, agenti=("claude",), su_windows=True):
    monkeypatch.setattr(voce_windows.Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(voce_windows, "_agente_presente", lambda nome: nome in agenti)
    monkeypatch.setattr(voce_windows, "_su_windows", lambda: su_windows)
    (tmp_path / ".claude").mkdir(exist_ok=True)
    return tmp_path / ".claude" / "settings.json"


def test_windows_check_hooks_non_dice_piu_configurato_per_un_gancio_che_non_parte(
        tmp_path, monkeypatch, capsys):
    settings = _casa_finta(tmp_path, monkeypatch)
    # la forma vecchia, scritta dal vecchio installer: il percorso nel file c'e'
    settings.write_text(json.dumps({"hooks": {"Stop": [
        {"hooks": [{"type": "command", "command": voce_windows._comando_hook(), "timeout": 10}]}]}}),
        encoding="utf-8")
    assert voce_windows.hook_collegato(settings) is True          # «configurato»: lo era
    assert voce_windows.controlla_hook_agenti() is False          # ma NON funziona, e lo dice
    assert "NON FUNZIONA" in capsys.readouterr().out
    voce_windows.installa_hook_agenti()                           # la riparazione
    assert voce_windows.controlla_hook_agenti() is True
    assert "configurato e funzionante" in capsys.readouterr().out


def test_windows_check_hooks_senza_gancio_resta_non_configurato(tmp_path, monkeypatch, capsys):
    _casa_finta(tmp_path, monkeypatch)
    assert voce_windows.controlla_hook_agenti() is False
    assert "NON configurato" in capsys.readouterr().out


def test_windows_l_avviso_all_accensione_dice_cosa_non_va(tmp_path, monkeypatch):
    settings = _casa_finta(tmp_path, monkeypatch, agenti=("claude", "codex"))
    assert "nessun agente" in voce_windows.avviso_collegamento()   # niente collegato
    voce_windows.installa_hook_agenti()
    assert voce_windows.avviso_collegamento() == ""                # tutto parte
    # Claude Code torna alla forma rotta: l'avviso lo nomina e dice cosa significa
    settings.write_text(json.dumps({"hooks": {"Stop": [
        {"hooks": [{"type": "command", "command": voce_windows._comando_hook()}]}]}}),
        encoding="utf-8")
    avviso = voce_windows.avviso_collegamento()
    assert "Claude Code" in avviso and "non funziona" in avviso and "non verranno lette" in avviso
    assert "Codex" not in avviso                                   # l'altro e' a posto


def test_windows_il_gancio_lascia_una_riga_a_ogni_chiamata(tmp_path, monkeypatch):
    from io import StringIO

    _isola_coda_windows(tmp_path, monkeypatch)
    log = tmp_path / "voice_hook.log"
    monkeypatch.setattr(voce_windows, "FLAG_VOICE_ON", tmp_path / "VOICE_ON")
    monkeypatch.setattr(voce_windows, "ULTIMA_LETTURA", tmp_path / "ULTIMA_LETTURA")
    voce_windows.main()                                            # voce spenta
    (tmp_path / "VOICE_ON").touch()
    monkeypatch.setattr(voce_windows.sys, "stdin", StringIO("non e' json"))
    voce_windows.main()                                            # voce accesa, dati rotti
    dati = {"session_id": "s", "last_assistant_message": "Risposta da leggere"}
    monkeypatch.setattr(voce_windows.sys, "stdin", StringIO(json.dumps(dati)))
    voce_windows.main()                                            # una risposta vera
    monkeypatch.setattr(voce_windows.sys, "stdin", StringIO(json.dumps(dati)))
    voce_windows.main()                                            # lo stesso evento due volte
    monkeypatch.setattr(voce_windows.sys, "stdin", StringIO(json.dumps({"session_id": "s"})))
    voce_windows.main()                                            # niente da leggere
    righe = log.read_text(encoding="utf-8").splitlines()
    assert [r.split("voce agenti: ")[1] for r in righe] == [
        "voce spenta, non leggo", "chiamata senza dati leggibili",
        "leggo 19 caratteri (messaggio diretto)",
        "lettura doppia scartata (19 caratteri, messaggio diretto)",
        "nessun testo da leggere (messaggio diretto)",
    ]


def test_windows_il_registro_del_gancio_non_cresce_senza_fine(tmp_path, monkeypatch):
    log = tmp_path / "voice_hook.log"
    monkeypatch.setattr(voce_windows, "LOG_GANCIO", log)
    monkeypatch.setattr(voce_windows, "TETTO_LOG_GANCIO", 2000)
    for numero in range(200):
        voce_windows.traccia(f"riga numero {numero}")
    assert log.stat().st_size < 4000
    assert log.read_text(encoding="utf-8").splitlines()[-1].endswith("riga numero 199")


def _commuta_voce_windows(tmp_path, avviso, voce_agenti_presente=True):
    """`commuta_voce` dell'app Windows con tutto finto: torna cosa dice a voce."""
    dette = []
    flag = tmp_path / "VOICE_ON"
    agenti = SimpleNamespace(avviso_collegamento=avviso) if voce_agenti_presente else None
    spazio = _funzioni_pure_app(
        "commuta_voce", "_avviso_collegamento", FLAG_VOICE_ON=flag, voce_agenti=agenti,
        pronuncia=dette.append, logging=logging,
    )
    return spazio["commuta_voce"], dette, flag


def test_windows_accendendo_la_voce_avverte_se_il_collegamento_non_funziona(tmp_path):
    attesa = "Voce AI accesa. Le risposte dell'agente sono audio sintetico."
    guasto = "Attenzione: il collegamento con Claude Code non funziona, le risposte non verranno lette."
    commuta, dette, flag = _commuta_voce_windows(tmp_path, lambda: guasto)
    commuta()
    assert dette == [attesa + " " + guasto] and flag.exists()      # una frase sola: la precedente si ferma
    commuta()
    assert dette[-1] == "Voce AI spenta" and not flag.exists()     # spegnendo non c'e' niente da controllare
    # collegamento sano, controllo che si rompe, app senza il modulo: l'annuncio di sempre
    for avviso, presente in ((lambda: "", True), (lambda: 1 / 0, True), (lambda: "x", False)):
        commuta, dette, flag = _commuta_voce_windows(tmp_path, avviso, presente)
        commuta()
        assert dette == [attesa]
        flag.unlink()


def test_windows_claude_code_troppo_vecchio_per_la_forma_senza_shell_non_passa(
        tmp_path, monkeypatch, capsys):
    """Una Claude Code che non conosce `args` lancerebbe `command` da solo con
    la shell: il comando parte nella nostra prova e non nella sua. Stesso
    silenzio di prima, quindi il controllo dice «aggiornala»."""
    _casa_finta(tmp_path, monkeypatch)
    voce_windows.installa_hook_agenti()
    capsys.readouterr()
    for versione, atteso in (((2, 1, 138), False), ((2, 1, 139), True), ((2, 1, 286), True),
                             ((3, 0, 0), True), (None, True)):   # None: non si legge, non si boccia
        monkeypatch.setattr(voce_windows, "versione_claude_code", lambda v=versione: v)
        assert voce_windows.controlla_hook_agenti() is atteso, versione
        uscita = capsys.readouterr().out
        assert ("non conosce il collegamento senza shell" in uscita) is (not atteso), versione


def test_windows_la_versione_di_claude_code_si_legge_da_claude_version(monkeypatch):
    monkeypatch.setattr(voce_windows.shutil, "which", lambda nome: r"C:\Users\mario\.local\bin\claude.exe")
    for uscita, atteso in (("2.1.286 (Claude Code)\n", (2, 1, 286)), ("boh", None), ("", None)):
        monkeypatch.setattr(
            voce_windows.subprocess, "run",
            lambda *a, _u=uscita, **k: SimpleNamespace(stdout=_u, stderr="", returncode=0))
        assert voce_windows.versione_claude_code() == atteso, uscita
    monkeypatch.setattr(voce_windows.shutil, "which", lambda nome: None)    # non nel PATH
    assert voce_windows.versione_claude_code() is None

    def non_parte(*a, **k):
        raise OSError("no")

    monkeypatch.setattr(voce_windows.shutil, "which", lambda nome: "claude")
    monkeypatch.setattr(voce_windows.subprocess, "run", non_parte)
    assert voce_windows.versione_claude_code() is None


# --- Voce insieme alla scrittura e controllo di consegna (02/10/2026, gemella del Mac) ---

def _iso_w(epoch):
    from datetime import datetime, timezone
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat().replace("+00:00", "Z")


def _funzioni_pure_app_con_costanti():
    path = REPO_ROOT / "windows" / "voice_dettatura_windows.py"
    albero = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    nomi = {"cartella_registri_claude", "_compatta", "chiave_consegna", "_istante_riga",
            "_testo_inviato_da_utente", "messaggio_in_registri", "verifica_consegna"}
    costanti = {"CHIAVE_CONSEGNA_CARATTERI", "CODA_REGISTRO_BYTE", "RIGA_MASSIMA_BYTE"}
    nodi = [n for n in albero.body
            if (isinstance(n, ast.FunctionDef) and n.name in nomi)
            or (isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id in costanti for t in n.targets))]
    spazio = {"json": json, "os": __import__("os"), "time": time, "Path": Path}
    exec(compile(ast.Module(body=nodi, type_ignores=[]), str(path), "exec"), spazio)
    return spazio


def _registro_w(tmp_path, righe, nome="sessione-1"):
    cartella = tmp_path / "progetti" / "-C-Users-sal-casa"
    cartella.mkdir(parents=True, exist_ok=True)
    (cartella / f"{nome}.jsonl").write_text("\n".join(righe) + "\n", encoding="utf-8")
    return tmp_path / "progetti"


def test_windows_consegna_si_riconosce_nel_registro_solo_se_scritto_dopo(tmp_path):
    f = _funzioni_pure_app_con_costanti()
    ora = time.time()
    progetti = _registro_w(tmp_path, [
        json.dumps({"type": "user", "timestamp": _iso_w(ora + 1), "message": {"role": "user", "content": "Ciao Claude, com'è andata la riunione di oggi?"}}),
        json.dumps({"type": "queue-operation", "operation": "enqueue", "timestamp": _iso_w(ora + 1), "content": "Messaggio messo in coda mentre lavora"}),
        json.dumps({"type": "user", "timestamp": _iso_w(ora - 900), "message": {"role": "user", "content": "Frase di un quarto d'ora fa"}}),
    ])
    assert f["messaggio_in_registri"]("Ciao Claude, com'è  andata la riunione di oggi? ", ora, progetti) is True
    assert f["messaggio_in_registri"]("Messaggio messo in coda mentre lavora", ora, progetti) is True
    assert f["messaggio_in_registri"]("Frase di un quarto d'ora fa", ora, progetti) is False
    assert f["messaggio_in_registri"]("Mai arrivata, questa frase", ora, progetti) is False
    assert f["messaggio_in_registri"]("qualunque", ora, tmp_path / "non-esiste") is False


def _consegna_finta_w(arrivi, intervento=True, ammesso=True):
    f = _funzioni_pure_app_con_costanti()
    azioni = []
    esito = f["verifica_consegna"](
        "messaggio", 0.0, lambda t, d: len(azioni) >= arrivi if arrivi is not None else False,
        lambda: intervento, lambda: azioni.append("invio"), lambda: azioni.append("incolla+invio"),
        recupero_ammesso=ammesso, attesa_sec=0.2, passo_sec=0.1, attendi=lambda _s: None)
    return esito, azioni


def test_windows_consegna_persa_prima_invio_poi_reincolla_e_mai_senza_conferma():
    assert _consegna_finta_w(0) == ("arrivato", [])
    assert _consegna_finta_w(1) == ("recuperato", ["invio"])
    assert _consegna_finta_w(2) == ("recuperato", ["invio", "incolla+invio"])
    assert _consegna_finta_w(None) == ("persa", ["invio", "incolla+invio"])
    assert _consegna_finta_w(None, ammesso=False) == ("non_confermato", [])
    assert _consegna_finta_w(None, intervento=False) == ("annullato", [])


def _percorso_verifica_w(registro_ha_il_messaggio=False, davanti=True, exe="Claude"):
    nomi = {43: f"Claude {exe}", 44: "Claude - Google Chrome chrome"}
    tasti, incollati = [], []
    f = _funzioni_pure_app_con_costanti()
    spazio = dict(
        logging=logging, threading=__import__("threading"), time=time,
        CFG={"verifica_consegna": True, "verifica_consegna_app": ["Claude"], "verifica_consegna_storico_min": 30},
        nome_finestra=lambda h: nomi[h], recording=False, key_down=False, ultima_pressione_utente=0.0,
        coda_dettature=SimpleNamespace(occupata=lambda: False),
        finestra_frontale=lambda: 43 if davanti else 99,
        riattiva_bersaglio=lambda h: None, metti_cursore_in_casella=lambda h: True,
        paste_text=lambda t, **k: incollati.append(t),
        keyboard_controller=SimpleNamespace(press=tasti.append, release=lambda _: None),
        Key=SimpleNamespace(enter="enter"),
        messaggio_in_registri=lambda t, d: registro_ha_il_messaggio,
        verifica_consegna=lambda *a, **k: f["verifica_consegna"](*a, **{**k, "attesa_sec": 0.2, "passo_sec": 0.1, "attendi": lambda _s: None}),
        _consegne_confermate={},
    )
    path = REPO_ROOT / "windows" / "voice_dettatura_windows.py"
    nodi = [n for n in ast.parse(path.read_text(encoding="utf-8")).body if isinstance(n, ast.FunctionDef)
            and n.name in ("_eseguibile_finestra", "_app_con_registro", "_controlla_consegna", "_verifica_consegna")]
    exec(compile(ast.Module(body=nodi, type_ignores=[]), str(path), "exec"), spazio)
    return SimpleNamespace(spazio=spazio, tasti=tasti, incollati=incollati)


def test_windows_consegna_solo_per_il_programma_di_claude_code_non_per_il_browser():
    p = _percorso_verifica_w()
    assert p.spazio["_app_con_registro"](43) is True
    assert p.spazio["_app_con_registro"](44) is False     # claude.ai nel browser: nessun registro locale
    assert p.spazio["_app_con_registro"](None) is False


def test_windows_consegna_senza_conferma_recente_si_limita_a_registrare():
    p = _percorso_verifica_w()
    p.spazio["_verifica_consegna"]("Messaggio per Claude", 43, 0.0)
    assert p.tasti == [] and p.incollati == []


def test_windows_consegna_con_conferma_recente_ripreme_invio_poi_reincolla():
    p = _percorso_verifica_w()
    p.spazio["_consegne_confermate"]["claude"] = time.monotonic()
    p.spazio["_verifica_consegna"]("Messaggio per Claude", 43, 0.0)
    assert p.tasti == ["enter", "enter"] and p.incollati == ["Messaggio per Claude "]


def test_windows_consegna_arrivata_ricorda_che_il_registro_funziona_e_non_tocca_niente():
    p = _percorso_verifica_w(registro_ha_il_messaggio=True)
    p.spazio["_verifica_consegna"]("Messaggio per Claude", 43, 0.0)
    assert "claude" in p.spazio["_consegne_confermate"] and p.tasti == []


def test_windows_consegna_non_interviene_se_sal_e_andato_in_un_altra_finestra():
    p = _percorso_verifica_w(davanti=False)
    p.spazio["_consegne_confermate"]["claude"] = time.monotonic()
    p.spazio["_verifica_consegna"]("Messaggio per Claude", 43, 0.0)
    assert p.tasti == [] and p.incollati == []


def test_windows_l_incolla_chiama_il_controllo_di_consegna_e_la_voce_segue_la_scrittura():
    sorgente = (REPO_ROOT / "windows" / "voice_dettatura_windows.py").read_text(encoding="utf-8")
    corpo = sorgente.split("def _incolla_messaggio", 1)[1].split("\ndef ", 1)[0]
    assert "_controlla_consegna(text, finestra_bersaglio, chat_agente)" in corpo
    assert 'CFG.get("voce_mentre_scrive", True)' in sorgente and "voce_agenti.SeguiRegistro(" in sorgente
    config = json.loads((REPO_ROOT / "windows" / "config.json").read_text(encoding="utf-8"))
    assert config["voce_mentre_scrive"] is True and config["verifica_consegna"] is True
    assert config["verifica_consegna_app"] == ["Claude"]


def test_windows_coda_accoda_i_blocchi_e_senza_accoda_sostituisce(tmp_path):
    pendente = tmp_path / "LETTURA_PENDENTE"
    origine = {"id": "s1", "nome": "Claude"}
    voce_windows.scrivi_pendente("Primo.", pendente, origine, accoda=True)
    voce_windows.scrivi_pendente("Secondo.", pendente, origine, accoda=True)
    assert voce_windows.prendi_pendente(pendente) == "Primo.\n\nSecondo."
    voce_windows.scrivi_pendente("Vecchia.", pendente, origine)
    voce_windows.scrivi_pendente("Nuova.", pendente, origine)
    assert voce_windows.prendi_pendente(pendente) == "Nuova."


def test_windows_accordo_gancio_e_registro(tmp_path):
    assert voce_windows.reclama_lettura("s1", "Ho finito il lavoro e il risultato e' pronto per la verifica finale.", 1000.0) is True
    assert voce_windows.reclama_lettura("s1", "Ho finito il lavoro e il risultato e' pronto per la verifica finale.", 1001.0) is False
    assert voce_windows.reclama_lettura("s2", "Ho finito il lavoro e il risultato e' pronto per la verifica finale.", 1001.0) is True
    assert voce_windows.reclama_lettura("s1", "Va bene così.", 1000.0) is True
    assert voce_windows.reclama_lettura("s1", "così.", 1001.0) is True          # breve: doppione solo se identico
    assert voce_windows.reclama_lettura("s1", "Fatto.", 1000.0) is True
    assert voce_windows.reclama_lettura("s1", "Fatto.", 1000.0 + voce_windows.FINESTRA_LETTO_SEC + 1) is True


def test_windows_il_gancio_tace_se_il_registro_l_ha_gia_letta(tmp_path, monkeypatch):
    from io import StringIO

    _isola_coda_windows(tmp_path, monkeypatch)
    (tmp_path / "VOICE_ON").touch()
    monkeypatch.setattr(voce_windows, "FLAG_VOICE_ON", tmp_path / "VOICE_ON")
    monkeypatch.setattr(voce_windows, "ULTIMA_LETTURA", tmp_path / "ULTIMA_LETTURA")
    risposta = "Il lavoro e' finito e i test sono verdi, resta solo la pubblicazione."
    assert voce_windows.reclama_lettura("s", risposta) is True     # l'ha letta il seguitore
    monkeypatch.setattr(voce_windows.sys, "stdin", StringIO(json.dumps({"session_id": "s", "last_assistant_message": risposta})))
    voce_windows.main()
    assert voce_windows.prendi_pendente() is None
    assert "gia' letta mentre veniva scritta" in (tmp_path / "voice_hook.log").read_text(encoding="utf-8")


def _riga_ass_w(testo, **extra):
    return json.dumps({"type": "assistant", "message": {"role": "assistant", "model": "claude-x",
                       "content": [{"type": "text", "text": testo}]}, **extra})


def test_windows_blocchi_e_sessioni_come_sul_mac(tmp_path):
    f = voce_windows.blocco_di_riga
    assert f(_riga_ass_w("  Ecco il risultato.  ")) == "Ecco il risultato."
    assert f(_riga_ass_w("subagente", isSidechain=True)) is None
    assert f(json.dumps({"type": "assistant", "message": {"model": "<synthetic>", "content": [{"type": "text", "text": "x"}]}})) is None
    assert f(json.dumps({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Bash"}]}})) is None
    def scrivi(nome, riga):
        p = tmp_path / nome
        p.write_text(json.dumps(riga), encoding="utf-8")
        return p
    assert voce_windows.sessione_interattiva(scrivi("a.jsonl", {"type": "user", "entrypoint": "claude-desktop", "message": {"content": "ciao"}})) is True
    assert voce_windows.sessione_interattiva(scrivi("b.jsonl", {"type": "user", "entrypoint": "sdk-cli", "message": {"content": "ciao"}})) is False
    assert voce_windows.sessione_interattiva(scrivi("c.jsonl", {"type": "user", "message": {"content": "<scheduled-task name=\"x\">"}})) is False
    assert voce_windows.sessione_interattiva(tmp_path / "manca.jsonl") is True


def test_windows_seguitore_legge_il_blocco_nuovo_non_il_passato_e_non_con_la_voce_spenta(tmp_path):
    progetti = tmp_path / "progetti" / "-C-casa"
    progetti.mkdir(parents=True)
    lette, stato = [], {"attiva": True}
    seg = voce_windows.SeguiRegistro(cartella=tmp_path / "progetti", leggi=lambda t, o: lette.append((t, o)),
                                     attiva=lambda: stato["attiva"], traccia_fn=lambda m: None)
    chat = progetti / "s.jsonl"
    with open(chat, "a", encoding="utf-8") as f:
        f.write(_riga_ass_w("Passato.") + "\n")
    assert seg.giro() == 0
    with open(chat, "a", encoding="utf-8") as f:
        f.write(_riga_ass_w("Primo blocco nuovo.") + "\n" + _riga_ass_w("Secondo blocco nuovo.") + "\n")
    assert seg.giro() == 2
    assert lette == [("Primo blocco nuovo.\n\nSecondo blocco nuovo.", {"id": "s", "nome": "Claude"})]
    stato["attiva"] = False
    with open(chat, "a", encoding="utf-8") as f:
        f.write(_riga_ass_w("A voce spenta.") + "\n")
    assert seg.giro() == 0
    stato["attiva"] = True
    assert seg.giro() == 0 and len(lette) == 1


def test_windows_invio_di_sal_mentre_il_testo_compare_conta_come_si():
    # gemella Mac (30/10/2026): l'Invio premuto mentre il testo atterrava si manda
    f = _funzioni_pure_app("invio_di_sal_durante_incolla")["invio_di_sal_durante_incolla"]
    assert f("enter", "enter", 10.3, 10.0, 10.7) is True
    assert f("enter", "enter", 10.0, 10.0, 10.7) is False
    assert f("enter", "enter", 10.8, 10.0, 10.7) is False
    assert f("a", "enter", 10.3, 10.0, 10.7) is False
    assert f("clic", "enter", 10.3, 10.0, 10.7) is False
    sorgente = (REPO_ROOT / "windows" / "voice_dettatura_windows.py").read_text(encoding="utf-8")
    assert "fine_incolla = time.monotonic()" in sorgente
    assert "Invio di Sal arrivato mentre il testo compariva" in sorgente
    assert "ultimo_tasto_utente" in sorgente


# --- 31/10/2026: le tre novita' del Mac gemellate su Windows ---
# 1. Orecchio (Silero VAD con onnxruntime, stesso modello): prima di Whisper, niente voce =
#    niente trascrizione, silenzi lunghi accorciati. Su Windows non ci sono le mani libere.
# 2. Esc annulla la dettatura: filtro dell'hook di tastiera di pynput, SPENTO di serie.
# 3. Menu Voce: «Copia l'ultima dettatura» e «Ritrascrivi l'ultima», solo in memoria.
# Tutto provato con eventi, finestre e motori finti: nessun PC Windows reale qui.

import queue as _queue
import threading as _threading

import numpy as np

WIN_APP = REPO_ROOT / "windows" / "voice_dettatura_windows.py"
SHA_SILERO_V6_2_3 = "1a153a22f4509e292a94e67d6f9b85e8deb25b4988682b7e174c65279d8788e3"
NOMI_ORECCHIO = ["FRAME_ORECCHIO", "CONTESTO_ORECCHIO", "FlussoOrecchio", "frame_da_ms",
                 "c_e_voce_umana", "maschera_voce", "Orecchio"]


def _dall_app_windows(nomi, spazio):
    """Funzioni, classi e costanti VERE del file Windows, eseguite in `spazio`."""
    albero = ast.parse(WIN_APP.read_text(encoding="utf-8"), filename=str(WIN_APP))
    nodi = [n for n in albero.body
            if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name in nomi
            or isinstance(n, ast.Assign) and any(getattr(t, "id", None) in nomi for t in n.targets)]
    trovati = {getattr(n, "name", None) or n.targets[0].id for n in nodi}
    assert trovati == set(nomi), f"mancano nel file Windows: {set(nomi) - trovati}"
    exec(compile(ast.Module(body=nodi, type_ignores=[]), str(WIN_APP), "exec"), spazio)
    return spazio


@pytest.fixture(scope="module")
def mac_lib():
    """La libreria del Mac (il MASTER), per confrontare la gemella numero per numero."""
    spec = importlib.util.spec_from_file_location("voce_lib_mac_per_windows", REPO_ROOT / "mac" / "voce_lib.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def _orecchio_windows(**extra):
    return _dall_app_windows(NOMI_ORECCHIO + list(extra.pop("nomi", [])), {"np": np, **extra})


def _modello_finto_w(voce=lambda frame: float(np.abs(frame).max()) > 0.02):
    """Silero finto: voce = 0,9, altrimenti 0,05 (come nelle prove del Mac)."""
    chiamate = []

    def modello(ingresso, stato):
        chiamate.append(ingresso.copy())
        return (0.9 if voce(ingresso[0, 64:]) else 0.05), stato + 1
    modello.chiamate = chiamate
    return modello


def _audio_a_tratti_w(*tratti):
    """[(secondi, ampiezza)] -> audio a 16 kHz: 0 = silenzio, >0 = voce (per il modello finto)."""
    pezzi = []
    for secondi, ampiezza in tratti:
        n = int(round(secondi * 16000))
        pezzi.append(np.full(n, ampiezza, dtype="float32") * np.where(np.arange(n) % 2, 1, -1))
    return np.concatenate(pezzi)


def _coda_windows():
    return _dall_app_windows(["CodaDettature"], {"threading": _threading})["CodaDettature"]()


def _ultime_windows():
    return _dall_app_windows(["_ordine_turno", "UltimeDettature"], {"threading": _threading})["UltimeDettature"]()


def test_windows_orecchio_gemello_del_mac_stessi_numeri_e_stesso_audio(mac_lib):
    w = _orecchio_windows()
    assert (w["FRAME_ORECCHIO"], w["CONTESTO_ORECCHIO"]) == (mac_lib.FRAME_ORECCHIO, mac_lib.CONTESTO_ORECCHIO) == (512, 64)
    for ms in (10, 60, 450, 1400):
        assert w["frame_da_ms"](ms) == mac_lib.frame_da_ms(ms)
    di_serie = w["Orecchio"].da_config({}, modello=_modello_finto_w())
    assert (di_serie.soglia, di_serie.attacco, di_serie.prima, di_serie.dopo) == (0.3, 2, 14, 14)  # valori di Handy
    cfg = {"orecchio_soglia": 0.5, "orecchio_attacco_ms": 100, "orecchio_prima_ms": 200, "orecchio_dopo_ms": 300}
    a, b = w["Orecchio"].da_config(cfg, modello=None or _modello_finto_w()), mac_lib.Orecchio.da_config(cfg, modello=_modello_finto_w())
    assert (a.soglia, a.attacco, a.prima, a.dopo) == (b.soglia, b.attacco, b.prima, b.dopo)
    casi = [
        ((3.0, 0.0),),                                             # silenzio
        ((31 * 512 / 16000, 0.0), (0.02, 0.5), (1.0, 0.0)),        # un colpo da 20 ms: non e' voce
        ((2.0, 0.0), (1.0, 0.1), (3.0, 0.0), (1.0, 0.1), (2.0, 0.0)),  # voce con silenzi lunghi
        ((0.7, 0.1),),                                             # voce sola, coda oltre l'ultimo frame
    ]
    for tratti in casi:
        audio = _audio_a_tratti_w(*tratti)
        pronto_w, prob_w = w["Orecchio"].da_config({}, modello=_modello_finto_w()).prepara(audio)
        pronto_m, prob_m = mac_lib.Orecchio.da_config({}, modello=_modello_finto_w()).prepara(audio)
        assert prob_w == prob_m
        assert (pronto_w is None) == (pronto_m is None)
        if pronto_w is not None:
            assert np.array_equal(pronto_w, pronto_m)


def test_windows_flusso_orecchio_stesse_probabilita_a_pezzi_diversi_e_contesto_di_silero():
    w = _orecchio_windows()
    audio = _audio_a_tratti_w((0.5, 0.0), (0.4, 0.1), (0.7, 0.0))
    risultati = []
    for misura in (480, 1000, len(audio)):
        modello = _modello_finto_w()
        flusso = w["FlussoOrecchio"](modello)
        prob = []
        for i in range(0, len(audio), misura):
            prob += flusso.probabilita(audio[i:i + misura])
        risultati.append(prob)
        assert all(c.shape == (1, 576) for c in modello.chiamate)  # 64 campioni di contesto + 512
        assert np.array_equal(modello.chiamate[1][0, :64], audio[512 - 64:512])
    assert risultati[0] == risultati[1] == risultati[2]


def test_windows_whisper_non_parte_senza_voce_e_riceve_l_audio_accorciato(caplog):
    w = _orecchio_windows()
    ricevuti = []

    class Motore:
        def transcribe(self, audio, **kw):
            ricevuti.append((audio, kw))
            return iter([SimpleNamespace(text="Ciao.")]), None
    spazio = dict(np=np, logging=logging, time=time, SAMPLE_RATE=16000, CFG={}, load_model=lambda: Motore(),
                  ORECCHIO=w["Orecchio"].da_config({}, modello=_modello_finto_w()))
    _dall_app_windows(["_whisper_grezzo"], spazio)
    audio = _audio_a_tratti_w((2.0, 0.0), (1.0, 0.1), (2.0, 0.0))
    with caplog.at_level(logging.INFO):
        assert spazio["_whisper_grezzo"](_audio_a_tratti_w((4.0, 0.0)), "Claude Code.") == ""
        assert ricevuti == [] and "orecchio: nessuna voce in 4.0s" in caplog.text   # sul silenzio niente «Grazie.»
        assert spazio["_whisper_grezzo"](audio, "Claude Code.") == "Ciao."
    inviato, kw = ricevuti[0]
    assert len(inviato) / 16000 == pytest.approx(1.0 + 2 * 0.448, abs=0.07)  # 450 ms per lato, nient'altro
    assert int((np.abs(inviato) > 0.05).sum()) == int((np.abs(audio) > 0.05).sum())  # nessun campione di voce perso
    assert kw["vad_filter"] is True and kw["initial_prompt"] == "Claude Code."  # il motore resta com'era
    assert "orecchio: voce, 5.0s -> 1.9s" in caplog.text


def test_windows_un_guasto_o_l_orecchio_spento_mandano_a_whisper_l_audio_intero(caplog):
    class Rotto:
        def prepara(self, audio):
            raise RuntimeError("onnx")
    ricevuti = []

    class Motore:
        def transcribe(self, audio, **kw):
            ricevuti.append(audio)
            return iter([SimpleNamespace(text="Ciao.")]), None
    audio = np.full(16000, 0.04, dtype="float32")
    for orecchio in (Rotto(), None):
        spazio = dict(np=np, logging=logging, time=time, SAMPLE_RATE=16000, CFG={},
                      load_model=lambda: Motore(), ORECCHIO=orecchio)
        _dall_app_windows(["_whisper_grezzo"], spazio)
        with caplog.at_level(logging.INFO):
            assert spazio["_whisper_grezzo"](audio, None) == "Ciao."
        assert len(ricevuti[-1]) == 16000
    assert "orecchio: errore, Whisper sull'audio intero" in caplog.text


def test_windows_carica_orecchio_spento_senza_modello_o_col_modello_vero(tmp_path):
    pytest.importorskip("onnxruntime")
    spazio = _orecchio_windows(nomi=["FILE_ORECCHIO", "ModelloOrecchio", "carica_orecchio"],
                               Path=Path, BASE=tmp_path)
    assert spazio["carica_orecchio"]({"orecchio": False}) == (None, 'spento in config.json ("orecchio": false)')
    orecchio, stato = spazio["carica_orecchio"]({})          # nella cartella non c'e' il modello
    assert orecchio is None and stato.startswith("non caricato") and stato.endswith("come prima")
    spazio["FILE_ORECCHIO"] = REPO_ROOT / "windows" / "silero_vad.onnx"
    orecchio, stato = spazio["carica_orecchio"]({})
    assert orecchio is not None
    assert stato == ("Silero VAD caricato (silero_vad.onnx): soglia 0.3, voce dopo 2 frame da 32 ms, "
                     "margini 14+14 frame")
    sorgente = WIN_APP.read_text(encoding="utf-8")
    assert "ORECCHIO, ORECCHIO_STATO = carica_orecchio(CFG)" in sorgente
    assert 'logging.info("orecchio: %s", ORECCHIO_STATO)' in sorgente.split("def main()", 1)[1]


def _parlato_sintetico_w(tmp_path, frase="Buongiorno, questa è una prova della dettatura."):
    """Voce italiana di macOS (Alice) a 16 kHz: una persona che parla, ripetibile."""
    import wave
    if not shutil.which("say"):
        pytest.skip("say non disponibile")
    wav = tmp_path / "parlato.wav"
    esito = subprocess.run(["say", "-v", "Alice", "-o", str(wav), "--file-format=WAVE",
                            "--data-format=LEI16@16000", frase], capture_output=True)
    if esito.returncode != 0 or not wav.exists():
        pytest.skip("voce Alice non disponibile")
    with wave.open(str(wav)) as w:
        return np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype("float32") / 32768


def test_windows_silero_vero_sente_una_persona_non_il_rumore_e_da_gli_stessi_numeri_del_mac(tmp_path, mac_lib):
    """Il vero `silero_vad.onnx` della cartella windows/ col vero onnxruntime, dal codice Windows."""
    pytest.importorskip("onnxruntime")
    w = _orecchio_windows(nomi=["FILE_ORECCHIO", "ModelloOrecchio"], Path=Path, BASE=REPO_ROOT / "windows")
    orecchio = w["Orecchio"].da_config({})                  # il modello di serie: windows/silero_vad.onnx
    rng = np.random.default_rng(0)
    for nome, audio in {
        "silenzio": np.zeros(3 * 16000, dtype="float32"),
        "fruscio": (rng.standard_normal(3 * 16000) * 0.01).astype("float32"),
        "rumore forte": (rng.standard_normal(3 * 16000) * 0.2).astype("float32"),
        "ronzio 50 Hz": (0.05 * np.sin(2 * np.pi * 50 * np.arange(3 * 16000) / 16000)).astype("float32"),
    }.items():
        assert orecchio.prepara(audio)[0] is None, nome
    parlato = _parlato_sintetico_w(tmp_path)
    pausa = np.zeros(3 * 16000, dtype="float32")
    audio = np.concatenate([pausa, parlato, pausa, parlato, pausa])
    pronto, prob = orecchio.prepara(audio)
    assert pronto is not None
    voce = np.repeat(np.array(prob) >= 0.3, 512)[:len(audio)]
    assert not (voce & ~w["maschera_voce"](len(audio), prob)).any()   # la voce resta tutta
    assert len(pronto) < len(audio) - 4 * 16000                       # 9 s di pause diventano meno di 3
    mac = mac_lib.Orecchio.da_config({}, modello=mac_lib.ModelloOrecchio(REPO_ROOT / "mac" / "silero_vad.onnx"))
    assert np.allclose(prob, mac.probabilita(audio), atol=1e-6)       # stesso modello, stesse probabilita'


def test_windows_porta_lo_stesso_modello_del_mac_con_licenza_installer_e_dipendenza():
    import hashlib
    modello = REPO_ROOT / "windows" / "silero_vad.onnx"
    assert modello.stat().st_size == 2327524
    assert hashlib.sha256(modello.read_bytes()).hexdigest() == SHA_SILERO_V6_2_3
    assert modello.read_bytes() == (REPO_ROOT / "mac" / "silero_vad.onnx").read_bytes()
    assert "Silero Team" in (REPO_ROOT / "windows" / "silero_vad_LICENSE.txt").read_text(encoding="utf-8")
    installer = (REPO_ROOT / "windows" / "install.ps1").read_text(encoding="utf-8")
    assert '@("silero_vad.onnx", "silero_vad_LICENSE.txt")' in installer
    assert installer.index("silero_vad.onnx") < installer.index("--merge-config")
    righe = (REPO_ROOT / "windows" / "requirements.txt").read_text(encoding="utf-8").split()
    assert "onnxruntime==1.27.0" in righe                      # come sul Mac; faster-whisper lo usa gia'
    assert not any(r.startswith("torch") for r in righe)
    cfg = json.loads((REPO_ROOT / "windows" / "config.json").read_text(encoding="utf-8"))
    assert cfg["orecchio"] is True and cfg["esc_annulla"] is False
    assert "silero_vad.onnx" in (REPO_ROOT / "windows" / "README.md").read_text(encoding="utf-8")


# --- Esc annulla ---

def test_windows_esc_stesse_decisioni_del_mac(mac_lib):
    import random
    EscW = _dall_app_windows(["EscAnnulla"], {})["EscAnnulla"]
    assert EscW.SCADENZA_SEC == mac_lib.EscAnnulla.SCADENZA_SEC
    rng = random.Random(31)
    w, m, ora = EscW(), mac_lib.EscAnnulla(), 0.0
    for _ in range(3000):
        ora += rng.choice([0.03, 0.4, 2.0, 4.0])
        evento = (rng.random() < 0.6, rng.random() < 0.3, rng.random() < 0.2, rng.random() < 0.5, ora)
        assert w.evento(*evento) == m.evento(*evento)
        assert w.serve(ora) == m.serve(ora)


class _Trattenuto(Exception):
    """Come SystemHook.SuppressException di pynput: l'hook restituisce 1, il tasto non arriva."""


NOMI_FILTRO_ESC = ["VK_ESC", "FINESTRA_ESC_MAX_SEC", "RIPETIZIONE_ESC_SEC", "_WM_TASTO_GIU", "_LLKHF_INIETTATO",
                   "_VK_MODIFICATORI", "EscAnnulla", "esc_annulla", "modificatore_di_sistema_giu",
                   "finestra_esc_aperta", "_filtro_tastiera"]


def _filtro_esc_windows(*, aperta=True, registrazione_fa=1.0, recording=False, giu=()):
    """Il filtro vero dell'hook con un KBDLLHOOKSTRUCT finto e GetAsyncKeyState finto."""
    coda = _coda_windows()
    if aperta:
        coda.apri("t")
    comandi = []

    class Ascoltatore:
        def suppress_event(self):
            raise _Trattenuto()
    user32 = SimpleNamespace(GetAsyncKeyState=lambda vk: 0x8000 if vk in giu else 0)
    spazio = dict(time=time, ctypes=SimpleNamespace(windll=SimpleNamespace(user32=user32)),
                  coda_dettature=coda, commands=SimpleNamespace(put=comandi.append), recording=recording,
                  VK_TASTO_DETTA=0xA3, ascoltatore_tastiera=Ascoltatore(), _esc_giu=False, _ultimo_esc=0.0,
                  _ultima_registrazione=time.monotonic() - registrazione_fa)
    _dall_app_windows(NOMI_FILTRO_ESC, spazio)

    def premi(vk, msg=0x0100, flags=0):
        try:
            esito = spazio["_filtro_tastiera"](msg, SimpleNamespace(vkCode=vk, flags=flags))
        except _Trattenuto:
            return "trattenuto"
        assert esito is True    # mai False: un tasto che passa arriva anche ai callback dell'app
        return "passa"
    return SimpleNamespace(premi=premi, coda=coda, comandi=comandi, spazio=spazio)


def test_windows_filtro_esc_trattiene_solo_esc_e_solo_durante_la_dettatura():
    f = _filtro_esc_windows()
    assert f.premi(0x41) == "passa" and f.premi(0x0D) == "passa"   # lettere e Invio passano sempre
    assert f.premi(0x1B) == "trattenuto"                          # Esc: all'app non arriva
    assert f.comandi == ["annulla"] and f.coda.annullato("t")
    assert f.premi(0x1B) == "trattenuto"                          # tenuto premuto: la ripetizione di Windows
    assert f.comandi == ["annulla"]                               # si butta una volta sola
    assert f.premi(0x1B, msg=0x0101) == "trattenuto"              # e nemmeno il rilascio arriva
    fuori = _filtro_esc_windows(aperta=False)
    assert fuori.premi(0x1B) == "passa" and fuori.premi(0x1B, msg=0x0101) == "passa"
    assert fuori.comandi == []                                    # fuori dalla dettatura Esc e' dell'app
    registra = _filtro_esc_windows(aperta=False, recording=True)
    assert registra.premi(0x1B) == "trattenuto" and registra.comandi == ["annulla"]


def test_windows_filtro_esc_ctrl_alt_win_restano_del_sistema_il_tasto_detta_no():
    for vk in (0xA2, 0xA4, 0xA5, 0x5B, 0x5C):   # Ctrl sinistro, Alt, Alt Gr, Win sinistro e destro
        f = _filtro_esc_windows(giu=(vk,))
        assert f.premi(0x1B) == "passa" and f.comandi == [], hex(vk)
    f = _filtro_esc_windows(giu=(0xA3,))       # Ctrl destro e' il tasto-detta: chi detta lo tiene giu'
    assert f.premi(0x1B) == "trattenuto" and f.comandi == ["annulla"]


def test_windows_filtro_esc_programmi_code_appese_ed_errori_lasciano_passare():
    f = _filtro_esc_windows()
    assert f.premi(0x1B, flags=0x10) == "passa"                   # Esc mandato da un programma
    assert f.premi(0x1B, flags=0x02) == "passa"
    assert f.comandi == []
    appesa = _filtro_esc_windows(registrazione_fa=121.0)          # coda rimasta aperta da un guasto
    assert appesa.premi(0x1B) == "passa" and appesa.comandi == []
    rotto = _filtro_esc_windows()
    assert rotto.spazio["_filtro_tastiera"](0x0100, SimpleNamespace(flags=0)) is True   # dati senza vkCode
    rotto.spazio["coda_dettature"] = None                          # una coda che esplode
    assert rotto.spazio["_filtro_tastiera"](0x0100, SimpleNamespace(vkCode=0x1B, flags=0)) is True
    rotto.spazio["ctypes"] = SimpleNamespace()                     # fuori da Windows: nessun modificatore
    assert rotto.spazio["modificatore_di_sistema_giu"]() is False


def test_windows_esc_spento_di_serie_e_il_filtro_si_aggancia_solo_se_acceso():
    cfg = json.loads((REPO_ROOT / "windows" / "config.json").read_text(encoding="utf-8"))
    assert cfg["esc_annulla"] is False
    sorgente = WIN_APP.read_text(encoding="utf-8")
    assert 'ESC_ANNULLA = bool(CFG.get("esc_annulla", False))' in sorgente   # anche senza la chiave: spento
    main = sorgente.split("def main()", 1)[1]
    # un filtro None farebbe chiamare None a pynput: il listener si fermerebbe al primo tasto
    assert '{"win32_event_filter": _filtro_tastiera} if ESC_ANNULLA else {}' in main
    assert "keyboard.Listener(on_press=on_press, on_release=on_release, **opzioni_tastiera)" in main


def test_windows_pynput_bloccato_trattiene_davvero_col_filtro():
    """Il contratto di pynput su cui poggia Esc, letto nei sorgenti della versione bloccata:
    il filtro gira dentro l'hook, suppress_event fa restituire 1 (nessuna app riceve il
    tasto), e un'altra eccezione nel filtro fermerebbe il listener."""
    import importlib.metadata
    import importlib.util as iu
    bloccata = next(r.split("==")[1] for r in (REPO_ROOT / "windows" / "requirements.txt")
                    .read_text(encoding="utf-8").split() if r.startswith("pynput=="))
    try:
        installata = importlib.metadata.version("pynput")
    except importlib.metadata.PackageNotFoundError:
        pytest.skip("pynput non installato")
    if installata != bloccata:
        pytest.skip(f"pynput {installata} installato, il prodotto blocca {bloccata}")
    cartella = Path(iu.find_spec("pynput").submodule_search_locations[0])
    gancio = (cartella / "_util" / "win32.py").read_text(encoding="utf-8")
    tastiera = (cartella / "keyboard" / "_win32.py").read_text(encoding="utf-8")
    base = (cartella / "keyboard" / "_base.py").read_text(encoding="utf-8")
    assert "except self.SuppressException:" in gancio and "return 1" in gancio
    assert "raise SystemHook.SuppressException()" in gancio
    assert "_HANDLED_EXCEPTIONS = (SystemHook.SuppressException,)" in tastiera
    assert "if self._event_filter(msg, data) is False:" in tastiera
    assert "'event_filter', lambda msg, data: True" in tastiera
    assert "``win32_event_filter``" in base and "suppress_event()" in base
    assert "self.stop()" in (cartella / "_util" / "__init__.py").read_text(encoding="utf-8")


def test_windows_coda_esc_butta_tutto_cio_che_non_e_incollato_e_nessun_invio():
    coda = _coda_windows()
    assert coda.annulla() is False and not coda.aperta()
    consegne, chiusi = [], []
    coda.apri("prima")
    coda.apri("seconda")
    coda.completa("prima", "Gia trascritta.", "chat")
    assert coda.aperta() and coda.annulla() is True
    assert coda.annullato("seconda")
    coda.completa("seconda", "Arrivata dopo Esc.", "chat")
    coda.consegna_pronte(lambda *a: consegne.append(a), chiusi.append)
    assert consegne == [] and chiusi == ["prima", "seconda"]
    assert not coda.aperta() and not coda.annullato("seconda")


def test_windows_coda_esc_dopo_una_ripresa_non_manda_l_invio_sospeso():
    coda = _coda_windows()
    consegne = []

    def consegna(testo, bersaglio, revisione):
        consegne.append(testo)
        return True                     # Invio sospeso: si e' ripreso a parlare
    coda.apri("prima")
    coda.completa("prima", "Prima.", "chat")
    coda.consegna_pronte(consegna, lambda _: None)
    coda.apri("ripresa")
    coda.annulla()                      # Esc durante la ripresa
    coda.completa("ripresa", "", "chat")
    coda.consegna_pronte(consegna, lambda _: None)
    assert consegne == ["Prima."]       # nessun Invio vuoto per la frase prima


def test_windows_coda_aperta_fino_all_incolla_non_durante_l_attesa_dell_invio():
    coda = _coda_windows()
    stati = []

    def consegna(testo, bersaglio, revisione):
        stati.append(coda.aperta())     # cerca la casella: Esc butta ancora
        coda.incollato()
        stati.append(coda.aperta())     # testo incollato: Esc torna all'app
        return False
    coda.apri("t")
    coda.completa("t", "Testo.", "chat")
    coda.consegna_pronte(consegna, lambda _: None)
    assert stati == [True, False]


class _FineComandiW(Exception):
    pass


class _ComandiFinitiW:
    """La coda dei comandi audio: il worker vero li esegue tutti, poi si ferma."""
    def __init__(self):
        self.voci = []

    def put(self, comando):
        self.voci.append(comando)

    def get(self):
        if not self.voci:
            raise _FineComandiW()
        return self.voci.pop(0)


class _LavoroSubitoW:
    def __init__(self, target=None, args=(), kwargs=None, daemon=None):
        self.target, self.args, self.kwargs = target, args, kwargs or {}

    def start(self):
        self.target(*self.args, **self.kwargs)


def _dettatura_con_esc_windows(tmp_path):
    """Tasto, filtro di Esc, worker, avvio, annullo e stop VERI di Windows; microfono, beep,
    finestre e trascrizione finti."""
    import collections
    eventi, log, chiusure, conclusi, trascritti = _queue.Queue(), [], [], [], []
    coda, comandi = _coda_windows(), _ComandiFinitiW()

    class Stream:
        def __init__(self, **kw):
            pass

        def start(self):
            pass

        def stop(self):
            pass

        def close(self):
            chiusure.append(True)

    class Ascoltatore:
        def suppress_event(self):
            raise _Trattenuto()

    spazio = dict(
        np=np, time=time,
        logging=SimpleNamespace(info=lambda m, *a: log.append(m % a if a else m), warning=lambda *a: None,
                                exception=lambda *a: log.append("ERRORE")),
        threading=SimpleNamespace(Thread=_LavoroSubitoW), sd=SimpleNamespace(InputStream=Stream),
        coda_dettature=coda, ultime_dettature=_ultime_windows(), commands=comandi, eventi=eventi,
        apri_turno_utente=lambda: "1:100", ferma_voce=lambda: None, beep=lambda *a: None,
        finestra_frontale=lambda: 42, _sveglia_accessibilita=lambda hwnd: None,
        _avvisa_errore_audio=lambda testo: eventi.put(("errore_audio", testo)),
        transcribe_and_paste=lambda *a, **kw: trascritti.append(a), chiudi_turno_utente=conclusi.append,
        _incolla_messaggio=lambda *a: pytest.fail("dopo Esc niente incolla"),
        audio_callback=None, PID_FILE=tmp_path / "voce_pid", PROGRESSIVA=False, N_BARRE=18,
        SAMPLE_RATE=16000, CODA_RILASCIO_SEC=0.0, MIN_RECORDING_SEC=0.4, HOTKEY="ctrl_r", TASTO_VOCE=None,
        key_down=False, voice_key_down=False, pressioni_tasto=0, recording=False, recording_started_at=None,
        blocks=[], rms_blocks=[], livelli=collections.deque([0.0] * 18, maxlen=18), guasti_cattura=set(),
        turno_utente_token=None, sessione_progressiva=None, stream=None, ultima_pressione_utente=0.0,
        ultimo_tasto_utente=None, ctypes=SimpleNamespace(), VK_TASTO_DETTA=0xA3,
        ascoltatore_tastiera=Ascoltatore(), _esc_giu=False, _ultimo_esc=0.0, _ultima_registrazione=-1e9,
    )
    _dall_app_windows(["on_press", "on_release", "worker", "start_recording", "stop_recording",
                       "annulla_dettatura", "_concludi_dettatura", "_consegna_dettature"] + NOMI_FILTRO_ESC, spazio)

    def lavora():
        with pytest.raises(_FineComandiW):
            spazio["worker"]()

    def esc(msg=0x0100):
        try:
            spazio["_filtro_tastiera"](msg, SimpleNamespace(vkCode=0x1B, flags=0))
        except _Trattenuto:
            return "trattenuto"
        return "passa"
    return SimpleNamespace(spazio=spazio, coda=coda, comandi=comandi, eventi=eventi, log=log, esc=esc,
                           lavora=lavora, chiusure=chiusure, conclusi=conclusi, trascritti=trascritti)


def test_windows_esc_mentre_registra_chiude_senza_whisper_e_il_rilascio_non_trascrive(tmp_path):
    d = _dettatura_con_esc_windows(tmp_path)
    s = d.spazio
    s["on_press"]("ctrl_r")
    d.lavora()
    assert s["recording"] is True and s["stream"] is not None
    assert d.esc() == "trattenuto"               # Esc non arriva all'app davanti
    assert d.esc(msg=0x0101) == "trattenuto"
    d.lavora()                                   # il worker esegue «annulla»
    assert s["recording"] is False and s["stream"] is None and d.chiusure == [True]
    assert d.conclusi == ["1:100"] and not d.coda.aperta()      # nessun turno resta appeso
    assert ("avviso", "Dettatura annullata", 1.5) in list(d.eventi.queue)
    assert "dettatura annullata con Esc: niente incolla, niente Invio" in d.log
    s["on_release"]("ctrl_r")                    # il tasto si molla dopo
    d.lavora()
    assert d.trascritti == []                    # niente Whisper, niente incolla
    assert d.esc() == "passa" and d.comandi.voci == []   # dettatura finita: Esc torna all'app


def test_windows_esc_prima_di_whisper_niente_trascrizione_e_la_dettatura_vera_resta_nel_menu(tmp_path):
    coda, ultime, conclusi = _coda_windows(), _ultime_windows(), []
    spazio = dict(np=np, logging=logging, BASE=tmp_path, SAMPLE_RATE=16000, CFG={},
                  coda_dettature=coda, ultime_dettature=ultime,
                  salva_audio_recente=lambda *a, **kw: pytest.fail("niente lavoro"),
                  _trascrivi_con_sessione=lambda *a: pytest.fail("Whisper non deve partire"),
                  _concludi_dettatura=lambda *a: conclusi.append(a),
                  _avvisa_errore_audio=lambda testo: None)
    _dall_app_windows(["transcribe_and_paste", "TrascrizioneIncompleta"], spazio)
    coda.apri("1:1")
    coda.annulla()
    spazio["transcribe_and_paste"](np.full(16000, 0.04, dtype="float32"), 42, token_turno="1:1")
    assert conclusi == [("1:1", "", 42, False)]
    spazio.update(salva_audio_recente=lambda *a, **kw: None,
                  _trascrivi_con_sessione=lambda audio, sessione: "apri cloud code",
                  e_allucinazione=lambda testo: False, destinazione_agente=lambda nome: False,
                  nome_finestra=lambda hwnd: "Notepad", CFG={"sostituzioni": {"cloud code": "Claude Code"}},
                  applica_sostituzioni=_funzioni_pure_app("applica_sostituzioni")["applica_sostituzioni"],
                  converti_punteggiatura_dettata=lambda testo: testo)
    coda.apri("1:2")
    spazio["transcribe_and_paste"]("audio-2", 42, token_turno="1:2")
    assert conclusi[-1] == ("1:2", "apri Claude Code", 42, False)
    ultime.consegnata("apri Claude Code")
    assert ultime.ultima() == ("apri Claude Code", ["audio-2"])


def _consegna_windows(*, durante_casella=None, durante_incolla=None, attesa=0.0, prima_dell_invio=None):
    """Il percorso vero dell'incolla di Windows (casella, Ctrl+V, attesa, Invio) con finti."""
    coda, ultime = _coda_windows(), _ultime_windows()
    orologio, campo, inviati = [100.0], [], []

    def premi(tasto):
        if tasto == "enter":
            inviati.append("".join(campo).strip())
            campo.clear()

    def casella(hwnd):
        if durante_casella:
            durante_casella(coda)
        return True

    def incolla(testo, **kw):
        campo.append(testo)
        if durante_incolla:
            durante_incolla(coda)

    def ritardo(*a):
        if prima_dell_invio:
            prima_dell_invio(coda)
        return attesa
    tastiera = SimpleNamespace(press=premi, release=lambda tasto: None)
    spazio = dict(
        time=SimpleNamespace(monotonic=lambda: orologio[0],
                             sleep=lambda s: orologio.__setitem__(0, orologio[0] + s)),
        logging=logging, coda_dettature=coda, ultime_dettature=ultime,
        destinazione_agente=lambda nome: True, nome_finestra=lambda hwnd: "Claude",
        riattiva_bersaglio=lambda hwnd: None, metti_cursore_in_casella=casella,
        _bersaglio_di_riserva=lambda *a: None, paste_text=incolla, winsound=None, _ultima_chat_ai=None,
        recording=False, eventi=_queue.Queue(), INVIO_AUTOMATICO=True, ritardo_invio=ritardo, CFG={},
        voce_attiva=lambda: False, ultima_pressione_utente=0.0, key_down=False, ultimo_tasto_utente=None,
        Key=SimpleNamespace(enter="enter"), keyboard_controller=tastiera,
        _controlla_consegna=lambda *a: None, chiudi_turno_utente=lambda token: None,
    )
    _dall_app_windows(["invio_da_annullare", "invio_di_sal_durante_incolla", "_incolla_messaggio",
                       "_consegna_dettature"], spazio)
    coda.apri("t")
    coda.completa("t", "Ciao a tutti.", 42)
    return SimpleNamespace(consegna=spazio["_consegna_dettature"], coda=coda, ultime=ultime,
                           campo=campo, inviati=inviati)


def test_windows_consegna_ricorda_l_ultima_e_chiude_la_finestra_di_esc_dopo_l_incolla():
    stati = []
    c = _consegna_windows(durante_casella=lambda coda: stati.append(coda.aperta()),
                          prima_dell_invio=lambda coda: stati.append(coda.aperta()))
    c.consegna()
    assert c.inviati == ["Ciao a tutti."]
    assert stati == [True, False]                 # Esc butta fino all'incolla, poi e' dell'app
    assert c.ultime.ultima()[0] == "Ciao a tutti."


def test_windows_esc_mentre_cerca_la_casella_niente_incolla_e_niente_invio(caplog):
    c = _consegna_windows(durante_casella=lambda coda: coda.annulla())
    with caplog.at_level(logging.INFO):
        c.consegna()
    assert c.campo == [] and c.inviati == []
    assert "dettatura annullata con Esc: niente incolla, niente Invio" in caplog.text
    assert c.ultime.disponibili() == (False, False)


def test_windows_esc_durante_l_incolla_ferma_l_invio(caplog):
    c = _consegna_windows(durante_incolla=lambda coda: coda.annulla(), attesa=2.0)
    with caplog.at_level(logging.INFO):
        c.consegna()
    assert "".join(c.campo).strip() == "Ciao a tutti." and c.inviati == []   # il testo resta, l'Invio no
    assert "invio automatico ANNULLATO (Esc)" in caplog.text


# --- Menu Voce: ultime dettature ---

def _menu_windows(ultime, voce_agenti=None):
    """`_aggiorna_menu_voce` vero del Pannello Tk con un menu finto."""
    voci, lavori, chiamate = [], [], []

    class Menu:
        def delete(self, *a):
            voci.clear()

        def add_command(self, **kw):
            voci.append(("comando", kw))

        def add_separator(self):
            voci.append(("separatore", {}))

        def add_radiobutton(self, **kw):
            voci.append(("scelta", kw))

    class Thread:
        def __init__(self, target=None, daemon=None, **kw):
            self.target, self.daemon = target, daemon
            lavori.append(self)

        def start(self):
            self.target()
    spazio = dict(voce_agenti=voce_agenti, ultime_dettature=ultime, logging=logging,
                  threading=SimpleNamespace(Thread=Thread),
                  copia_ultima_dettatura=lambda: chiamate.append("copia"),
                  ritrascrivi_ultima=lambda: chiamate.append("ritrascrivi"))
    classe = next(n for n in ast.parse(WIN_APP.read_text(encoding="utf-8")).body
                  if isinstance(n, ast.ClassDef) and n.name == "Pannello")
    metodi = [n for n in classe.body if isinstance(n, ast.FunctionDef)
              and n.name in ("_aggiorna_menu_voce", "_aggiungi_ultime_dettature", "_esegui_comando_voce")]
    assert len(metodi) == 3
    exec(compile(ast.Module(body=metodi, type_ignores=[]), str(WIN_APP), "exec"), spazio)
    p = SimpleNamespace(menu_voce=Menu(), stato_conversazione=SimpleNamespace(set=lambda t: None),
                        conversazione_scelta=SimpleNamespace(set=lambda v: None),
                        root=SimpleNamespace(after=lambda ms, f: None))
    for nome in ("_aggiorna_menu_voce", "_aggiungi_ultime_dettature", "_esegui_comando_voce"):
        setattr(p, nome, (lambda f: lambda *a: f(p, *a))(spazio[nome]))
    return SimpleNamespace(aggiorna=p._aggiorna_menu_voce, voci=voci, lavori=lavori, chiamate=chiamate)


@pytest.mark.parametrize("con_voce_agenti", [False, True])
def test_windows_menu_ultime_dettature_in_fondo_spente_finche_non_ce_n_e_una(con_voce_agenti):
    agenti = SimpleNamespace(elenco_conversazioni=lambda: {"rileggibile": False, "preferita": None,
                                                           "conversazioni": []}) if con_voce_agenti else None
    ultime = _ultime_windows()
    m = _menu_windows(ultime, agenti)
    m.aggiorna()
    (s, _), (c1, copia), (c2, ritrascrivi) = m.voci[-3:]
    assert (s, c1, c2) == ("separatore", "comando", "comando")
    assert copia["label"] == "Copia l’ultima dettatura" and copia["state"] == "disabled"
    assert ritrascrivi["label"] == "Ritrascrivi l’ultima" and ritrascrivi["state"] == "disabled"
    ultime.pezzo("1:1", np.zeros(10), "Ciao.")
    ultime.consegnata("Ciao.")
    m.aggiorna()                                   # il menu si rifa' a ogni apertura
    (_, copia), (_, ritrascrivi) = m.voci[-2:]
    assert copia["state"] == ritrascrivi["state"] == "normal"
    copia["command"]()
    ritrascrivi["command"]()
    assert m.chiamate == ["copia", "ritrascrivi"]
    assert m.lavori and all(lavoro.daemon for lavoro in m.lavori)   # mai sul thread di Tk


def test_windows_menu_stesse_voci_del_mac():
    mac = (REPO_ROOT / "mac" / "detta.py").read_text(encoding="utf-8")
    win = WIN_APP.read_text(encoding="utf-8")
    for etichetta in ("Copia l’ultima dettatura", "Ritrascrivi l’ultima"):
        assert etichetta in mac and etichetta in win


def _azioni_menu_windows(ultime, passaggio=lambda audio: audio):
    appunti, eventi, righe = [], _queue.Queue(), []
    spazio = dict(ultime_dettature=ultime, eventi=eventi, _passaggio_unico=passaggio,
                  e_allucinazione=_e_allucinazione_windows(), _lock_trascrizione=_threading.Lock(),
                  _negli_appunti=appunti.append, CFG={"sostituzioni": {"cloud code": "Claude Code"}},
                  applica_sostituzioni=_funzioni_pure_app("applica_sostituzioni")["applica_sostituzioni"],
                  converti_punteggiatura_dettata=_funzioni_pure_app(
                      "converti_punteggiatura_dettata")["converti_punteggiatura_dettata"],
                  logging=SimpleNamespace(info=lambda m, *a: righe.append(m % a),
                                          exception=lambda m, *a: righe.append(m)))
    _dall_app_windows(["copia_ultima_dettatura", "ritrascrivi_ultima"], spazio)
    return spazio, appunti, eventi, righe


def test_windows_copia_l_ultima_dettatura_va_negli_appunti_e_il_testo_non_va_nel_registro():
    ultime = _ultime_windows()
    ultime.consegnata("Una frase privata.")
    spazio, appunti, _, righe = _azioni_menu_windows(ultime)
    spazio["copia_ultima_dettatura"]()
    assert appunti == ["Una frase privata."]
    assert righe and all("privata" not in r for r in righe)


def test_windows_ritrascrivi_l_ultima_unisce_i_pezzi_corregge_i_nomi_e_lo_dice_la_pill():
    ultime = _ultime_windows()
    ultime.pezzo("1:1", "Prima parte con cloud code.", "x")
    ultime.pezzo("1:2", "Grazie.", "x")            # un pezzo che oggi esce fantasma: non entra
    ultime.pezzo("1:3", "Seconda parte.", "x")
    ultime.consegnata("x")
    spazio, appunti, eventi, righe = _azioni_menu_windows(ultime)
    spazio["ritrascrivi_ultima"]()
    assert appunti == ["Prima parte con Claude Code. Seconda parte."]
    avvisi = [e[1] for e in list(eventi.queue)]
    assert avvisi[0] == "Ritrascrivo..." and "Appunti" in avvisi[-1]
    assert all("parte" not in r for r in righe)


def test_windows_ritrascrivi_senza_voce_o_con_errore_lo_dice_e_non_tocca_gli_appunti():
    ultime = _ultime_windows()
    ultime.pezzo("1:1", "", "x")
    ultime.consegnata("x")
    spazio, appunti, eventi, _ = _azioni_menu_windows(ultime)
    spazio["ritrascrivi_ultima"]()
    assert appunti == [] and list(eventi.queue)[-1][1] == "Niente da ritrascrivere"

    def rotto(audio):
        raise RuntimeError("motore")
    spazio, appunti, eventi, righe = _azioni_menu_windows(ultime, rotto)
    spazio["ritrascrivi_ultima"]()
    assert appunti == [] and list(eventi.queue)[-1][1] == "Ritrascrizione fallita"


def test_windows_avviso_con_la_sua_durata_nella_pill():
    eventi, testi, visibile, ora = _queue.Queue(), [], [False], [100.0]
    root = SimpleNamespace(deiconify=lambda: visibile.__setitem__(0, True),
                           withdraw=lambda: visibile.__setitem__(0, False), after=lambda *a: None)
    spazio = dict(queue=_queue, eventi=eventi, recording=False, time=SimpleNamespace(monotonic=lambda: ora[0]))
    classe = next(n for n in ast.parse(WIN_APP.read_text(encoding="utf-8")).body
                  if isinstance(n, ast.ClassDef) and n.name == "Pannello")
    metodo = next(n for n in classe.body if isinstance(n, ast.FunctionDef) and n.name == "tick")
    exec(compile(ast.Module(body=[metodo], type_ignores=[]), str(WIN_APP), "exec"), spazio)
    ui = SimpleNamespace(stato="nascosto", root=root, tick=lambda: None, _disegna_ascolto=lambda: None,
                         _disegna_trascrivo=lambda testo="Trascrivo...": testi.append(testo))
    eventi.put(("avviso", "Dettatura annullata", 1.5))
    eventi.put("nascosto")                          # la coda si chiude subito: l'avviso resta
    spazio["tick"](ui)
    assert visibile[0] and testi[-1] == "Dettatura annullata"
    ora[0] += 1.0
    spazio["tick"](ui)
    assert visibile[0]
    ora[0] += 0.6
    spazio["tick"](ui)
    assert not visibile[0]                          # 1,5 s, non i 4 degli errori


def test_windows_incolla_e_menu_condividono_il_lucchetto_degli_appunti():
    sorgente = WIN_APP.read_text(encoding="utf-8")
    for funzione in ("def paste_text", "def _negli_appunti"):
        corpo = sorgente.split(funzione, 1)[1].split("\ndef ", 1)[0]
        assert "with _lock_appunti:" in corpo


def test_windows_nessun_carattere_che_tk_non_sa_disegnare():
    """Tk 8.6 su Windows non disegna i caratteri fuori dal piano base (le emoji del Mac):
    pill e menu usano solo testo che Tk sa mostrare."""
    testo = WIN_APP.read_text(encoding="utf-8")
    assert [c for c in testo if ord(c) > 0xFFFF] == []
