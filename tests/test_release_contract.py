"""Contratto minimo della repo consegnabile Voce."""

import json
import os
import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
LINK_ULTIMA_VERSIONE = "https://github.com/salChiarenza/voce/releases/latest/download/Voce.zip"


def test_versione_unica_valida():
    versione = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    assert re.fullmatch(r"\d+\.\d+\.\d+(?:-rc\.\d+)?", versione)


def test_repo_contiene_entrambe_le_versioni_e_il_percorso_cliente():
    richiesti = [
        "README.md",
        "LICENSE",
        "VERSION",
        "CHANGELOG.md",
        "mac/Installa Voce.command",
        "mac/INSTALLA_CON_AI.md",
        "mac/Voce LeaderAI firmato.shortcut",
        "windows/install.bat",
        "windows/INSTALLA_CON_AI.md",
    ]
    mancanti = [path for path in richiesti if not (ROOT / path).exists()]
    assert mancanti == []


def test_installer_copiano_versione_e_missione_locale():
    mac = (ROOT / "mac/install.sh").read_text(encoding="utf-8")
    windows = (ROOT / "windows/install.ps1").read_text(encoding="utf-8")
    for testo in (mac, windows):
        assert "VERSION" in testo
        assert "INSTALLA_CON_AI.md" in testo
        assert "voce_hook.py" in testo


def test_dipendenze_del_prodotto_sono_bloccate():
    for path in (
        ROOT / "requirements-test.txt",
        ROOT / "mac/requirements.txt",
        ROOT / "windows/requirements.txt",
    ):
        righe = [
            riga.strip()
            for riga in path.read_text(encoding="utf-8").splitlines()
            if riga.strip() and not riga.lstrip().startswith("#")
        ]
        assert righe
        assert all("==" in riga for riga in righe)


def test_collaudo_codex_richiede_fiducia_e_prova_reale():
    for path in (
        ROOT / "mac/INSTALLA_CON_AI.md",
        ROOT / "windows/INSTALLA_CON_AI.md",
    ):
        testo = path.read_text(encoding="utf-8")
        assert "/hooks" in testo
        assert "risposta completa" in testo


def test_consegna_senza_passaggi_tecnici_del_proprietario():
    """Il contratto blocca il ritorno delle vecchie istruzioni manuali."""
    testi = {
        "README.md": (ROOT / "README.md").read_text(encoding="utf-8"),
        "mac/README.md": (ROOT / "mac/README.md").read_text(encoding="utf-8"),
        "mac/INSTALLA_CON_AI.md": (ROOT / "mac/INSTALLA_CON_AI.md").read_text(encoding="utf-8"),
        "windows/README.md": (ROOT / "windows/README.md").read_text(encoding="utf-8"),
        "windows/INSTALLA_CON_AI.md": (ROOT / "windows/INSTALLA_CON_AI.md").read_text(encoding="utf-8"),
    }
    vietate = ("Apri Download", "Estrai tutto", "estrai tutto", "[LINK_ARCHIVIO_VERIFICATO]", "/archive/")
    for nome, testo in testi.items():
        for frase in vietate:
            assert frase not in testo, f"{nome} chiede ancora un passaggio tecnico al proprietario: {frase}"

    for nome in ("mac/INSTALLA_CON_AI.md", "windows/INSTALLA_CON_AI.md"):
        assert LINK_ULTIMA_VERSIONE in testi[nome]   # la sorgente e' GitHub, sempre l'ultima versione
        assert "Drive" not in testi[nome].replace("PSDrive", "").replace("SystemDrive", "")
    for nome in ("mac/INSTALLA_CON_AI.md", "windows/INSTALLA_CON_AI.md"):
        assert "pacchetto Mac + Windows" in testi[nome]
        assert "git clone" not in testi[nome]


def test_consegna_resta_una_missione_unica_fino_alla_prova():
    for sistema in ("mac", "windows"):
        missione = (ROOT / sistema / "INSTALLA_CON_AI.md").read_text(encoding="utf-8")
        assert "Continuazione automatica dopo l'installazione" in missione
        assert "prosegui nella stessa sessione" in missione
        assert "Messaggio diretto per l'agente dopo l'installazione" not in missione
        assert "Invia questo messaggio direttamente" not in missione


def test_voce_ai_dichiara_audio_sintetico_su_mac_e_windows():
    mac = (ROOT / "mac/detta.py").read_text(encoding="utf-8")
    windows = (ROOT / "windows/voice_dettatura_windows.py").read_text(encoding="utf-8")
    avviso = "Le risposte dell'agente sono audio sintetico."
    assert avviso in mac
    assert avviso in windows
    assert "● AI" in mac
    assert "🔊 AI" in mac

    for sistema in ("mac", "windows"):
        privacy = (ROOT / sistema / "PRIVACY.md").read_text(encoding="utf-8")
        missione = (ROOT / sistema / "INSTALLA_CON_AI.md").read_text(encoding="utf-8")
        assert "non lo registra" in privacy
        assert "non lo salva" in privacy
        assert "audio sintetico" in missione


