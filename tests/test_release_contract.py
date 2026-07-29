"""Contratto minimo della repo consegnabile Voce."""

import json
import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_versione_unica_valida():
    versione = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    assert re.fullmatch(r"\d+\.\d+\.\d+(?:-rc\.\d+)?", versione)


def test_repo_contiene_entrambe_le_versioni_e_il_percorso_cliente():
    richiesti = [
        "AGENTS.md",
        "CLAUDE.md",
        "README.md",
        "VERSION",
        "CHANGELOG.md",
        "EMAIL_CONSEGNA.md",
        "mac/Installa Voce.command",
        "mac/INSTALLA_CON_AI.md",
        "mac/Voce LeaderAI firmato.shortcut",
        "windows/install.bat",
        "windows/INSTALLA_CON_AI.md",
    ]
    mancanti = [path for path in richiesti if not (ROOT / path).exists()]
    assert mancanti == []


def test_claude_legge_lo_stesso_contratto():
    assert (ROOT / "CLAUDE.md").read_text(encoding="utf-8").strip() == "@AGENTS.md"


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


def test_email_impone_versione_esatta_e_prova_destinatario():
    email = (ROOT / "EMAIL_CONSEGNA.md").read_text(encoding="utf-8")
    for frase in (
        "[LINK_ARCHIVIO_VERIFICATO]",
        "stesso accesso del destinatario",
        "PROVA_DESTINATARIO_OK",
        "INVIO_OK",
    ):
        assert frase in email


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


def test_app_viva_sal_non_puo_derivare_dal_profilo_pubblico():
    runtime = Path.home() / "leaderai" / "tools" / "voce"
    locale = runtime / "config.local.json"
    if not locale.exists():
        pytest.skip("Controllo disponibile solo sulla macchina di Sal")

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
        assert (runtime / file_name).resolve() == (ROOT / "mac" / file_name).resolve()
