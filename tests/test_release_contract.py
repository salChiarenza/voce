"""Contratto minimo della repo consegnabile Voce."""

import re
from pathlib import Path


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