def test_nessuna_configurazione_personale_nella_repo():
    assert not list(ROOT.glob("**/config.local.json"))
    assert not list(ROOT.glob("**/voce.log"))


def test_profilo_mac_pubblico_e_la_fotocopia_funzionale_di_sal():
    cfg = json.loads((ROOT / "mac/config.json").read_text(encoding="utf-8"))
    assert cfg["hotkey"] == "cmd_r"
    assert cfg["voce"] == "Siri (Voce 2)"
    assert cfg["comando_voce"] == "Voce LeaderAI firmato"
    assert cfg["voce_shortcut_id"] == "com.apple.siri.natural.Francesca"
    assert cfg["voce_shortcut_velocita"] == 0.5
    assert cfg["voce_shortcut_tono"] == 1.0
    assert cfg["invio_automatico"] is True
    assert cfg["invio_automatico_ritardo_sec"] == 2.5
    assert cfg["invio_automatico_ritardo_conversazione_sec"] == 2.5
    assert cfg["invio_automatico_ritardo_chat_ai_sec"] == 2.0  # 17/09/2026: un secondo non bastava per bloccare con uno spazio
    assert cfg["mani_libere_soglia_voce"] == 0.018
    assert cfg["mani_libere_soglia_stop"] == 0.013
    codice = (ROOT / "mac/detta.py").read_text(encoding="utf-8")
    assert "TASTO = getattr(Key, cfg[\"hotkey\"])" in codice
    assert "TASTO_COMBO_VOCE = Key.left" in codice
    assert "_option_giu()" in codice
    assert "_cmd_giu()" in codice
    missione = (ROOT / "mac/INSTALLA_CON_AI.md").read_text(encoding="utf-8")
    assert "Cmd destro per dettare" in missione
    assert "Option + freccia sinistra per la voce" in missione
    assert "Cmd destro + Option per le mani libere" in missione
    assert "FOTOCOPIA_SAL_OK" in missione


def test_comportamento_invio_gemello_su_windows():
    mac = json.loads((ROOT / "mac/config.json").read_text(encoding="utf-8"))
    windows = json.loads((ROOT / "windows/config.json").read_text(encoding="utf-8"))
    assert windows["invio_automatico_ritardo_sec"] == mac["invio_automatico_ritardo_sec"]
    assert (
        windows["invio_automatico_ritardo_conversazione_sec"]
        == mac["invio_automatico_ritardo_conversazione_sec"]
    )
    assert (
        windows["invio_automatico_ritardo_chat_ai_sec"]
        == mac["invio_automatico_ritardo_chat_ai_sec"]
    )


def test_windows_dichiara_il_modello_piccolo_per_la_poca_memoria():
    """P-088 su Windows: sul Mac lo fa `scegli_modello` (rc.30, defaults nel codice);
    qui il prodotto dichiara il modello piccolo e la soglia nel suo config."""
    windows = json.loads((ROOT / "windows/config.json").read_text(encoding="utf-8"))
    assert windows["model_poca_memoria"] != windows["model"]
    assert windows["memoria_minima_modello_gb"] > 4         # un PC da 4 GB sta sotto la soglia


def test_coda_al_rilascio_del_tasto_gemella():
    """Mollare il tasto un pelo prima della fine frase non deve tagliare
    l'ultima sillaba: mezzo secondo di coda, solo sulla dettatura manuale."""
    mac = json.loads((ROOT / "mac/config.json").read_text(encoding="utf-8"))
    windows = json.loads((ROOT / "windows/config.json").read_text(encoding="utf-8"))
    assert mac["coda_rilascio_sec"] == 0.5
    assert windows["coda_rilascio_sec"] == mac["coda_rilascio_sec"]
    for sorgente in ("mac/detta.py", "windows/voice_dettatura_windows.py"):
        codice = (ROOT / sorgente).read_text(encoding="utf-8")
        assert 'CFG.get("coda_rilascio_sec", 0.5)' in codice or 'cfg.get("coda_rilascio_sec", 0.5)' in codice
        assert 'put("stop_coda")' in codice  # il rilascio manuale passa dalla coda
        assert 'elif cmd == "stop_coda":' in codice or 'elif command == "stop_coda":' in codice
        assert "time.sleep(CODA_RILASCIO_SEC)" in codice
    # il rilascio manuale e' l'unico a usare la coda: VAD e anti-incanto restano "stop"
    detta = (ROOT / "mac/detta.py").read_text(encoding="utf-8")
    assert detta.count('put("stop_coda")') == 1
    win = (ROOT / "windows/voice_dettatura_windows.py").read_text(encoding="utf-8")
    assert win.count('put("stop_coda")') == 1

def test_tetto_registrazione_col_tasto_gemello_su_windows():
    mac = json.loads((ROOT / "mac/config.json").read_text(encoding="utf-8"))
    windows = json.loads((ROOT / "windows/config.json").read_text(encoding="utf-8"))
    assert mac["max_registrazione_tasto_sec"] == 300
    assert windows["max_registrazione_tasto_sec"] == mac["max_registrazione_tasto_sec"]
    # il tetto duro deve stare sopra il tetto soft, su entrambe
    assert mac["max_registrazione_tasto_sec"] > mac["max_registrazione_sec"]
    assert windows["max_registrazione_tasto_sec"] > windows["max_recording_sec"]


def test_trascrizione_progressiva_gemella_su_windows():
    mac = json.loads((ROOT / "mac/config.json").read_text(encoding="utf-8"))
    windows = json.loads((ROOT / "windows/config.json").read_text(encoding="utf-8"))
    for chiave in ("trascrizione_progressiva", "trascrizione_progressiva_blocco_sec"):
        assert chiave in mac and chiave in windows, chiave
        assert windows[chiave] == mac[chiave], chiave
    assert mac["trascrizione_progressiva"] is True
    assert mac["trascrizione_progressiva_blocco_sec"] == 12


def test_app_viva_sal_non_puo_derivare_dal_profilo_pubblico():
    # Controllo di chi ha una copia viva dell'app: indica la cartella con VOCE_RUNTIME.
    cartella = os.environ.get("VOCE_RUNTIME")
    if not cartella or not (Path(cartella) / "config.local.json").exists():
        pytest.skip("Serve VOCE_RUNTIME: la cartella di una copia viva dell'app")
    runtime = Path(cartella)
    locale = runtime / "config.local.json"

    defaults = json.loads((ROOT / "mac/config.json").read_text(encoding="utf-8"))
    overrides = json.loads(locale.read_text(encoding="utf-8"))
    effettiva = defaults | overrides
    chiavi_standard = (
        "hotkey",
        "voce",
        "comando_voce",
        "invio_automatico",
        "invio_automatico_ritardo_sec",
        "invio_automatico_ritardo_conversazione_sec",
        "coda_rilascio_sec",

        "invio_automatico_ritardo_chat_ai_sec",
        "detta_pulito",
        "pulizia_in_conversazione",
        "mani_libere_attivazione_sec",
        "mani_libere_silenzio_sec",
        "mani_libere_soglia_voce",
        "mani_libere_soglia_stop",
        "mani_libere_autospegnimento_min",
    )
    assert {key: effettiva[key] for key in chiavi_standard} == {
        key: defaults[key] for key in chiavi_standard
    }
    for file_name in ("detta.py", "parla.py", "voce_hook.py", "voce_lib.py", "voce"):
        assert (runtime / file_name).read_bytes() == (ROOT / "mac" / file_name).read_bytes()


def test_guide_partono_dalla_diagnosi_e_spiegano_i_testi_scritti_da_soli():
    """P-190 (17/10/2026): prima i requisiti, poi l'installazione; chi l'ha gia' installata
    trova la sezione del sintomo con le righe di registro sempre scritte, non quelle di debug."""
    for sistema in ("mac", "windows"):
        guida = (ROOT / sistema / "INSTALLA_CON_AI.md").read_text(encoding="utf-8")
        assert guida.index("## Fase 0: diagnosi, prima di installare") < guida.index("## Missione unica dell'agente")
        assert "la Voce non va per questo computer" in guida
        assert "## Se la Voce scrive da sola" in guida
        assert "invio automatico premuto" in guida
        assert "Python 3.11" in guida and "16 GB" in guida
    mac = (ROOT / "mac/INSTALLA_CON_AI.md").read_text(encoding="utf-8")
    assert "bash mac/voce diagnosi" in mac
    assert "incollato \\(app bersaglio" in mac
    assert "Mani libere: SPENTE" in mac and "NESSUN TESTO DA SOLO" in mac
    assert "debug_dettature" in mac  # dice che le righe «grezzo:» non ci sono di serie


def test_righe_di_registro_della_guida_esistono_davvero_nel_codice():
    mac = (ROOT / "mac/detta.py").read_text(encoding="utf-8")
    windows = (ROOT / "windows/voice_dettatura_windows.py").read_text(encoding="utf-8")
    for riga in ("incollato (app bersaglio", "invio automatico premuto", "combo mani libere: ON",
                 "mani libere: ascolto partito dal volume", "mani libere: ATTIVE (%s)",
                 "gia' accese all'avvio", "registrazione avviata"):
        assert riga in mac, riga
    for riga in ("incollato (programma bersaglio", "invio automatico premuto"):
        assert riga in windows, riga
