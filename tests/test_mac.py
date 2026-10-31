"""Test delle funzioni pure della versione Mac di Voce."""
import ast
import json
import logging
import os
import plistlib
import sqlite3
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "mac"))
import voce_lib
import voce_hook
import parla


@pytest.fixture(autouse=True)
def _gancio_nella_cartella_temporanea(tmp_path, monkeypatch):
    """Il gancio scrive log e `LETTI_DAL_REGISTRO` nella sua cartella: mai in quella della repo,
    dove un file rimasto da una prova farebbe tacere la prova dopo."""
    casa = tmp_path / "casa-gancio"
    casa.mkdir()
    monkeypatch.setattr(voce_hook, "BASE", casa)


def test_base_operativa_conserva_la_cartella_dei_symlink(tmp_path):
    sorgente = tmp_path / "repo" / "mac"
    runtime = tmp_path / "leaderai" / "tools" / "voce"
    sorgente.mkdir(parents=True)
    runtime.mkdir(parents=True)
    modulo = sorgente / "voce_lib.py"
    modulo.touch()
    (runtime / "voce_lib.py").symlink_to(modulo)

    base = voce_lib._base_operativa(
        module_file=modulo,
        argv0=runtime / "detta.py",
    )

    assert base == runtime


def test_carica_config():
    cfg = voce_lib.carica_config()
    assert cfg["lingua"] == "it"
    assert cfg["hotkey"] == "cmd_r"  # detta: Cmd destro; voce/mani libere usano i combo fissi dell'app
    assert cfg["modello"].startswith("mlx-community/")


def test_config_prodotto_unico_con_override_personale(tmp_path, monkeypatch):
    defaults = tmp_path / "config.json"
    local = tmp_path / "config.local.json"
    defaults.write_text(
        json.dumps({"voce": "Siri (Voce 2)", "glossario": ["LeaderAI"], "soglia": 1}),
        encoding="utf-8",
    )
    local.write_text(
        json.dumps({"glossario": ["Cliente personale"], "soglia_locale": 2}),
        encoding="utf-8",
    )
    monkeypatch.setattr(voce_lib, "CONFIG_DEFAULT", defaults)
    monkeypatch.setattr(voce_lib, "CONFIG_LOCAL", local)

    cfg = voce_lib.carica_config()

    assert cfg["voce"] == "Siri (Voce 2)"
    assert cfg["glossario"] == ["Cliente personale"]
    assert cfg["soglia"] == 1
    assert cfg["soglia_locale"] == 2


def test_aggiornamento_config_applica_fotocopia_e_conserva_solo_dati_personali(tmp_path):
    defaults = tmp_path / "defaults.json"
    current = tmp_path / "config.json"
    defaults.write_text(
        json.dumps(
            {
                "voce": "Siri (Voce 2)",
                "comando_voce": "Voce LeaderAI firmato",
                "glossario": ["LeaderAI"],
                "sostituzioni": {},
                "mani_libere_soglia_voce": 0.018,
                "detta_pulito": True,
                "invio_automatico_ritardo_conversazione_sec": 2.5,
                "nuovo_default": "entra",
            }
        ),
        encoding="utf-8",
    )
    current.write_text(
        json.dumps(
            {
                "voce": "Alice",
                "comando_voce": "Voce Siri",
                "glossario": ["Cliente X"],
                "sostituzioni": {"pronotare": "prenotare"},
                "mani_libere_soglia_voce": 0.077,
                "detta_pulito": False,
                "invio_automatico_ritardo_conversazione_sec": 1.2,
                "chiave_cliente": "resta",
            }
        ),
        encoding="utf-8",
    )

    voce_hook.unisci_config(str(defaults), str(current))
    merged = json.loads(current.read_text(encoding="utf-8"))

    assert merged["voce"] == "Siri (Voce 2)"
    assert merged["comando_voce"] == "Voce LeaderAI firmato"
    assert merged["glossario"] == ["Cliente X"]
    assert merged["sostituzioni"] == {"pronotare": "prenotare"}
    assert merged["mani_libere_soglia_voce"] == 0.018
    assert merged["detta_pulito"] is True
    assert merged["invio_automatico_ritardo_conversazione_sec"] == 2.5
    assert "chiave_cliente" not in merged
    assert merged["nuovo_default"] == "entra"
    assert (tmp_path / "config.pre-aggiornamento.json").exists()


def _crea_db_shortcut(tmp_path, voce_id, velocita=None, tono=None):
    db = tmp_path / "Shortcuts.sqlite"
    params = {
        "WFSpeakTextVoice": voce_id,
        "WFText": "test",
    }
    if velocita is not None:
        params["WFSpeakTextRate"] = velocita
    if tono is not None:
        params["WFSpeakTextPitch"] = tono
    actions = [
        {
            "WFWorkflowActionIdentifier": "is.workflow.actions.speaktext",
            "WFWorkflowActionParameters": params,
        }
    ]
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE ZSHORTCUT (Z_PK INTEGER, ZNAME TEXT)")
        conn.execute("CREATE TABLE ZSHORTCUTACTIONS (ZSHORTCUT INTEGER, ZDATA BLOB)")
        conn.execute(
            "INSERT INTO ZSHORTCUT (Z_PK, ZNAME) VALUES (?, ?)",
            (1, "Voce LeaderAI firmato"),
        )
        conn.execute(
            "INSERT INTO ZSHORTCUTACTIONS (ZSHORTCUT, ZDATA) VALUES (?, ?)",
            (1, plistlib.dumps(actions, fmt=plistlib.FMT_BINARY)),
        )
    return db


def test_profilo_shortcut_accetta_la_fotocopia_esatta(tmp_path):
    db = _crea_db_shortcut(
        tmp_path,
        voce_id="com.apple.siri.natural.Francesca",
    )
    cfg = {
        "comando_voce": "Voce LeaderAI firmato",
        "voce_shortcut_id": "com.apple.siri.natural.Francesca",
        "voce_shortcut_velocita": 0.5,
        "voce_shortcut_tono": 1.0,
    }

    profilo = voce_hook.controlla_profilo_shortcut(db_path=db, cfg=cfg)

    assert profilo == {
        "voce_id": "com.apple.siri.natural.Francesca",
        "velocita": 0.5,
        "tono": 1.0,
    }


def test_profilo_shortcut_blocca_voce_o_velocita_diverse(tmp_path):
    db = _crea_db_shortcut(
        tmp_path,
        voce_id="com.apple.siri.natural.Paolo",
        velocita=0.35,
    )
    cfg = {
        "comando_voce": "Voce LeaderAI firmato",
        "voce_shortcut_id": "com.apple.siri.natural.Francesca",
        "voce_shortcut_velocita": 0.5,
        "voce_shortcut_tono": 1.0,
    }

    try:
        voce_hook.controlla_profilo_shortcut(db_path=db, cfg=cfg)
    except RuntimeError as exc:
        assert "Profilo voce diverso" in str(exc)
        assert "voce_id" in str(exc)
        assert "velocita" in str(exc)
    else:
        raise AssertionError("Il profilo diverso doveva essere bloccato")


def test_reinstallazione_hook_rimuove_anche_il_vecchio_path_tools(tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_text(
        json.dumps(
            {
                "hooks": {
                    "Stop": [
                        {
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": "python /Users/utente/progetto/tools/voce/voce_hook.py",
                                }
                            ]
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )

    voce_hook.collega_hook(settings)
    data = json.loads(settings.read_text(encoding="utf-8"))
    commands = [
        hook.get("command", "")
        for gruppo in data["hooks"]["Stop"]
        for hook in gruppo.get("hooks", [])
    ]

    assert sum("voce_hook.py" in command for command in commands) == 1


def test_collegamento_hook_conserva_hook_esistenti(tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_text(
        json.dumps(
            {
                "hooks": {
                    "Stop": [
                        {"hooks": [{"type": "command", "command": "echo esistente"}]}
                    ]
                }
            }
        ),
        encoding="utf-8",
    )

    voce_hook.collega_hook(settings)
    data = json.loads(settings.read_text(encoding="utf-8"))
    commands = [
        hook.get("command", "")
        for gruppo in data["hooks"]["Stop"]
        for hook in gruppo.get("hooks", [])
    ]

    assert "echo esistente" in commands
    assert any("voce_hook.py" in command for command in commands)
    assert settings.with_name("settings.json.pre-voce.bak").exists()


def test_parla_deposita_e_non_uccide_la_lettura_in_corso(tmp_path, monkeypatch):
    """Una nuova risposta non tronca piu' quella in lettura: va in attesa e
    la leggera' il lettore gia' in corsa (caso 30/08/2026: tre risposte in
    21 secondi, solo l'ultima arrivava in fondo)."""
    pendente = tmp_path / "LETTURA_PENDENTE"
    avvii, comandi = [], []
    monkeypatch.setattr(parla, "LETTURA_PENDENTE", pendente)
    monkeypatch.setattr(parla, "_lettore_in_corsa", lambda: True)  # lettore vivo
    monkeypatch.setattr(parla, "_pid_lettore", lambda: 123)
    monkeypatch.setattr(parla.subprocess, "Popen", lambda *a, **k: avvii.append(a))
    monkeypatch.setattr(parla.subprocess, "run", lambda c, **k: comandi.append(c))

    parla.parla("prima risposta")
    parla.parla("seconda risposta")

    assert parla.prendi_pendente(pendente) == "seconda risposta"  # vince l'ultima
    assert avvii == []    # nessun secondo lettore
    assert comandi == []  # e soprattutto nessun pkill della voce in corso


def test_parla_avvia_un_lettore_sganciato_quando_manca(tmp_path, monkeypatch):
    """Senza lettore in corsa ne parte uno solo, in una sessione nuova: deve
    sopravvivere all'hook Stop (timeout 10s) per letture piu' lunghe."""
    avvii = []
    monkeypatch.setattr(parla, "BASE", tmp_path)
    monkeypatch.setattr(parla, "LETTURA_PENDENTE", tmp_path / "LETTURA_PENDENTE")
    monkeypatch.setattr(parla, "LETTORE_LOCK", tmp_path / "LETTORE_LOCK")
    monkeypatch.setattr(
        parla.subprocess, "Popen",
        lambda comando, **kw: avvii.append((comando, kw.get("start_new_session"))),
    )

    parla.parla("risposta da leggere")

    assert len(avvii) == 1
    comando, sessione_nuova = avvii[0]
    assert comando[-1] == "--lettore"
    assert sessione_nuova is True


def test_parla_scartata_se_arriva_mentre_sal_sta_dettando(tmp_path, monkeypatch):
    """Una risposta chiusa mentre il turno vocale e' ancora aperto e' vecchia:
    non deve parlare sopra Sal ne' restare in coda dopo la sua domanda."""
    pendente = tmp_path / "LETTURA_PENDENTE"
    turno_utente = tmp_path / "TURNO_UTENTE"
    turno_utente.touch()
    avvii = []
    monkeypatch.setattr(parla, "LETTURA_PENDENTE", pendente)
    monkeypatch.setattr(parla, "FLAG_TURNO_UTENTE", turno_utente, raising=False)
    monkeypatch.setattr(parla, "_avvia_lettore_se_serve", lambda: avvii.append(True))
    monkeypatch.setattr(parla, "_traccia", lambda _messaggio: None)

    parla.parla("Risposta del turno precedente")

    assert parla.prendi_pendente(pendente) is None
    assert avvii == []


def test_lettore_non_parte_se_sal_inizia_a_dettare_dopo_la_coda(tmp_path, monkeypatch):
    lette = []
    turno_utente = tmp_path / "TURNO_UTENTE"
    monkeypatch.setattr(parla, "LETTURA_PENDENTE", tmp_path / "LETTURA_PENDENTE")
    monkeypatch.setattr(parla, "LETTORE_LOCK", tmp_path / "LETTORE_LOCK")
    monkeypatch.setattr(parla, "LETTORE_PID", tmp_path / "LETTORE_PID")
    monkeypatch.setattr(parla, "FLAG_PARLANDO", tmp_path / "PARLANDO")
    monkeypatch.setattr(parla, "FLAG_TURNO_UTENTE", turno_utente, raising=False)
    monkeypatch.setattr(parla, "_leggi_adesso", lambda testo: lette.append(testo))
    monkeypatch.setattr(parla, "_traccia", lambda _messaggio: None)
    parla.scrivi_pendente("Risposta gia' accodata")
    turno_utente.touch()

    parla.lettore()

    assert lette == []
    assert parla.prendi_pendente() is None


def test_turni_vocali_sovrapposti_non_liberano_il_turno_piu_nuovo(tmp_path, monkeypatch):
    """La trascrizione vecchia puo' finire dopo l'inizio della nuova dettatura:
    chiudendo il suo turno non deve riaprire la voce sopra Sal."""
    flag = tmp_path / "TURNO_UTENTE"
    monkeypatch.setattr(voce_lib, "FLAG_TURNO_UTENTE", flag, raising=False)
    apri = getattr(voce_lib, "apri_turno_utente", None)
    chiudi = getattr(voce_lib, "chiudi_turno_utente", None)
    assert callable(apri) and callable(chiudi)

    primo = apri()
    secondo = apri()
    chiudi(primo)
    assert flag.exists()
    chiudi(secondo)
    assert not flag.exists()


def test_parla_rilettura_immediata_dopo_stop_attende_rilascio_nel_figlio(tmp_path, monkeypatch):
    avvii = []
    monkeypatch.setattr(parla, "BASE", tmp_path)
    monkeypatch.setattr(parla, "LETTURA_PENDENTE", tmp_path / "LETTURA_PENDENTE")
    monkeypatch.setattr(parla, "LETTORE_PID", tmp_path / "LETTORE_PID")
    monkeypatch.setattr(parla, "FLAG_PARLANDO", tmp_path / "PARLANDO")
    monkeypatch.setattr(parla.subprocess, "run", lambda *a, **kw: None)
    monkeypatch.setattr(parla, "_lettore_in_corsa", lambda: True)
    monkeypatch.setattr(parla.subprocess, "Popen", lambda comando, **kw: avvii.append(comando))
    parla.scrivi_pendente("risposta interrotta", origine={"id": "A", "nome": "Claude"})
    assert parla.prendi_pendente() == "risposta interrotta"
    parla.ferma()

    # Il vecchio processo sta ancora rilasciando il lock dopo SIGTERM.
    assert parla.rileggi_ultima()

    assert len(avvii) == 1
    assert avvii[0][-1] == "--lettore-attendi"
    assert parla.prendi_pendente() == "risposta interrotta"


def test_prendi_pendente_vince_l_ultimo(tmp_path):
    pendente = tmp_path / "LETTURA_PENDENTE"
    parla.scrivi_pendente("risposta vecchia", pendente)
    parla.scrivi_pendente("risposta nuova", pendente)

    assert parla.prendi_pendente(pendente) == "risposta nuova"
    assert parla.prendi_pendente(pendente) is None  # l'attesa e' un posto solo


def test_prendi_pendente_conserva_fonti_distinte_e_aggiorna_solo_la_stessa(tmp_path):
    pendente = tmp_path / "LETTURA_PENDENTE"
    parla.scrivi_pendente("prima A", pendente, {"id": "A", "nome": "Claude: Proposta"})
    parla.scrivi_pendente("prima B", pendente, {"id": "B", "nome": "Codex: Voce"})
    parla.scrivi_pendente("ultima A", pendente, {"id": "A", "nome": "Claude: Proposta"})

    assert parla.prendi_pendente(pendente, con_origine=True) == {
        "id": "A", "nome": "Claude: Proposta", "testo": "ultima A",
    }
    assert parla.prendi_pendente(pendente, con_origine=True)["testo"] == "prima B"
    assert not parla.ha_pendenti(pendente)


def test_prendi_pendente_scelta_legge_solo_conversazione_selezionata(tmp_path, monkeypatch):
    pendente = tmp_path / "LETTURA_PENDENTE"
    avvii = []
    monkeypatch.setattr(parla, "LETTURA_PENDENTE", pendente)
    monkeypatch.setattr(parla, "_avvia_lettore_se_serve", lambda: avvii.append(True))
    parla.scrivi_pendente("risposta A", origine={"id": "A", "nome": "Claude"})
    parla.scrivi_pendente("risposta B", origine={"id": "B", "nome": "Codex"})

    assert not parla.scegli_conversazione("inesistente")
    assert parla.scegli_conversazione("B")
    assert parla.prendi_pendente() == "risposta B"
    assert parla.prendi_pendente() is None
    assert not parla.ha_pendenti()
    stato = parla.elenco_conversazioni()
    assert stato["preferita"] == "B"
    assert stato["rileggibile"]
    assert next(c for c in stato["conversazioni"] if c["id"] == "A")["in_attesa"]
    assert parla.scegli_conversazione(None)
    assert parla.ha_pendenti()
    assert parla.prendi_pendente() == "risposta A"
    assert len(avvii) == 2


def test_prendi_pendente_migra_vecchio_testo_e_conserva_ultima(tmp_path, monkeypatch):
    pendente = tmp_path / "LETTURA_PENDENTE"
    pendente.write_text("risposta dalla versione precedente", encoding="utf-8")
    monkeypatch.setattr(parla, "LETTURA_PENDENTE", pendente)
    monkeypatch.setattr(parla, "_avvia_lettore_se_serve", lambda: None)

    assert parla.prendi_pendente() == "risposta dalla versione precedente"
    assert parla.prendi_pendente() is None
    assert parla.rileggi_ultima()
    assert parla.prendi_pendente() == "risposta dalla versione precedente"
    assert pendente.stat().st_mode & 0o777 == 0o600


def test_ferma_conserva_rilettura_e_preferenza(tmp_path, monkeypatch):
    monkeypatch.setattr(parla, "LETTURA_PENDENTE", tmp_path / "LETTURA_PENDENTE")
    monkeypatch.setattr(parla, "LETTORE_PID", tmp_path / "LETTORE_PID")
    monkeypatch.setattr(parla, "FLAG_PARLANDO", tmp_path / "PARLANDO")
    monkeypatch.setattr(parla.subprocess, "run", lambda *a, **k: None)
    monkeypatch.setattr(parla, "_avvia_lettore_se_serve", lambda: None)
    parla.scrivi_pendente("risposta da recuperare", origine={"id": "A", "nome": "Claude"})
    assert parla.scegli_conversazione("A")
    assert parla.prendi_pendente() == "risposta da recuperare"
    parla.scrivi_pendente("altra risposta", origine={"id": "B", "nome": "Codex"})

    parla.ferma()

    assert not parla.ha_pendenti()
    assert parla.elenco_conversazioni()["preferita"] == "A"
    assert parla.rileggi_ultima()
    assert parla.prendi_pendente() == "risposta da recuperare"


def test_prendi_pendente_rilettura_non_perde_risposta_nuova(tmp_path, monkeypatch):
    monkeypatch.setattr(parla, "LETTURA_PENDENTE", tmp_path / "LETTURA_PENDENTE")
    monkeypatch.setattr(parla, "_avvia_lettore_se_serve", lambda: None)
    assert not parla.rileggi_ultima()
    parla.scrivi_pendente("già ascoltata")
    assert parla.prendi_pendente() == "già ascoltata"
    parla.scrivi_pendente("appena arrivata")
    assert parla.rileggi_ultima()

    assert parla.prendi_pendente() == "già ascoltata"
    assert parla.prendi_pendente() == "appena arrivata"


def test_prendi_pendente_annuncio_non_sostituisce_ultima_risposta(tmp_path, monkeypatch):
    monkeypatch.setattr(parla, "LETTURA_PENDENTE", tmp_path / "LETTURA_PENDENTE")
    monkeypatch.setattr(parla, "_avvia_lettore_se_serve", lambda: None)
    parla.scrivi_pendente("risposta dell'agente", origine={"id": "A", "nome": "Claude"})
    assert parla.prendi_pendente() == "risposta dell'agente"
    parla.scrivi_pendente("Voce AI spenta")
    assert parla.prendi_pendente() == "Voce AI spenta"

    assert parla.rileggi_ultima()
    assert parla.prendi_pendente() == "risposta dell'agente"


def test_prendi_pendente_annunci_toggle_passano_anche_con_scelta(tmp_path, monkeypatch):
    monkeypatch.setattr(parla, "LETTURA_PENDENTE", tmp_path / "LETTURA_PENDENTE")
    monkeypatch.setattr(parla, "_avvia_lettore_se_serve", lambda: None)
    parla.scrivi_pendente("risposta A", origine={"id": "A", "nome": "Claude"})
    assert parla.prendi_pendente() == "risposta A"
    assert parla.scegli_conversazione("A")
    parla.scrivi_pendente("Voce AI accesa")

    assert parla.ha_pendenti()
    assert parla.prendi_pendente() == "Voce AI accesa"
    assert [c["id"] for c in parla.elenco_conversazioni()["conversazioni"]] == ["A"]
    assert parla.rileggi_ultima()
    assert parla.prendi_pendente() == "risposta A"


def test_prendi_pendente_rilettura_scelta_non_legge_due_volte_la_stessa_attesa(tmp_path, monkeypatch):
    monkeypatch.setattr(parla, "LETTURA_PENDENTE", tmp_path / "LETTURA_PENDENTE")
    monkeypatch.setattr(parla, "_avvia_lettore_se_serve", lambda: None)
    parla.scrivi_pendente("risposta da leggere", origine={"id": "A", "nome": "Claude"})
    assert parla.scegli_conversazione("A")
    assert parla.rileggi_ultima()

    assert parla.prendi_pendente() == "risposta da leggere"
    assert parla.prendi_pendente() is None


def test_prendi_pendente_scritture_parallele_non_perdono_fonti(tmp_path):
    import subprocess
    pendente = tmp_path / "LETTURA_PENDENTE"
    script = (
        "import sys; from pathlib import Path; import parla; "
        "parla.scrivi_pendente(sys.argv[2], Path(sys.argv[1]), "
        "{'id': sys.argv[2], 'nome': 'Conversazione ' + sys.argv[2]})"
    )
    env = dict(os.environ, PYTHONPATH=str(REPO_ROOT / "mac"))
    processi = [subprocess.Popen(
        [sys.executable, "-c", script, str(pendente), str(i)], env=env,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    ) for i in range(8)]
    for processo in processi:
        _, errore = processo.communicate(timeout=15)
        assert processo.returncode == 0, errore.decode()
    lette = [parla.prendi_pendente(pendente, con_origine=True)["id"] for _ in range(8)]
    assert set(lette) == {str(i) for i in range(8)}
    assert parla.prendi_pendente(pendente) is None


def test_prendi_pendente_limita_storia_a_otto_conversazioni(tmp_path, monkeypatch):
    monkeypatch.setattr(parla, "LETTURA_PENDENTE", tmp_path / "LETTURA_PENDENTE")
    monkeypatch.setattr(parla, "_avvia_lettore_se_serve", lambda: None)
    parla.scrivi_pendente("preserva selezionata", origine={"id": "A"})
    assert parla.scegli_conversazione("A")
    for i in range(12):
        parla.scrivi_pendente(str(i), origine={"id": str(i)})
    stato = parla.elenco_conversazioni()
    assert len(stato["conversazioni"]) == 8
    assert stato["preferita"] == "A"
    assert parla.prendi_pendente() == "preserva selezionata"


def test_lettore_legge_in_fila_e_poi_pulisce(tmp_path, monkeypatch):
    """Il lettore legge anche cio' che arriva DURANTE una lettura, col flag
    PARLANDO alzato per tutta la corsa; alla fine toglie flag e lock."""
    flag = tmp_path / "PARLANDO"
    pendente = tmp_path / "LETTURA_PENDENTE"
    lock = tmp_path / "LETTORE_PID"
    lette = []

    def leggi_finto(testo):
        assert flag.exists()  # mani-libere in pausa mentre la voce parla
        lette.append(testo)
        if testo == "prima":
            parla.scrivi_pendente("arrivata durante", pendente)

    monkeypatch.setattr(parla, "BASE", tmp_path)  # il registro resta nel tmp
    monkeypatch.setattr(parla, "FLAG_PARLANDO", flag)
    monkeypatch.setattr(parla, "LETTURA_PENDENTE", pendente)
    monkeypatch.setattr(parla, "LETTORE_LOCK", tmp_path / "LETTORE_LOCK")
    monkeypatch.setattr(parla, "LETTORE_PID", lock)
    monkeypatch.setattr(parla, "_leggi_adesso", leggi_finto)
    parla.scrivi_pendente("prima", pendente)

    parla.lettore()

    assert lette == ["prima", "arrivata durante"]
    assert not flag.exists()
    assert not lock.exists()


def test_lettore_unico_col_lock_del_kernel(tmp_path, monkeypatch):
    """Il flock ammette un solo lettore e si libera col rilascio (o con la
    morte del processo): niente lock stantii da rubare."""
    monkeypatch.setattr(parla, "LETTORE_LOCK", tmp_path / "LETTORE_LOCK")

    assert parla._prendi_lock() is True        # primo lettore
    assert parla._lettore_in_corsa() is True   # visto da fuori
    assert parla._prendi_lock() is False       # niente secondo lettore

    parla._rilascia_lock()
    assert parla._lettore_in_corsa() is False
    assert parla._prendi_lock() is True        # libero: si riprende subito
    parla._rilascia_lock()


def test_lettore_in_attesa_del_rilascio_non_parte_in_parallelo(tmp_path, monkeypatch):
    import fcntl
    import threading
    iniziato = threading.Event()
    acquisito = threading.Event()
    monkeypatch.setattr(parla, "LETTORE_LOCK", tmp_path / "LETTORE_LOCK")
    precedente = os.open(parla.LETTORE_LOCK, os.O_CREAT | os.O_RDWR, 0o600)
    fcntl.flock(precedente, fcntl.LOCK_EX)

    def attendi_rilascio():
        iniziato.set()
        if parla._prendi_lock(attendi=True):
            acquisito.set()

    attesa = threading.Thread(target=attendi_rilascio, daemon=True)
    attesa.start()
    assert iniziato.wait(1)
    assert not acquisito.wait(0.02)
    os.close(precedente)
    attesa.join(timeout=1)
    try:
        assert not attesa.is_alive()
        assert acquisito.is_set()
    finally:
        parla._rilascia_lock()


def test_lettore_annuncia_cambio_fonte_senza_id_e_non_interrompe(tmp_path, monkeypatch):
    lette = []
    monkeypatch.setattr(parla, "BASE", tmp_path)
    monkeypatch.setattr(parla, "FLAG_PARLANDO", tmp_path / "PARLANDO")
    monkeypatch.setattr(parla, "LETTURA_PENDENTE", tmp_path / "LETTURA_PENDENTE")
    monkeypatch.setattr(parla, "LETTORE_LOCK", tmp_path / "LETTORE_LOCK")
    monkeypatch.setattr(parla, "LETTORE_PID", tmp_path / "LETTORE_PID")

    def lettura(testo):
        lette.append(testo)
        if len(lette) == 1:
            # La selezione cambia mentre A parla: il primo testo arriva intero.
            assert parla.scegli_conversazione("id-privato-B")
            parla.scrivi_pendente("A nuova in attesa", origine={"id": "id-privato-A", "nome": "Claude"})

    monkeypatch.setattr(parla, "_leggi_adesso", lettura)
    parla.scrivi_pendente("Risposta A completa.", origine={"id": "id-privato-A", "nome": "Claude"})
    parla.scrivi_pendente("Risposta B completa.", origine={"id": "id-privato-B", "nome": "Codex"})

    parla.lettore()

    assert lette == ["Claude.\n\nRisposta A completa.", "Codex.\n\nRisposta B completa."]
    assert not parla.ha_pendenti()  # A resta salvata, senza un lettore in ciclo
    assert next(c for c in parla.elenco_conversazioni()["conversazioni"] if c["id"] == "id-privato-A")["in_attesa"]
    assert "Risposta A completa" not in (tmp_path / "voce.log").read_text()


def test_lettore_recupera_arrivo_nel_momento_dell_uscita(tmp_path, monkeypatch):
    lette = []
    monkeypatch.setattr(parla, "BASE", tmp_path)
    monkeypatch.setattr(parla, "FLAG_PARLANDO", tmp_path / "PARLANDO")
    monkeypatch.setattr(parla, "LETTURA_PENDENTE", tmp_path / "LETTURA_PENDENTE")
    monkeypatch.setattr(parla, "LETTORE_LOCK", tmp_path / "LETTORE_LOCK")
    monkeypatch.setattr(parla, "LETTORE_PID", tmp_path / "LETTORE_PID")
    monkeypatch.setattr(parla, "_leggi_adesso", lette.append)
    rilascia = parla._rilascia_lock

    def rilascio_con_arrivo():
        rilascia()
        if len(lette) == 1:
            parla.scrivi_pendente("arrivo durante uscita")

    monkeypatch.setattr(parla, "_rilascia_lock", rilascio_con_arrivo)
    parla.scrivi_pendente("prima")

    parla.lettore()

    assert lette == ["prima", "arrivo durante uscita"]
    assert not parla.ha_pendenti()


def test_lettura_incantata_viene_uccisa_e_si_va_avanti(tmp_path, monkeypatch):
    """Uno `shortcuts run` appeso non deve ammutolire le risposte successive:
    scaduto il tetto (proporzionale al testo) la lettura si uccide."""
    comandi = []

    def run_finto(comando, **kw):
        if comando[0] != "pkill":
            raise parla.subprocess.TimeoutExpired(comando, kw.get("timeout"))
        comandi.append(comando)

    monkeypatch.setattr(parla, "BASE", tmp_path)  # il registro resta nel tmp
    monkeypatch.setattr(parla, "carica_config", lambda: {"voce": "Siri (Voce 2)"})
    monkeypatch.setattr(parla.subprocess, "run", run_finto)

    parla._leggi_adesso("testo che incanta la voce")

    assert ["pkill", "-x", "say"] in comandi
    assert ["pkill", "-f", "shortcuts run"] in comandi


def test_ferma_svuota_attesa_voce_e_stato(tmp_path, monkeypatch):
    flag = tmp_path / "PARLANDO"
    flag.touch()
    pendente = tmp_path / "LETTURA_PENDENTE"
    pendente.write_text("in attesa")
    lock = tmp_path / "LETTORE_PID"
    lock.write_text("999999999")
    comandi = []
    monkeypatch.setattr(parla, "FLAG_PARLANDO", flag)
    monkeypatch.setattr(parla, "LETTURA_PENDENTE", pendente)
    monkeypatch.setattr(parla, "LETTORE_PID", lock)
    monkeypatch.setattr(parla.subprocess, "run", lambda c, **k: comandi.append(c))

    parla.ferma()

    assert not flag.exists() and not parla.ha_pendenti(pendente) and not lock.exists()
    assert ["pkill", "-x", "say"] in comandi


def test_voce_attiva_segue_il_flag(tmp_path, monkeypatch):
    flag = tmp_path / "VOICE_ON"
    monkeypatch.setattr(voce_lib, "FLAG_VOICE_ON", flag)
    assert voce_lib.voce_attiva() is False
    flag.touch()
    assert voce_lib.voce_attiva() is True


# --- Menu Voce: comportamento AppKit simulato, senza importare detta.py ---

def _menu_voce_simulato(stato, ultime=None):
    import ast
    import types

    class Elemento:
        @classmethod
        def alloc(cls):
            return cls()

        @classmethod
        def separatorItem(cls):
            item = cls()
            item.separatore = True
            return item

        def initWithTitle_action_keyEquivalent_(self, titolo, azione, tasto):
            self.titolo, self.azione, self.tasto = titolo, azione, tasto
            self.separatore = False
            return self

        def setTarget_(self, gestore):
            self.gestore = gestore

        def setRepresentedObject_(self, valore):
            self.valore = valore

        def representedObject(self):
            return self.valore

        def setEnabled_(self, attivo):
            self.attivo = attivo

        def setState_(self, stato):
            self.stato = stato

        def seleziona(self):
            if not self.separatore and self.attivo:
                getattr(self.gestore, self.azione.replace(":", "_"))(self)

    class Menu:
        @classmethod
        def alloc(cls):
            return cls()

        def initWithTitle_(self, titolo):
            self.titolo, self.elementi = titolo, []
            return self

        def setAutoenablesItems_(self, valore):
            self.abilitazione_automatica = valore

        def addItem_(self, item):
            self.elementi.append(item)

    class Indicatore:
        def __init__(self):
            self.titoli, self.menu_creati = [], []

        def button(self):
            return self

        def setTitle_(self, titolo):
            self.titoli.append(titolo)

        def setMenu_(self, menu):
            self.menu = menu
            self.menu_creati.append(menu)

    chiamate, lavori = [], []

    class ThreadSimulato:
        def __init__(self, target, args=(), daemon=False):
            self.target, self.args, self.daemon = target, args, daemon

        def start(self):
            lavori.append(self)
            self.target(*self.args)  # soltanto le spie, nessuna voce vera

    attivo = {"voce": False, "mani_libere": False}
    indicatore = Indicatore()
    spazio = {
        "AppKit": types.SimpleNamespace(NSMenu=Menu, NSMenuItem=Elemento, NSObject=object),
        "threading": types.SimpleNamespace(Thread=ThreadSimulato),
        "json": json,
        "indicatore_menu": indicatore,
        "_stato_menu": None,
        "elenco_conversazioni": lambda: json.loads(json.dumps(stato)),
        "voce_attiva": lambda: attivo["voce"],
        "mani_libere_attive": lambda: attivo["mani_libere"],
        "rileggi_ultima": lambda: chiamate.append(("rileggi",)),
        "scegli_conversazione": lambda identita: chiamate.append(("scegli", identita)),
        # 31/10/2026: le ultime dettature in fondo al menu
        "ultime_dettature": ultime if ultime is not None else voce_lib.UltimeDettature(),
        "copia_ultima_dettatura": lambda: chiamate.append(("copia",)),
        "ritrascrivi_ultima": lambda: chiamate.append(("ritrascrivi",)),
    }
    sorgente = REPO_ROOT / "mac" / "detta.py"
    albero = ast.parse(sorgente.read_text(encoding="utf-8"))
    aggiorna = next(n for n in albero.body
                    if isinstance(n, ast.FunctionDef) and n.name == "aggiorna_indicatore_menu")
    gestore = next(n for n in albero.body
                  if isinstance(n, ast.ClassDef) and n.name == "GestorePannello")
    gestore.body = [n for n in gestore.body if isinstance(n, ast.FunctionDef)
                   and n.name in {"rileggiVoce_", "scegliConversazione_",
                                  "copiaUltimaDettatura_", "ritrascriviUltima_"}]
    exec(compile(ast.Module(body=[aggiorna, gestore], type_ignores=[]), str(sorgente), "exec"), spazio)
    pannello = spazio["GestorePannello"]()
    return types.SimpleNamespace(
        aggiorna=lambda: spazio["aggiorna_indicatore_menu"](pannello),
        indicatore=indicatore, attivo=attivo, chiamate=chiamate, lavori=lavori,
    )


def test_menu_voce_spenta_resta_accessibile_e_replay_segue_la_disponibilita():
    stato = {"rileggibile": False, "preferita": None, "conversazioni": []}
    app = _menu_voce_simulato(stato)
    app.aggiorna()

    assert app.indicatore.titoli[-1] == "Voce"
    replay, _, tutte = app.indicatore.menu.elementi[:-3]  # in fondo: separatore e ultime dettature
    assert not replay.attivo and tutte.attivo
    replay.seleziona()
    assert app.chiamate == []

    stato["rileggibile"] = True  # una risposta ora e' recuperabile, voce ancora OFF
    app.aggiorna()
    replay = app.indicatore.menu.elementi[0]
    assert replay.attivo
    replay.seleziona()
    assert app.chiamate == [("rileggi",)]
    assert len(app.lavori) == 1 and app.lavori[0].daemon


def test_menu_voce_scelta_usa_identita_e_tutte_passano_nessun_filtro():
    stato = {
        "rileggibile": True, "preferita": "id-privato-B",
        "conversazioni": [
            {"id": "id-privato-A", "nome": "Claude", "anteprima": "Risposta A", "in_attesa": True},
            {"id": "id-privato-B", "nome": "Claude", "anteprima": "Risposta B", "in_attesa": False},
        ],
    }
    app = _menu_voce_simulato(stato)
    app.aggiorna()
    tutte, fonte_a, fonte_b = app.indicatore.menu.elementi[2:-3]
    assert (tutte.stato, fonte_a.stato, fonte_b.stato) == (0, 0, 1)
    fonte_b.titolo = "Nome visibile cambiato"  # il comando non puo' dipendere dall'etichetta
    fonte_b.seleziona()
    fonte_a.seleziona()
    tutte.seleziona()

    assert app.chiamate == [("scegli", "id-privato-B"), ("scegli", "id-privato-A"), ("scegli", None)]
    assert all(lavoro.daemon for lavoro in app.lavori)


def test_menu_voce_etichette_distinguono_fonti_con_anteprima_senza_id():
    stato = {
        "rileggibile": True, "preferita": None,
        "conversazioni": [
            {"id": "sessione-segreta-A", "nome": "Codex — Proposta", "anteprima": "  Preventivo\n pronto  ", "in_attesa": True},
            {"id": "sessione-segreta-B", "nome": "Codex — Proposta", "anteprima": "Riepilogo completato", "in_attesa": False},
            {"id": "sessione-segreta-C", "nome": "", "anteprima": "", "in_attesa": False},
        ],
    }
    app = _menu_voce_simulato(stato)
    app.aggiorna()
    prima, seconda, senza_nome = app.indicatore.menu.elementi[3:-3]
    assert "Codex — Proposta" in prima.titolo and "Preventivo pronto" in prima.titolo
    assert "Riepilogo completato" in seconda.titolo and prima.titolo != seconda.titolo
    assert "in attesa" in prima.titolo and "in attesa" not in seconda.titolo
    assert senza_nome.titolo.strip()
    assert all("sessione-segreta" not in item.titolo for item in (prima, seconda, senza_nome))


def test_menu_voce_non_ricrea_uguale_e_riflette_cambiamenti_reali():
    stato = {"rileggibile": True, "preferita": None, "conversazioni": []}
    app = _menu_voce_simulato(stato)
    app.aggiorna()
    primo_menu = app.indicatore.menu
    app.aggiorna()  # il lettore restituisce un oggetto nuovo con gli stessi valori
    assert app.indicatore.menu is primo_menu
    assert len(app.indicatore.menu_creati) == 1 and len(app.indicatore.titoli) == 1

    app.attivo["voce"] = True
    app.aggiorna()
    assert app.indicatore.menu is not primo_menu
    assert app.indicatore.titoli[-1] != app.indicatore.titoli[0]
    stato["rileggibile"] = False
    app.aggiorna()
    assert not app.indicatore.menu.elementi[0].attivo
    assert len(app.indicatore.menu_creati) == 3


def test_pulisci_per_voce_toglie_il_markdown():
    testo = (
        "## Titolo\n"
        "Ecco **grassetto** e *corsivo* e `codice`.\n"
        "```python\nprint('x')\n```\n"
        "- punto elenco\n"
        "Un [link](https://example.com) e https://nudo.it/pagina fine."
    )
    pulito = voce_lib.pulisci_per_voce(testo)
    assert "**" not in pulito and "`" not in pulito and "#" not in pulito
    assert "print" not in pulito          # il codice non si legge a voce
    assert "codice omesso" in pulito
    assert "link" in pulito               # il testo del link resta
    assert "https://" not in pulito       # gli URL no
    assert "grassetto" in pulito and "corsivo" in pulito


def test_pulisci_per_voce_testo_vuoto():
    assert voce_lib.pulisci_per_voce("") == ""


def test_pulisci_per_voce_separa_titoli_elenchi_e_paragrafi():
    testo = (
        "## Prossimi passi\n"
        "- Controlla il preventivo\n"
        "- Non inviare prima del 07/09/2026\n\n"
        "Il saldo resta\n"
        "di €497,50."
    )
    assert voce_lib.pulisci_per_voce(testo) == (
        "Prossimi passi. Controlla il preventivo. "
        "Non inviare prima del 07/09/2026. Il saldo resta di €497,50."
    )


def test_pulisci_per_voce_tabella_conserva_colonne_e_tutti_i_valori():
    testo = (
        "| Attività | Importo | Scadenza |\n"
        "| :--- | ---: | --- |\n"
        "| Saldo | €497,50 | 07/09/2026 |\n"
        "| Verifica | -12,5% | Non prima del 14/09/2026 |\n"
    )
    assert voce_lib.pulisci_per_voce(testo) == (
        "Attività: Saldo; Importo: €497,50; Scadenza: 07/09/2026. "
        "Attività: Verifica; Importo: -12,5%; Scadenza: Non prima del 14/09/2026."
    )


def test_pulisci_per_voce_tabella_senza_bordi_e_cella_con_barra():
    testo = (
        "Nome | Stato\n"
        "--- | ---\n"
        "A\\|B | **Non pagato**\n"
        "C | In attesa | dettaglio aggiuntivo\n"
    )
    pulito = voce_lib.pulisci_per_voce(testo)
    assert "Nome: A|B; Stato: Non pagato." in pulito
    assert "Nome: C; Stato: In attesa; Colonna 3: dettaglio aggiuntivo." in pulito


def test_pulisci_per_voce_writing_legge_solo_il_corpo_integrale():
    testo = (
        ':::writing{variant="email" id="59310" subject="Titolo interno"}\n'
        "Ciao Sal,\n\n"
        "non ho inviato la fattura da €1.250,00.\n"
        "La data è 14/09/2026 e restano 3 documenti.\n"
        ":::\n"
    )
    pulito = voce_lib.pulisci_per_voce(testo)
    assert "writing" not in pulito and "59310" not in pulito
    assert "Titolo interno" not in pulito and "variant" not in pulito
    assert "Ciao Sal" in pulito
    assert "non ho inviato la fattura da €1.250,00." in pulito
    assert "La data è 14/09/2026 e restano 3 documenti." in pulito


def test_pulisci_per_voce_percorsi_conservano_nome_file_e_riga():
    testo = (
        "Apri `/Users/utente/Documenti/Report finale.pdf` e "
        "[controllo](</Users/utente/progetto/tools/verifica.py:12>). "
        "Su Windows usa `C:\\Users\\utente\\Documenti\\Report finale.pdf`. "
        "L'altro file è /Users/utente/progetto/docs/STATUS.md."
    )
    pulito = voce_lib.pulisci_per_voce(testo)
    assert "/Users/" not in pulito and "C:\\" not in pulito
    assert pulito.count("Report finale.pdf") == 2
    assert "controllo" in pulito and "verifica.py" in pulito and "riga 12" in pulito
    assert "STATUS.md" in pulito


def test_pulisci_per_voce_file_etichettato_non_ripete_il_nome():
    pulito = voce_lib.pulisci_per_voce(
        "Apri [verifica.py](/Users/utente/tools/verifica.py:12)."
    )
    assert pulito == "Apri verifica.py, riga 12."


def test_pulisci_per_voce_percorsi_quotati_con_spazi_e_windows_nudo():
    pulito = voce_lib.pulisci_per_voce(
        'Apri "/Users/utente/My Documents/Report finale.pdf". '
        "Poi C:\\Users\\utente\\Documenti\\REPORT.md. Non cambiare il rapporto costo/beneficio."
    )
    assert pulito == (
        'Apri "Report finale.pdf". Poi REPORT.md. '
        "Non cambiare il rapporto costo/beneficio."
    )


def test_pulisci_per_voce_url_nudo_mantiene_pausa_e_link_etichettato():
    pulito = voce_lib.pulisci_per_voce(
        "Vai su https://esempio.it/risorsa?a=1. "
        "Poi leggi [la guida](https://esempio.it/guida). Non pagare €50."
    )
    assert pulito == "Vai su collegamento. Poi leggi la guida. Non pagare €50."


def test_pulisci_per_voce_fence_completo_o_aperto_omette_solo_codice():
    testo = (
        "Prima.\n~~~~python\nprint('segreto')\n```\n~~~~\n"
        "Dopo: non inviare 2 fatture.\n```python\nprint('altro codice')"
    )
    pulito = voce_lib.pulisci_per_voce(testo)
    assert pulito.count("codice omesso") == 2
    assert "print" not in pulito and "segreto" not in pulito and "`" not in pulito
    assert "Prima." in pulito and "Dopo: non inviare 2 fatture." in pulito


def test_pulisci_per_voce_idempotente_e_senza_tagli_di_contenuto():
    testo = (
        "## Riepilogo\n"
        "- Non inviare 3 fatture da €1.250,00 prima del 14/09/2026\n"
        "- Apri `/Users/utente/relazioni/report_2026-09-05.md`\n\n"
        "| Voce | Valore |\n| --- | --- |\n| Sconto | -12,5% |\n\n"
        "Ultima parte: " + "verifica completa " * 300 + "fine."
    )
    pulito = voce_lib.pulisci_per_voce(testo)
    assert voce_lib.pulisci_per_voce(pulito) == pulito
    assert "report_2026-09-05.md" in pulito
    assert "Non inviare 3 fatture da €1.250,00 prima del 14/09/2026" in pulito
    assert "Voce: Sconto; Valore: -12,5%" in pulito
    assert pulito.count("verifica completa") == 300 and pulito.endswith("fine.")


def test_estrai_ultima_risposta(tmp_path):
    transcript = tmp_path / "t.jsonl"
    righe = [
        '{"type":"user","message":{"content":"ciao"}}',
        '{"type":"assistant","message":{"content":[{"type":"text","text":"prima risposta"}]}}',
        '{"type":"assistant","message":{"content":[{"type":"tool_use","name":"Bash"}]}}',
        '{"type":"assistant","message":{"content":[{"type":"text","text":"ultima risposta"}]}}',
        "riga non json da ignorare",
    ]
    transcript.write_text("\n".join(righe))
    assert voce_lib.estrai_ultima_risposta(str(transcript)) == "ultima risposta"


def test_estrai_ultima_risposta_transcript_antigravity(tmp_path):
    """Antigravity scrive lo stesso file con altri nomi: source MODEL e testo
    pronto in `content` (forma vera del 13/09/2026)."""
    transcript = tmp_path / "transcript.jsonl"
    righe = [
        '{"step_index":1,"source":"USER_EXPLICIT","type":"USER_INPUT","status":"DONE","content":"<USER_REQUEST>ciao</USER_REQUEST>"}',
        '{"step_index":2,"source":"MODEL","type":"PLANNER_RESPONSE","status":"DONE","content":"prima risposta"}',
        '{"step_index":3,"source":"MODEL","type":"TOOL_CALL","status":"RUNNING","content":"sto guardando un file"}',
        '{"step_index":4,"source":"MODEL","type":"PLANNER_RESPONSE","status":"DONE","content":"ultima risposta"}',
    ]
    transcript.write_text("\n".join(righe), encoding="utf-8")
    assert voce_lib.estrai_ultima_risposta(str(transcript)) == "ultima risposta"


def test_payload_antigravity_tradotto_nei_nostri_nomi():
    dati = voce_hook.normalizza_payload({
        "conversationId": "abc-123",
        "transcriptPath": "/Users/utente/.gemini/antigravity/brain/abc-123/.system_generated/logs/transcript.jsonl",
        "modelName": "gemini-3.6-flash-medium",
        "terminationReason": "model_stop",
    })
    assert dati["session_id"] == "abc-123"
    assert dati["transcript_path"].endswith("transcript.jsonl")
    assert voce_hook.origine_risposta(dati)["nome"] == "Antigravity"


def test_hook_antigravity_scritto_nel_suo_formato(tmp_path):
    hooks = tmp_path / "hooks.json"
    hooks.write_text(json.dumps({"altro-gestore": {"enabled": True, "Stop": [
        {"hooks": [{"type": "command", "command": "./mio.sh"}]}]}}), encoding="utf-8")
    voce_hook.collega_hook_antigravity(hooks)
    dati = json.loads(hooks.read_text(encoding="utf-8"))
    assert dati["altro-gestore"]["Stop"], "gli hook di altri non si toccano"
    nostro = dati["voce-leaderai"]
    assert nostro["enabled"] is True
    assert "voce_hook.py" in nostro["Stop"][0]["hooks"][0]["command"]
    assert voce_hook.hook_antigravity_collegato(hooks) is True


# --- cancello sull'energia: distingue parlato da silenzio/rumore di fondo ---

def test_c_e_voce_scarta_silenzio_e_rumore_basso():
    assert voce_lib.c_e_voce(np.zeros(16000, dtype="float32")) is False
    np.random.seed(0)
    rumore = (np.random.randn(16000) * 0.003).astype("float32")  # respiro / fruscio
    assert voce_lib.c_e_voce(rumore) is False


def test_c_e_voce_accetta_parlato():
    np.random.seed(0)
    parlato = (np.random.randn(16000) * 0.05).astype("float32")  # energia da voce
    assert voce_lib.c_e_voce(parlato) is True


def test_c_e_voce_audio_vuoto():
    assert voce_lib.c_e_voce(np.array([], dtype="float32")) is False


# --- audio muto: distinguere il guadagno d'ingresso abbassato dallo stream incantato ---
# Caso 01/08/2026: volume d'ingresso di sistema sceso da solo a 36/100, parlato
# a rms 0.0012-0.0014 (sotto SOGLIA_VOCE) e app muta senza diagnosi. Il vecchio
# airbag riavviava il processo, rimedio inutile contro un guadagno abbassato.

def test_diagnosi_audio_muto_riconosce_il_guadagno_abbassato():
    causa, da_impostare = voce_lib.diagnosi_audio_muto(0.0014, 36)
    assert causa == "guadagno_basso"
    assert da_impostare == voce_lib.GUADAGNO_INGRESSO_TARGET


def test_diagnosi_audio_muto_col_guadagno_giusto_incolpa_lo_stream():
    causa, da_impostare = voce_lib.diagnosi_audio_muto(0.0014, 75)
    assert causa == "stream_muto"
    assert da_impostare is None


def test_diagnosi_audio_muto_al_minimo_esatto_non_tocca_il_guadagno():
    causa, _ = voce_lib.diagnosi_audio_muto(0.0014, voce_lib.GUADAGNO_INGRESSO_MINIMO)
    assert causa == "stream_muto"


def test_diagnosi_audio_muto_senza_lettura_del_guadagno_ricade_sullo_stream():
    # non-Mac o osascript fallito: non si puo' incolpare il guadagno
    causa, da_impostare = voce_lib.diagnosi_audio_muto(0.0014, None)
    assert causa == "stream_muto"
    assert da_impostare is None


def test_diagnosi_audio_muto_audio_sano_non_e_un_guasto():
    causa, da_impostare = voce_lib.diagnosi_audio_muto(0.0128, 36)
    assert causa == "ok"
    assert da_impostare is None


# --- corsie di pulizia: spegnersi si', ma con una via di ritorno ---
# Caso 27-29/07/2026: la corsia veloce si spegne dopo 2 fallimenti di fila e non
# torna piu' fino al riavvio. Il processo di Sal e' rimasto su 2 giorni e 16 ore,
# quindi per giorni ogni dettatura e' passata dall'agente lento (12 timeout da
# 20s il solo 29/07, e dopo 20s si incolla comunque il grezzo).

def test_corsia_utilizzabile_finche_i_guasti_sono_pochi():
    assert voce_lib.corsia_utilizzabile(0, None, 1000) is True
    assert voce_lib.corsia_utilizzabile(1, 900, 1000) is True


def test_corsia_si_spegne_dopo_due_guasti_di_fila():
    assert voce_lib.corsia_utilizzabile(2, 1000, 1000) is False


def test_corsia_torna_da_sola_dopo_il_riposo():
    ultimo = 1000
    riposo = voce_lib.RIPOSO_CORSIA_SEC
    assert voce_lib.corsia_utilizzabile(2, ultimo, ultimo + riposo - 1) is False
    assert voce_lib.corsia_utilizzabile(2, ultimo, ultimo + riposo) is True


def test_un_successo_azzera_i_guasti():
    assert voce_lib.registra_esito_corsia(1, True, 500) == (0, None)


def test_un_fallimento_conta_e_segna_il_momento():
    assert voce_lib.registra_esito_corsia(1, False, 500) == (2, 500)


def test_riposo_corsia_non_dura_quanto_una_sessione():
    # il difetto era proprio questo: spegnimento di fatto permanente
    assert 0 < voce_lib.RIPOSO_CORSIA_SEC <= 1800


def test_guadagno_target_tiene_il_rumore_ambiente_nella_banda_calibrata():
    # il target deve stare sopra il minimo e non al massimo: a 100 il rumore
    # ambiente misurato saliva a 0.0120, sopra SOGLIA_VOCE e vicino alla
    # soglia mani libere 0.018 (si auto-innescava).
    assert voce_lib.GUADAGNO_INGRESSO_MINIMO < voce_lib.GUADAGNO_INGRESSO_TARGET < 100


# --- rete di sicurezza: frasi-fantasma che Whisper inventa sul silenzio ---

def test_e_allucinazione_riconosce_le_frasi_fantasma():
    for f in ["Grazie.", " Grazie a tutti. ", "grazie", "GRAZIE!",
              "Sottotitoli e revisione a cura di QTSS", "",
              "Yeah.", "yeah", "Thank you."]:
        assert voce_lib.e_allucinazione(f) is True, f


def test_e_allucinazione_non_scarta_testo_vero():
    for f in ["Apri il file e correggi la funzione di pagamento.",
              "Grazie mille per la proposta, la rivediamo domani."]:
        assert voce_lib.e_allucinazione(f) is False, f


def test_e_allucinazione_riconosce_ripetizione_patologica():
    # collasso reale visto 05/07: audio di 1.7s -> centinaia di "мент" ripetuto
    assert voce_lib.e_allucinazione(("мент " * 200).strip()) is True
    assert voce_lib.e_allucinazione(("Pier " * 200).strip()) is True


def test_e_allucinazione_riconosce_ripetizione_senza_spazi():
    # collasso reale visto 06/07: "Ecologia" + "版" (cinese) ripetuto senza
    # spazi -> lo split per parole lo vede come "1 parola sola", serve il
    # controllo a livello di carattere
    assert voce_lib.e_allucinazione("Ecologia" + "版" * 200) is True


def test_e_allucinazione_non_scarta_ripetizioni_legittime():
    # una parola ripetuta poche volte in una frase vera non deve scattare
    assert voce_lib.e_allucinazione(
        "No no no, non intendevo quello, fammi ripetere la domanda per bene."
    ) is False


# --- P-117 (28/09/2026): la rete confronta i PEZZI, non solo la stringa intera ---
# 12 secondi di parlato vero di Sal (rms 0,052) sono usciti da Whisper come una
# frase da fine-video; l'elenco la conosceva solo se identica a una voce intera,
# e questa era appena piu' lunga: incollata in chat e inviata da sola.

FRASE_INVENTATA_28_09 = (
    "Grazie a tutti per aver guardato il video, vi ringrazio per avermi seguito, "
    "e vi ringrazio per avermi seguito."
)


def test_e_allucinazione_riconosce_la_frase_inventata_del_28_09():
    assert voce_lib.e_allucinazione(FRASE_INVENTATA_28_09) is True


def test_e_allucinazione_riconosce_le_varianti_della_stessa_famiglia():
    # fratelli mai visti: stesse formule da fine-video, messe insieme in altri
    # modi (un'altra frase, un'altra lunghezza, un altro ordine, maiuscole)
    for f in [
        "Grazie mille per la visione, ci vediamo al prossimo video, ciao a tutti.",
        "Iscrivetevi al canale e alla prossima.",
        "grazie per averci seguito e ci vediamo nel prossimo video",
        "VI RINGRAZIO PER AVERMI SEGUITO!",
        "Grazie per aver guardato questo video. Alla prossima.",
        "Grazie a tutti. Grazie a tutti. Grazie a tutti.",   # collasso a ciclo di una frase nota
        "Thank you. Thank you. Thank you.",
    ]:
        assert voce_lib.e_allucinazione(f) is True, f


def test_e_allucinazione_non_scarta_frasi_vere_che_contengono_le_formule():
    # le formule dentro una frase vera restano: il testo dev'essere fatto SOLO di formule
    for f in [
        "Grazie a tutti per aver guardato il video che ti ho mandato ieri, fammi sapere cosa ne pensi.",
        "Ti ringrazio per avermi seguito nel progetto, ora passiamo alla seconda fase del lavoro.",
        "Alla prossima riunione porta i numeri del cliente.",
        "Ciao a tutti, oggi parliamo del nuovo listino.",
        "Iscriviti al canale Slack del team e scrivi li.",
        "Ci vediamo domani alle nove in ufficio.",
        "Grazie mille, a presto.",   # solo cortesie: senza riferimento al video non e' un fantasma
        "Perfetto, grazie. Ci vediamo alla prossima.",
        "Grazie, grazie!",           # una persona che ringrazia: il ciclo comincia a tre
        "Grazie a tutti. Grazie a tutti.",
    ]:
        assert voce_lib.e_allucinazione(f) is False, f


def _audio_sintetico(secondi, rms):
    """Rumore con l'rms (e la durata, a 16 kHz) che si vuole: un parlato, un colpo, un fruscio."""
    a = np.random.default_rng(0).standard_normal(int(secondi * 16000)).astype("float32")
    return a * (rms / float(np.sqrt(np.mean(a * a))))


PARLATO_DEL_28_09 = (12.3, 0.052)   # durata e rms veri della dettatura delle 21:58


def _trascrivi_mac(passaggi, glossario="Glossario: Claude Code."):
    """`trascrivi` di mac/detta.py con Whisper finto (le soglie del secondo passaggio
    sono quelle vere del sorgente): `passaggi` e' cio' che Whisper risponde a ogni
    chiamata; torna (funzione, prompt usati)."""
    path = REPO_ROOT / "mac" / "detta.py"
    nodi = [n for n in ast.parse(path.read_text(encoding="utf-8")).body
            if isinstance(n, ast.FunctionDef) and n.name == "trascrivi"
            or isinstance(n, ast.Assign) and any(
                getattr(t, "id", "") in ("SECONDO_PASSAGGIO_MIN_SEC", "SECONDO_PASSAGGIO_ENERGIA")
                for t in n.targets)]
    assert len(nodi) == 3
    prompt_usati = []
    risposte = iter(passaggi)

    def whisper(audio, prompt=None):
        prompt_usati.append(prompt)
        return next(risposte)

    spazio = {
        "_whisper_grezzo": whisper, "_rifinisci": lambda testo: testo,
        "e_allucinazione": voce_lib.e_allucinazione, "c_e_voce": voce_lib.c_e_voce,
        "SOGLIA_VOCE": voce_lib.SOGLIA_VOCE, "FREQ": 16000,
        "GLOSSARIO_PROMPT": glossario, "cfg": {}, "logging": logging,
    }
    exec(compile(ast.Module(body=nodi, type_ignores=[]), str(path), "exec"), spazio)
    return spazio["trascrivi"], prompt_usati


def test_trascrivi_riprova_senza_glossario_se_esce_un_fantasma_su_parlato_vero():
    """P-117: col prompt del glossario Whisper inventa la frase da fine-video
    sul parlato vero; senza prompt trascrive quello che e' stato detto. Il
    parlato non si butta: secondo passaggio, una volta, senza glossario."""
    vero = "anche perche' non mi ricordo veramente che dobbiamo fare, vedete"
    trascrivi, prompt = _trascrivi_mac([FRASE_INVENTATA_28_09, vero])
    assert trascrivi(_audio_sintetico(*PARLATO_DEL_28_09)) == vero
    assert prompt == ["Glossario: Claude Code.", None]


def test_trascrivi_non_riprova_se_il_testo_e_vero_o_non_e_un_parlato():
    parlato = _audio_sintetico(*PARLATO_DEL_28_09)
    trascrivi, prompt = _trascrivi_mac(["Apri il file e correggi la funzione."])
    assert trascrivi(parlato) == "Apri il file e correggi la funzione."
    assert len(prompt) == 1
    # un colpo sul tavolo (1 s, forte) o un fruscio lungo: il fantasma e' l'esito giusto, niente secondo giro
    for audio in (_audio_sintetico(1.0, 0.15), _audio_sintetico(8.0, 0.01), _audio_sintetico(8.0, 0.0)):
        trascrivi, prompt = _trascrivi_mac(["Grazie."])
        assert trascrivi(audio) == "Grazie."
        assert len(prompt) == 1
    # senza glossario non c'e' un prompt da togliere
    trascrivi, prompt = _trascrivi_mac([FRASE_INVENTATA_28_09], glossario=None)
    assert trascrivi(parlato) == FRASE_INVENTATA_28_09
    assert len(prompt) == 1


def test_trascrivi_il_confine_del_parlato_vero_e_tre_secondi_e_cinque_volte_la_soglia():
    # dai registri di Sal: 43 fantasmi con testo, mediana 1 s; solo 3 durano >= 3 s con energia da parlato
    for secondi, rms, riprova in ((3.0, 0.021, True), (2.9, 0.05, False), (3.0, 0.019, False), (30.0, 0.3, True)):
        trascrivi, prompt = _trascrivi_mac([FRASE_INVENTATA_28_09, "ok, vedo che funziona"])
        trascrivi(_audio_sintetico(secondi, rms))
        assert (len(prompt) == 2) is riprova, (secondi, rms)


def test_trascrivi_se_anche_il_secondo_passaggio_e_un_fantasma_torna_il_primo():
    """Il chiamante lo scarta con e_allucinazione: mai incollato."""
    trascrivi, prompt = _trascrivi_mac([FRASE_INVENTATA_28_09, "Grazie a tutti."])
    risultato = trascrivi(_audio_sintetico(*PARLATO_DEL_28_09))
    assert voce_lib.e_allucinazione(risultato) is True
    assert len(prompt) == 2


def test_trascrivi_un_errore_nel_secondo_passaggio_non_rompe_la_dettatura():
    path = REPO_ROOT / "mac" / "detta.py"
    chiamate = []

    def whisper(audio, prompt=None):
        chiamate.append(prompt)
        if prompt is None:
            raise RuntimeError("memoria finita")
        return FRASE_INVENTATA_28_09

    nodi = [n for n in ast.parse(path.read_text(encoding="utf-8")).body
            if isinstance(n, ast.FunctionDef) and n.name == "trascrivi"
            or isinstance(n, ast.Assign) and any(
                getattr(t, "id", "") in ("SECONDO_PASSAGGIO_MIN_SEC", "SECONDO_PASSAGGIO_ENERGIA")
                for t in n.targets)]
    spazio = {
        "_whisper_grezzo": whisper, "_rifinisci": lambda testo: testo,
        "e_allucinazione": voce_lib.e_allucinazione, "c_e_voce": voce_lib.c_e_voce,
        "SOGLIA_VOCE": voce_lib.SOGLIA_VOCE, "FREQ": 16000,
        "GLOSSARIO_PROMPT": "Glossario: X.", "cfg": {}, "logging": logging,
    }
    exec(compile(ast.Module(body=nodi, type_ignores=[]), str(path), "exec"), spazio)
    assert voce_lib.e_allucinazione(spazio["trascrivi"](_audio_sintetico(*PARLATO_DEL_28_09))) is True
    assert len(chiamate) == 2


# --- callback blindata: un errore non deve mai spegnere l'hotkey ---

def test_esegui_sicuro_esegue_e_passa_gli_argomenti():
    raccolti = []
    voce_lib.esegui_sicuro(raccolti.append, "ciao")
    assert raccolti == ["ciao"]


def test_esegui_sicuro_ingoia_le_eccezioni():
    def esplode():
        raise RuntimeError("boom")
    # non deve sollevare: il thread della tastiera deve sopravvivere all'errore
    voce_lib.esegui_sicuro(esplode)


# --- airbag anti-incanto: logica testabile senza microfono/CoreAudio ---

def test_timeout_registrazione_scade_solo_oltre_limite():
    assert voce_lib.timeout_scaduto(True, 10.0, 101.0, 90.0) is True
    assert voce_lib.timeout_scaduto(True, 10.0, 99.0, 90.0) is False
    assert voce_lib.timeout_scaduto(False, 10.0, 101.0, 90.0) is False
    assert voce_lib.timeout_scaduto(True, None, 101.0, 90.0) is False


def test_stop_audio_bloccato_scade_solo_oltre_limite():
    assert voce_lib.timeout_scaduto(True, 20.0, 31.0, 10.0) is True
    assert voce_lib.timeout_scaduto(True, 20.0, 29.0, 10.0) is False


def test_tetto_soft_non_scatta_col_tasto_fisicamente_giu():
    # caso 04/09 06:41: 90s+ di dettatura, tasto ancora premuto -> non si ferma
    assert voce_lib.stop_anti_incanto(True, 0.0, 91.0, True, 90.0, 300.0) is False
    assert voce_lib.stop_anti_incanto(True, 0.0, 299.0, True, 90.0, 300.0) is False


def test_tetto_soft_scatta_col_tasto_rilasciato():
    # rilascio perso da pynput: tasto su, registrazione aperta -> stop come prima
    assert voce_lib.stop_anti_incanto(True, 0.0, 91.0, False, 90.0, 300.0) is True
    assert voce_lib.stop_anti_incanto(True, 0.0, 89.0, False, 90.0, 300.0) is False


def test_tetto_duro_scatta_comunque_col_tasto_incastrato():
    assert voce_lib.stop_anti_incanto(True, 0.0, 301.0, True, 90.0, 300.0) is True


def test_tetto_anti_incanto_ignora_registrazione_ferma_o_senza_inizio():
    assert voce_lib.stop_anti_incanto(False, 0.0, 500.0, False, 90.0, 300.0) is False
    assert voce_lib.stop_anti_incanto(True, None, 500.0, False, 90.0, 300.0) is False


def test_vad_mani_libere_conserva_il_solo_tetto_soft():
    # nel VAD il tasto non c'entra: tasto_giu=False -> 90s ferma come prima
    assert voce_lib.stop_anti_incanto(True, 0.0, 91.0, False, 90.0, 300.0) is True


# --- glossario: nomi propri e termini del mestiere scritti giusti ---

def test_glossario_iniziale_costruisce_il_prompt_per_whisper():
    cfg = {"glossario": ["LeaderAI", "salchiarenza.ai", "Systeme.io"]}
    prompt = voce_lib.glossario_iniziale(cfg)
    assert "LeaderAI" in prompt and "Systeme.io" in prompt


def test_glossario_iniziale_e_un_elenco_senza_etichetta():
    """11/10/2026, banco su 30 dettature vere di Sal: con l'etichetta
    «Glossario:» davanti il motore large-v3 salta parole e punteggiatura
    (34 parole sbagliate su 800); con lo stesso elenco nudo 32, e col
    glossario allargato 35 contro 18. L'etichetta non si detta mai: il
    prompt e' solo l'elenco dei nomi, chiuso dal punto."""
    prompt = voce_lib.glossario_iniziale({"glossario": ["LeaderAI", " ", "ChatGPT", "Claude Code"]})
    assert prompt == "LeaderAI, ChatGPT, Claude Code."
    assert "glossario" not in prompt.lower()


def test_glossario_iniziale_vuoto_o_assente():
    assert voce_lib.glossario_iniziale({}) is None
    assert voce_lib.glossario_iniziale({"glossario": []}) is None


def test_applica_sostituzioni_parola_intera_e_case_insensitive():
    mappa = {"sistemi io": "Systeme.io", "leader ai": "LeaderAI"}
    testo = "Apri Sistemi Io e controlla leader ai, poi i sistemi ionici."
    esito = voce_lib.applica_sostituzioni(testo, mappa)
    assert "Systeme.io" in esito and "LeaderAI" in esito
    assert "sistemi ionici" in esito     # sostituisce solo la parola intera


def test_applica_sostituzioni_senza_mappa_non_tocca_nulla():
    assert voce_lib.applica_sostituzioni("testo com'e'", {}) == "testo com'e'"


# --- detta pulito: solo se attivo e solo su dettature lunghe ---

def test_serve_pulizia_solo_se_attiva_e_testo_lungo():
    lungo = "parola " * 20
    corto = "apri il file di ieri"
    assert voce_lib.serve_pulizia(lungo, {"detta_pulito": True}) is True
    assert voce_lib.serve_pulizia(corto, {"detta_pulito": True}) is False
    assert voce_lib.serve_pulizia(lungo, {"detta_pulito": False}) is False
    assert voce_lib.serve_pulizia(lungo, {}) is False


def test_serve_pulizia_rispetta_la_soglia_configurata():
    testo = "una due tre quattro cinque"
    assert voce_lib.serve_pulizia(testo, {"detta_pulito": True, "pulizia_min_parole": 5}) is True
    assert voce_lib.serve_pulizia(testo, {"detta_pulito": True, "pulizia_min_parole": 6}) is False


def test_destinazione_agente_riconosce_app_e_schede_web():
    assert voce_lib.destinazione_agente("ChatGPT", "") is True
    assert voce_lib.destinazione_agente("Claude", "") is True
    assert voce_lib.destinazione_agente("Google Chrome", "https://chatgpt.com/c/123") is True
    assert voce_lib.destinazione_agente("Safari", "https://claude.ai/chat/123") is True
    assert voce_lib.destinazione_agente("Antigravity", "") is True
    assert voce_lib.destinazione_agente("Google Chrome", "https://gemini.google.com/app") is True
    assert voce_lib.destinazione_agente("Mail", "") is False
    assert voce_lib.destinazione_agente("Google Chrome", "https://example.com") is False


def test_ritardo_invio_segue_il_contesto():
    cfg = {
        "invio_automatico_ritardo_sec": 2.5,
        "invio_automatico_ritardo_conversazione_sec": 0.4,
        "invio_automatico_ritardo_chat_ai_sec": 1.0,
    }
    # voce agenti accesa: botta e risposta, vince sempre la conversazione
    assert voce_lib.ritardo_invio(cfg, True, True) == 0.4
    assert voce_lib.ritardo_invio(cfg, True, False) == 0.4
    # chat AI a voce spenta: il testo si vede, parte quasi subito
    assert voce_lib.ritardo_invio(cfg, False, True) == 1.0
    # documenti, email, social: tempo per correggere
    assert voce_lib.ritardo_invio(cfg, False, False) == 2.5


def test_ritardo_invio_default_senza_chiavi():
    assert voce_lib.ritardo_invio({}, True, False) == 0.3
    assert voce_lib.ritardo_invio({}, False, True) == 2.0  # 17/09/2026: due secondi per bloccare con uno spazio
    assert voce_lib.ritardo_invio({}, False, False) == 2.5
    assert voce_lib.ritardo_invio({"invio_automatico_ritardo_chat_ai_sec": "0.8"}, False, True) == 0.8


def test_invio_automatico_mac_usa_il_ritardo_di_contesto():
    sorgente = (REPO_ROOT / "mac" / "detta.py").read_text(encoding="utf-8")
    corpo = sorgente.split("def _incolla_messaggio", 1)[1].split("\ndef ", 1)[0]
    assert "ritardo_invio(cfg, voce_attiva(), chat_agente)" in corpo
    assert "invio automatico ANNULLATO" in corpo  # l'annullamento su tasto resta


def test_percorso_interattivo_mac_non_chiama_un_agente():
    sorgente = (REPO_ROOT / "mac" / "detta.py").read_text(encoding="utf-8")
    corpo = sorgente.split("def _trascrivi_e_incolla", 1)[1].split("\ndef ", 1)[0]
    assert "pulisci_con_agente" not in corpo
    assert "destinazione_agente" in corpo
    assert json.loads((REPO_ROOT / "mac" / "config.json").read_text())["pulizia_timeout_shortcut_sec"] == 2


def test_prompt_pulizia_contiene_testo_e_glossario():
    p = voce_lib.prompt_pulizia("ci vediamo martedì anzi mercoledì", ["LeaderAI"])
    assert "martedì anzi mercoledì" in p
    assert "LeaderAI" in p
    # la formulazione imperativa faceva appendere il glossario al testo (bug 03/07)
    assert "Scrivi correttamente questi nomi" not in p
    assert "Non aggiungere mai nomi" in p


# --- guardia anti-eco: la pulizia non deve inventare nomi mai dettati ---

GLOSSARIO_8 = ["LeaderAI", "salchiarenza.ai", "Systeme.io", "Claude Code",
               "Codex", "Anthropic", "DVR Assistant", "AI con Sal"]


def test_pulizia_inventa_nomi_scatta_sul_glossario_appeso():
    grezzo = "Poi prendi la call che abbiamo fatto e la guardiamo insieme."
    pulito = grezzo + " LeaderAI, salchiarenza.ai, Systeme.io, Claude Code, Codex, Anthropic, DVR Assistant, AI con Sal."
    assert voce_lib.pulizia_inventa_nomi(grezzo, pulito, GLOSSARIO_8) is True


def test_pulizia_inventa_nomi_tollera_una_correzione_di_grafia():
    grezzo = "scrivilo su leader ai per favore"
    pulito = "Scrivilo su LeaderAI per favore."
    assert voce_lib.pulizia_inventa_nomi(grezzo, pulito, GLOSSARIO_8) is False


def test_pulizia_inventa_nomi_blocca_una_sostituzione_di_significato():
    grezzo = "Apri il collegamento di OpenAI e controllalo."
    pulito = "Apri il collegamento di LeaderAI e controllalo."
    assert voce_lib.pulizia_inventa_nomi(grezzo, pulito, GLOSSARIO_8) is True


def test_pulizia_inventa_nomi_ok_se_i_nomi_erano_dettati():
    grezzo = "apri claude code e codex e controlla"
    pulito = "Apri Claude Code e Codex e controlla."
    assert voce_lib.pulizia_inventa_nomi(grezzo, pulito, GLOSSARIO_8) is False


def test_pulizia_sospetta_scatta_sul_collasso_del_testo():
    grezzo = ("Poi prendi la call che abbiamo fatto, apri Docs, ti guardi la call, "
              "c'è una procedura che avevano detto, così la prossima la guardiamo insieme.")
    # visto dal vivo 03/07: il modellino risponde solo con l'esempio della regola 1
    assert voce_lib.pulizia_sospetta(grezzo, "mercoledí", GLOSSARIO_8) is True


def test_pulizia_sospetta_blocca_anche_un_taglio_di_meta_frase():
    grezzo = (
        "Giusto, il primo è il setup dell'ecosistema perché si fa e si spiega, "
        "poi colleghiamo i vari strumenti e verifichiamo insieme il risultato finale."
    )
    pulito = "Giusto, il primo è il setup dell'ecosistema, poi colleghiamo i vari strumenti."
    assert voce_lib.pulizia_sospetta(grezzo, pulito, GLOSSARIO_8) is True


def test_pulizia_sospetta_accetta_una_pulizia_normale():
    grezzo = "Ok, ehm, ora da un po' mi da questa qua, cioè, non funziona più come prima."
    pulito = "Ok, ora da un po' mi da questa qua, non funziona più come prima."
    assert voce_lib.pulizia_sospetta(grezzo, pulito, GLOSSARIO_8) is False


def test_pulisci_con_agente_scarta_output_con_glossario_inventato(monkeypatch):
    grezzo = "una frase dettata senza nomi di brand dentro"
    eco = grezzo + " LeaderAI, Systeme.io, Codex."

    class Esito:
        returncode = 0
        stdout = eco

    monkeypatch.setattr(voce_lib.subprocess, "run", lambda *a, **k: Esito())
    # None = corsia fallita (stesso contratto della corsia veloce): il
    # chiamante fa `pulito or testo`, quindi il grezzo non si perde.
    assert voce_lib.pulisci_con_agente(grezzo, ["finto"], glossario=GLOSSARIO_8) is None


# --- agente locale per la pulizia: claude prima, codex come riserva ---

def test_comando_agente_preferisce_claude(monkeypatch):
    monkeypatch.setattr(voce_lib.shutil, "which", lambda n: "/usr/local/bin/claude" if n == "claude" else None)
    cmd = voce_lib.comando_agente()
    assert cmd[0] == "claude"
    # avvio "spoglio": niente MCP, tool, settings o sessione su disco (~2-3s in meno)
    for flag in ("--strict-mcp-config", "--no-session-persistence", "--tools", "--setting-sources"):
        assert flag in cmd, flag


def test_comando_agente_ripiega_su_codex(monkeypatch):
    monkeypatch.setattr(voce_lib.shutil, "which", lambda n: "/usr/local/bin/codex" if n == "codex" else None)
    assert voce_lib.comando_agente()[0] == "codex"


def test_comando_agente_nessun_agente_installato(monkeypatch):
    monkeypatch.setattr(voce_lib.shutil, "which", lambda n: None)
    assert voce_lib.comando_agente() is None


def test_pulisci_con_agente_usa_l_output_del_comando():
    esito = voce_lib.pulisci_con_agente(
        "testo grezzo", ["/bin/sh", "-c", "echo testo sistemato"], timeout=5
    )
    assert esito == "testo sistemato"


def test_pulisci_con_agente_dichiara_il_fallimento_del_comando():
    originale = "testo grezzo da tenere"
    assert voce_lib.pulisci_con_agente(originale, ["/bin/sh", "-c", "exit 1"], timeout=5) is None
    assert voce_lib.pulisci_con_agente(originale, ["/bin/sh", "-c", "true"], timeout=5) is None


def test_pulisci_con_agente_dichiara_il_fallimento_su_timeout():
    originale = "testo grezzo da tenere"
    esito = voce_lib.pulisci_con_agente(originale, ["/bin/sh", "-c", "sleep 5"], timeout=0.2)
    assert esito is None
    assert (esito or originale) == originale  # il grezzo resta garantito dal chiamante


# --- corsia veloce: modello Apple on-device via Comando Rapido (solo Mac) ---

def test_shortcut_pulizia_disponibile(monkeypatch):
    class Esito:
        stdout = "Voce Pulita\nVoce LeaderAI firmato\n"
        returncode = 0
    monkeypatch.setattr(voce_lib.shutil, "which", lambda n: "/usr/bin/shortcuts" if n == "shortcuts" else None)
    monkeypatch.setattr(voce_lib.subprocess, "run", lambda *a, **k: Esito())
    assert voce_lib.shortcut_pulizia_disponibile("Voce Pulita") is True
    assert voce_lib.shortcut_pulizia_disponibile("Non Esiste") is False


def test_shortcut_pulizia_non_disponibile_senza_cli(monkeypatch):
    monkeypatch.setattr(voce_lib.shutil, "which", lambda n: None)  # es. Windows
    assert voce_lib.shortcut_pulizia_disponibile("Voce Pulita") is False


def test_pulisci_con_shortcut_usa_l_output(monkeypatch, tmp_path):
    def finto_run(cmd, **kw):
        # il comando è ["shortcuts","run",nome,"-i",input,"-o",output,...]: scrive l'output
        out = cmd[cmd.index("-o") + 1]
        with open(out, "w") as f:
            f.write("Testo grezzo.")
        class E: returncode = 0
        return E()
    monkeypatch.setattr(voce_lib.subprocess, "run", finto_run)
    esito = voce_lib.pulisci_con_shortcut("testo grezzo", "Voce Pulita", timeout=5)
    assert esito == "Testo grezzo."


# --- apprendimento automatico: Voce impara le parole che sbaglia sempre ---

def test_estrai_grezzi_dal_log(tmp_path):
    log = tmp_path / "voce.log"
    log.write_text(
        "2026-07-02 15:10:04,597 INFO grezzo: Prima frase dettata.\n"
        "2026-07-02 15:10:05,885 INFO pulizia shortcut 1.3s: ok\n"
        "2026-07-02 15:12:47,848 INFO grezzo: Seconda frase dettata.\n"
        "2026-07-02 15:13:02,225 INFO pulito: Seconda frase pulita.\n"
    )
    grezzi = voce_lib.estrai_grezzi_dal_log(log)
    assert grezzi == ["Prima frase dettata.", "Seconda frase dettata."]


def test_estrai_grezzi_dal_log_limite_e_file_mancante(tmp_path):
    log = tmp_path / "voce.log"
    log.write_text("".join(f"x INFO grezzo: frase {i}\n" for i in range(60)))
    assert len(voce_lib.estrai_grezzi_dal_log(log, massimo=50)) == 50
    assert voce_lib.estrai_grezzi_dal_log(tmp_path / "non_esiste.log") == []


def test_unisci_sostituzioni_non_sovrascrive_e_scarta_spazzatura():
    attuali = {"leader ai": "LeaderAI"}
    nuove = {
        "leader ai": "ALTRO",          # gia' presente: non si tocca
        "giornato": "giornale",        # buona: entra
        "uguale": "uguale",            # identita': scartata
        "": "vuoto",                   # chiave vuota: scartata
        "x" * 60: "troppo lunga",      # sproporzionata: scartata
    }
    esito = voce_lib.unisci_sostituzioni(attuali, nuove)
    assert esito == {"giornato": "giornale"}
    assert attuali == {"leader ai": "LeaderAI"}  # l'originale resta intatto


def test_estrai_json_dalla_risposta():
    testo = 'Ecco le coppie:\n{"giornato": "giornale", "stema": "sistema"}\nfine.'
    assert voce_lib.estrai_json(testo) == {"giornato": "giornale", "stema": "sistema"}
    assert voce_lib.estrai_json("nessun json qui") == {}


def test_impara_sostituzioni_propone_senza_cambiare_il_config(tmp_path, caplog):
    log = tmp_path / "voce.log"
    log.write_text("x INFO grezzo: il giornato di oggi\nx INFO grezzo: apri il giornato\n")
    config = tmp_path / "config.json"
    config.write_text('{"sostituzioni": {}}')
    comando = ["/bin/sh", "-c", 'echo \'{"giornato": "giornale"}\'']
    nuove = voce_lib.impara_sostituzioni(log, config, comando, timeout=10)
    assert nuove == {"giornato": "giornale"}
    import json
    assert json.loads(config.read_text())["sostituzioni"] == {}


def test_ipotesi_arbitro_non_corrompono_parole_corrette(tmp_path, monkeypatch, caplog):
    log = tmp_path / "voce.log"
    frase = "Vi mando il documento al cliente. La call è programmata per domani."
    log.write_text("x INFO grezzo: " + frase + "\n", encoding="utf-8")
    config = tmp_path / "config.local.json"
    prima = '{"sostituzioni": {"cloud code": "Claude Code"}, "glossario": ["Cliente"]}'
    config.write_text(prima, encoding="utf-8")
    proposte = {"vi": "mi", "al": "il", "programmata": "programmato"}
    monkeypatch.setattr(voce_lib, "chiedi_arbitro", lambda *a: (proposte, None))
    caplog.set_level("INFO", logger="voce")

    assert voce_lib.impara_sostituzioni(log, config, ["arbitro-finto"]) == proposte

    assert config.read_text(encoding="utf-8") == prima
    attive = json.loads(config.read_text())["sostituzioni"]
    assert voce_lib.applica_sostituzioni(frase, attive) == frase
    assert voce_lib.applica_sostituzioni("Apri cloud code", attive) == "Apri Claude Code"
    assert "non applicate" in caplog.text


def test_proposte_json_malformate_non_diventano_testo():
    assert voce_lib.unisci_sostituzioni({}, {
        "vi": {"giusto": "mi"}, "al": ["il"], "tre": 3,
        "niente": None, "vuoto": "  ", "pronotare": "prenotare",
    }) == {"pronotare": "prenotare"}


def test_apprendimento_giornaliero_non_attiva_proposte_in_memoria(tmp_path):
    import ast
    import logging
    import time
    sorgente = REPO_ROOT / "mac" / "detta.py"
    funzione = next(n for n in ast.parse(sorgente.read_text()).body
                    if isinstance(n, ast.FunctionDef) and n.name == "_impara_dagli_errori")
    cfg = {"debug_dettature": True, "conserva_audio_n": 0,
           "sostituzioni": {"cloud code": "Claude Code"}}
    spazio = {"__file__": str(tmp_path / "detta.py"), "os": os, "time": time,
              "logging": logging, "cfg": cfg, "COMANDO_APPRENDIMENTO": ["finto"],
              "config_scrivibile": lambda: tmp_path / "config.local.json",
              "impara_sostituzioni": lambda *a: {"vi": "mi", "al": "il"}}
    exec(compile(ast.Module(body=[funzione], type_ignores=[]), str(sorgente), "exec"), spazio)

    spazio["_impara_dagli_errori"]()

    assert cfg["sostituzioni"] == {"cloud code": "Claude Code"}


def test_impara_sostituzioni_senza_grezzi_non_fa_nulla(tmp_path):
    config = tmp_path / "config.json"
    config.write_text('{"sostituzioni": {}}')
    nuove = voce_lib.impara_sostituzioni(tmp_path / "vuoto.log", config, ["/bin/true"], timeout=5)
    assert nuove == {}


def test_audio_fuori_scala_scarta_lo_stream_corrotto():
    # Caso 09/07: per ~20s CoreAudio ha consegnato sample fuori da [-1, 1]
    # (rms 2.7-4.4 contro lo 0.15 del parlato) e Whisper allucinava.
    assert voce_lib.audio_fuori_scala(3.2381) is True
    assert voce_lib.audio_fuori_scala(4.4269) is True
    # parlato vero, anche urlato con clipping, resta fisicamente <= 1.0
    assert voce_lib.audio_fuori_scala(0.16) is False
    assert voce_lib.audio_fuori_scala(1.0) is False


def test_aggiorna_scarti_fuori_scala_riavvia_solo_se_persiste():
    # dettatura sana: contatore azzerato, niente scarto ne' riavvio
    assert voce_lib.aggiorna_scarti_fuori_scala(1, 0.16) == (0, False, False)
    # primo fuori scala: scarta ma non riavvia (transitorio che si riassorbe da solo)
    assert voce_lib.aggiorna_scarti_fuori_scala(0, 3.2) == (1, True, False)
    # secondo di fila: la corruzione persiste, scarta e riavvia lo stream
    assert voce_lib.aggiorna_scarti_fuori_scala(1, 4.4) == (2, True, True)


def test_pulisci_con_shortcut_none_su_errore_o_vuoto(monkeypatch):
    def esplode(cmd, **kw):
        raise voce_lib.subprocess.TimeoutExpired(cmd, 1)
    monkeypatch.setattr(voce_lib.subprocess, "run", esplode)
    assert voce_lib.pulisci_con_shortcut("testo", "Voce Pulita", timeout=1) is None

    def vuoto(cmd, **kw):
        class E: returncode = 0
        return E()  # non scrive nessun output
    monkeypatch.setattr(voce_lib.subprocess, "run", vuoto)
    assert voce_lib.pulisci_con_shortcut("testo", "Voce Pulita", timeout=1) is None


def test_ruolo_editabile_riconosce_le_caselle_di_testo():
    assert voce_lib.ruolo_editabile("AXTextArea")
    assert voce_lib.ruolo_editabile("AXTextField")
    assert voce_lib.ruolo_editabile("AXSearchField")
    assert not voce_lib.ruolo_editabile("AXButton")
    assert not voce_lib.ruolo_editabile("AXWebArea")
    assert not voce_lib.ruolo_editabile(None)


def test_scegli_casella_prende_la_piu_in_basso_poi_la_piu_larga():
    # y cresce verso il basso: nelle chat la casella di scrittura sta in fondo
    assert voce_lib.scegli_casella([]) is None
    assert voce_lib.scegli_casella([(100, 500), (700, 300)]) == 1
    assert voce_lib.scegli_casella([(700, 200), (700, 600)]) == 1


def test_file_audio_da_eliminare_tiene_solo_le_ultime():
    nomi = [f"dettatura_2026082{i}_120000.wav" for i in range(5)]
    assert voce_lib.file_audio_da_eliminare(nomi, 3) == nomi[:2]
    assert voce_lib.file_audio_da_eliminare(nomi, 10) == []
    assert voce_lib.file_audio_da_eliminare(nomi, 0) == nomi  # spenta: via tutto


def test_salva_audio_recente_scrive_wav_e_ruota(tmp_path):
    import wave
    audio = np.zeros(1600, dtype="float32")
    # spenta di default: non scrive niente e non crea cartelle
    assert voce_lib.salva_audio_recente(audio, tmp_path / "audio", 0) is None
    assert not (tmp_path / "audio").exists()
    percorsi = [voce_lib.salva_audio_recente(audio, tmp_path / "audio", 2) for _ in range(3)]
    assert all(p is not None for p in percorsi)
    rimasti = sorted(p.name for p in (tmp_path / "audio").glob("dettatura_*.wav"))
    assert len(rimasti) == 2
    assert percorsi[0].name not in rimasti  # la piu' vecchia e' stata eliminata
    with wave.open(str(percorsi[-1]), "rb") as w:
        assert w.getframerate() == 16000
        assert w.getnchannels() == 1
        assert w.getnframes() == 1600


def test_in_zona_scrittura_esclude_le_barre_in_alto():
    # finestra da y=0 alta 1000: la barra degli indirizzi (y=50) e' esclusa,
    # la casella della chat in fondo (y=900) e' ammessa
    assert not voce_lib.in_zona_scrittura(50, 0, 1000)
    assert voce_lib.in_zona_scrittura(900, 0, 1000)
    # finestra su un monitor sopra (coordinate negative): stesso criterio
    assert not voce_lib.in_zona_scrittura(-950, -1000, 900)
    assert voce_lib.in_zona_scrittura(-150, -1000, 900)


def test_rimuovi_eco_glossario_sul_caso_reale():
    glossario = ["Claude Code", "Codex", "LeaderAI", "salchiarenza.ai"]
    # caso reale 29/08/2026: il suggerimento colato in testa alla frase
    assert voce_lib.rimuovi_eco_glossario("Glossario, mi arrendo.", glossario) == "mi arrendo."
    # eco completo: anche i nomi ricopiati vanno via
    assert voce_lib.rimuovi_eco_glossario(
        "Glossario: Claude Code, Codex, LeaderAI, salchiarenza.ai. Ciao a te.", glossario
    ) == "Ciao a te."
    # eco puro senza parlato: resta vuoto (scartato a valle come testo vuoto)
    assert voce_lib.rimuovi_eco_glossario("Glossario: LeaderAI.", glossario) == ""


def test_rimuovi_eco_glossario_non_tocca_le_frasi_vere():
    glossario = ["LeaderAI"]
    # "glossario" nel corpo della frase resta
    assert voce_lib.rimuovi_eco_glossario(
        "Aggiungi al glossario la parola LeaderAI", glossario
    ) == "Aggiungi al glossario la parola LeaderAI"
    # "glossario" in apertura seguito da parola normale (niente :/,/.) resta
    assert voce_lib.rimuovi_eco_glossario("Glossario aggiornato bene", glossario) == "Glossario aggiornato bene"
    assert voce_lib.rimuovi_eco_glossario("Mi arrendo.", glossario) == "Mi arrendo."


def test_origine_distingue_sessioni_nella_stessa_cartella():
    a = voce_hook.origine_risposta({"session_id": "sessione-a", "cwd": "/lavoro/LeaderAI",
                                   "transcript_path": "/home/.codex/sessions/a.jsonl"})
    b = voce_hook.origine_risposta({"session_id": "sessione-b", "cwd": "/lavoro/LeaderAI",
                                   "transcript_path": "/home/.claude/projects/b.jsonl"})
    assert a["id"] != b["id"]
    assert a["nome"] == "ChatGPT"
    assert b["nome"] == "Claude"


def test_origine_usa_transcript_senza_leggerlo_e_non_accorpa_sconosciute():
    dati = {"transcript_path": r"C:\Users\utente\.claude\projects\uno.jsonl",
            "cwd": r"C:\Lavoro\Cliente"}
    a = voce_hook.origine_risposta(dati)
    assert a == voce_hook.origine_risposta(dati)
    assert a["nome"] == "Claude"
    assert voce_hook.origine_risposta({"cwd": "/stessa"})["id"] != voce_hook.origine_risposta({"cwd": "/stessa"})["id"]


def test_doppione_e_circoscritto_alla_conversazione(tmp_path, monkeypatch):
    monkeypatch.setattr(voce_hook, "ULTIMA_LETTURA", tmp_path / "ULTIMA_LETTURA")
    a, b = {"id": "a", "nome": "Claude"}, {"id": "b", "nome": "Codex"}
    assert voce_hook.gia_letto_da_poco("Fatto", a) is False
    assert voce_hook.gia_letto_da_poco("Fatto", b) is False
    assert voce_hook.gia_letto_da_poco("Fatto", a) is True


def test_hook_consegna_testo_e_origine_al_lettore(tmp_path, monkeypatch):
    import io
    ricevute = []
    monkeypatch.setattr(voce_hook, "BASE", tmp_path)
    monkeypatch.setattr(voce_hook, "ULTIMA_LETTURA", tmp_path / "ULTIMA_LETTURA")
    monkeypatch.setattr(voce_hook, "voce_attiva", lambda: True)
    monkeypatch.setattr(voce_hook, "parla", lambda testo, origine=None: ricevute.append((testo, origine)))
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({
        "session_id": "sessione-codex", "cwd": "/lavoro/Cliente",
        "model": "modello", "turn_id": "turno", "transcript_path": None,
        "last_assistant_message": "Proposta pronta.",
    })))
    voce_hook.main()
    assert ricevute == [("Proposta pronta.", {"id": "sessione-codex", "nome": "ChatGPT"})]


def test_lettura_doppia_ravvicinata_viene_scartata(tmp_path, monkeypatch):
    """Il doppio evento di fine risposta non deve far partire due voci.

    Ogni parla() uccide la lettura in corso: senza questa guardia la seconda
    chiamata tronca l'audio appena iniziato (misurato il 30/08/2026)."""
    monkeypatch.setattr(voce_hook, "ULTIMA_LETTURA", tmp_path / "ULTIMA_LETTURA")

    assert voce_hook.gia_letto_da_poco("stessa risposta") is False
    assert voce_hook.gia_letto_da_poco("stessa risposta") is True
    assert voce_hook.gia_letto_da_poco("risposta diversa") is False


def test_stessa_risposta_dopo_la_finestra_si_rilegge(tmp_path, monkeypatch):
    """Passata la finestra, ripetere la stessa frase resta possibile."""
    monkeypatch.setattr(voce_hook, "ULTIMA_LETTURA", tmp_path / "ULTIMA_LETTURA")
    monkeypatch.setattr(voce_hook, "FINESTRA_DOPPIONE_SEC", 0.0)

    assert voce_hook.gia_letto_da_poco("stessa risposta") is False
    assert voce_hook.gia_letto_da_poco("stessa risposta") is False


def test_punteggiatura_dettata_diventa_segni_veri():
    f = voce_lib.converti_punteggiatura_dettata
    assert f("Domani si parte punto esclamativo") == "Domani si parte!"
    assert f("Si parte, punto esclamativo, e andiamo") == "Si parte! E andiamo"
    assert f("Hai capito punto interrogativo") == "Hai capito?"
    assert f("Aspetta puntini di sospensione") == "Aspetta..."
    assert f("prima riga a capo seconda riga") == "prima riga\nSeconda riga"
    assert f("poi vai a capo subito") == "poi\nSubito"


def test_punteggiatura_dettata_non_tocca_il_parlato_normale():
    f = voce_lib.converti_punteggiatura_dettata
    # con l'articolo si parla DEL segno: resta parola
    assert f("Il punto esclamativo non me lo becca") == "Il punto esclamativo non me lo becca"
    # idioma, non comando
    assert f("Non ne vengo a capo") == "Non ne vengo a capo"
    # "punto" e "virgola" da soli restano parole (li mette gia' Whisper)
    assert f("Il punto e' questo, virgola piu' virgola meno") == "Il punto e' questo, virgola piu' virgola meno"


def test_ripasso_abbina_audio_e_grezzo():
    grezzi = voce_lib.estrai_grezzi_con_orario([
        "2026-08-30 14:19:32,192 INFO grezzo: Frase giusta della dettatura.",
        "2026-08-30 14:19:52,850 INFO grezzo: Altra frase.",
        "riga qualunque senza grezzo",
    ])
    assert len(grezzi) == 2
    assert voce_lib.abbina_audio_a_grezzo(
        "dettatura_20260830_141931.wav", grezzi) == "Frase giusta della dettatura."
    # nessun grezzo nei 15 secondi dopo il salvataggio: niente abbinamento
    assert voce_lib.abbina_audio_a_grezzo("dettatura_20260830_120000.wav", grezzi) is None


def test_ripasso_trova_i_disaccordi_veri():
    assert voce_lib.disaccordi_parole(
        "Dalle colle è emerso questo.", "Dalle call è emerso questo."
    ) == [("colle", "call")]
    # punteggiatura e maiuscole non contano come disaccordo
    assert voce_lib.disaccordi_parole("Va bene, ok.", "va bene ok") == []


def test_ripasso_propone_senza_rendere_globale_una_correzione(tmp_path, monkeypatch, caplog):
    """Giro completo con audio finto: secondo riconoscitore in disaccordo,
    arbitro che propone: anche un suo assenso non modifica il config."""
    import types
    cartella = tmp_path / "audio_recenti"
    cartella.mkdir()
    (cartella / "dettatura_20260830_141931.wav").touch()
    log = tmp_path / "voce.log"
    log.write_text("2026-08-30 14:19:32,000 INFO grezzo: Dalle colle è emerso questo.\n")
    config = tmp_path / "config.local.json"
    config.write_text('{"sostituzioni": {}}')

    finto_mlx = types.SimpleNamespace(
        transcribe=lambda *a, **k: {"text": "Dalle call è emerso questo."})
    monkeypatch.setitem(sys.modules, "mlx_whisper", finto_mlx)
    monkeypatch.setattr(
        voce_lib, "carica_config",
        lambda: {"lingua": "it", "glossario": [], "sostituzioni": {}})

    class Arbitro:
        returncode = 0
        stdout = '{"colle": "call"}'
        stderr = ""
    monkeypatch.setattr(voce_lib.subprocess, "run", lambda *a, **k: Arbitro())

    nuove = voce_lib.ripassa_audio_conservati(
        cartella, [log], config, ["agente-finto"], "modello-finto")

    assert nuove == {"colle": "call"}
    assert json.loads(config.read_text())["sostituzioni"] == {}


def test_risposta_arbitro_smaschera_agente_fallito():
    """Caso vero del 04/09/2026: la CLI con la sessione OAuth scaduta esce con
    1 e stampa l'errore su stdout. Prima passava per 'nessuna correzione
    sicura'; ora torna l'errore reale da mettere nel registro."""
    proposte, errore = voce_lib.risposta_arbitro(
        1, "Failed to authenticate: OAuth session expired and could not be refreshed\n")
    assert proposte == {}
    assert "codice 1" in errore and "OAuth session expired" in errore
    # uscita zero ma senza JSON: e' comunque un fallimento, non "nessuna coppia"
    proposte, errore = voce_lib.risposta_arbitro(0, "Non posso rispondere.")
    assert proposte == {} and "senza JSON" in errore
    proposte, errore = voce_lib.risposta_arbitro(0, "", "boom su stderr")
    assert proposte == {} and "boom su stderr" in errore
    # risposte vere: JSON con coppie, o {} sincero dell'arbitro
    assert voce_lib.risposta_arbitro(0, 'Ecco: {"colle": "call"}') == ({"colle": "call"}, None)
    assert voce_lib.risposta_arbitro(0, "{}") == ({}, None)


def test_ripasso_arbitro_fallito_lo_dice_nel_registro(tmp_path, monkeypatch, caplog):
    """Stesso giro del test sopra, ma l'arbitro fallisce come la notte del
    04/09/2026: niente imparato, config intatto e nel registro l'errore vero,
    non 'nessuna correzione sicura'."""
    import logging
    import types
    cartella = tmp_path / "audio_recenti"
    cartella.mkdir()
    (cartella / "dettatura_20260830_141931.wav").touch()
    log = tmp_path / "voce.log"
    log.write_text("2026-08-30 14:19:32,000 INFO grezzo: Dalle colle è emerso questo.\n")
    config = tmp_path / "config.local.json"
    config.write_text('{"sostituzioni": {}}')
    finto_mlx = types.SimpleNamespace(
        transcribe=lambda *a, **k: {"text": "Dalle call è emerso questo."})
    monkeypatch.setitem(sys.modules, "mlx_whisper", finto_mlx)
    monkeypatch.setattr(
        voce_lib, "carica_config",
        lambda: {"lingua": "it", "glossario": [], "sostituzioni": {}})

    class ArbitroScaduto:
        returncode = 1
        stdout = "Failed to authenticate: OAuth session expired and could not be refreshed\n"
        stderr = ""
    monkeypatch.setattr(voce_lib.subprocess, "run", lambda *a, **k: ArbitroScaduto())

    caplog.set_level(logging.INFO, logger="voce")
    nuove = voce_lib.ripassa_audio_conservati(
        cartella, [log], config, ["agente-finto"], "modello-finto")

    assert nuove == {}
    assert json.loads(config.read_text())["sostituzioni"] == {}
    assert "1 disaccordi, arbitro fallito" in caplog.text
    assert "OAuth session expired" in caplog.text
    assert "nessuna correzione sicura" not in caplog.text


def test_casella_ammissibile_accetta_documenti_e_rifiuta_barre():
    # chat in fondo alla finestra: ammessa (come prima)
    assert voce_lib.casella_ammissibile(y_casella=700, altezza_casella=40,
                                        y_finestra=0, altezza_finestra=800) is True
    # area documento: parte dall'alto ma copre meta' finestra -> ammessa
    assert voce_lib.casella_ammissibile(y_casella=60, altezza_casella=700,
                                        y_finestra=0, altezza_finestra=800) is True
    # barra degli indirizzi: in alto E bassa di statura -> mai
    assert voce_lib.casella_ammissibile(y_casella=40, altezza_casella=28,
                                        y_finestra=0, altezza_finestra=800) is False


# --- il cursore automatico non deve perdersi (misure vere 08/09/2026) ---
# Casi presi dal Mac di Sal: Chrome dichiara una finestra che non copre i
# suoi stessi pezzi, Claude espone una striscia da 33 punti, il Finder
# espone la scrivania. Su tutti e tre la dettatura finiva nel vuoto.

def test_cornice_reale_allarga_la_finestra_bugiarda_di_chrome():
    # Chrome: finestra dichiarata (-240,-958,1920,958), barra a y=-1028
    finestra = (-240, -958, 1920, 958)
    barra = (-82, -1028, 1416, 24)
    assert voce_lib.cornice_reale(finestra, [barra]) == (-240, -1028, 1920, 1028)
    # senza pezzi fuori, la finestra resta com'e'
    dentro = (-100, -500, 400, 40)
    assert voce_lib.cornice_reale(finestra, [dentro]) == finestra
    assert voce_lib.cornice_reale(finestra, []) == finestra


def test_finestra_credibile_scarta_striscia_e_scrivania():
    schermo = 1080
    # finestra vera di Claude
    assert voce_lib.finestra_credibile((0, 33, 1512, 949), schermo) is True
    # striscia da 33 punti esposta da Claude come prima finestra
    assert voce_lib.finestra_credibile((0, 0, 1512, 33), schermo) is False
    # scrivania del Finder: alta 2062, copre due monitor
    assert voce_lib.finestra_credibile((-240, -1080, 1920, 2062), schermo) is False
    # finestra alta esattamente quanto lo schermo: passa
    assert voce_lib.finestra_credibile((-240, -1080, 1920, 1080), schermo) is True
    assert voce_lib.finestra_credibile(None, schermo) is False


def test_ordina_finestre_il_mouse_sposta_solo_la_precedenza():
    finestre = [(0, 0, 800, 600), (1000, 0, 800, 600)]
    # mouse fermo altrove: ordine dell'app, nessuna finestra esclusa
    assert voce_lib.ordina_finestre(finestre, (5000, 5000)) == [0, 1]
    assert voce_lib.ordina_finestre(finestre, None) == [0, 1]
    # mouse dentro la seconda: si prova quella per prima, l'altra resta in coda
    assert voce_lib.ordina_finestre(finestre, (1400, 300)) == [1, 0]
    assert voce_lib.ordina_finestre([], (0, 0)) == []


def test_ordina_finestre_con_due_monitor_vince_quello_del_mouse():
    # coordinate Accessibility: il Samsung sta sopra il monitor integrato
    schermi = [(0, 0, 1512, 982), (-1015, -1080, 1920, 1080)]
    piccola = (100, 100, 800, 600)       # finestra col focus, monitor integrato
    grande = (-800, -900, 1200, 700)     # stessa app, sul Samsung
    finestre = [piccola, grande]
    # mouse sul Samsung ma fuori da tutte e due: prima la finestra sul suo monitor
    assert voce_lib.ordina_finestre(finestre, (-900, -50), schermi) == [1, 0]
    # mouse dentro la piccola: quella resta prima
    assert voce_lib.ordina_finestre(finestre, (300, 300), schermi) == [0, 1]
    # monitor sconosciuti o uno solo: ordine dell'app come prima
    assert voce_lib.ordina_finestre(finestre, (-900, -50), None) == [0, 1]
    assert voce_lib.ordina_finestre(finestre, (-900, -50), schermi[:1]) == [0, 1]


def test_app_sul_monitor_del_mouse_decide_il_bersaglio_con_due_monitor():
    # 20/09/2026 15:06: Chrome sul Samsung, Claude (col focus) sul monitor
    # piccolo; il mouse e la pill sul Samsung: il bersaglio deve essere Chrome.
    schermi = [(0, 0, 1512, 982), (-1015, -1080, 1920, 1080)]
    chrome, claude, voce = 716, 64330, 27843
    finestre = [(claude, (0, 33, 1512, 949)), (chrome, (-1015, -958, 1920, 958)),
                (voce, (-300, -200, 340, 60))]  # la pill stessa, mai bersaglio
    assert voce_lib.app_sul_monitor(finestre, claude, 1, schermi, voce) == chrome
    # l'app davanti sta gia' sul monitor del mouse: nulla cambia
    assert voce_lib.app_sul_monitor(finestre, chrome, 1, schermi, voce) is None
    assert voce_lib.app_sul_monitor(finestre, claude, 0, schermi, voce) is None
    # sul monitor del mouse non c'e' niente, o il monitor non si sa: nulla cambia
    assert voce_lib.app_sul_monitor([(claude, (0, 33, 1512, 949))], claude, 1, schermi) is None
    assert voce_lib.app_sul_monitor(finestre, claude, None, schermi) is None
    # due app sul Samsung: vince la piu' avanti
    finestre2 = [(claude, (0, 33, 1512, 949)), (99, (-900, -900, 800, 600)), (chrome, (-1015, -958, 1920, 958))]
    assert voce_lib.app_sul_monitor(finestre2, claude, 1, schermi) == 99


def test_app_ha_finestra_sul_monitor():
    # 20/09/2026 15:41: il ritorno alla chat Claude non deve cambiare monitor
    schermi = [(0, 0, 1512, 982), (-1015, -1080, 1920, 1080)]
    finestre = [(64330, (0, 33, 1512, 949)), (716, (-1015, -958, 1920, 958))]
    assert voce_lib.app_ha_finestra_sul_monitor(finestre, 64330, 0, schermi) is True
    assert voce_lib.app_ha_finestra_sul_monitor(finestre, 64330, 1, schermi) is False
    assert voce_lib.app_ha_finestra_sul_monitor(finestre, 716, 1, schermi) is True
    assert voce_lib.app_ha_finestra_sul_monitor(finestre, 716, None, schermi) is True
    assert voce_lib.app_ha_finestra_sul_monitor([], 716, 1, schermi) is False


def test_e_browser_chromium():
    # 20/09/2026, ChatGPT in Chrome: la pagina esiste per Accessibility solo
    # se si chiede l'interfaccia estesa; Safari e le app native non ne hanno bisogno
    assert voce_lib.e_browser_chromium("com.google.Chrome") is True
    assert voce_lib.e_browser_chromium("com.google.Chrome.canary") is True
    assert voce_lib.e_browser_chromium("com.brave.Browser") is True
    assert voce_lib.e_browser_chromium("com.apple.Safari") is False
    assert voce_lib.e_browser_chromium("com.anthropic.claudefordesktop") is False
    assert voce_lib.e_browser_chromium(None) is False


def test_sveglia_chiede_la_pagina_al_browser_chromium():
    # la richiesta parte al tasto premuto, una volta sola, e non tocca le altre app
    import ast
    import logging
    from types import SimpleNamespace
    set_attr = []
    stato = {"AXManualAccessibility": None, "AXEnhancedUserInterface": False}
    ax = SimpleNamespace(AXUIElementCreateApplication=lambda pid: "ax_app",
                         AXUIElementSetAttributeValue=lambda el, attr, val: set_attr.append((attr, val)) or 0)
    spazio = dict(
        logging=logging, cfg={"cursore_automatico": True}, AX=ax,
        _ax_valore=lambda el, attr: stato.get(attr),
        _focus_in_casella=lambda ax_app: True,
        e_browser_chromium=voce_lib.e_browser_chromium, app_su_chromium=voce_lib.app_su_chromium,
    )
    path = REPO_ROOT / "mac" / "detta.py"
    nodi = [n for n in ast.parse(path.read_text()).body
            if isinstance(n, ast.FunctionDef) and n.name in ("_sveglia_accessibilita", "_chiedi_albero_electron", "_chiedi_pagina_browser")]
    exec(compile(ast.Module(body=nodi, type_ignores=[]), str(path), "exec"), spazio)
    chrome = SimpleNamespace(processIdentifier=lambda: 716, bundleIdentifier=lambda: "com.google.Chrome")
    spazio["_sveglia_accessibilita"](chrome)
    assert set_attr == [("AXEnhancedUserInterface", True)]
    stato["AXEnhancedUserInterface"] = True  # gia' accesa: non si richiede
    spazio["_sveglia_accessibilita"](chrome)
    assert set_attr == [("AXEnhancedUserInterface", True)]
    claude = SimpleNamespace(processIdentifier=lambda: 1, bundleIdentifier=lambda: "com.anthropic.claudefordesktop")
    spazio["_sveglia_accessibilita"](claude)
    assert set_attr == [("AXEnhancedUserInterface", True)]  # app nativa: niente richiesta


def test_finestra_su_altro_schermo():
    schermi = [(0, 0, 1512, 982), (-1015, -1080, 1920, 1080)]
    assert voce_lib.schermo_del_punto((-900, -50), schermi) == 1
    assert voce_lib.schermo_del_punto((5000, 5000), schermi) is None
    assert voce_lib.schermo_della_finestra((100, 100, 800, 600), schermi) == 0
    assert voce_lib.finestra_su_altro_schermo((100, 100, 800, 600), (-900, -50), schermi) is True
    assert voce_lib.finestra_su_altro_schermo((-800, -900, 1200, 700), (-900, -50), schermi) is False
    # un monitor solo, mouse fuori da tutto o finestra illeggibile: mai una condizione
    assert voce_lib.finestra_su_altro_schermo((100, 100, 800, 600), (-900, -50), schermi[:1]) is False
    assert voce_lib.finestra_su_altro_schermo((100, 100, 800, 600), (5000, 5000), schermi) is False
    assert voce_lib.finestra_su_altro_schermo(None, (-900, -50), schermi) is False


# --- l'albero Accessibility delle app Electron si accende DOPO il primo tocco ---
# Caso reale 17/09/2026 (app Claude 2.110.x): "quando libero il tasto fa un
# rumore strano". Il cursore automatico leggeva un guscio di 9 gruppi senza
# caselle, dichiarava "nessuna casella" e l'incolla partiva alla cieca con
# l'avviso "Basso", anche se il cursore stava gia' nella chat (8 dettature su
# 8 quel mattino). Misurato: mezzo secondo dopo il primo tocco l'albero e'
# pieno (449-648 elementi, casella a fuoco).

def _cursore_automatico_mac():
    """Carica metti_cursore_in_casella di mac/detta.py con Accessibility finta.
    Torna uno stato con chiama(passate, focus_dopo_attesa=False, focus=False):
    passate = risultato di _cerca_casella a ogni giro (None = nessuna casella).
    La memoria delle caselle vive nello stesso spazio: piu' chiamate la condividono."""
    import ast
    import logging
    from types import SimpleNamespace

    stato = SimpleNamespace(attese=[], giri=[], click=[], salvataggi=[], focus=False, focus_dopo_attesa=False,
                            passate=[None], finestra=(0, 33, 1512, 949), casella_a_fuoco=(100, 900, 1300, 60),
                            schermi=[(0, 0, 1512, 982)], mouse=(700, 500))

    def cerca(ax_app, finestra, geo, con_pagina):
        stato.giri.append(con_pagina)
        return stato.passate[min(len(stato.giri) - 1, len(stato.passate) - 1)]

    def dormi(secondi):
        stato.attese.append(secondi)
        if stato.focus_dopo_attesa:  # albero acceso: la casella aveva gia' il focus
            stato.focus = True

    ax = SimpleNamespace(
        AXUIElementCreateApplication=lambda pid: "ax_app",
        AXUIElementSetAttributeValue=lambda *a: 0, kAXFocusedAttribute="AXFocused",
        kAXFocusedUIElementAttribute="AXFocusedUIElement",
    )
    spazio = dict(
        logging=logging, cfg={"cursore_automatico": True}, AX=ax,
        time=SimpleNamespace(sleep=dormi),
        _focus_in_casella=lambda ax_app: stato.focus,
        _finestre_bersaglio=lambda ax_app: ([("finestra", stato.finestra)], 0, 1),
        _cerca_casella=cerca, _click_sintetico=lambda geo: stato.click.append(geo),
        _geometria_finestra_a_fuoco=lambda ax_app: stato.finestra,
        _schermi_ax=lambda: stato.schermi, _posizione_mouse=lambda: stato.mouse,
        finestra_su_altro_schermo=voce_lib.finestra_su_altro_schermo,
        schermo_del_punto=voce_lib.schermo_del_punto, schermo_della_finestra=voce_lib.schermo_della_finestra,
        e_browser_chromium=voce_lib.e_browser_chromium, app_su_chromium=voce_lib.app_su_chromium,
        _salva_caselle_ricordate=lambda: stato.salvataggi.append(dict(spazio["_caselle_ricordate"])),
        _ax_valore=lambda el, attr: "casella", _ax_geometria=lambda el: stato.casella_a_fuoco,
        chiave_casella=voce_lib.chiave_casella, posizione_relativa=voce_lib.posizione_relativa,
        punto_da_relativa=voce_lib.punto_da_relativa,
    )
    path = REPO_ROOT / "mac" / "detta.py"
    nodi = [
        n for n in ast.parse(path.read_text()).body
        if (isinstance(n, ast.FunctionDef)
            and n.name in ("metti_cursore_in_casella", "_casella_nelle_finestre",
                           "_ricorda_casella", "_punto_ricordato", "_chiedi_albero_electron",
                           "_porta_sul_monitor_del_mouse", "_chiedi_pagina_browser"))
        or (isinstance(n, ast.Assign)
            and any(getattr(t, "id", "") in ("AX_ATTESA_RISVEGLIO_SEC", "AX_GIRI_RISVEGLIO", "_caselle_ricordate")
                    for t in n.targets))
    ]
    exec(compile(ast.Module(body=nodi, type_ignores=[]), str(path), "exec"), spazio)
    app = SimpleNamespace(processIdentifier=lambda: 41474, localizedName=lambda: "Claude",
                          bundleIdentifier=lambda: "com.anthropic.claudefordesktop")

    def chiama(passate, focus_dopo_attesa=False, focus=False):
        stato.passate, stato.focus_dopo_attesa, stato.focus = passate, focus_dopo_attesa, focus
        stato.attese, stato.giri, stato.click = [], [], []
        return spazio["metti_cursore_in_casella"](app)

    stato.chiama = chiama
    stato.spazio = spazio
    stato.attesa = spazio["AX_ATTESA_RISVEGLIO_SEC"]
    stato.giri_massimi = spazio["AX_GIRI_RISVEGLIO"]
    stato.memoria = spazio["_caselle_ricordate"]
    return stato


def test_cursore_automatico_riprova_quando_l_albero_e_addormentato():
    # primo giro: guscio vuoto; dopo l'attesa l'albero e' acceso e la casella
    # della chat ha gia' il focus -> si scrive li', niente avviso "Basso"
    s = _cursore_automatico_mac()
    assert s.chiama([None], focus_dopo_attesa=True) is True
    assert s.attesa in s.attese and s.attesa <= 0.5  # mezzo secondo, non uno
    assert len(s.giri) == 1 and s.click == []


def test_cursore_automatico_al_secondo_giro_trova_la_casella():
    s = _cursore_automatico_mac()
    casella = ("elemento", (100, 800, 1300, 60))
    assert s.chiama([None, casella]) is True
    assert s.attese.count(s.attesa) == 1
    assert len(s.giri) == 2


def test_cursore_automatico_dopo_tutti_i_giri_senza_memoria_dice_che_caselle_non_ce_ne_sono():
    # finestra leggibile, mai vista con una casella (Finder, Anteprima):
    # l'avviso "Basso" del 30/08 resta, ma solo dopo tutti i giri
    s = _cursore_automatico_mac()
    assert s.chiama([None]) is False
    assert s.giri_massimi == 5 and len(s.giri) == s.giri_massimi
    assert s.attese.count(s.attesa) == s.giri_massimi - 1
    assert s.click == []


def test_cursore_automatico_non_aspetta_se_la_casella_c_e_subito():
    s = _cursore_automatico_mac()
    casella = ("elemento", (100, 800, 1300, 60))
    assert s.chiama([casella]) is True
    assert s.attesa not in s.attese and len(s.giri) == 1


def test_cursore_automatico_ricorda_la_casella_e_ci_clicca_quando_la_finestra_dorme():
    # Sal 17/09/2026, due dettature alla cieca alle 12:47 anche col secondo giro:
    # "deve trovare da solo dove scrivere e deve scrivere". Prima dettatura:
    # casella a fuoco (albero acceso) -> posizione ricordata per app e taglia.
    s = _cursore_automatico_mac()
    assert s.chiama([None], focus=True) is True
    assert ("Claude", 1512, 949) in s.memoria
    # seconda: albero addormentato per tutti i giri -> click dove stava la casella
    assert s.chiama([None]) is True
    assert len(s.giri) == s.giri_massimi
    assert len(s.click) == 1
    x, y, _, _ = s.click[0]
    # dentro la casella vista prima (100, 900, 1300, 60): vicino al bordo sinistro e al fondo
    assert 100 <= x <= 200 and 900 <= y <= 960


def test_cursore_automatico_con_due_monitor_il_testo_segue_la_pill():
    # Sal 20/09/2026, monitor Samsung: la pill (mouse) sta sul Samsung, il focus
    # e' gia' in una casella della chat rimasta sul monitor piccolo e la dettatura
    # finiva la'. Se la stessa app ha una finestra con casella sul monitor del
    # mouse, il cursore va li'.
    s = _cursore_automatico_mac()
    s.schermi = [(0, 0, 1512, 982), (-1015, -1080, 1920, 1080)]
    s.mouse = (-300, -50)
    piccola, grande = (0, 33, 1512, 949), (-900, -1000, 1600, 900)
    s.finestra = piccola
    s.spazio["_finestre_bersaglio"] = lambda ax_app: ([("finestra", piccola), ("finestra", grande)], 0, 2)
    casella_grande = ("elemento", (-800, -200, 1400, 60))
    # il focus gentile non cambia finestra (la finestra a fuoco resta la piccola): si clicca
    assert s.chiama([casella_grande], focus=True) is True
    assert s.click == [casella_grande[1]]
    # un monitor solo, oppure mouse sullo stesso monitor del focus: niente click, come prima
    s.schermi = [(0, 0, 1512, 982)]
    assert s.chiama([casella_grande], focus=True) is True
    assert s.click == []
    s.schermi = [(0, 0, 1512, 982), (-1015, -1080, 1920, 1080)]
    s.mouse = (700, 500)
    assert s.chiama([casella_grande], focus=True) is True
    assert s.click == []
    # mouse sul Samsung ma di la' nessuna casella: il focus resta dov'e', si scrive comunque
    s.mouse = (-300, -50)
    assert s.chiama([None], focus=True) is True
    assert s.click == []


def test_cursore_automatico_la_memoria_vale_solo_per_la_stessa_finestra():
    s = _cursore_automatico_mac()
    casella = ("elemento", (100, 800, 1300, 60))
    assert s.chiama([casella]) is True  # ricordata dalla ricerca, finestra 1512x949
    s.finestra = (0, 33, 1000, 700)     # altra taglia: nessuna memoria, niente click, avviso
    assert s.chiama([None]) is False
    assert s.click == []


def test_sveglia_accessibilita_tocca_l_albero_e_chiede_l_accensione_electron():
    # Antigravity 17/09/2026 14:14: albero acceso da 1,5 a 3,5 s dopo la richiesta,
    # oltre l'attesa dell'incolla. Al tasto premuto si chiede e si tocca, mentre si parla.
    import ast
    import logging
    from types import SimpleNamespace
    set_attr, toccate, cercate = [], [], []
    ax = SimpleNamespace(AXUIElementCreateApplication=lambda pid: "ax_app",
                         AXUIElementSetAttributeValue=lambda el, attr, val: set_attr.append((attr, val)) or 0)
    spazio = dict(
        logging=logging, cfg={"cursore_automatico": True}, AX=ax,
        _ax_valore=lambda el, attr: False,  # app Electron con l'albero spento
        _focus_in_casella=lambda ax_app: toccate.append("focus") or False,
        _finestre_bersaglio=lambda ax_app: ([("finestra", (0, 33, 1512, 949))], 0, 1),
        _cerca_casella=lambda *a, **k: cercate.append(k) or None,
        e_browser_chromium=voce_lib.e_browser_chromium, app_su_chromium=voce_lib.app_su_chromium,
    )
    path = REPO_ROOT / "mac" / "detta.py"
    nodi = [n for n in ast.parse(path.read_text()).body
            if isinstance(n, ast.FunctionDef) and n.name in ("_sveglia_accessibilita", "_chiedi_albero_electron", "_chiedi_pagina_browser")]
    exec(compile(ast.Module(body=nodi, type_ignores=[]), str(path), "exec"), spazio)
    app = SimpleNamespace(processIdentifier=lambda: 1, localizedName=lambda: "Antigravity",
                          bundleIdentifier=lambda: "com.google.antigravity")
    spazio["_sveglia_accessibilita"](app)
    assert set_attr == [("AXManualAccessibility", True)]
    assert toccate == ["focus"] and len(cercate) == 1
    # app non Electron (attributo assente): nessuna richiesta, solo il tocco
    set_attr.clear(); toccate.clear(); cercate.clear()
    spazio["_ax_valore"] = lambda el, attr: None
    spazio["_sveglia_accessibilita"](app)
    assert set_attr == [] and toccate == ["focus"]
    # senza app davanti: niente
    spazio["_sveglia_accessibilita"](None)
    assert toccate == ["focus"]


def test_la_sveglia_parte_al_tasto_premuto_in_un_thread_a_parte():
    sorgente = (REPO_ROOT / "mac" / "detta.py").read_text()
    corpo = sorgente.split("def avvia_registrazione", 1)[1].split("\ndef ", 1)[0]
    assert "registrazione avviata" in corpo
    assert "threading.Thread(target=_sveglia_accessibilita" in corpo and "daemon=True" in corpo


def test_memoria_caselle_mac_salvata_a_ogni_novita():
    # la memoria vive su file accanto all'app: ripartendo, Voce e' gia' istruita
    s = _cursore_automatico_mac()
    casella = ("elemento", (100, 800, 1300, 60))
    assert s.chiama([casella]) is True
    assert len(s.salvataggi) == 1 and ("Claude", 1512, 949) in s.salvataggi[0]
    assert s.chiama([casella]) is True  # stessa posizione: niente riscrittura
    assert len(s.salvataggi) == 1


def test_posizione_relativa_e_punto_da_relativa_si_rispecchiano():
    finestra = (0, 33, 1512, 949)
    casella = (100, 900, 1300, 60)
    relativa = voce_lib.posizione_relativa(finestra, casella)
    assert voce_lib.punto_da_relativa(finestra, relativa) == pytest.approx((140, 940))
    # finestra piu' alta: il punto resta ancorato al fondo
    assert voce_lib.punto_da_relativa((0, 33, 1512, 1149), relativa) == pytest.approx((140, 1140))
    # fuori dalla finestra: niente click
    assert voce_lib.punto_da_relativa((0, 33, 1512, 30), relativa) is None
    assert voce_lib.chiave_casella("Claude", finestra) == ("Claude", 1512, 949)
    assert voce_lib.chiave_casella("", finestra) is None
    assert voce_lib.posizione_relativa((0, 0, 0, 0), casella) is None


def test_memoria_caselle_va_e_torna_dal_json():
    memoria = {("Claude", 1512, 949): (0.0926, 42.0), ("ChatGPT", 1000, 700): (0.2, 30.5)}
    testo = voce_lib.caselle_in_json(memoria)
    assert voce_lib.caselle_da_json(testo) == memoria
    # file rotto, vuoto o con righe strane: memoria vuota o solo le righe buone
    assert voce_lib.caselle_da_json("{rotto") == {}
    assert voce_lib.caselle_da_json("") == {}
    assert voce_lib.caselle_da_json('{"Claude|1512|949": [0.1, 40], "boh": 3, "X|a|b": [1, 2]}') == {("Claude", 1512, 949): (0.1, 40.0)}


# --- trascrizione progressiva (04/09/2026): dove tagliare, come rincollare ---
# Blocchi sintetici: 400 campioni a 16 kHz = 25 ms l'uno, 40 blocchi = 1 s.

def _blocchi(*tratti):
    """tratti = (secondi, rms): torna (rms_per_blocco, campioni_per_blocco)."""
    rms, campioni = [], []
    for secondi, volume in tratti:
        for _ in range(int(round(secondi * 40))):
            rms.append(volume)
            campioni.append(400)
    return rms, campioni


def test_trova_taglio_aspetta_i_12_secondi_anche_con_pause_prima():
    rms, campioni = _blocchi((5, 0.02), (1, 0.005), (5, 0.02))  # pausa a 5s: troppo presto
    assert voce_lib.trova_taglio(rms, campioni, 0) is None


def test_trova_taglio_cade_sulla_prima_pausa_dopo_i_12_secondi():
    rms, campioni = _blocchi((13, 0.02), (1, 0.005), (5, 0.02))
    taglio = voce_lib.trova_taglio(rms, campioni, 0)
    # 13 s di voce + 0,5 s di silenzio = blocco 540 (escluso)
    assert taglio == 13 * 40 + 20
    assert all(v < 0.010 for v in rms[13 * 40:taglio])  # il segmento chiude nel silenzio


def test_trova_taglio_non_taglia_a_meta_parola():
    # parlato continuo con micro-pause da 0,2 s: mai mezzo secondo sotto soglia
    rms, campioni = _blocchi((14, 0.02), (0.2, 0.005), (10, 0.02), (0.2, 0.005), (10, 0.02))
    assert voce_lib.trova_taglio(rms, campioni, 0) is None


def test_trova_taglio_riparte_dall_inizio_del_segmento_aperto():
    rms, campioni = _blocchi((13, 0.02), (1, 0.005), (13, 0.02), (1, 0.005))
    primo = voce_lib.trova_taglio(rms, campioni, 0)
    secondo = voce_lib.trova_taglio(rms, campioni, primo)
    assert primo == 13 * 40 + 20
    # dal primo taglio: 0,5 s di coda di pausa + 13 s voce + 0,5 s silenzio
    assert secondo == primo + 20 + 13 * 40 + 20
    assert voce_lib.trova_taglio(rms, campioni, secondo) is None


def test_trova_taglio_tollera_liste_di_lunghezza_diversa():
    rms, campioni = _blocchi((13, 0.02), (1, 0.005))
    assert voce_lib.trova_taglio(rms + [0.02], campioni, 0) == 13 * 40 + 20
    assert voce_lib.trova_taglio([], [], 0) is None


def test_trova_taglio_rispetta_blocco_minimo_configurato():
    rms, campioni = _blocchi((7, 0.02), (1, 0.005), (7, 0.02))
    assert voce_lib.trova_taglio(rms, campioni, 0) is None
    assert voce_lib.trova_taglio(rms, campioni, 0, blocco_min_sec=6) == 7 * 40 + 20


def test_unisci_segmenti_spazi_singoli_e_maiuscola_dopo_il_punto():
    assert voce_lib.unisci_segmenti(["Ciao a tutti.", "  oggi parliamo di voce.  "]) == (
        "Ciao a tutti. Oggi parliamo di voce."
    )
    assert voce_lib.unisci_segmenti(["", "Solo questo", None]) == "Solo questo"
    assert voce_lib.unisci_segmenti([]) == ""


def test_unisci_segmenti_niente_doppi_segni():
    assert voce_lib.unisci_segmenti(["Prima frase.", ". seconda frase"]) == "Prima frase. Seconda frase"
    assert voce_lib.unisci_segmenti(["Prima frase,", ", e poi"]) == "Prima frase, e poi"
    assert voce_lib.unisci_segmenti(["prima parola", ", e poi"]) == "prima parola, e poi"


def test_unisci_segmenti_frase_a_meta_riparte_minuscola_ma_non_i_nomi():
    glossario = ["Claude Code", "LeaderAI"]
    assert voce_lib.unisci_segmenti(["stavo dicendo che", "Il cliente vuole"], glossario) == (
        "stavo dicendo che il cliente vuole"
    )
    assert voce_lib.unisci_segmenti(["lo faccio con", "LeaderAI e basta"], glossario) == (
        "lo faccio con LeaderAI e basta"
    )
    assert voce_lib.unisci_segmenti(["usa", "Claude Code per questo"], glossario) == (
        "usa Claude Code per questo"
    )
    assert voce_lib.unisci_segmenti(["mando il", "PDF domani"]) == "mando il PDF domani"
    assert voce_lib.unisci_segmenti(["mando il file,", "Domani"]) == "mando il file, domani"


def test_prompt_con_contesto_glossario_piu_coda_del_pezzo_prima():
    glossario = "Glossario: LeaderAI, Codex."
    assert voce_lib.prompt_con_contesto(glossario, "") == glossario
    assert voce_lib.prompt_con_contesto(None, "") is None
    assert voce_lib.prompt_con_contesto(None, "ciao") == "ciao"
    lungo = " ".join(f"parola{i}" for i in range(80))
    prompt = voce_lib.prompt_con_contesto(glossario, lungo)
    coda = prompt[len(glossario) + 1:]
    assert prompt.startswith(glossario + " ")
    assert len(coda) <= 200
    assert coda.startswith("parola")  # tagliato a inizio parola
    assert prompt.endswith("parola79")


# --- catena di arbitri: il primo agente che risponde vince (04/09/2026) ---

def test_comandi_agente_elenca_tutti_gli_agenti_presenti(monkeypatch):
    monkeypatch.setattr(voce_lib.shutil, "which", lambda n: f"/usr/local/bin/{n}")
    comandi = voce_lib.comandi_agente()
    assert [c[0] for c in comandi] == ["claude", "codex"]
    assert voce_lib.comando_agente() == comandi[0]  # compatibilita': il primo


def test_chiedi_arbitro_ripiega_sul_secondo_agente(monkeypatch):
    """Claude installato ma con la sessione scaduta (rc=1) non deve piu'
    azzerare l'apprendimento: si passa a Codex nello stesso giro."""
    chiamate = []

    class Esito:
        def __init__(self, rc, out):
            self.returncode, self.stdout, self.stderr = rc, out, ""

    def finto_run(cmd, **k):
        chiamate.append(cmd[0])
        if cmd[0] == "claude":
            return Esito(1, "Failed to authenticate: OAuth session expired")
        return Esito(0, '{"colle": "call"}')

    monkeypatch.setattr(voce_lib.subprocess, "run", finto_run)
    comandi = [["claude", "-p"], ["codex", "exec"]]
    proposte, errore = voce_lib.chiedi_arbitro(comandi, "prompt")
    assert (proposte, errore) == ({"colle": "call"}, None)
    assert chiamate == ["claude", "codex"]


def test_chiedi_arbitro_dice_chi_ha_fallito(monkeypatch):
    class Esito:
        returncode, stdout, stderr = 1, "sessione scaduta", ""

    def finto_run(cmd, **k):
        if cmd[0] == "codex":
            raise OSError("codex non parte")
        return Esito()

    monkeypatch.setattr(voce_lib.subprocess, "run", finto_run)
    proposte, errore = voce_lib.chiedi_arbitro([["claude"], ["codex"]], "prompt")
    assert proposte == {}
    assert "claude:" in errore and "codex:" in errore and "non parte" in errore
    # nessun agente: errore parlante, niente eccezioni
    assert voce_lib.chiedi_arbitro([], "prompt") == ({}, "nessun agente locale installato")
    # un comando solo (lista di stringhe) resta accettato
    proposte, errore = voce_lib.chiedi_arbitro(["claude"], "prompt")
    assert proposte == {} and errore.startswith("claude:")


# Una ripresa durante Whisper appartiene ancora allo stesso messaggio.
# Le due implementazioni vengono esercitate senza microfono, clipboard o Invio reali.
def _coda_dettature(sistema):
    import ast
    import threading
    if sistema == 'mac':
        return voce_lib.CodaDettature()
    path = REPO_ROOT / 'windows' / 'voice_dettatura_windows.py'
    nodi = [n for n in ast.parse(path.read_text()).body
            if isinstance(n, ast.ClassDef) and n.name == 'CodaDettature']
    spazio = {'threading': threading}
    exec(compile(ast.Module(body=nodi, type_ignores=[]), str(path), 'exec'), spazio)
    assert 'CodaDettature' in spazio, 'Manca la coda che aspetta tutte le dettature'
    return spazio['CodaDettature']()


import pytest


@pytest.mark.parametrize('sistema', ['mac', 'windows'])
def test_dettature_riprese_aspettano_e_si_uniscono_in_ordine(sistema):
    coda = _coda_dettature(sistema)
    consegne, chiusi = [], []
    consegna = lambda testo, bersaglio, revisione: consegne.append((testo, bersaglio))
    coda.apri('prima')
    coda.apri('seconda')
    # La seconda finisce prima della prima: nemmeno in quel caso puo' partire.
    coda.completa('seconda', 'Poi questa.', 'chat')
    coda.consegna_pronte(consegna, chiusi.append)
    assert consegne == [] and chiusi == []
    coda.completa('prima', 'Prima questa.', 'chat')
    coda.consegna_pronte(consegna, chiusi.append)
    assert consegne == [('Prima questa. Poi questa.', 'chat')]
    assert chiusi == ['prima', 'seconda']
    coda.consegna_pronte(consegna, chiusi.append)
    assert len(consegne) == 1


@pytest.mark.parametrize('sistema', ['mac', 'windows'])
def test_dettatura_aperta_trattiene_testo_anche_se_whisper_ha_finito(sistema):
    coda = _coda_dettature(sistema)
    consegne, chiusi = [], []
    coda.apri('prima')
    coda.apri('ancora-parlando')
    coda.completa('prima', 'Una frase.', 'chat')
    coda.consegna_pronte(lambda *args: consegne.append(args), chiusi.append)
    assert consegne == [] and chiusi == []
    # Tocco breve / silenzio: non incastra il testo valido precedente.
    coda.completa('ancora-parlando')
    coda.consegna_pronte(lambda testo, *_: consegne.append(testo), chiusi.append)
    assert consegne == ['Una frase.']
    assert chiusi == ['prima', 'ancora-parlando']


@pytest.mark.parametrize('sistema', ['mac', 'windows'])
def test_ripresa_durante_incolla_invalida_invio_anche_dopo_rilascio(sistema):
    coda = _coda_dettature(sistema)
    coda.apri('prima')
    coda.completa('prima', 'Prima.', 'chat')
    controlli = []
    def consegna(testo, bersaglio, revisione):
        controlli.append(coda.puo_inviare(revisione))
        coda.interrompi_invio()  # pressione, prima ancora che parta il worker audio
        controlli.append(coda.puo_inviare(revisione))
        coda.apri('seconda')
        coda.completa('seconda', 'Seconda.', 'chat')
        controlli.append(coda.puo_inviare(revisione))
    # Prova il primo blocco soltanto; il secondo resta pronto per il prossimo giro.
    coda.consegna_pronte(consegna, lambda _: None)
    assert controlli == [True, False, False]


@pytest.mark.parametrize('sistema', ['mac', 'windows'])
def test_dettature_destinazioni_diverse_non_si_mescolano(sistema):
    coda = _coda_dettature(sistema)
    consegne = []
    for token, testo, target in [('a', 'Uno.', 'chat-a'), ('b', 'Due.', 'chat-b')]:
        coda.apri(token)
        coda.completa(token, testo, target)
    coda.consegna_pronte(lambda testo, target, _: consegne.append((testo, target)), lambda _: None)
    assert consegne == [('Uno.', 'chat-a'), ('Due.', 'chat-b')]


@pytest.mark.parametrize('sistema', ['mac', 'windows'])
def test_click_in_coda_audio_trattiene_il_messaggio(sistema):
    coda = _coda_dettature(sistema)
    consegne = []
    coda.apri('prima')
    coda.completa('prima', 'Prima.', 'chat')
    coda.interrompi_invio()  # tasto gia' rilasciato, worker ancora nella coda audio
    coda.consegna_pronte(lambda *args: consegne.append(args), lambda _: None)
    assert consegne == []
    coda.apri('seconda')
    coda.completa('seconda', 'Seconda.', 'chat')
    coda.consegna_pronte(lambda testo, *_: consegne.append(testo), lambda _: None)
    assert consegne == ['Prima. Seconda.']


def _percorso_consegna_completo(sistema, tmp_path, seconda_durante_incolla=False, *,
                                casella=True, chat=True, vive=None, chat_su_altro_monitor=False):
    """Il percorso reale dell'incolla (funzioni prese dal sorgente) con
    tastiera, finestre e Accessibility finti. `casella` e `chat` possono
    essere un valore fisso o una funzione del NOME del bersaglio; `vive` e'
    l'elenco dei nomi delle app/finestre ancora aperte (tutte, se None)."""
    import ast
    import logging
    import queue
    import threading
    from types import SimpleNamespace
    coda = _coda_dettature(sistema)
    nomi = {42: 'ChatGPT', 43: 'Claude', 44: 'Google Chrome', 45: 'Antigravity'}
    def app_finta(hwnd):
        nome = nomi[hwnd]
        return SimpleNamespace(localizedName=lambda: nome, processIdentifier=lambda: hwnd,
                               isTerminated=lambda: vive is not None and nome not in vive)
    def bersaglio_di(hwnd):
        return (app_finta(hwnd), None) if sistema == 'mac' else hwnd
    def nome_di(bersaglio):
        return bersaglio[0].localizedName() if sistema == 'mac' else nomi[bersaglio]
    bersaglio = bersaglio_di(42)
    campo, inviati, chiusi, riattivati, suoni, controlli = [], [], [], [], [], []
    def incolla(testo, **kwargs):
        campo.append(testo)
        if seconda_durante_incolla and len(campo) == 1:
            coda.interrompi_invio()
            coda.apri('seconda')
            coda.completa('seconda', 'Seconda.', bersaglio)
    def premi(tasto):
        assert tasto == 'enter'
        inviati.append(''.join(campo).strip())
        campo.clear()
    def esito_casella(target):
        nome = target.localizedName() if sistema == 'mac' else nomi[target]
        return casella(nome) if callable(casella) else casella
    def chat_ai(nome, *a):
        return chat(nome) if callable(chat) else chat
    tastiera = SimpleNamespace(press=premi, release=lambda _: None)
    tempo = SimpleNamespace(monotonic=lambda: 100.0, sleep=lambda _: None)
    spazio = dict(
        logging=logging, threading=threading, coda_dettature=coda,
        time=tempo, eventi=queue.Queue(), cfg={'invio_automatico': True},
        CFG={}, INVIO_AUTOMATICO=True, registrando=False, recording=False,
        tasto_premuto=False, key_down=False, ultima_pressione_utente=0,
        ultimo_tasto_utente=None,  # 30/10/2026: un Invio arrivato mentre il testo compariva e' un si'
        invio_di_sal_durante_incolla=voce_lib.invio_di_sal_durante_incolla,  # il Mac la importa, Windows la ridefinisce
        Key=SimpleNamespace(enter='enter'), tastiera=tastiera,
        keyboard_controller=tastiera, incolla=incolla, paste_text=incolla,
        esegui_sicuro=lambda f, *a, **kw: f(*a, **kw),
        riattiva_bersaglio=lambda target, *a: riattivati.append(
            target.localizedName() if sistema == 'mac' else nomi[target]),
        metti_cursore_in_casella=esito_casella,
        voce_attiva=lambda: False, destinazione_agente=chat_ai,
        nome_finestra=lambda hwnd: nomi[hwnd], ritardo_invio=lambda *a: 0,
        finestra_viva=lambda hwnd: vive is None or nomi[hwnd] in vive,
        _ultima_chat_ai=None,
        _fuori_dal_monitor_del_mouse=lambda app: chat_su_altro_monitor,  # solo Mac, due monitor
        chiudi_turno_utente=chiusi.append, _nascondi_o_arma=lambda: None,
        suono=suoni.append, winsound=None,  # avviso "incollato alla cieca"
        _controlla_consegna=lambda *a: controlli.append(a),  # controllo di consegna: provato a parte
        ultime_dettature=voce_lib.UltimeDettature(),  # 31/10/2026: menu Voce, solo in memoria (il Mac)
    )
    path = REPO_ROOT / ('mac/detta.py' if sistema == 'mac' else 'windows/voice_dettatura_windows.py')
    nodi = [n for n in ast.parse(path.read_text()).body
            if isinstance(n, ast.FunctionDef)
            and n.name in ('_incolla_messaggio', '_consegna_dettature', '_bersaglio_di_riserva',
                           'invio_da_annullare', 'invio_di_sal_durante_incolla')]  # le ultime due esistono solo su Windows
    exec(compile(ast.Module(body=nodi, type_ignores=[]), str(path), 'exec'), spazio)
    return SimpleNamespace(
        coda=coda, bersaglio=bersaglio, bersaglio_di=bersaglio_di, nome_di=nome_di,
        consegna=spazio['_consegna_dettature'], campo=campo, inviati=inviati,
        chiusi=chiusi, riattivati=riattivati, suoni=suoni, controlli=controlli, spazio=spazio)


def _percorso_consegna(sistema, tmp_path, seconda_durante_incolla=False, *, casella=True, chat=True):
    p = _percorso_consegna_completo(sistema, tmp_path, seconda_durante_incolla,
                                    casella=casella, chat=chat)
    return p.coda, p.bersaglio, p.consegna, p.campo, p.inviati, p.chiusi


@pytest.mark.parametrize('sistema', ['mac', 'windows'])
def test_consegna_reale_due_pezzi_un_incolla_un_invio(sistema, tmp_path):
    coda, target, consegna, campo, inviati, chiusi = _percorso_consegna(sistema, tmp_path)
    coda.apri('prima')
    coda.apri('seconda')
    coda.completa('prima', 'Prima.', target)
    consegna()
    assert campo == [] and inviati == [] and chiusi == []
    coda.completa('seconda', 'Seconda.', target)
    consegna()
    assert inviati == ['Prima. Seconda.']
    assert chiusi == ['prima', 'seconda']


@pytest.mark.parametrize('sistema', ['mac', 'windows'])
def test_consegna_reale_ripresa_durante_incolla_un_solo_invio(sistema, tmp_path):
    coda, target, consegna, campo, inviati, _ = _percorso_consegna(sistema, tmp_path, True)
    coda.apri('prima')
    coda.completa('prima', 'Prima.', target)
    consegna()
    assert inviati == []
    consegna()
    assert inviati == ['Prima. Seconda.']


@pytest.mark.parametrize('sistema', ['mac', 'windows'])
def test_ripresa_vuota_dopo_incolla_invia_testo_precedente_una_volta(sistema, tmp_path):
    coda, target, consegna, campo, inviati, _ = _percorso_consegna(sistema, tmp_path, True)
    coda.apri('prima')
    coda.completa('prima', 'Prima.', target)
    consegna()
    assert inviati == []
    coda.completa('seconda')  # nessun nuovo parlato, prima frase gia' nel campo
    consegna()
    assert inviati == ['Prima.']
    consegna()
    assert inviati == ['Prima.']


@pytest.mark.parametrize('sistema', ['mac', 'windows'])
def test_chat_ai_senza_casella_invia_lo_stesso(sistema, tmp_path):
    """Antigravity (13/09/2026) non espone nessuna casella all'accessibilita':
    il testo veniva incollato e restava li' finche' Sal non premeva Invio a
    mano, e una frase mai inviata si e' persa. In una chat AI riconosciuta
    l'Invio deve partire lo stesso."""
    coda, target, consegna, campo, inviati, _ = _percorso_consegna(
        sistema, tmp_path, casella=False, chat=True)
    coda.apri('sola')
    coda.completa('sola', 'Frase in una chat cieca.', target)
    consegna()
    assert inviati == ['Frase in una chat cieca.']


@pytest.mark.parametrize('sistema', ['mac', 'windows'])
def test_fuori_dalle_chat_ai_senza_casella_non_si_invia(sistema, tmp_path):
    """Fuori dalle chat AI la prudenza resta: senza casella l'Invio finirebbe
    su un focus ignoto (un bottone qualunque di una pagina)."""
    coda, target, consegna, campo, inviati, _ = _percorso_consegna(
        sistema, tmp_path, casella=False, chat=False)
    coda.apri('sola')
    coda.completa('sola', 'Frase in un documento.', target)
    consegna()
    assert inviati == []


@pytest.mark.parametrize('sistema', ['mac', 'windows'])
def test_davanti_senza_casella_il_testo_torna_nell_ultima_chat_ai(sistema, tmp_path):
    """Sal 18/09/2026 11:36, due dettature per Claude fatte con Gmail davanti
    (Chrome, nessuna casella): incollate alla cieca e perse. «Io non devo
    mettere per forza il cursore all'interno della chat in modo tale che la
    voce capisca dove devo andare. Perché passo da una pagina all'altra.»
    Se davanti non c'e' dove scrivere, il testo torna nell'ultima chat AI."""
    p = _percorso_consegna_completo(
        sistema, tmp_path,
        casella=lambda nome: nome != 'Google Chrome',
        chat=lambda nome: nome == 'Claude')
    p.coda.apri('chat')
    p.coda.completa('chat', 'Guarda la prima email.', p.bersaglio_di(43))
    p.consegna()
    assert p.inviati == ['Guarda la prima email.']
    p.coda.apri('gmail')
    p.coda.completa('gmail', 'Manda, archivia e passa alla prossima.', p.bersaglio_di(44))
    p.consegna()
    assert p.riattivati == ['Claude', 'Google Chrome', 'Claude']
    assert p.inviati == ['Guarda la prima email.', 'Manda, archivia e passa alla prossima.']
    assert p.suoni == []  # nessun «Basso»: il testo e' arrivato


def test_il_ritorno_alla_chat_non_cambia_monitor(tmp_path):
    """Sal 20/09/2026 15:41, Samsung sopra il Mac: Chrome sul Samsung per un
    attimo senza casella leggibile, e il ritorno alla chat Claude tirava il
    testo nell'app sul monitor piccolo: «continua a mettermi dove vuole».
    Se la chat di riserva sta su un altro monitor, il testo resta dov'e'
    (alla cieca, negli Appunti, con l'avviso), senza cambiare monitor."""
    p = _percorso_consegna_completo(
        'mac', tmp_path,
        casella=lambda nome: nome != 'Google Chrome',
        chat=lambda nome: nome == 'Claude',
        chat_su_altro_monitor=True)
    p.coda.apri('chat')
    p.coda.completa('chat', 'Guarda la prima email.', p.bersaglio_di(43))
    p.consegna()
    p.coda.apri('samsung')
    p.coda.completa('samsung', 'Io ho il Mac da 14.', p.bersaglio_di(44))
    p.consegna()
    assert p.riattivati == ['Claude', 'Google Chrome']  # nessun ritorno a Claude
    assert p.suoni == ['Basso']  # alla cieca: testo negli Appunti, avviso


@pytest.mark.parametrize('sistema', ['mac', 'windows'])
def test_una_chat_ai_senza_casella_leggibile_resta_il_bersaglio(sistema, tmp_path):
    """Antigravity non espone caselle (13/09): dettando li' il testo resta li',
    anche se prima si parlava con Claude. La riserva vale solo fuori dalle chat AI."""
    p = _percorso_consegna_completo(
        sistema, tmp_path,
        casella=lambda nome: nome == 'Claude',
        chat=lambda nome: nome in ('Claude', 'Antigravity'))
    p.coda.apri('chat')
    p.coda.completa('chat', 'Prima.', p.bersaglio_di(43))
    p.consegna()
    p.coda.apri('anti')
    p.coda.completa('anti', 'Seconda.', p.bersaglio_di(45))
    p.consegna()
    assert p.riattivati == ['Claude', 'Antigravity']
    assert p.inviati == ['Prima.', 'Seconda.']


@pytest.mark.parametrize('sistema', ['mac', 'windows'])
def test_senza_una_chat_ai_aperta_l_incolla_alla_cieca_resta_come_prima(sistema, tmp_path):
    p = _percorso_consegna_completo(
        sistema, tmp_path,
        casella=lambda nome: nome == 'Claude',
        chat=lambda nome: nome == 'Claude', vive=['Google Chrome'])  # Claude chiusa
    p.coda.apri('chat')
    p.coda.completa('chat', 'Prima.', p.bersaglio_di(43))
    p.consegna()
    p.coda.apri('gmail')
    p.coda.completa('gmail', 'Nel vuoto.', p.bersaglio_di(44))
    p.consegna()
    assert p.riattivati == ['Claude', 'Google Chrome']
    assert p.inviati == ['Prima.']
    assert p.suoni == ['Basso'] if sistema == 'mac' else p.suoni == []


@pytest.mark.parametrize('sistema', ['mac', 'windows'])
def test_errore_stop_non_blocca_dettature_successive(sistema):
    import ast
    import logging
    from types import SimpleNamespace
    coda = _coda_dettature(sistema)
    coda.apri('guasta')
    def guasto(*args):
        raise RuntimeError('microfono scollegato / finestra non disponibile')
    spazio = dict(coda_dettature=coda, logging=logging,
                  registrando=True, recording=True, inizio_registrazione=10,
                  recording_started_at=10, turno_utente_token='guasta',
                  sessione_progressiva=None, stream=SimpleNamespace(stop=guasto),
                  app_frontale=guasto, finestra_frontale=lambda: 42,
                  eventi=SimpleNamespace(put=lambda evento: None),
                  _concludi_dettatura=coda.completa,
                  _nascondi_o_arma=lambda: None)
    nome = 'ferma_e_trascrivi' if sistema == 'mac' else 'stop_recording'
    path = REPO_ROOT / ('mac/detta.py' if sistema == 'mac' else 'windows/voice_dettatura_windows.py')
    nodi = [n for n in ast.parse(path.read_text()).body
            if isinstance(n, ast.FunctionDef) and n.name in (nome, '_avvisa_errore_audio')]
    exec(compile(ast.Module(body=nodi, type_ignores=[]), str(path), 'exec'), spazio)
    try:
        spazio[nome]()
    except RuntimeError:
        pass  # anche il worker runtime cattura l'errore: la coda deve comunque liberarsi
    coda.apri('successiva')
    coda.completa('successiva', 'Questa deve arrivare.', 'chat')
    consegne = []
    coda.consegna_pronte(lambda testo, *_: consegne.append(testo), lambda _: None)
    assert consegne == ['Questa deve arrivare.']


@pytest.mark.parametrize('sistema', ['mac', 'windows'])
def test_errore_trascrizione_conserva_testo_senza_inviare_parziale(sistema, tmp_path):
    coda, target, consegna, campo, inviati, chiusi = _percorso_consegna(sistema, tmp_path)
    coda.apri('prima')
    coda.apri('guasta')
    coda.completa('prima', 'Prima.', target)
    coda.completa('guasta', fallita=True)
    consegna()
    assert ''.join(campo).strip() == 'Prima.'
    assert inviati == []
    assert chiusi == ['prima', 'guasta']


@pytest.mark.parametrize('sistema', ['mac', 'windows'])
def test_pipeline_trascrive_due_pezzi_prima_di_inviare(sistema, tmp_path):
    import ast
    from types import SimpleNamespace
    coda, target, consegna, campo, inviati, chiusi = _percorso_consegna(sistema, tmp_path)
    spazio = consegna.__globals__
    spazio.update(np=np, BASE=tmp_path, SAMPLE_RATE=16000,
                  salva_audio_recente=lambda *a, **kw: None,
                  _trascrivi_con_sessione=lambda audio, sessione: audio,
                  _registra_attesa=lambda durata: None,
                  e_allucinazione=lambda testo: False,
                  applica_sostituzioni=lambda testo, _: testo,
                  converti_punteggiatura_dettata=lambda testo: testo,
                  mani_libere_attive=lambda: False, SHORTCUT_PULIZIA=None,
                  _concludi_dettatura=lambda token, testo='', bersaglio=None, fallita=False:
                      coda.completa(token, testo, bersaglio, fallita))
    path = REPO_ROOT / ('mac/detta.py' if sistema == 'mac' else 'windows/voice_dettatura_windows.py')
    nome = '_trascrivi_e_incolla' if sistema == 'mac' else 'transcribe_and_paste'
    nodi = [n for n in ast.parse(path.read_text()).body
            if isinstance(n, ast.FunctionDef) and n.name == nome]
    exec(compile(ast.Module(body=nodi, type_ignores=[]), str(path), 'exec'), spazio)
    coda.apri('prima')
    coda.apri('seconda')
    args = target if sistema == 'mac' else (target,)
    spazio[nome]('Seconda.', *args, token_turno='seconda')
    consegna()
    assert inviati == [] and campo == [] and chiusi == []
    spazio[nome]('Prima.', *args, token_turno='prima')
    consegna()
    assert inviati == ['Prima. Seconda.']
    assert chiusi == ['prima', 'seconda']


# --- Riaprire il microfono mentre la frase prima si trascrive (30/10/2026) ---
# Sal, 30/10/2026: «quando io ho detto, poi mollo, poi riapro il microfono, la seconda
# dettatura non parte, si è fermata, si è bloccata». Registro, 14:12:26-14:12:31: la
# seconda pressione arriva mentre Whisper lavora sulla prima; parte tardi e perde
# l'attacco (nel wav di 1,5 s c'e' solo «…delle risorse»), Whisper risponde «Grazie.»,
# scartato come allucinazione; il pezzo vuoto contava come un guasto e la prima frase
# restava incollata senza Invio. In due settimane 10 casi su 98 riprese durante la
# trascrizione.

class _LavoroSubito:
    """Thread finto: il lavoro gira subito, la prova resta deterministica."""
    def __init__(self, target=None, args=(), kwargs=None, daemon=None):
        self.target, self.args, self.kwargs = target, args, kwargs or {}

    def start(self):
        self.target(*self.args, **self.kwargs)


def _pipeline_due_pressioni(sistema, tmp_path, testi):
    """Trascrizione, chiusura del pezzo e consegna vere; ogni audio e' il nome del pezzo
    e `testi` dice cosa risponde Whisper (un'eccezione = motore guasto)."""
    from types import SimpleNamespace
    p = _percorso_consegna_completo(sistema, tmp_path)
    spazio = p.spazio

    def whisper(audio, sessione):
        if isinstance(testi[audio], Exception):
            raise testi[audio]
        return testi[audio]
    spazio.update(np=np, BASE=tmp_path, SAMPLE_RATE=16000, threading=SimpleNamespace(Thread=_LavoroSubito),
                  salva_audio_recente=lambda *a, **kw: None, _registra_attesa=lambda _: None,
                  _trascrivi_con_sessione=whisper, e_allucinazione=voce_lib.e_allucinazione,
                  applica_sostituzioni=voce_lib.applica_sostituzioni,
                  converti_punteggiatura_dettata=voce_lib.converti_punteggiatura_dettata,
                  mani_libere_attive=lambda: False, SHORTCUT_PULIZIA=None)
    nome = '_trascrivi_e_incolla' if sistema == 'mac' else 'transcribe_and_paste'
    _dal_sorgente(sistema, [nome, '_concludi_dettatura', '_avvisa_errore_audio', 'TrascrizioneIncompleta'], spazio)
    args = p.bersaglio if sistema == 'mac' else (p.bersaglio,)
    p.trascrivi = lambda pezzo: spazio[nome](pezzo, *args, token_turno=pezzo)
    p.avvisi = lambda: [e[1] for e in list(spazio['eventi'].queue)
                        if isinstance(e, tuple) and e[0] == 'errore_audio']
    return p


@pytest.mark.parametrize('sistema', ['mac', 'windows'])
@pytest.mark.parametrize('seconda', ['Grazie.', ''])  # frase-fantasma di Whisper, oppure niente
def test_seconda_pressione_scartata_la_prima_frase_arriva_e_parte(sistema, seconda, tmp_path):
    """Il caso del 30/10/2026 14:12 sul percorso vero: la prima frase arriva e parte con
    l'Invio una volta sola, come se la seconda pressione non ci fosse stata; per la
    seconda resta l'avviso «ripeti»."""
    prima = "Ok, si è aperto e adesso sono direttamente in quella pagina là."
    p = _pipeline_due_pressioni(sistema, tmp_path, {'prima': prima, 'seconda': seconda})
    p.coda.apri('prima')
    p.coda.apri('seconda')          # Sal riapre mentre Whisper lavora sulla prima
    p.trascrivi('prima')
    assert p.inviati == [] and p.campo == []  # la prima aspetta la seconda, giusto
    p.trascrivi('seconda')
    assert p.inviati == [prima]
    assert p.chiusi == ['prima', 'seconda']
    assert any('ripeti' in avviso for avviso in p.avvisi())


@pytest.mark.parametrize('sistema', ['mac', 'windows'])
def test_prima_pressione_scartata_la_frase_dopo_arriva_e_parte(sistema, tmp_path):
    """Fratello, 30/10/2026 11:31: il pezzo vuoto e' il primo (un tocco diventato «Grazie.»)
    e la frase intera dettata subito dopo restava incollata senza Invio."""
    frase = "Vedi che è arrivata l'email dell'aggiornamento del mio ecosistema."
    p = _pipeline_due_pressioni(sistema, tmp_path, {'tocco': 'Grazie.', 'frase': frase})
    p.coda.apri('tocco')
    p.coda.apri('frase')
    p.trascrivi('tocco')
    p.trascrivi('frase')
    assert p.inviati == [frase]


@pytest.mark.parametrize('sistema', ['mac', 'windows'])
def test_ripresa_scartata_dopo_l_incolla_manda_la_frase_gia_scritta(sistema, tmp_path):
    """Fratello: Sal riprende mentre la prima frase compare (Invio sospeso) e la ripresa
    esce «Grazie.»: la frase gia' nella casella parte, una volta sola, senza reincollarla."""
    prima = "Questa e' la frase che deve partire."
    p = _pipeline_due_pressioni(sistema, tmp_path, {'prima': prima, 'seconda': 'Grazie.'})
    incolla = p.spazio['incolla']

    def incolla_e_riprendi(testo, **kw):
        incolla(testo, **kw)
        p.coda.interrompi_invio()   # il tasto, prima ancora del worker audio
        p.coda.apri('seconda')
    p.spazio['incolla'] = p.spazio['paste_text'] = incolla_e_riprendi
    p.coda.apri('prima')
    p.trascrivi('prima')
    assert p.inviati == []
    p.spazio['incolla'] = p.spazio['paste_text'] = incolla
    p.trascrivi('seconda')
    assert p.inviati == [prima]


@pytest.mark.parametrize('sistema', ['mac', 'windows'])
def test_seconda_pressione_muta_non_ferma_la_frase_prima(sistema, tmp_path):
    """Fratello: una ripresa senza voce (un tocco, mezzo secondo sotto soglia) avvisa
    «Non ho sentito: ripeti.» e non trattiene la frase valida."""
    from types import SimpleNamespace
    import queue
    coda, target, consegna, campo, inviati, chiusi = _percorso_consegna(sistema, tmp_path)
    spazio = consegna.__globals__
    coda.apri('valida')
    coda.apri('muta')
    coda.completa('valida', 'La prima frase parte.', target)
    muta = np.zeros((8000, 1), dtype='float32')  # tocco: 0,5 s di coda e niente voce
    eventi = queue.Queue()
    spazio.update(np=np, FREQ=16000, SAMPLE_RATE=16000, MIN_RECORDING_SEC=0.4, SOGLIA_VOCE=0.004,
                  blocchi=[muta], blocks=[muta], scarti_fuori_scala=0, guasti_cattura=set(),
                  registrando=True, recording=True, inizio_registrazione=-4,
                  recording_started_at=-4, turno_utente_token='muta', sessione_progressiva=None,
                  eventi=eventi, stream=SimpleNamespace(stop=lambda: None, close=lambda: None),
                  app_frontale=lambda: target[0] if sistema == 'mac' else None,
                  scheda_browser_frontale=lambda app: '', finestra_frontale=lambda: target,
                  suono=lambda _: None, beep=lambda *a: None, _concludi_dettatura=coda.completa,
                  _nascondi_o_arma=lambda: eventi.put('nascosto'),
                  _avvisa_errore_audio=lambda testo: eventi.put(('errore_audio', testo)),
                  aggiorna_scarti_fuori_scala=voce_lib.aggiorna_scarti_fuori_scala,
                  audio_fuori_scala=voce_lib.audio_fuori_scala, c_e_voce=voce_lib.c_e_voce,
                  has_voice=lambda audio: voce_lib.c_e_voce(audio),
                  ripara_guadagno_ingresso=lambda rms: False, airbag_stream_muto=lambda durata: None,
                  _trascrivi_e_incolla=lambda *a: pytest.fail('niente voce: Whisper non serve'),
                  transcribe_and_paste=lambda *a: pytest.fail('niente voce: Whisper non serve'))
    nome = 'ferma_e_trascrivi' if sistema == 'mac' else 'stop_recording'
    _dal_sorgente(sistema, [nome], spazio)
    spazio[nome]()
    consegna()
    assert inviati == ['La prima frase parte.']
    assert chiusi == ['valida', 'muta']
    assert ('errore_audio', 'Non ho sentito: ripeti.') in list(eventi.queue)


@pytest.mark.parametrize('sistema', ['mac', 'windows'])
def test_un_guasto_vero_nella_ripresa_ferma_ancora_l_invio(sistema, tmp_path):
    """Il confine della regola: se il motore si rompe Sal ha detto qualcosa che si e'
    perso, e la frase prima non parte da sola (resta incollata, avviso «ripeti»)."""
    prima = "La prima frase resta qui."
    p = _pipeline_due_pressioni(sistema, tmp_path, {'prima': prima, 'seconda': RuntimeError('motore')})
    p.coda.apri('prima')
    p.coda.apri('seconda')
    p.trascrivi('prima')
    p.trascrivi('seconda')
    assert ''.join(p.campo).strip() == prima
    assert p.inviati == []
    assert any('ripeti' in avviso for avviso in p.avvisi())


class _FineComandi(Exception):
    pass


class _ComandiFiniti:
    """La coda dei comandi audio: il worker vero li esegue tutti, poi si ferma."""
    def __init__(self):
        self.voci = []

    def put(self, comando):
        self.voci.append(comando)

    def get(self):
        if not self.voci:
            raise _FineComandi()
        return self.voci.pop(0)


def _avvio_mac(tmp_path, costo_zittire=0.35):
    """Tasto, callback audio, worker e avvio veri del Mac; orologio, voce, suoni e
    finestre finti. Zittire la voce costa quanto misurato con Whisper al lavoro
    (due pkill: mediana 0,18 s, massimo 0,35 s, 30/10/2026)."""
    import collections
    import queue
    import sounddevice as sd
    from types import SimpleNamespace
    orologio = [100.0]
    eventi, suoni, zittita, log = queue.Queue(), [], [], []
    parla = tmp_path / 'PARLANDO'

    def zittisci():
        zittita.append((spazio['registrando'], list(eventi.queue), list(suoni)))
        parla.unlink(missing_ok=True)
        orologio[0] += costo_zittire

    spazio = dict(
        np=np, collections=collections, logging=SimpleNamespace(getLogger=lambda *a: SimpleNamespace(
            info=lambda m, *a: log.append(m % a if a else m), warning=lambda *a: None,
            exception=lambda *a: None)),
        time=SimpleNamespace(monotonic=lambda: orologio[0],
                             sleep=lambda s: orologio.__setitem__(0, orologio[0] + s)),
        threading=SimpleNamespace(Thread=_LavoroSubito), esegui_sicuro=voce_lib.esegui_sicuro,
        coda_dettature=voce_lib.CodaDettature(), comandi_audio=_ComandiFiniti(), eventi=eventi,
        apri_turno_utente=lambda: 'turno', ferma_voce=zittisci, suono=suoni.append,
        app_frontale=lambda: 'Claude', _sveglia_accessibilita=lambda app: None,
        _avvisa_errore_audio=lambda testo: eventi.put(('errore_audio', testo)),
        _concludi_dettatura=lambda *a, **kw: None, ferma_e_trascrivi=lambda: None,
        FLAG_PARLANDO=parla, PROGRESSIVA=False, BARRE=18, FREQ=16000, CODA_RILASCIO_SEC=0.5,
        TASTO='cmd_r', _option_giu=lambda: False, tasto_premuto=False, pressioni_tasto=0,
        registrando=False, inizio_registrazione=None, blocchi=[], rms_blocchi=[],
        livelli=collections.deque([0.0] * 18, maxlen=18), guasti_cattura=set(), volume_corrente=0.0,
        turno_utente_token=None, sessione_progressiva=None,
        ultima_pressione_utente=0.0, ultimo_tasto_utente=None,
        orecchio_vivo=None, apri_rubinetto_esc=lambda: None,  # 31/10/2026: orecchio spento, Esc a parte
    )
    spazio.update({n: getattr(voce_lib, n) for n in ('AnelloAudio', 'inizio_pre_registrazione', 'volumi_barre')
                   if hasattr(voce_lib, n)})
    _dal_sorgente('mac', ['pre_registrazione', 'su_callback', 'su_pressione', 'su_rilascio',
                          'worker_audio', 'avvia_registrazione'], spazio)

    def suona(secondi, valore, blocco=15):
        """Il microfono consegna blocchi da `blocco` campioni: 15 era lo stream di prima
        (misura 30/10/2026), 480 (30 ms) quello di adesso."""
        for _ in range(round(secondi * 16000 / blocco)):
            orologio[0] += blocco / 16000
            spazio['su_callback'](np.full((blocco, 1), valore, dtype='float32'), blocco, None, sd.CallbackFlags())

    def lavora():
        with pytest.raises(_FineComandi):
            spazio['worker_audio']()

    def secondi_presi(valore):
        return sum(len(b) for b in spazio['blocchi'] if abs(float(b[0, 0]) - valore) < 1e-6) / 16000
    return SimpleNamespace(spazio=spazio, orologio=orologio, eventi=eventi, suoni=suoni, zittita=zittita,
                           log=log, parla=parla, suona=suona, lavora=lavora, secondi_presi=secondi_presi)


def test_ripresa_mentre_whisper_lavora_registra_dal_tasto_non_da_quando_parte(tmp_path):
    """La causa dei 1,5 s: Sal parla appena preme, ma la registrazione partiva solo dopo
    aver zittito la voce (fino a 0,35 s con Whisper al lavoro) e l'anello che doveva coprire
    il ritardo («~1 s», 32 blocchi) teneva 0,03 s, perche' i blocchi sono di 15 campioni.
    Ora la frase parte dal tasto (piu' un attimo prima), anche se il worker arriva tardi,
    e pill e suono arrivano prima del lavoro lento."""
    m = _avvio_mac(tmp_path)
    m.suona(1.0, 0.0)                          # silenzio, fuori registrazione
    m.spazio['su_pressione']('cmd_r')          # Sal preme e comincia subito a parlare
    m.suona(0.6, 0.1)                          # il worker e' in ritardo di 0,6 s
    m.lavora()
    assert m.spazio['registrando'] is True
    assert m.secondi_presi(0.1) >= 0.59        # l'attacco della frase c'e' tutto
    assert 0.25 <= m.secondi_presi(0.0) <= 0.31  # piu' un attimo prima del tasto, non di piu'
    # segnali prima del lavoro lento: quando si zittisce la voce, Sal vede e sente gia'
    (registrava, eventi_visti, suoni_sentiti), = m.zittita
    assert registrava and 'ascolto' in eventi_visti and 'Pop' in suoni_sentiti
    # e il registro dice da quanto era premuto il tasto: il caso si legge la prossima volta
    assert any(r.startswith('registrazione avviata') and '0.60s dopo il tasto' in r for r in m.log)


def test_se_l_agente_sta_parlando_la_sua_voce_non_entra_nella_dettatura(tmp_path):
    """Fratello: col tasto premuto mentre l'agente legge ad alta voce, prima si zittisce la
    voce e solo dopo si registra: la sua lettura nelle casse non diventa testo di Sal."""
    m = _avvio_mac(tmp_path, costo_zittire=0.05)
    m.parla.touch()
    m.suona(1.0, 0.2)                          # la voce dell'agente nelle casse
    m.spazio['su_pressione']('cmd_r')
    m.suona(0.1, 0.2)
    m.lavora()
    (registrava, _, _), = m.zittita
    assert registrava is False                 # zittita prima di registrare
    assert m.secondi_presi(0.2) == 0           # niente voce dell'agente nel messaggio
    assert m.spazio['registrando'] is True


def test_mani_libere_partono_con_mezzo_secondo_di_attacco(tmp_path):
    """Fratello: il VAD delle mani libere scatta quando Sal parla gia' da 0,2 s. L'anello
    doveva dargli «~1 s» di attacco e ne dava 0,03: ora mezzo secondo, sotto la pausa di
    0,7 s che le mani libere aspettano dopo la voce dell'agente."""
    m = _avvio_mac(tmp_path)
    m.suona(1.0, 0.0)
    m.suona(0.4, 0.1)                          # Sal parla, il volume fa scattare l'ascolto
    m.spazio['comandi_audio'].put('start')     # come worker_mani_libere: senza tasto
    m.lavora()
    assert m.secondi_presi(0.1) >= 0.39
    assert 0.49 <= m.secondi_presi(0.1) + m.secondi_presi(0.0) <= 0.51


@pytest.mark.parametrize('ripresa', ['tenuta', 'tocco'])
def test_ripreso_nella_coda_del_rilascio_la_registrazione_continua(tmp_path, ripresa):
    """Fratello: Sal molla e ripreme entro il mezzo secondo di coda (15 volte in due
    settimane, 4 erano tocchi). Prima la ripresa aspettava la fine della coda, la
    registrazione si chiudeva e ne partiva una nuova da mezzo secondo muto, che
    tratteneva la frase. Ora e' la stessa registrazione che continua."""
    m = _avvio_mac(tmp_path)
    fermate = []

    def ferma():
        m.spazio['registrando'] = False
        fermate.append(m.orologio[0])
    m.spazio['ferma_e_trascrivi'] = ferma
    m.spazio['su_pressione']('cmd_r')
    m.lavora()
    m.suona(2.0, 0.1)
    m.spazio['su_rilascio']('cmd_r')
    dorme = m.spazio['time'].sleep
    ripreso = []

    def coda_con_ripresa(secondi):
        if not ripreso:                         # a meta' della coda Sal ripreme
            ripreso.append(True)
            dorme(0.3)
            m.spazio['su_pressione']('cmd_r')
            if ripresa == 'tocco':
                dorme(0.05)
                m.spazio['su_rilascio']('cmd_r')
            dorme(secondi - 0.3 - (0.05 if ripresa == 'tocco' else 0))
        else:
            dorme(secondi)
    m.spazio['time'].sleep = coda_con_ripresa
    m.lavora()
    if ripresa == 'tenuta':
        assert fermate == [] and m.spazio['registrando'] is True
        m.spazio['su_rilascio']('cmd_r')
        m.lavora()
    assert len(fermate) == 1                   # una registrazione sola
    assert sum(r.startswith('registrazione avviata') for r in m.log) == 1
    assert m.spazio['coda_dettature']._avvii_in_attesa == 0  # nessun avvio appeso che trattenga l'Invio


def test_ripreso_dopo_la_coda_e_una_registrazione_nuova(tmp_path):
    """Il confine: oltre il mezzo secondo la prima registrazione e' chiusa e la ripresa
    ne apre un'altra, come sempre."""
    m = _avvio_mac(tmp_path)
    fermate = []

    def ferma():
        m.spazio['registrando'] = False
        fermate.append(m.orologio[0])
    m.spazio['ferma_e_trascrivi'] = ferma
    m.spazio['su_pressione']('cmd_r')
    m.lavora()
    m.suona(2.0, 0.1)
    m.spazio['su_rilascio']('cmd_r')
    m.lavora()
    m.suona(0.3, 0.0)
    m.spazio['su_pressione']('cmd_r')
    m.lavora()
    assert len(fermate) == 1 and m.spazio['registrando'] is True
    assert sum(r.startswith('registrazione avviata') for r in m.log) == 2


# --- Lo stream consegna blocchi fissi da 30 ms (30/10/2026) ---
# Sal, 30/10/2026: «perché non possiamo risolverlo adesso?». Con `blocksize` di serie lo
# stream del Mac consegna blocchi da 15 campioni: il callback Python gira 1.030 volte al
# secondo e, quando un altro thread tiene il GIL, i blocchi si perdono senza alcun avviso.
# Misura sull'hardware (processo a parte, 10 s): col carico Whisper -1,56% di audio, con un
# thread Python occupato -84%; con 480 campioni (30 ms) 0% in entrambi, nessun overflow.
# Nel registro le dettature lunghe uscivano piu' corte del tempo registrato (33,19 s -> 32,86 s).

def _stream_aperto_da_avvia_stream():
    from types import SimpleNamespace
    aperti = []

    class Stream:
        def __init__(self, **kw):
            aperti.append(kw)

        def start(self):
            pass
    spazio = dict(sd=SimpleNamespace(InputStream=Stream), FREQ=16000, su_callback='callback',
                  nome_device_input=lambda: 'Microfono MacBook Pro')
    spazio.update({n: getattr(voce_lib, n) for n in dir(voce_lib) if n.isupper()})
    _dal_sorgente('mac', ['avvia_stream'], spazio)
    spazio['avvia_stream']()
    return aperti


def test_lo_stream_consegna_blocchi_fissi_da_30_ms():
    """Fra 10 e 30 ms, misurati sull'hardware sotto carico: 10 ms perdeva il 33%, 20 ms
    l'1%, 30 ms niente. 30 ms sono anche il blocco classico del riconoscimento vocale."""
    aperto, = _stream_aperto_da_avvia_stream()
    assert aperto['blocksize'] == 480                      # 30 ms a 16 kHz
    assert aperto['samplerate'] == 16000 and aperto['channels'] == 1 and aperto['dtype'] == 'float32'
    assert aperto['callback'] == 'callback'


def test_le_lineette_della_pill_restano_al_millisecondo_coi_blocchi_grandi():
    """Le lineette disegnano gli ultimi 18 valori di `livelli`: con i blocchi da 15
    campioni erano 18 ms di voce. Con un valore per blocco da 30 ms diventerebbero mezzo
    secondo e la pill cambierebbe aspetto: restano pezzetti da 1 ms, come Sal li vede."""
    import collections
    import sounddevice as sd
    spazio = dict(np=np, registrando=True, guasti_cattura=set(), blocchi=[], rms_blocchi=[],
                  livelli=collections.deque([0.0] * 18, maxlen=18), volume_corrente=0.0,
                  pre_registrazione=None, time=None, FREQ=16000, orecchio_vivo=None)
    spazio.update({n: getattr(voce_lib, n) for n in ('volumi_barre',) if hasattr(voce_lib, n)})
    _dal_sorgente('mac', ['su_callback'], spazio)
    blocco = np.repeat(np.arange(30, dtype='float32') / 1000, 16).reshape(-1, 1)  # 30 pezzetti da 1 ms
    spazio['su_callback'](blocco, 480, None, sd.CallbackFlags())
    assert list(spazio['livelli']) == pytest.approx([k / 1000 for k in range(12, 30)])
    assert spazio['rms_blocchi'] == [pytest.approx(float(np.sqrt(np.mean(blocco ** 2))))]  # pause: per blocco
    assert spazio['volume_corrente'] == pytest.approx(spazio['rms_blocchi'][0])


@pytest.mark.parametrize('blocco', [15, 480])
def test_attacco_dal_tasto_giusto_anche_coi_blocchi_da_30_ms(tmp_path, blocco):
    """Controllo dell'anello coi blocchi nuovi: il tempo, non il numero dei blocchi."""
    m = _avvio_mac(tmp_path)
    m.suona(1.0, 0.0, blocco)
    m.spazio['su_pressione']('cmd_r')
    m.suona(0.6, 0.1, blocco)
    m.lavora()
    assert m.secondi_presi(0.1) >= 0.59
    assert 0.27 <= m.secondi_presi(0.0) <= 0.33              # 0,3 s prima del tasto, al blocco


@pytest.mark.parametrize('blocco', [15, 480])
def test_mani_libere_partono_e_si_fermano_uguali_coi_blocchi_da_30_ms(tmp_path, blocco):
    """Controllo del VAD vero (`worker_mani_libere`) coi blocchi nuovi: legge solo il
    volume dell'ultimo blocco ogni 50 ms. Parte dopo 0,2 s di voce, si ferma dopo 1,4 s
    di silenzio, come prima; l'attacco preso dall'anello resta mezzo secondo."""
    m = _avvio_mac(tmp_path)
    spazio = m.spazio
    comandi = []
    spazio['comandi_audio'] = type('C', (), {'put': lambda self, c: comandi.append((round(m.orologio[0], 2), c))})()
    spazio.update(mani_libere_attive=lambda: True, ultimo_testo_incollato=0.0,
                  FLAG_MANI_LIBERE_ON=tmp_path / 'MANI_LIBERE_ON',
                  cfg={'mani_libere_soglia_voce': 0.018, 'mani_libere_soglia_stop': 0.013,
                       'mani_libere_attivazione_sec': 0.2, 'mani_libere_silenzio_sec': 1.4,
                       'mani_libere_grazia_dopo_voce_sec': 0.7, 'mani_libere_autospegnimento_min': 10})
    _dal_sorgente('mac', ['worker_mani_libere'], spazio)
    inizio, debito, giri = m.orologio[0], [0.0], [0]

    def dorme(secondi):                         # il tempo passa e il microfono consegna
        giri[0] += 1
        if giri[0] > 80:
            raise _FineComandi()
        debito[0] += secondi * 16000
        while debito[0] >= blocco:
            debito[0] -= blocco
            t = m.orologio[0] - inizio
            m.suona(blocco / 16000, 0.05 if 1.0 <= t < 2.0 else 0.002, blocco)
    spazio['time'].sleep = dorme
    with pytest.raises(_FineComandi):
        spazio['worker_mani_libere']()
    (t_start, c_start), (t_stop, c_stop) = comandi
    assert c_start == 'start' and 1.15 <= t_start - inizio <= 1.30
    assert c_stop == 'stop' and 3.35 <= t_stop - inizio <= 3.50


@pytest.mark.parametrize('blocco', [15, 480])
def test_la_progressiva_taglia_sulla_pausa_anche_coi_blocchi_da_30_ms(blocco):
    """Controllo della progressiva coi blocchi nuovi: 12,6 s di voce e poi silenzio, il
    taglio cade a 0,5 s dentro la pausa, alla precisione di un blocco."""
    voce, pausa = round(12.6 * 16000 / blocco), round(1.0 * 16000 / blocco)
    rms = [0.05] * voce + [0.004] * pausa
    campioni = [blocco] * len(rms)
    taglio = voce_lib.trova_taglio(rms, campioni, 0, 16000, voce_lib.SOGLIA_SILENZIO_PROGRESSIVA)
    assert taglio is not None
    assert abs(sum(campioni[:taglio]) / 16000 - 13.1) <= blocco / 16000 + 1e-9


def _avvio_windows(tmp_path):
    """Tasto, worker e avvio veri di Windows; microfono, voce, beep e finestre finti."""
    import collections
    import queue
    from types import SimpleNamespace
    orologio = [100.0]
    eventi, beep, zittita, stream_aperti, log = queue.Queue(), [], [], [], []
    pid = tmp_path / 'voce_pid'

    class Stream:
        def __init__(self, **kw):
            pass

        def start(self):
            stream_aperti.append(orologio[0])
            orologio[0] += 0.1                 # aprire il microfono su Windows costa

    def zittisci():
        zittita.append((spazio['recording'], list(eventi.queue), list(beep), list(stream_aperti)))
        pid.unlink(missing_ok=True)
        orologio[0] += 0.2

    spazio = dict(
        np=np, logging=SimpleNamespace(info=lambda m, *a: log.append(m % a if a else m),
                                       warning=lambda *a: None, exception=lambda *a: None,
                                       getLogger=lambda *a: SimpleNamespace(exception=lambda *a: None)),
        time=SimpleNamespace(monotonic=lambda: orologio[0],
                             sleep=lambda s: orologio.__setitem__(0, orologio[0] + s)),
        threading=SimpleNamespace(Thread=_LavoroSubito), sd=SimpleNamespace(InputStream=Stream),
        coda_dettature=_coda_dettature('windows'), commands=_ComandiFiniti(), eventi=eventi,
        apri_turno_utente=lambda: 'turno', ferma_voce=zittisci, beep=lambda *a: beep.append(a),
        finestra_frontale=lambda: 42, _sveglia_accessibilita=lambda hwnd: None,
        _avvisa_errore_audio=lambda testo: eventi.put(('errore_audio', testo)),
        _concludi_dettatura=lambda *a, **kw: None, stop_recording=lambda: None, audio_callback=None,
        PID_FILE=pid, PROGRESSIVA=False, N_BARRE=18, SAMPLE_RATE=16000, CODA_RILASCIO_SEC=0.5,
        HOTKEY='ctrl_r', TASTO_VOCE=None, key_down=False, voice_key_down=False, pressioni_tasto=0,
        recording=False, recording_started_at=None, blocks=[], rms_blocks=[],
        livelli=collections.deque([0.0] * 18, maxlen=18),
        guasti_cattura=set(), turno_utente_token=None, sessione_progressiva=None, stream=None,
        ultima_pressione_utente=0.0, ultimo_tasto_utente=None,
    )
    _dal_sorgente('windows', ['on_press', 'on_release', 'worker', 'start_recording'], spazio)

    def lavora():
        with pytest.raises(_FineComandi):
            spazio['worker']()
    return SimpleNamespace(spazio=spazio, orologio=orologio, eventi=eventi, beep=beep, zittita=zittita,
                           stream_aperti=stream_aperti, log=log, pid=pid, lavora=lavora)


def test_windows_ripresa_apre_il_microfono_prima_di_zittire_la_voce(tmp_path):
    """Gemella Windows dove il sistema lo permette: lo stream si apre a ogni registrazione
    e un anello come sul Mac non c'e'; almeno microfono, pill e beep non aspettano piu'
    lo stop della voce, e il registro dice quanto dopo il tasto e' partita."""
    w = _avvio_windows(tmp_path)
    w.spazio['on_press']('ctrl_r')
    w.orologio[0] += 0.4                       # il worker arriva tardi
    w.lavora()
    (registrava, eventi_visti, beep_sentiti, aperti), = w.zittita
    assert registrava and aperti and 'ascolto' in eventi_visti and beep_sentiti
    # 0,4 s di ritardo del worker + 0,1 s per aprire il microfono: quanto dell'attacco manca
    assert any(r.startswith('registrazione avviata') and '0.50s dopo il tasto' in r for r in w.log)


def test_windows_se_l_agente_parla_prima_lo_zittisce(tmp_path):
    w = _avvio_windows(tmp_path)
    w.pid.write_text('1234')
    w.spazio['on_press']('ctrl_r')
    w.lavora()
    (registrava, _, _, aperti), = w.zittita
    assert registrava is False and aperti == []
    assert w.spazio['recording'] is True


@pytest.mark.parametrize('ripresa', ['tenuta', 'tocco'])
def test_windows_ripreso_nella_coda_del_rilascio_la_registrazione_continua(tmp_path, ripresa):
    w = _avvio_windows(tmp_path)
    fermate = []

    def ferma():
        w.spazio['recording'] = False
        fermate.append(w.orologio[0])
    w.spazio['stop_recording'] = ferma
    w.spazio['on_press']('ctrl_r')
    w.lavora()
    w.orologio[0] += 2.0
    w.spazio['on_release']('ctrl_r')
    dorme = w.spazio['time'].sleep
    ripreso = []

    def coda_con_ripresa(secondi):
        if not ripreso:
            ripreso.append(True)
            dorme(0.3)
            w.spazio['on_press']('ctrl_r')
            if ripresa == 'tocco':
                w.spazio['on_release']('ctrl_r')
            dorme(secondi - 0.3)
        else:
            dorme(secondi)
    w.spazio['time'].sleep = coda_con_ripresa
    w.lavora()
    if ripresa == 'tenuta':
        assert fermate == [] and w.spazio['recording'] is True
        w.spazio['on_release']('ctrl_r')
        w.lavora()
    assert len(fermate) == 1
    assert len(w.stream_aperti) == 1
    assert w.spazio['coda_dettature']._avvii_in_attesa == 0


# --- Pill: logo "LeaderAI." con il punto verde vivo (23/09/2026) ---

_PROVA_PILL = """
import collections, json, sys
from pathlib import Path
import AppKit, Quartz
root, brand = Path(sys.argv[1]), sys.argv[2]
sorgente = (root / "mac" / "detta.py").read_text(encoding="utf-8")
sezione = sorgente[sorgente.index("# --- pannello di stato nativo"):
                   sorgente.index("# --- microfonino mani-libere")]
spazio = {"AppKit": AppKit, "Quartz": Quartz, "collections": collections,
          "cfg": {"brand": brand}, "SOURCE_BASE": root / "mac",
          "voce_attiva": lambda: False,
          "livelli": collections.deque([0.0] * 18, maxlen=18)}
exec(compile(sezione, "detta.py", "exec"), spazio)
p, f = spazio["punto"], spazio["firma"]
chiavi = lambda: list(p.animationKeys() or []) if p is not None else []
esito = {"testo": spazio["TESTO_MARCHIO"], "punto": p is not None, "firma": f is not None,
         "famiglia": str(spazio["FONT_MARCHIO"].familyName())}
spazio["marchio_entra"]()
esito["entra"] = "entra" in chiavi()
esito["firma_si_disegna"] = f is not None and "disegna" in list(f.animationKeys() or [])
if f is not None:  # la firma sta sotto il testo, lunga quanto il marchio
    esito["firma_sotto"] = f.position().y < spazio["Y_BASE_MARCHIO"]
    esito["firma_lunga"] = abs(f.bounds().size.width - spazio["TESTO_BRAND"].size().width) < 0.5
spazio["punto_pulsa"](True)
esito["pulsa"] = "pulsa" in chiavi()
spazio["punto_pulsa"](False)
esito["pulsa_dopo"] = "pulsa" in chiavi()
spazio["punto_segue_voce"](0.05)
esito["scala_voce_forte"] = p.transform().m11 if p is not None else None
# le scritte di stato sono piccole: in risalto resta il marchio
esito["etichetta_piccola"] = spazio["etichetta"].font().pointSize() <= 0.7 * spazio["FONT_MARCHIO"].pointSize()
spazio["marchio_in_evidenza"](True, subito=True)
m = spazio["marchio"]
base_pill = 58 + m.transform().m11 * (44 + spazio["Y_BASE_MARCHIO"] - 58) + m.transform().m42
esito["evidenza"] = [m.transform().m11, round(base_pill, 1)]
spazio["marchio_in_evidenza"](False, subito=True)
esito["torna_normale"] = m.transform().m11 == 1.0 and m.transform().m42 == 0.0
print(json.dumps(esito))
"""


def _osserva_pill(brand):
    """Costruisce la pill con il codice vero di detta.py, senza mostrarla, in un
    processo a parte: AppKit non accetta due volte le stesse classi."""
    import subprocess
    uscita = subprocess.run([sys.executable, "-c", _PROVA_PILL, str(REPO_ROOT), brand],
                            capture_output=True, text=True, timeout=60, check=True)
    return json.loads(uscita.stdout.strip().splitlines()[-1])


def test_pill_logo_leaderai_con_punto_vivo():
    config = json.loads((REPO_ROOT / "mac" / "config.json").read_text(encoding="utf-8"))
    assert config["brand"] == "LeaderAI."
    # il carattere del logo arriva anche al cliente: l'installazione lo copia
    assert "Onest.ttf" in (REPO_ROOT / "mac" / "install.sh").read_text(encoding="utf-8")
    esito = _osserva_pill(config["brand"])
    assert esito["testo"] == "LeaderAI" and esito["famiglia"] == "Onest" and esito["punto"]
    assert esito["entra"]                                # la pill compare: il punto si accende
    assert esito["firma_si_disegna"] and esito["firma_sotto"] and esito["firma_lunga"]
    assert esito["pulsa"] and not esito["pulsa_dopo"]    # trascrive: pulsa, poi si ferma
    assert esito["scala_voce_forte"] > 1.5               # voce forte: il punto cresce
    # Sal, 23/09/2026: «deve restare in risalto sempre LeaderAI, anche quando trascrivi;
    # le altre scritte piu' piccoline» — scritta piccola, marchio grande al centro
    assert esito["etichetta_piccola"]
    assert esito["evidenza"][0] > 1.2 and esito["evidenza"][1] < 44  # piu' grande e sceso al centro
    assert esito["torna_normale"]                        # mentre parli torna in alto


def test_pill_marchio_senza_punto_finale_resta_testo():
    esito = _osserva_pill("Studio Bianchi")
    assert esito["testo"] == "Studio Bianchi" and not esito["punto"] and not esito["firma"]
    assert esito["evidenza"][0] > 1.2 and esito["torna_normale"]  # anche un marchio qualsiasi resta in risalto


# --- Pill: «Trascrivo…» sparisce quando il testo arriva, non dopo l'Invio (23/09/2026) ---

def _consegna_che_guarda_la_pill(sistema, tmp_path, seconda_durante_incolla=False):
    """Percorso di consegna vero che annota lo stato della pill all'Invio."""
    p = _percorso_consegna_completo(sistema, tmp_path, seconda_durante_incolla)
    eventi = p.spazio['eventi']
    if sistema == 'mac':
        p.spazio['_nascondi_o_arma'] = lambda: eventi.put('nascosto')
    alla_pressione = []
    tastiera = p.spazio['tastiera']
    premi = tastiera.press
    def premi_e_guarda(tasto):
        alla_pressione.append(list(eventi.queue))
        premi(tasto)
    tastiera.press = premi_e_guarda
    return p, eventi, alla_pressione


@pytest.mark.parametrize('sistema', ['mac', 'windows'])
def test_pill_si_chiude_quando_il_testo_e_incollato_non_dopo_l_invio(sistema, tmp_path):
    """Sal, 23/09/2026: la trascrizione dura 1,5 s, ma «Trascrivo…» restava in
    media 4,4 s perche' la pill si chiudeva solo dopo l'Invio automatico, due
    secondi dopo che il testo era gia' nella casella (74 dettature del giorno)."""
    p, eventi, alla_pressione = _consegna_che_guarda_la_pill(sistema, tmp_path)
    p.coda.apri('sola')
    p.coda.completa('sola', 'Frase pronta.', p.bersaglio)
    p.consegna()
    assert p.inviati == ['Frase pronta.']
    assert alla_pressione == [['nascosto']]  # all'Invio la pill era gia' chiusa


@pytest.mark.parametrize('sistema', ['mac', 'windows'])
def test_pill_resta_aperta_se_un_altro_pezzo_sta_arrivando(sistema, tmp_path):
    """Ripresa durante l'incolla: il secondo pezzo e' ancora in coda, la pill
    non si chiude e l'Invio aspetta; si chiude quando arriva anche lui."""
    p, eventi, alla_pressione = _consegna_che_guarda_la_pill(sistema, tmp_path, True)
    p.coda.apri('prima')
    p.coda.completa('prima', 'Prima.', p.bersaglio)
    p.consegna()
    assert p.inviati == [] and list(eventi.queue) == []
    p.consegna()
    assert p.inviati == ['Prima. Seconda.']
    assert alla_pressione == [['nascosto']]


@pytest.mark.parametrize('sistema', ['mac', 'windows'])
def test_pill_si_chiude_all_incolla_anche_in_un_documento(sistema, tmp_path):
    """Il fratello del caso del 23/09: fuori dalle chat AI l'attesa prima
    dell'Invio e' piu' lunga, e la scritta sbagliata sarebbe durata di piu'.
    Anche li' la pill si chiude quando il testo arriva."""
    from types import SimpleNamespace
    p = _percorso_consegna_completo(sistema, tmp_path, casella=True, chat=False)
    eventi = p.spazio['eventi']
    if sistema == 'mac':
        p.spazio['_nascondi_o_arma'] = lambda: eventi.put('nascosto')
    p.spazio['ritardo_invio'] = lambda *a: 3.0
    orologio = [100.0]  # l'attesa dell'Invio scorre davvero, in tempo finto
    p.spazio["time"] = SimpleNamespace(monotonic=lambda: orologio[0],
                                       sleep=lambda s: orologio.__setitem__(0, orologio[0] + s))
    p.spazio['invio_da_annullare'] = lambda ultima, riferimento, nuova: ultima > riferimento or nuova  # solo Windows
    alla_pressione = []
    tastiera = p.spazio['tastiera']
    premi = tastiera.press
    tastiera.press = lambda tasto: (alla_pressione.append(list(eventi.queue)), premi(tasto))
    p.coda.apri('sola')
    p.coda.completa('sola', 'Riga di un documento.', p.bersaglio)
    p.consegna()
    assert p.inviati == ['Riga di un documento.']
    assert alla_pressione == [['nascosto']]


# --- ChatGPT per Mac e' costruita su Chromium: la pagina si chiede (23/09/2026) ---
# Stanotte 12 dettature su 12 nell'app ChatGPT sono partite alla cieca col suono
# d'avviso. Misurato sull'app vera (com.openai.codex): senza richiesta 8 elementi
# e nessuna casella; con l'interfaccia estesa, dopo 2,4 s, 568 elementi e la
# casella «Lavora con ChatGPT». Non e' nell'elenco dei browser e non e' Electron.

def _app_finta(tmp_path, nome, aiutante=None):
    app = tmp_path / f"{nome}.app"
    (app / "Contents" / "MacOS").mkdir(parents=True)
    if aiutante:
        cartella, file = aiutante
        (app / "Contents" / "Frameworks" / cartella).mkdir(parents=True)
        (app / "Contents" / "Frameworks" / cartella / file).touch()
    return app


def test_app_su_chromium_si_riconosce_dal_gestore_dei_crash(tmp_path):
    chatgpt = _app_finta(tmp_path, "ChatGPT", ("Codex Framework.framework/Versions/153.0.8010.48/Helpers", "browser_crashpad_handler"))
    chrome = _app_finta(tmp_path, "Google Chrome", ("Google Chrome Framework.framework/Versions/140.0/Helpers", "chrome_crashpad_handler"))
    nativa = _app_finta(tmp_path, "Note")
    assert voce_lib.app_su_chromium(str(chatgpt)) is True
    assert voce_lib.app_su_chromium(str(chrome)) is True     # il fratello: ogni app su Chromium
    assert voce_lib.app_su_chromium(str(nativa)) is False
    assert voce_lib.app_su_chromium(None) is False


def test_sveglia_chiede_la_pagina_anche_a_chatgpt_per_mac(tmp_path):
    import ast
    import logging
    from types import SimpleNamespace
    set_attr = []
    stato = {"AXManualAccessibility": None, "AXEnhancedUserInterface": False}
    ax = SimpleNamespace(AXUIElementCreateApplication=lambda pid: "ax_app",
                         AXUIElementSetAttributeValue=lambda el, attr, val: set_attr.append((attr, val)) or 0)
    spazio = dict(
        logging=logging, cfg={"cursore_automatico": True}, AX=ax,
        _ax_valore=lambda el, attr: stato.get(attr),
        _focus_in_casella=lambda ax_app: True,
        e_browser_chromium=voce_lib.e_browser_chromium, app_su_chromium=voce_lib.app_su_chromium,
    )
    path = REPO_ROOT / "mac" / "detta.py"
    nodi = [n for n in ast.parse(path.read_text()).body
            if isinstance(n, ast.FunctionDef) and n.name in ("_sveglia_accessibilita", "_chiedi_albero_electron", "_chiedi_pagina_browser")]
    exec(compile(ast.Module(body=nodi, type_ignores=[]), str(path), "exec"), spazio)
    def app(bundle, cartella):
        url = SimpleNamespace(path=lambda: str(cartella))
        return SimpleNamespace(processIdentifier=lambda: 7, bundleIdentifier=lambda: bundle, bundleURL=lambda: url)
    chatgpt = _app_finta(tmp_path, "ChatGPT", ("Codex Framework.framework/Versions/153.0.8010.48/Helpers", "browser_crashpad_handler"))
    spazio["_sveglia_accessibilita"](app("com.openai.codex", chatgpt))
    assert set_attr == [("AXEnhancedUserInterface", True)]
    set_attr.clear()
    spazio["_sveglia_accessibilita"](app("com.apple.Notes", _app_finta(tmp_path, "Note")))
    assert set_attr == []                                      # app nativa: niente richiesta
    stato["AXManualAccessibility"] = False                     # app Electron: la sua strada, non questa
    electron = _app_finta(tmp_path, "Claude", ("Electron Framework.framework/Versions/A/Helpers", "chrome_crashpad_handler"))
    spazio["_sveglia_accessibilita"](app("com.anthropic.claudefordesktop", electron))
    assert set_attr == [("AXManualAccessibility", True)]


def test_invio_fermato_dice_quale_tasto_lo_ha_fermato(tmp_path, caplog):
    """23/09/2026: 4 Invii su 10 si fermano per un tasto premuto nei 2 secondi
    (149 su 416 il 22/09). Il registro dice se era Invio premuto a mano, cosi'
    si decide con i numeri se l'attesa e' troppo lunga."""
    import logging
    from types import SimpleNamespace
    p = _percorso_consegna_completo('mac', tmp_path)
    orologio = [100.0]
    def dormi(s):
        orologio[0] += s
        if orologio[0] > 100.5:  # a meta' attesa la persona preme Invio da sola
            p.spazio['ultima_pressione_utente'] = orologio[0]
            p.spazio['ultimo_tasto_utente'] = 'enter'
    p.spazio['time'] = SimpleNamespace(monotonic=lambda: orologio[0], sleep=dormi)
    p.spazio['ritardo_invio'] = lambda *a: 2.0
    p.spazio['ultimo_tasto_utente'] = None
    p.coda.apri('sola')
    p.coda.completa('sola', 'Frase.', p.bersaglio)
    with caplog.at_level(logging.INFO):
        p.consegna()
    assert p.inviati == []
    assert "invio automatico ANNULLATO (Invio premuto a mano)" in caplog.text


# --- Un tasto o un clic di Sal ferma l'Invio anche mentre il testo compare (23/09/2026) ---
# Sal: «quando metto il cursore nella scrittura o faccio spazio, scrivo una
# lettera, l'Invio automatico si deve bloccare». Il clic non era ascoltato
# affatto e i tasti premuti nel mezzo secondo in cui il testo compariva non
# contavano: 16:35:53 la frase «volevo cercare di capire come» e' partita
# mentre Sal la stava correggendo.

def _consegna_a_orologio(sistema, tmp_path):
    from types import SimpleNamespace
    p = _percorso_consegna_completo(sistema, tmp_path)
    orologio = [100.0]
    p.spazio['time'] = SimpleNamespace(monotonic=lambda: orologio[0],
                                       sleep=lambda s: orologio.__setitem__(0, orologio[0] + s))
    p.spazio['ritardo_invio'] = lambda *a: 2.0
    p.spazio['ultimo_tasto_utente'] = None
    p.coda.apri('sola')
    p.coda.completa('sola', 'Volevo cercare di capire come...', p.bersaglio)
    return p, orologio


def _dal_sorgente(sistema, nomi, spazio):
    import ast
    path = REPO_ROOT / ('mac/detta.py' if sistema == 'mac' else 'windows/voice_dettatura_windows.py')
    nodi = [n for n in ast.parse(path.read_text()).body
            if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name in nomi
            or isinstance(n, ast.Assign) and any(getattr(t, 'id', '') in nomi for t in n.targets)]
    assert {getattr(n, 'name', None) or n.targets[0].id for n in nodi} == set(nomi)
    exec(compile(ast.Module(body=nodi, type_ignores=[]), str(path), 'exec'), spazio)


@pytest.mark.parametrize('sistema', ['mac', 'windows'])
def test_overflow_cattura_si_conserva_senza_io_nel_callback(sistema, caplog):
    """Un buffer perso deve invalidare la registrazione; la callback non fa log."""
    import collections
    import sounddevice as sd
    guasti = set()
    spazio = dict(np=np, logging=logging, registrando=True, recording=True,
                  blocchi=[], blocks=[], rms_blocchi=[], rms_blocks=[],
                  livelli=[], pre_registrazione=collections.deque(maxlen=32),
                  guasti_cattura=guasti, FREQ=16000, volumi_barre=voce_lib.volumi_barre,
                  orecchio_vivo=None)
    nome = 'su_callback' if sistema == 'mac' else 'audio_callback'
    _dal_sorgente(sistema, [nome], spazio)
    stato = sd.CallbackFlags()
    stato.input_overflow = True
    with caplog.at_level(logging.INFO):
        spazio[nome](np.full((400, 1), 0.04, dtype='float32'), 400, None, stato)
    assert guasti == {'input_overflow'}
    assert caplog.records == []


@pytest.mark.parametrize('sistema', ['mac', 'windows'])
@pytest.mark.parametrize('guasto', ['fuori_scala', 'overflow', 'non_finito'])
def test_cattura_guasta_conserva_pezzo_valido_e_non_invia_parziale(sistema, guasto, tmp_path):
    from types import SimpleNamespace
    import queue
    coda, target, consegna, campo, inviati, chiusi = _percorso_consegna(sistema, tmp_path)
    spazio = consegna.__globals__
    coda.apri('valida')
    coda.apri('guasta')
    coda.completa('valida', 'La prima frase resta.', target)
    a = np.full((64000, 1), 1.3 if guasto == 'fuori_scala' else 0.04, dtype='float32')
    if guasto == 'non_finito':
        a[12000] = np.nan
    eventi = queue.Queue()
    trascrizioni = []
    class Lavoro:
        def __init__(self, target, args=(), **kw):
            self.target, self.args = target, args
        def start(self):
            self.target(*self.args)
    spazio.update(np=np, FREQ=16000, SAMPLE_RATE=16000, MIN_RECORDING_SEC=0.4,
                  SOGLIA_VOCE=0.004, threading=SimpleNamespace(Thread=Lavoro),
                  blocchi=[a], blocks=[a], scarti_fuori_scala=0,
                  guasti_cattura={'input_overflow'} if guasto == 'overflow' else set(),
                  registrando=True, recording=True, inizio_registrazione=-4,
                  recording_started_at=-4, turno_utente_token='guasta',
                  sessione_progressiva=None, eventi=eventi,
                  stream=SimpleNamespace(stop=lambda: None, close=lambda: None),
                  app_frontale=lambda: target[0] if sistema == 'mac' else None,
                  scheda_browser_frontale=lambda app: '', finestra_frontale=lambda: target,
                  suono=lambda _: None, beep=lambda *a: None,
                  _concludi_dettatura=coda.completa,
                  _nascondi_o_arma=lambda: eventi.put('nascosto'),
                  _avvisa_errore_audio=lambda testo: eventi.put(('errore_audio', testo)),
                  aggiorna_scarti_fuori_scala=voce_lib.aggiorna_scarti_fuori_scala,
                  audio_fuori_scala=voce_lib.audio_fuori_scala, c_e_voce=voce_lib.c_e_voce,
                  has_voice=lambda audio: voce_lib.c_e_voce(audio),
                  ripara_guadagno_ingresso=lambda rms: False,
                  airbag_stream_muto=lambda durata: None,
                  _trascrivi_e_incolla=lambda *a: trascrizioni.append(a),
                  transcribe_and_paste=lambda *a: trascrizioni.append(a))
    nome = 'ferma_e_trascrivi' if sistema == 'mac' else 'stop_recording'
    _dal_sorgente(sistema, [nome], spazio)
    spazio[nome]()
    consegna()
    assert ''.join(campo).strip() == 'La prima frase resta.'
    assert inviati == []
    assert chiusi == ['valida', 'guasta']
    assert trascrizioni == []
    assert any(isinstance(e, tuple) and e[0] == 'errore_audio' for e in list(eventi.queue))


@pytest.mark.parametrize('sistema', ['mac', 'windows'])
@pytest.mark.parametrize('pezzi,atteso,riprovato', [
    (['Prima.', '', 'Ultima.'], 'Prima. Non inviare. Ultima.', True),
    (['Prima.', 'Sottotitoli e revisione a cura di QTSS', 'Ultima.'],
     'Prima. Non inviare. Ultima.', True),
    (['Prima.', 'Non inviare.', 'Ultima.'], 'Prima. Non inviare. Ultima.', False),
])
def test_progressiva_non_elimina_un_pezzo_senza_recuperare_audio_intero(sistema, pezzi, atteso, riprovato):
    from types import SimpleNamespace
    import threading, queue, time
    chiamate = []
    audio = np.full(48000, 0.04, dtype='float32')
    sessione = SimpleNamespace(pezzi=pezzi, campioni=[16000]*3, inizio_segmento=3,
                              guasta=False, ferma=lambda: None,
                              thread=SimpleNamespace(join=lambda **kw: None, is_alive=lambda: False))
    def intero(a):
        chiamate.append(len(a))
        return 'Prima. Non inviare. Ultima.'
    spazio = dict(np=np, FREQ=16000, SAMPLE_RATE=16000, time=time, logging=logging,
                  cfg={}, CFG={}, eventi=queue.Queue(), _lock_trascrizione=threading.Lock(),
                  trascrivi=intero, _passaggio_unico=intero,
                  e_allucinazione=voce_lib.e_allucinazione, _rifinisci=lambda t: t,
                  unisci_segmenti=voce_lib.unisci_segmenti)
    _dal_sorgente(sistema, ['_trascrivi_con_sessione'], spazio)
    assert spazio['_trascrivi_con_sessione'](audio, sessione) == atteso
    assert chiamate == ([48000] if riprovato else [])


@pytest.mark.parametrize('sistema', ['mac', 'windows'])
@pytest.mark.parametrize('esito', ['vuoto', 'errore'])
def test_progressiva_recupero_fallito_conserva_testo_affidabile(sistema, esito):
    from types import SimpleNamespace
    import threading, queue, time
    sessione = SimpleNamespace(pezzi=['Prima.', '', 'Ultima.'], campioni=[16000]*3,
                              inizio_segmento=3, guasta=False, ferma=lambda: None,
                              thread=SimpleNamespace(join=lambda **kw: None, is_alive=lambda: False))
    def intero(a):
        if esito == 'errore':
            raise RuntimeError('motore indisponibile')
        return ''
    spazio = dict(np=np, FREQ=16000, SAMPLE_RATE=16000, time=time, logging=logging,
                  cfg={}, CFG={}, eventi=queue.Queue(), _lock_trascrizione=threading.Lock(),
                  trascrivi=intero, _passaggio_unico=intero,
                  e_allucinazione=voce_lib.e_allucinazione, _rifinisci=lambda t: t,
                  unisci_segmenti=voce_lib.unisci_segmenti)
    _dal_sorgente(sistema, ['_trascrivi_con_sessione', 'TrascrizioneIncompleta'], spazio)
    with pytest.raises(spazio['TrascrizioneIncompleta']) as incompleto:
        spazio['_trascrivi_con_sessione'](np.full(48000, 0.04, dtype='float32'), sessione)
    assert incompleto.value.testo == 'Prima. Ultima.'


@pytest.mark.parametrize('sistema', ['mac', 'windows'])
def test_progressiva_coda_silenziosa_non_inventa_e_non_riprova(sistema):
    from types import SimpleNamespace
    import threading, queue, time
    audio = np.concatenate([np.full(16000, 0.04, dtype='float32'), np.zeros(16000, dtype='float32')])
    sessione = SimpleNamespace(pezzi=['Non inviare.'], campioni=[16000], inizio_segmento=1,
                              guasta=False, ferma=lambda: None,
                              thread=SimpleNamespace(join=lambda **kw: None, is_alive=lambda: False))
    spazio = dict(np=np, FREQ=16000, SAMPLE_RATE=16000, time=time, logging=logging,
                  cfg={}, CFG={}, eventi=queue.Queue(), _lock_trascrizione=threading.Lock(),
                  SOGLIA_VOCE=0.004, c_e_voce=voce_lib.c_e_voce, has_voice=voce_lib.c_e_voce,
                  trascrivi=lambda a: pytest.fail('ripasso non necessario'),
                  _passaggio_unico=lambda a: pytest.fail('ripasso non necessario'),
                  e_allucinazione=voce_lib.e_allucinazione, _rifinisci=lambda t: t,
                  unisci_segmenti=voce_lib.unisci_segmenti)
    _dal_sorgente(sistema, ['_trascrivi_con_sessione'], spazio)
    assert spazio['_trascrivi_con_sessione'](audio, sessione) == 'Non inviare.'


@pytest.mark.parametrize('sistema', ['mac', 'windows'])
def test_pipeline_progressiva_incompleta_incolla_valido_e_sospende_invio(sistema, tmp_path):
    p = _percorso_consegna_completo(sistema, tmp_path)
    spazio = p.spazio
    spazio.update(np=np, BASE=tmp_path, SAMPLE_RATE=16000,
                  salva_audio_recente=lambda *a, **kw: None,
                  _registra_attesa=lambda _: None,
                  applica_sostituzioni=voce_lib.applica_sostituzioni,
                  converti_punteggiatura_dettata=voce_lib.converti_punteggiatura_dettata,
                  _concludi_dettatura=p.coda.completa)
    nome = '_trascrivi_e_incolla' if sistema == 'mac' else 'transcribe_and_paste'
    _dal_sorgente(sistema, [nome, 'TrascrizioneIncompleta', '_avvisa_errore_audio'], spazio)
    def incompleto(*a):
        raise spazio['TrascrizioneIncompleta']('Prima. Ultima.')
    spazio['_trascrivi_con_sessione'] = incompleto
    p.coda.apri('turno')
    args = p.bersaglio if sistema == 'mac' else (p.bersaglio,)
    spazio[nome](np.full(16000, 0.04, dtype='float32'), *args, token_turno='turno')
    p.consegna()
    assert ''.join(p.campo).strip() == 'Prima. Ultima.'
    assert p.inviati == []
    assert any(isinstance(e, tuple) and e[0] == 'errore_audio' for e in list(spazio['eventi'].queue))


@pytest.mark.parametrize('debug', [False, True])
def test_log_whisper_e_postcorrezioni_distinti_e_solo_debug(debug, caplog):
    from types import SimpleNamespace
    spazio = dict(cfg={'modello': 'locale', 'lingua': 'it', 'debug_dettature': debug,
                       'sostituzioni': {'cloud code': 'Claude Code'}}, logging=logging,
                  mlx_whisper=SimpleNamespace(transcribe=lambda *a, **kw:
                      {'text': 'Apri cloud code.', 'segments': []}),
                  rimuovi_eco_glossario=voce_lib.rimuovi_eco_glossario,
                  applica_sostituzioni=voce_lib.applica_sostituzioni,
                  converti_punteggiatura_dettata=voce_lib.converti_punteggiatura_dettata,
                  ORECCHIO=None)  # 31/10/2026: l'orecchio ha le sue prove
    _dal_sorgente('mac', ['_whisper_grezzo', '_rifinisci'], spazio)
    with caplog.at_level(logging.INFO):
        raw = spazio['_whisper_grezzo'](np.ones(16000, dtype='float32')*0.04)
        assert spazio['_rifinisci'](raw) == 'Apri Claude Code.'
    if debug:
        assert 'whisper originale: Apri cloud code.' in caplog.text
        assert 'postcorrezioni: Apri Claude Code.' in caplog.text
        assert 'grezzo: Apri Claude Code.' not in caplog.text
    else:
        assert 'cloud code' not in caplog.text and 'Claude Code' not in caplog.text


@pytest.mark.parametrize('sistema', ['mac', 'windows'])
def test_avviso_audio_pill_non_scompare_con_chiusura_coda(sistema):
    """L'errore resta leggibile, poi si chiude; una nuova dettatura lo sostituisce."""
    import queue
    from types import SimpleNamespace
    eventi, testi, visibile, ora = queue.Queue(), [], [False], [100.0]
    pannello = SimpleNamespace(orderFrontRegardless=lambda: visibile.__setitem__(0, True),
                              orderOut_=lambda _: visibile.__setitem__(0, False))
    root = SimpleNamespace(deiconify=lambda: visibile.__setitem__(0, True),
                           withdraw=lambda: visibile.__setitem__(0, False), after=lambda *a: None)
    class Elemento:
        def __getattr__(self, nome):
            return lambda *a, **kw: testi.append(a[0]) if nome == 'setStringValue_' else None
    spazio = dict(queue=queue, eventi=eventi, registrando=False, recording=False,
                  time=SimpleNamespace(monotonic=lambda: ora[0]), pannello=pannello,
                  posiziona_pannello=lambda: None, aggiorna_indicatore_voce=lambda: None,
                  brand=Elemento(), etichetta=Elemento(), onda=Elemento(),
                  marchio_in_evidenza=lambda *a, **kw: None, marchio_entra=lambda: None,
                  punto_pulsa=lambda _: None, mascotte_ferma=lambda: None,
                  stop_se_registrazione_troppo_lunga=lambda: None,
                  punto_segue_voce=lambda _: None, volume_corrente=0.04, listener=None,
                  esegui_sicuro=lambda f: f(), aggiorna_rubinetto_esc=lambda: None)
    path = REPO_ROOT / ('mac/detta.py' if sistema == 'mac' else 'windows/voice_dettatura_windows.py')
    classe = next(n for n in ast.parse(path.read_text()).body if isinstance(n, ast.ClassDef)
                  and n.name == ('GestorePannello' if sistema == 'mac' else 'Pannello'))
    metodo = next(n for n in classe.body if isinstance(n, ast.FunctionDef)
                  and n.name == ('tick_' if sistema == 'mac' else 'tick'))
    exec(compile(ast.Module(body=[metodo], type_ignores=[]), str(path), 'exec'), spazio)
    ui = SimpleNamespace(stato='nascosto', _tick=1, _aggiorna_mini=lambda: None,
                         root=root, _disegna_ascolto=lambda: None,
                         _disegna_trascrivo=lambda testo='Trascrivo...': testi.append(testo))
    tick = lambda: spazio[metodo.name](ui, None) if sistema == 'mac' else spazio[metodo.name](ui)
    ui.tick = tick
    eventi.put(('errore_audio', 'Audio interrotto: ripeti.'))
    eventi.put('nascosto')
    tick()
    assert visibile[0] and any('ripeti' in t.lower() for t in testi)
    ora[0] += 5
    tick()
    assert not visibile[0]
    eventi.put(('errore_audio', 'Audio interrotto: ripeti.'))
    tick()
    eventi.put('ascolto')
    tick()
    assert ui.stato == 'ascolto' and visibile[0]


@pytest.mark.parametrize('sistema', ['mac', 'windows'])
def test_tasto_premuto_mentre_il_testo_compare_ferma_l_invio(sistema, tmp_path):
    p, orologio = _consegna_a_orologio(sistema, tmp_path)
    incolla = p.spazio['incolla']
    def incolla_e_sal_corregge(testo, **kw):
        incolla(testo, **kw)                                # il testo compare
        orologio[0] += 0.1
        p.spazio['ultima_pressione_utente'] = orologio[0]   # Sal cancella i puntini
        orologio[0] += 0.4                                  # l'incolla finisce il suo giro
    p.spazio['incolla'] = p.spazio['paste_text'] = incolla_e_sal_corregge
    p.consegna()
    assert p.inviati == []


@pytest.mark.parametrize('sistema', ['mac', 'windows'])
def test_clic_nel_testo_ferma_l_invio_quello_del_programma_no(sistema, tmp_path, caplog):
    import logging
    nome = 'su_clic' if sistema == 'mac' else 'on_click'
    for del_programma, atteso in ((False, []), (True, ['Volevo cercare di capire come...'])):
        p, orologio = _consegna_a_orologio(sistema, tmp_path)
        _dal_sorgente(sistema, [nome], p.spazio)
        clic = p.spazio[nome]
        def dormi(s):
            orologio[0] += s
            if 101.0 < orologio[0] <= 101.1:  # a meta' attesa: cursore nel testo
                clic(del_programma) if sistema == 'mac' else clic(5, 5, 'left', True, del_programma)
        p.spazio['time'].sleep = dormi
        with caplog.at_level(logging.INFO):
            p.consegna()
        assert p.inviati == atteso
    if sistema == 'mac':
        assert "invio automatico ANNULLATO (clic del mouse)" in caplog.text


@pytest.mark.parametrize('sistema', ['mac', 'windows'])
def test_i_tasti_del_programma_non_contano_come_gesti_di_sal(sistema):
    """Il Cmd+V dell'incolla e' un tasto anche lui: prima lo si scansava con
    un margine di tempo che rendeva l'app cieca proprio mentre il testo
    compariva. Ora conta solo chi preme: i tasti del programma no."""
    from types import SimpleNamespace
    orologio = [100.0]
    spazio = dict(time=SimpleNamespace(monotonic=lambda: orologio[0]),
                  ultima_pressione_utente=0.0, ultimo_tasto_utente=None,
                  TASTO='cmd_r', TASTO_COMBO_VOCE='left', HOTKEY='ctrl_r', TASTO_VOCE=None,
                  tasto_premuto=False, key_down=False, voice_key_down=False,
                  combo_voce_scattato=False)
    nome = 'su_pressione' if sistema == 'mac' else 'on_press'
    _dal_sorgente(sistema, [nome], spazio)
    spazio[nome]('v', True)                 # Cmd+V del programma
    assert spazio['ultima_pressione_utente'] == 0.0
    orologio[0] = 101.0
    spazio[nome]('v', False)                # Sal preme un tasto vero
    assert spazio['ultima_pressione_utente'] == 101.0


def test_il_listener_del_mac_sente_anche_i_clic():
    import logging
    from types import SimpleNamespace
    ricevuti = []
    class Tastiera:
        _EVENTS = 1 << 10
        def _handle_message(self, proxy, tipo, evento, refcon, injected):
            ricevuti.append(('tasto', injected))
    quartz = SimpleNamespace(kCGEventTapDisabledByTimeout=-1, kCGEventTapDisabledByUserInput=-2,
                             kCGEventLeftMouseDown=1, kCGEventRightMouseDown=3,
                             kCGEventOtherMouseDown=25, CGEventMaskBit=lambda t: 1 << t)
    spazio = dict(Quartz=quartz, keyboard=SimpleNamespace(Listener=Tastiera), logging=logging,
                  su_clic=lambda injected=False: ricevuti.append(('clic', injected)))
    _dal_sorgente('mac', ['_TAP_DISABILITATO', '_CLIC', 'ListenerResiliente'], spazio)
    ascolta = spazio['ListenerResiliente']
    assert ascolta._EVENTS == (1 << 10) | (1 << 1) | (1 << 3) | (1 << 25)
    ascolta._handle_message(ascolta.__new__(ascolta), None, 1, 'clic', None, False)
    ascolta._handle_message(ascolta.__new__(ascolta), None, 10, 'tasto', None, False)
    assert ricevuti == [('clic', False), ('tasto', False)]


# --- rc.27: tetto alla memoria di lavoro del motore (P-095) ---

def _tetto_memoria(cfg):
    import logging
    from types import SimpleNamespace
    chiamate = []
    spazio = dict(mx=SimpleNamespace(set_cache_limit=chiamate.append), logging=logging)
    _dal_sorgente('mac', ['limita_memoria_motore'], spazio)
    esito = spazio['limita_memoria_motore'](cfg)
    return esito, chiamate


def test_il_motore_ha_un_tetto_di_memoria_di_512_mb_per_default():
    esito, chiamate = _tetto_memoria({})
    assert esito == 512
    assert chiamate == [512 * 1024 * 1024]


def test_il_tetto_di_memoria_si_regola_da_config_e_ignora_valori_storti():
    assert _tetto_memoria({'memoria_motore_mb': 256}) == (256, [256 * 1024 * 1024])
    assert _tetto_memoria({'memoria_motore_mb': 0}) == (0, [0])          # cache spenta: ammesso
    assert _tetto_memoria({'memoria_motore_mb': 'boh'})[0] == 512        # valore storto: default
    assert _tetto_memoria({'memoria_motore_mb': -5})[0] == 512           # negativo: default


def test_il_tetto_si_mette_prima_di_scaldare_il_modello():
    sorgente = (REPO_ROOT / 'mac' / 'detta.py').read_text(encoding='utf-8')
    avvio = sorgente[sorgente.index('if __name__ == "__main__":'):]
    assert avvio.index('limita_memoria_motore(cfg)') < avvio.index('target=_scalda_modello')
    cfg = json.loads((REPO_ROOT / 'mac' / 'config.json').read_text(encoding='utf-8'))
    assert cfg['memoria_motore_mb'] == 512


# --- 01/10/2026: Voce veloce anche con la RAM divorata da un altro programma ---

def test_memoria_fissa_e_modello_piu_margine_mai_oltre_un_quarto_della_ram():
    mb = 1024 * 1024
    gb = 1024 * mb
    # 3 GB di modello + 512 MB di margine su un Mac da 64 GB
    assert voce_lib.tetto_memoria_fissa(3 * gb, 64 * gb) == 3 * gb + 512 * mb
    # Mac da 8 GB: il tetto e' il 25% = 2 GB, anche se il modello e' piu' grande
    assert voce_lib.tetto_memoria_fissa(3 * gb, 8 * gb) == 2 * gb
    # chiave di config: vince sul calcolo, ma sempre sotto il 25%
    assert voce_lib.tetto_memoria_fissa(3 * gb, 64 * gb, fissa_mb=4000) == 4000 * mb
    assert voce_lib.tetto_memoria_fissa(3 * gb, 16 * gb, fissa_mb=9000) == 4 * gb
    assert voce_lib.tetto_memoria_fissa(3 * gb, 64 * gb, fissa_mb="boh") == 3 * gb + 512 * mb


def test_fissa_memoria_motore_chiama_il_motore_e_non_si_ferma_se_fallisce():
    from types import SimpleNamespace
    gb = 1024 ** 3
    chiamate = []
    mx = SimpleNamespace(
        get_active_memory=lambda: 3 * gb,
        device_info=lambda: {"memory_size": 64 * gb},
        set_wired_limit=chiamate.append,
    )
    assert voce_lib.fissa_memoria_motore({}, mx=mx) == 3 * gb + 512 * 1024 * 1024
    assert chiamate == [3 * gb + 512 * 1024 * 1024]

    def rifiuta(_):
        raise ValueError("oltre il massimo")
    mx.set_wired_limit = rifiuta
    assert voce_lib.fissa_memoria_motore({}, mx=mx) is None  # warning, si va avanti


def test_le_attese_lente_contano_di_fila_e_una_veloce_azzera():
    c = 0
    for durata in (9.0, 15.0):
        c = voce_lib.conta_attese_lente(c, durata)
    assert c == 2
    assert voce_lib.conta_attese_lente(c, 2.0) == 0
    assert voce_lib.conta_attese_lente(0, 8.0) == 0  # esattamente 8 s non e' lenta


def test_riavvio_per_memoria_solo_a_riposo_e_dopo_trenta_secondi_di_quiete():
    f = voce_lib.motivo_riavvio
    assert f(5000, 4500, 0, False, 60) is not None          # troppa memoria, a riposo
    assert f(4000, 4500, 0, False, 60) is None              # sotto soglia
    assert f(5000, 4500, 0, True, 60) is None               # sta registrando/trascrivendo
    assert f(5000, 4500, 0, False, 10) is None              # meno di 30 s di silenzio
    assert f(5000, 0, 0, False, 60) is None                 # soglia 0 = spento
    assert f(None, 4500, 0, False, 60) is None              # memoria non leggibile


def test_riavvio_per_attese_lente_dopo_tre_di_fila():
    f = voce_lib.motivo_riavvio
    assert f(3000, 4500, 3, False, 60) is not None
    assert f(3000, 4500, 2, False, 60) is None
    assert f(3000, 4500, 3, True, 60) is None
    assert f(3000, 4500, 3, False, 29) is None


def test_la_guardia_salute_usa_execv_e_parte_all_avvio():
    sorgente = (REPO_ROOT / 'mac' / 'detta.py').read_text(encoding='utf-8')
    assert 'os.execv(sys.executable' in sorgente        # stesso processo: tiene i permessi tastiera
    avvio = sorgente[sorgente.index('if __name__ == "__main__":'):]
    assert 'target=_guardia_salute' in avvio
    assert 'fissa_memoria_motore(cfg)' in sorgente


def test_memoria_processo_e_il_footprint_di_macos_non_il_solo_rss():
    mb = voce_lib.memoria_processo_mb()
    assert mb is not None and mb > 20  # il processo di test esiste ed e' leggibile
    assert voce_lib.memoria_processo_mb(99999999) is None


# --- 01/10/2026: motore leggero da solo sui Mac da 16 GB o meno ---

GB = 1024 ** 3
MOTORE_PIENO = "mlx-community/whisper-large-v3-mlx"
MOTORE_LEGGERO = "mlx-community/whisper-large-v3-turbo"


def test_mac_da_16_gb_o_meno_usa_il_motore_leggero_e_dice_perche():
    cfg = {"modello": MOTORE_PIENO}
    for ram in (8, 16):  # 16 esatto e' dentro la soglia
        modello, motivo = voce_lib.scegli_modello(cfg, {}, ram * GB)
        assert modello == MOTORE_LEGGERO
        assert motivo.startswith("leggero") and f"{ram} GB" in motivo


def test_sopra_16_gb_resta_il_motore_pieno_e_sul_mac_di_sal_non_cambia_niente():
    for ram in (18, 24, 32, 64):
        modello, motivo = voce_lib.scegli_modello({"modello": MOTORE_PIENO}, {}, ram * GB)
        assert modello == MOTORE_PIENO
        assert motivo.startswith("pieno") and f"{ram} GB" in motivo
    # il config vero del prodotto, con 32 GB: lo stesso modello di prima
    prodotto = voce_lib.carica_config()
    assert voce_lib.scegli_modello(prodotto, {}, 32 * GB)[0] == prodotto["modello"] == MOTORE_PIENO


def test_il_modello_scritto_dalla_persona_vince_sempre():
    cfg = {"modello": MOTORE_PIENO}
    scelto = "mlx-community/whisper-small-mlx"
    for ram in (8, 16, 32):
        modello, motivo = voce_lib.scegli_modello(cfg, {"modello": scelto}, ram * GB)
        assert modello == scelto and "config.local.json" in motivo
    # un config locale senza `modello` (glossario, soglie...) non e' una scelta di motore
    assert voce_lib.scegli_modello(cfg, {"glossario": ["Cliente"]}, 8 * GB)[0] == MOTORE_LEGGERO
    assert voce_lib.scegli_modello(cfg, {"modello": ""}, 8 * GB)[0] == MOTORE_LEGGERO


def test_soglia_e_motore_leggero_si_cambiano_con_le_chiavi_opzionali():
    cfg = {"modello": MOTORE_PIENO, "ram_mac_piccoli_gb": 8, "modello_mac_piccoli": "mlx-community/altro-leggero"}
    assert voce_lib.scegli_modello(cfg, {}, 8 * GB)[0] == "mlx-community/altro-leggero"
    assert voce_lib.scegli_modello(cfg, {}, 16 * GB)[0] == MOTORE_PIENO
    # soglia storta: torna a 16; leggero vuoto: torna al turbo; soglia 0 = mai leggero
    assert voce_lib.scegli_modello({"modello": MOTORE_PIENO, "ram_mac_piccoli_gb": "boh"}, {}, 16 * GB)[0] == MOTORE_LEGGERO
    assert voce_lib.scegli_modello({"modello": MOTORE_PIENO, "modello_mac_piccoli": ""}, {}, 8 * GB)[0] == MOTORE_LEGGERO
    assert voce_lib.scegli_modello({"modello": MOTORE_PIENO, "ram_mac_piccoli_gb": 0}, {}, 8 * GB)[0] == MOTORE_PIENO


def test_ram_non_leggibile_lascia_il_motore_pieno():
    for ram in (None, 0):
        modello, motivo = voce_lib.scegli_modello({"modello": MOTORE_PIENO}, {}, ram)
        assert modello == MOTORE_PIENO and "non leggibile" in motivo


def test_la_ram_fisica_si_legge_su_questo_mac():
    ram = voce_lib.ram_fisica_bytes()
    assert ram and ram >= 4 * GB


def test_config_locale_da_solo_le_scelte_personali(tmp_path, monkeypatch):
    locale = tmp_path / "config.local.json"
    monkeypatch.setattr(voce_lib, "CONFIG_LOCAL", locale)
    assert voce_lib.config_locale() == {}                       # nessun file
    locale.write_text(json.dumps({"glossario": ["Cliente"]}), encoding="utf-8")
    assert voce_lib.config_locale() == {"glossario": ["Cliente"]}
    locale.write_text(json.dumps({"modello": "mlx-community/x"}), encoding="utf-8")
    assert voce_lib.config_locale()["modello"] == "mlx-community/x"


def test_il_motore_leggero_e_scelto_all_avvio_e_scritto_nel_registro():
    sorgente = (REPO_ROOT / 'mac' / 'detta.py').read_text(encoding='utf-8')
    scelta = 'cfg["modello"], MOTIVO_MODELLO = scegli_modello(cfg, config_locale(), ram_fisica_bytes())'
    assert scelta in sorgente
    # prima di qualunque uso del modello e prima che parta il riscaldamento
    assert sorgente.index(scelta) < sorgente.index('path_or_hf_repo=cfg["modello"]')
    avvio = sorgente[sorgente.index('if __name__ == "__main__":'):]
    riga = 'logging.getLogger("voce").info("motore di trascrizione: %s (%s)", cfg["modello"], MOTIVO_MODELLO)'
    assert riga in avvio
    assert avvio.index('"avvio dettatura"') < avvio.index(riga) < avvio.index('target=_scalda_modello')


def test_il_glossario_passato_a_whisper_e_scritto_nel_registro_all_avvio():
    """11/10/2026: per dire che dopo un riavvio gira il glossario nuovo serve
    leggerlo nel registro, non dedurlo dal file."""
    sorgente = (REPO_ROOT / 'mac' / 'detta.py').read_text(encoding='utf-8')
    avvio = sorgente[sorgente.index('if __name__ == "__main__":'):]
    riga = 'logging.getLogger("voce").info("glossario per Whisper: %d nomi: %s", len(cfg.get("glossario", [])), GLOSSARIO_PROMPT)'
    assert riga in avvio
    assert avvio.index('"avvio dettatura"') < avvio.index(riga) < avvio.index('target=_scalda_modello')


def test_il_config_del_prodotto_non_fissa_il_motore_leggero():
    """Le due chiavi sono opzionali: i default stanno nel codice, il prodotto resta sul motore pieno."""
    cfg = json.loads((REPO_ROOT / 'mac' / 'config.json').read_text(encoding='utf-8'))
    assert cfg["modello"] == MOTORE_PIENO
    assert "modello_mac_piccoli" not in cfg and "ram_mac_piccoli_gb" not in cfg
    assert voce_lib.MODELLO_MAC_PICCOLI_DEFAULT == MOTORE_LEGGERO == cfg["modello_ripasso"]
    assert voce_lib.RAM_MAC_PICCOLI_GB_DEFAULT == 16


# --- P-085 (23/09/2026): la voce agenti non si accende per sbaglio ---
# Option + freccia sinistra e' anche il «vai alla parola prima» di ogni campo di
# testo: chi corregge una frase la premeva e la voce partiva da sola (durante
# la call di una cliente, quattro letture in sette minuti). Un tocco non basta
# piu': il gesto conta solo se TENUTO.

def _campiona(tenuta, giu_per_istante, passo=0.05, inizio=0.0):
    """Dà alla tenuta lo stato del gesto a ogni `passo` secondi; torna gli istanti in cui scatta."""
    scatti, ora = [], inizio
    for giu in giu_per_istante:
        if tenuta.aggiorna(giu, ora):
            scatti.append(round(ora, 2))
        ora += passo
    return scatti


def test_tenuta_un_tocco_o_dieci_non_scattano_mai():
    tenuta = voce_lib.TenutaGesto(1.0)
    # dieci tocchi da 0,15 s, come chi salta parola dopo parola: ZERO scatti
    assert _campiona(tenuta, ([True] * 3 + [False] * 5) * 10) == []


def test_tenuta_tasto_tenuto_a_meta_non_scatta_nemmeno_se_ripete():
    # chi tiene premuto per scorrere (il tasto si ripete dopo ~0,5 s) e molla a 0,7 s
    assert _campiona(voce_lib.TenutaGesto(1.0), [True] * 14 + [False] * 5) == []


def test_tenuta_scatta_una_volta_sola_appena_raggiunta_la_durata():
    scatti = _campiona(voce_lib.TenutaGesto(1.0), [True] * 40)  # due secondi di tasto giu'
    assert scatti == [1.0]


def test_tenuta_un_buco_nel_gesto_azzera_il_conto():
    # 0,8 s, un campione di rilascio, altri 0,8 s: mai un secondo di fila
    assert _campiona(voce_lib.TenutaGesto(1.0), [True] * 16 + [False] + [True] * 16) == []


def test_tenuta_dopo_il_rilascio_puo_scattare_di_nuovo():
    scatti = _campiona(voce_lib.TenutaGesto(1.0), [True] * 30 + [False] * 4 + [True] * 30)
    assert len(scatti) == 2


def test_prodotto_chiede_un_secondo_di_tenuta_su_mac_e_windows():
    mac = json.loads((REPO_ROOT / "mac" / "config.json").read_text(encoding="utf-8"))
    windows = json.loads((REPO_ROOT / "windows" / "config.json").read_text(encoding="utf-8"))
    assert mac["voce_tenuta_sec"] == windows["voce_tenuta_sec"] == 1.0


def _gesti_voce_mac(giu_per_istante, cfg=None):
    """Il poller VERO di detta.py (worker_combo_voce) con tempo e tasti finti:
    `giu_per_istante` e' lo stato di Option+freccia a ogni giro da 0,05 s.
    Torna quante volte e' partita commuta_voce."""
    from types import SimpleNamespace
    orologio = [0.0]
    stato = {"giu": False}
    copione = list(giu_per_istante)
    commutazioni = []

    class Fine(Exception):
        pass

    def dormi(secondi):
        orologio[0] += secondi
        if not copione:
            raise Fine
        stato["giu"] = copione.pop(0)

    class Filo:  # il thread di commuta_voce parte e gira subito
        def __init__(self, target=None, args=(), daemon=None):
            self.target, self.args = target, args

        def start(self):
            self.target(*self.args)

    spazio = dict(
        time=SimpleNamespace(sleep=dormi, monotonic=lambda: orologio[0]),
        threading=SimpleNamespace(Thread=Filo),
        TenutaGesto=voce_lib.TenutaGesto, cfg=cfg or {},
        esegui_sicuro=voce_lib.esegui_sicuro,
        commuta_voce=lambda: commutazioni.append(orologio[0]),
        _combo_voce_giu=lambda: stato["giu"],
    )
    _dal_sorgente("mac", ["worker_combo_voce"], spazio)
    try:
        spazio["worker_combo_voce"]()
    except Fine:
        pass
    return commutazioni


def test_il_poller_della_voce_ignora_i_tocchi_e_scatta_sul_gesto_tenuto():
    assert _gesti_voce_mac(([True] * 3 + [False] * 5) * 10) == []   # caso del 23/09/2026, P-085
    assert _gesti_voce_mac([True] * 14 + [False] * 5) == []         # scorre tenendo premuto
    assert len(_gesti_voce_mac([True] * 30 + [False] * 3)) == 1     # il gesto voluto
    assert len(_gesti_voce_mac([True] * 30 + [False] * 3 + [True] * 30)) == 2


def test_il_poller_non_scende_sotto_mezzo_secondo_nemmeno_da_config():
    # una soglia a 0 «per far prima» rimetterebbe il difetto: il pavimento e' mezzo secondo
    assert _gesti_voce_mac(([True] * 3 + [False] * 5) * 10, cfg={"voce_tenuta_sec": 0}) == []
    assert len(_gesti_voce_mac([True] * 12, cfg={"voce_tenuta_sec": 0})) == 1


def test_la_pressione_di_option_freccia_non_commuta_piu_la_voce_da_sola():
    """Il percorso vecchio: su_pressione commutava la voce al primo tocco."""
    from types import SimpleNamespace
    commutazioni = []

    class Filo:
        def __init__(self, target=None, args=(), daemon=None):
            self.target, self.args = target, args

        def start(self):
            self.target(*self.args)

    spazio = dict(
        time=SimpleNamespace(monotonic=lambda: 1.0),
        threading=SimpleNamespace(Thread=Filo), esegui_sicuro=voce_lib.esegui_sicuro,
        commuta_voce=lambda: commutazioni.append("commutata"),
        _option_giu=lambda: True, coda_dettature=SimpleNamespace(interrompi_invio=lambda: None),
        comandi_audio=SimpleNamespace(put=lambda c: None),
        TASTO="cmd_r", TASTO_COMBO_VOCE="left", tasto_premuto=False,
        combo_voce_scattato=False, ultima_pressione_utente=0.0, ultimo_tasto_utente=None,
    )
    _dal_sorgente("mac", ["su_pressione"], spazio)
    spazio["su_pressione"]("left")          # Option gia' giu', tocco sulla freccia
    spazio["su_pressione"]("left")          # e un secondo tocco
    assert commutazioni == []


def test_il_gesto_della_voce_legge_il_sistema_e_vuole_solo_option_e_freccia():
    """Maiusc seleziona le parole, Cmd cambia scheda, Ctrl cambia spazio: non
    sono il gesto della voce, anche se tenuti a lungo."""
    from types import SimpleNamespace
    ALT, CMD, CTRL, MAIUSC = 0x80000, 0x100000, 0x40000, 0x20000
    stato = {"flags": 0, "sinistra": False}
    quartz = SimpleNamespace(
        kCGEventSourceStateCombinedSessionState=0, kCGEventFlagMaskAlternate=ALT,
        kCGEventFlagMaskCommand=CMD, kCGEventFlagMaskControl=CTRL, kCGEventFlagMaskShift=MAIUSC,
        CGEventSourceFlagsState=lambda sorgente: stato["flags"],
        CGEventSourceKeyState=lambda sorgente, tasto: tasto == 0x7B and stato["sinistra"],
    )
    spazio = dict(Quartz=quartz, VK_FRECCIA_SINISTRA=0x7B)
    _dal_sorgente("mac", ["_combo_voce_giu"], spazio)
    giu = spazio["_combo_voce_giu"]
    casi = [
        (ALT, True, True), (ALT, False, False), (0, True, False),
        (ALT | MAIUSC, True, False), (ALT | CMD, True, False), (ALT | CTRL, True, False),
    ]
    for flags, sinistra, atteso in casi:
        stato["flags"], stato["sinistra"] = flags, sinistra
        assert giu() is atteso, (flags, sinistra)


# --- P-078 (22/09/2026): «configurato» non e' «funziona» (gemella del difetto di Windows) ---
# Il gancio di Windows e' fallito 410 volte su 410 e il controllo diceva
# «configurato» perche' il percorso nel file c'era. Sul Mac il comando e' scritto
# giusto, ma il controllo era lo stesso: cercava il percorso, non avviava niente.

def _casa_mac_finta(tmp_path, monkeypatch, agenti=("claude",)):
    monkeypatch.setattr(voce_hook.Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(voce_hook, "_agente_presente", lambda nome: nome in agenti)
    monkeypatch.setattr(voce_hook, "_antigravity_presente", lambda: False)
    (tmp_path / ".claude").mkdir(exist_ok=True)
    return tmp_path / ".claude" / "settings.json"


def test_mac_il_gancio_risponde_al_ping():
    esito = subprocess.run([sys.executable, str(REPO_ROOT / "mac" / "voce_hook.py"), "--ping"],
                           capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=60)
    assert esito.returncode == 0 and esito.stdout.strip() == "VOCE_HOOK_OK"


def test_mac_check_hooks_avvia_il_comando_e_dice_la_verita(tmp_path, monkeypatch, capsys):
    settings = _casa_mac_finta(tmp_path, monkeypatch)
    voce_hook.collega_hook(settings)                       # il comando vero, scritto dall'installer
    assert voce_hook.controlla_hook_agenti() is True
    assert "configurato e funzionante" in capsys.readouterr().out
    # lo stesso percorso nel file, ma un interprete che non c'e': prima diceva «configurato»
    mio = str(Path(voce_hook.__file__).absolute())
    settings.write_text(json.dumps({"hooks": {"Stop": [{"hooks": [
        {"type": "command", "command": f"/non/esiste/python {mio}", "timeout": 10}]}]}}),
        encoding="utf-8")
    assert voce_hook.hook_collegato(settings) is True
    assert voce_hook.controlla_hook_agenti() is False
    assert "NON FUNZIONA" in capsys.readouterr().out


def test_mac_la_forma_diretta_si_riconosce_e_si_prova(tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"hooks": {"Stop": [{"hooks": [{
        "type": "command", "command": sys.executable,
        "args": [str(Path(voce_hook.__file__).absolute())]}]}]}}), encoding="utf-8")
    gancio = voce_hook.trova_hook_voce(settings)
    assert gancio is not None and voce_hook.hook_collegato(settings) is True
    assert voce_hook.prova_esecuzione_hook(gancio) == (True, "ok")
    voce_hook.collega_hook(settings)           # l'aggiornamento la riconosce e la sostituisce
    ganci = [h for g in json.loads(settings.read_text(encoding="utf-8"))["hooks"]["Stop"] for h in g["hooks"]]
    assert len(ganci) == 1 and "args" not in ganci[0]


def test_mac_riconosce_il_proprio_gancio_anche_in_una_cartella_con_un_altro_nome(tmp_path):
    """Senza la parola «tools/voce» o «VoiceDettaturaMac» nel percorso un
    aggiornamento non sostituiva la vecchia voce: due ganci, uno rotto."""
    settings = tmp_path / "settings.json"
    voce_hook.collega_hook(settings)
    voce_hook.collega_hook(settings)
    ganci = [h for g in json.loads(settings.read_text(encoding="utf-8"))["hooks"]["Stop"] for h in g["hooks"]]
    assert len(ganci) == 1


def test_mac_l_avviso_all_accensione_dice_cosa_non_va(tmp_path, monkeypatch):
    settings = _casa_mac_finta(tmp_path, monkeypatch, agenti=("claude", "codex"))
    assert "nessun agente" in voce_hook.avviso_collegamento()
    voce_hook.installa_hook_agenti()
    assert voce_hook.avviso_collegamento() == ""
    mio = str(Path(voce_hook.__file__).absolute())
    settings.write_text(json.dumps({"hooks": {"Stop": [{"hooks": [
        {"type": "command", "command": f"/non/esiste/python {mio}"}]}]}}), encoding="utf-8")
    avviso = voce_hook.avviso_collegamento()
    assert "Claude Code" in avviso and "non funziona" in avviso and "Codex" not in avviso


def _commuta_voce_mac(tmp_path, monkeypatch, avviso):
    """`commuta_voce` di mac/detta.py con tutto finto: torna cosa dice a voce."""
    dette = []
    flag = tmp_path / "VOICE_ON"
    if isinstance(avviso, Exception):
        def finto():
            raise avviso
    else:
        def finto():
            return avviso
    monkeypatch.setattr(voce_hook, "avviso_collegamento", finto)
    path = REPO_ROOT / "mac" / "detta.py"
    nodi = [n for n in ast.parse(path.read_text(encoding="utf-8")).body
            if isinstance(n, ast.FunctionDef) and n.name in ("commuta_voce", "_avviso_collegamento")]
    spazio = {"FLAG_VOICE_ON": flag, "ferma_voce": lambda: None, "pronuncia": dette.append,
              "logging": logging}
    exec(compile(ast.Module(body=nodi, type_ignores=[]), str(path), "exec"), spazio)
    return spazio["commuta_voce"], dette, flag


def test_mac_accendendo_la_voce_avverte_se_il_collegamento_non_funziona(tmp_path, monkeypatch):
    attesa = "Voce AI accesa. Le risposte dell'agente sono audio sintetico."
    guasto = "Attenzione: il collegamento con Claude Code non funziona, le risposte non verranno lette."
    commuta, dette, flag = _commuta_voce_mac(tmp_path, monkeypatch, guasto)
    commuta()
    assert dette == [attesa + " " + guasto] and flag.exists()
    commuta()
    assert dette[-1] == "Voce AI spenta" and not flag.exists()
    for avviso in ("", RuntimeError("controllo rotto")):     # sano, oppure il controllo stesso si rompe
        commuta, dette, flag = _commuta_voce_mac(tmp_path, monkeypatch, avviso)
        commuta()
        assert dette == [attesa]
        flag.unlink()


# --- Voce insieme alla scrittura e controllo di consegna (02/10/2026, idea di una cliente) ---

def _riga_registro(tipo, ts, **campi):
    return json.dumps({"type": tipo, "timestamp": ts, **campi}, ensure_ascii=True)


def _iso(epoch):
    from datetime import datetime, timezone
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat().replace("+00:00", "Z")


def _registro(tmp_path, righe, nome="sessione-1"):
    cartella = tmp_path / "progetti" / "-Users-sal-casa"
    cartella.mkdir(parents=True, exist_ok=True)
    percorso = cartella / f"{nome}.jsonl"
    percorso.write_text("\n".join(righe) + "\n", encoding="utf-8")
    return tmp_path / "progetti", percorso


def test_consegna_il_messaggio_si_riconosce_nel_registro(tmp_path):
    import time as t
    ora = t.time()
    progetti, _ = _registro(tmp_path, [
        _riga_registro("user", _iso(ora + 1), message={"role": "user", "content": "Ciao Claude, com'è andata la riunione di oggi?"}),
    ])
    assert voce_lib.messaggio_in_registri("Ciao Claude, com'è  andata la riunione di oggi? ", ora, progetti) is True
    assert voce_lib.messaggio_in_registri("Un'altra frase mai arrivata", ora, progetti) is False


def test_consegna_riconosce_anche_il_messaggio_in_coda_e_i_blocchi_di_testo(tmp_path):
    import time as t
    ora = t.time()
    progetti, _ = _registro(tmp_path, [
        _riga_registro("queue-operation", _iso(ora + 1), operation="enqueue", content="Metti in coda questo messaggio lungo"),
        _riga_registro("user", _iso(ora + 2), message={"role": "user", "content": [
            {"type": "text", "text": "Guarda questo allegato qui"}, {"type": "image", "source": {}}]}),
        _riga_registro("queue-operation", _iso(ora + 2), operation="dequeue"),
    ])
    assert voce_lib.messaggio_in_registri("Metti in coda questo messaggio lungo", ora, progetti)
    assert voce_lib.messaggio_in_registri("Guarda questo allegato qui", ora, progetti)


def test_consegna_una_frase_uguale_di_prima_non_vale(tmp_path):
    import time as t
    ora = t.time()
    progetti, _ = _registro(tmp_path, [
        _riga_registro("user", _iso(ora - 600), message={"role": "user", "content": "Sì, va bene così"}),
    ])
    assert voce_lib.messaggio_in_registri("Sì, va bene così", ora, progetti) is False


def test_consegna_ignora_il_testo_dell_assistente_e_le_righe_enormi(tmp_path):
    import time as t
    ora = t.time()
    progetti, _ = _registro(tmp_path, [
        _riga_registro("assistant", _iso(ora + 1), message={"role": "assistant", "content": [{"type": "text", "text": "Messaggio dettato da Sal per prova"}]}),
        _riga_registro("user", _iso(ora + 1), message={"role": "user", "content": "x" * 120_000 + " Messaggio dettato da Sal per prova"}),
    ])
    assert voce_lib.messaggio_in_registri("Messaggio dettato da Sal per prova", ora, progetti) is False
    assert voce_lib.messaggio_in_registri("", ora, progetti) is False
    assert voce_lib.messaggio_in_registri("qualunque", ora, tmp_path / "non-esiste") is False


def _consegna_finta(arrivi, intervento=True, ammesso=True):
    """verifica_consegna con azioni finte: `arrivi` dice DOPO quante azioni il messaggio compare."""
    azioni = []
    def arrivato(testo, dal):
        return len(azioni) >= arrivi if arrivi is not None else False
    esito = voce_lib.verifica_consegna(
        "messaggio", 0.0, arrivato, lambda: intervento,
        lambda: azioni.append("invio"), lambda: azioni.append("incolla+invio"),
        recupero_ammesso=ammesso, attesa_sec=0.2, passo_sec=0.1, attendi=lambda _s: None)
    return esito, azioni


def test_consegna_arrivata_subito_non_tocca_niente():
    assert _consegna_finta(0) == ("arrivato", [])


def test_consegna_persa_prima_si_ripreme_invio_poi_si_reincolla():
    assert _consegna_finta(1) == ("recuperato", ["invio"])
    assert _consegna_finta(2) == ("recuperato", ["invio", "incolla+invio"])
    assert _consegna_finta(None) == ("persa", ["invio", "incolla+invio"])


def test_consegna_senza_conferma_recente_non_interviene_mai():
    """In una chat normale di Claude il messaggio non compare mai nel registro: reincollare farebbe un doppione."""
    assert _consegna_finta(None, ammesso=False) == ("non_confermato", [])


def test_consegna_se_sal_riprende_la_mano_non_ci_si_intromette():
    assert _consegna_finta(None, intervento=False) == ("annullato", [])


def _percorso_verifica_consegna(tmp_path, nome_app="Claude", registro_ha_il_messaggio=False, davanti=True):
    """Le funzioni di consegna di detta.py con tastiera, app e registro finti."""
    import ast
    import logging
    import threading
    from types import SimpleNamespace
    tasti, incollati, riattivati = [], [], []
    app = SimpleNamespace(localizedName=lambda: nome_app, processIdentifier=lambda: 43)
    fronte = SimpleNamespace(processIdentifier=lambda: 43 if davanti else 99)
    spazio = dict(
        logging=logging, threading=threading, time=__import__("time"),
        cfg={"verifica_consegna": True, "verifica_consegna_app": ["Claude"], "verifica_consegna_storico_min": 30},
        AppKit=SimpleNamespace(NSWorkspace=SimpleNamespace(sharedWorkspace=lambda: SimpleNamespace(frontmostApplication=lambda: fronte))),
        registrando=False, tasto_premuto=False, ultima_pressione_utente=0.0,
        coda_dettature=SimpleNamespace(occupata=lambda: False),
        tastiera=SimpleNamespace(press=tasti.append, release=lambda _: None),
        Key=SimpleNamespace(enter="enter"),
        riattiva_bersaglio=lambda a, s: riattivati.append(a.localizedName()),
        esegui_sicuro=lambda f, *a: f(*a), metti_cursore_in_casella=lambda a: True,
        incolla=lambda testo, **k: incollati.append(testo),
        messaggio_in_registri=lambda testo, dal: registro_ha_il_messaggio,
        verifica_consegna=lambda *a, **k: voce_lib.verifica_consegna(*a, **{**k, "attesa_sec": 0.2, "passo_sec": 0.1, "attendi": lambda _s: None}),
    )
    path = REPO_ROOT / "mac" / "detta.py"
    nodi = [n for n in ast.parse(path.read_text()).body if isinstance(n, ast.FunctionDef)
            and n.name in ("_app_con_registro", "_controlla_consegna", "_verifica_consegna")]
    spazio["_consegne_confermate"] = {}
    exec(compile(ast.Module(body=nodi, type_ignores=[]), str(path), "exec"), spazio)
    return SimpleNamespace(app=app, spazio=spazio, tasti=tasti, incollati=incollati, riattivati=riattivati)


def test_consegna_mac_solo_per_l_app_di_claude_code(tmp_path):
    p = _percorso_verifica_consegna(tmp_path)
    assert p.spazio["_app_con_registro"](p.app) is True
    assert p.spazio["_app_con_registro"](_app_di_nome("ChatGPT")) is False
    assert p.spazio["_app_con_registro"](None) is False


def _app_di_nome(nome):
    from types import SimpleNamespace
    return SimpleNamespace(localizedName=lambda: nome)


def test_consegna_mac_senza_conferma_recente_si_limita_a_registrare(tmp_path):
    p = _percorso_verifica_consegna(tmp_path)
    p.spazio["_verifica_consegna"]("Messaggio per Claude", (p.app, None), 0.0)
    assert p.tasti == [] and p.incollati == []


def test_consegna_mac_con_conferma_recente_ripreme_invio_poi_reincolla(tmp_path):
    p = _percorso_verifica_consegna(tmp_path)
    p.spazio["_consegne_confermate"]["Claude"] = __import__("time").monotonic()
    p.spazio["_verifica_consegna"]("Messaggio per Claude", (p.app, None), 0.0)
    assert p.tasti == ["enter", "enter"]            # ripremuto, poi reincollato e inviato
    assert p.incollati == ["Messaggio per Claude "]
    assert p.riattivati == ["Claude", "Claude"]


def test_consegna_mac_arrivata_ricorda_che_il_registro_funziona(tmp_path):
    p = _percorso_verifica_consegna(tmp_path, registro_ha_il_messaggio=True)
    p.spazio["_verifica_consegna"]("Messaggio per Claude", (p.app, None), 0.0)
    assert "Claude" in p.spazio["_consegne_confermate"] and p.tasti == []


def test_consegna_mac_non_interviene_se_sal_e_andato_in_un_altra_app(tmp_path):
    p = _percorso_verifica_consegna(tmp_path, davanti=False)
    p.spazio["_consegne_confermate"]["Claude"] = __import__("time").monotonic()
    p.spazio["_verifica_consegna"]("Messaggio per Claude", (p.app, None), 0.0)
    assert p.tasti == [] and p.incollati == []


def test_consegna_mac_spenta_da_config_non_parte(tmp_path):
    p = _percorso_verifica_consegna(tmp_path)
    p.spazio["cfg"]["verifica_consegna"] = False
    avviati = []
    p.spazio["threading"] = _thread_finto(avviati)
    p.spazio["_controlla_consegna"]("Messaggio", (p.app, None), True)
    assert avviati == []
    p.spazio["cfg"]["verifica_consegna"] = True
    p.spazio["_controlla_consegna"]("Messaggio", (p.app, None), True)
    assert len(avviati) == 1
    p.spazio["_controlla_consegna"]("Messaggio", (p.app, None), False)  # non e' una chat AI
    assert len(avviati) == 1


def _thread_finto(avviati):
    from types import SimpleNamespace
    class Finto:
        def __init__(self, target=None, args=(), daemon=None):
            self.args = args
        def start(self):
            avviati.append(self.args)
    return SimpleNamespace(Thread=Finto)


def test_il_percorso_dell_incolla_chiama_il_controllo_di_consegna_dopo_l_invio(tmp_path):
    p = _percorso_consegna_completo("mac", tmp_path, casella=True, chat=True)
    p.coda.apri("a")
    p.coda.completa("a", "Ciao Claude.", p.bersaglio)
    p.consegna()
    assert p.inviati == ["Ciao Claude."]
    assert len(p.controlli) == 1 and p.controlli[0][0] == "Ciao Claude."


def test_parla_accoda_i_blocchi_in_ordine_senza_sostituirsi(tmp_path):
    pendente = tmp_path / "LETTURA_PENDENTE"
    origine = {"id": "s1", "nome": "Claude"}
    parla.scrivi_pendente("Primo blocco.", pendente, origine, accoda=True)
    parla.scrivi_pendente("Secondo blocco.", pendente, origine, accoda=True)
    parla.scrivi_pendente("Altra chat.", pendente, {"id": "s2", "nome": "Claude"}, accoda=True)
    assert parla.prendi_pendente(pendente) == "Primo blocco.\n\nSecondo blocco."
    assert parla.prendi_pendente(pendente) == "Altra chat."


def test_parla_senza_accoda_continua_a_sostituire_l_attesa(tmp_path):
    """La risposta finale resta una sola: sostituisce il vecchio in attesa, come prima."""
    pendente = tmp_path / "LETTURA_PENDENTE"
    origine = {"id": "s1", "nome": "Claude"}
    parla.scrivi_pendente("Vecchia.", pendente, origine)
    parla.scrivi_pendente("Nuova.", pendente, origine)
    assert parla.prendi_pendente(pendente) == "Nuova."


def test_parla_accoda_dopo_una_lettura_gia_presa_riparte_pulito(tmp_path):
    pendente = tmp_path / "LETTURA_PENDENTE"
    origine = {"id": "s1", "nome": "Claude"}
    parla.scrivi_pendente("Letto.", pendente, origine, accoda=True)
    assert parla.prendi_pendente(pendente) == "Letto."
    parla.scrivi_pendente("Nuovo.", pendente, origine, accoda=True)
    assert parla.prendi_pendente(pendente) == "Nuovo."


def test_parla_accoda_ha_un_tetto_e_butta_i_paragrafi_piu_vecchi(tmp_path):
    pendente = tmp_path / "LETTURA_PENDENTE"
    origine = {"id": "s1", "nome": "Claude"}
    for i in range(30):
        parla.scrivi_pendente(f"Blocco {i}. " + "parola " * 150, pendente, origine, accoda=True)
    testo = parla.prendi_pendente(pendente)
    assert len(testo) <= parla.TETTO_ATTESA_ACCODATA
    assert "Blocco 29." in testo and "Blocco 0." not in testo


def test_parla_inoltra_accoda_al_deposito(tmp_path, monkeypatch):
    chiamate = []
    monkeypatch.setattr(parla, "FLAG_TURNO_UTENTE", tmp_path / "TURNO_UTENTE", raising=False)
    monkeypatch.setattr(parla, "scrivi_pendente", lambda testo, origine=None, accoda=False: chiamate.append(accoda))
    monkeypatch.setattr(parla, "ha_pendenti", lambda: False)
    parla.parla("Blocco da leggere.", origine={"id": "s", "nome": "Claude"}, accoda=True)
    parla.parla("Risposta finale.", origine={"id": "s", "nome": "Claude"})
    assert chiamate == [True, False]


def test_accordo_gancio_e_registro_il_primo_che_arriva_legge(tmp_path, monkeypatch):
    monkeypatch.setattr(voce_hook, "BASE", tmp_path)
    assert voce_hook.reclama_lettura("s1", "Ho finito il lavoro e il risultato e' pronto per la verifica finale.", 1000.0) is True
    assert voce_hook.reclama_lettura("s1", "Ho finito il lavoro e il risultato e' pronto per la verifica finale.", 1001.0) is False
    assert voce_hook.reclama_lettura("s2", "Ho finito il lavoro e il risultato e' pronto per la verifica finale.", 1001.0) is True


def test_accordo_il_testo_del_gancio_che_contiene_blocchi_gia_letti_non_si_rilegge(tmp_path, monkeypatch):
    monkeypatch.setattr(voce_hook, "BASE", tmp_path)
    blocco = "Ho controllato i file e i numeri tornano, procedo con la parte successiva del lavoro."
    assert voce_hook.reclama_lettura("s1", blocco, 1000.0) is True
    assert voce_hook.reclama_lettura("s1", "Ecco il riepilogo.\n\n" + blocco, 1010.0) is True   # testo piu' grande: lo legge il gancio
    assert voce_hook.reclama_lettura("s1", blocco, 1011.0) is False


def test_accordo_un_testo_breve_e_doppione_solo_se_identico(tmp_path, monkeypatch):
    """«Sì.» sta dentro «così.»: non e' un doppione."""
    monkeypatch.setattr(voce_hook, "BASE", tmp_path)
    assert voce_hook.reclama_lettura("s1", "Va bene così.", 1000.0) is True
    assert voce_hook.reclama_lettura("s1", "così.", 1001.0) is True
    assert voce_hook.reclama_lettura("s1", "Va bene così.", 1002.0) is False


def test_accordo_dopo_due_minuti_lo_stesso_testo_si_rilegge(tmp_path, monkeypatch):
    monkeypatch.setattr(voce_hook, "BASE", tmp_path)
    assert voce_hook.reclama_lettura("s1", "Fatto.", 1000.0) is True
    assert voce_hook.reclama_lettura("s1", "Fatto.", 1000.0 + voce_hook.FINESTRA_LETTO_SEC + 1) is True


def test_accordo_un_file_rotto_non_toglie_la_voce(tmp_path, monkeypatch):
    monkeypatch.setattr(voce_hook, "BASE", tmp_path)
    (tmp_path / "LETTI_DAL_REGISTRO").write_text("{non json", encoding="utf-8")
    assert voce_hook.reclama_lettura("s1", "Fatto.", 1000.0) is True
    monkeypatch.setattr(voce_hook, "BASE", tmp_path / "cartella-che-non-esiste")
    assert voce_hook.reclama_lettura("s1", "Fatto.", 1000.0) is True


def test_gancio_di_fine_risposta_tace_se_il_registro_l_ha_gia_letta(tmp_path, monkeypatch):
    import io
    ricevute = []
    monkeypatch.setattr(voce_hook, "BASE", tmp_path)
    monkeypatch.setattr(voce_hook, "ULTIMA_LETTURA", tmp_path / "ULTIMA_LETTURA")
    monkeypatch.setattr(voce_hook, "voce_attiva", lambda: True)
    monkeypatch.setattr(voce_hook, "parla", lambda testo, origine=None, accoda=False: ricevute.append((testo, origine, accoda)))
    risposta = "Il lavoro e' finito e i test sono verdi, resta solo la pubblicazione."
    assert voce_hook.reclama_lettura("sessione-1", risposta) is True   # l'ha letta il seguitore
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({
        "session_id": "sessione-1", "transcript_path": "/u/.claude/projects/x/sessione-1.jsonl",
        "last_assistant_message": risposta,
    })))
    voce_hook.main()
    assert ricevute == []
    assert "gia' letta mentre veniva scritta" in (tmp_path / "voce.log").read_text(encoding="utf-8")


def test_gancio_di_fine_risposta_legge_se_il_seguitore_non_c_era(tmp_path, monkeypatch):
    import io
    ricevute = []
    monkeypatch.setattr(voce_hook, "BASE", tmp_path)
    monkeypatch.setattr(voce_hook, "ULTIMA_LETTURA", tmp_path / "ULTIMA_LETTURA")
    monkeypatch.setattr(voce_hook, "voce_attiva", lambda: True)
    monkeypatch.setattr(voce_hook, "parla", lambda testo, origine=None, accoda=False: ricevute.append((testo, origine, accoda)))
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({
        "session_id": "sessione-1", "last_assistant_message": "Risposta da leggere a fine lavoro.",
        "transcript_path": "/u/.claude/projects/x/sessione-1.jsonl",
    })))
    voce_hook.main()
    assert ricevute == [("Risposta da leggere a fine lavoro.", {"id": "sessione-1", "nome": "Claude"}, False)]


def _riga_assistente(testo, **extra):
    return json.dumps({"type": "assistant", "uuid": "u", "message": {"role": "assistant", "model": "claude-x",
                       "content": [{"type": "text", "text": testo}]}, **extra})


def test_blocco_di_riga_prende_solo_il_testo_dell_assistente_principale():
    f = voce_hook.blocco_di_riga
    assert f(_riga_assistente("  Ecco il risultato.  ")) == "Ecco il risultato."
    assert f(_riga_assistente("di un subagente", isSidechain=True)) is None
    assert f(_riga_assistente("errore", isApiErrorMessage=True)) is None
    assert f(json.dumps({"type": "assistant", "message": {"model": "<synthetic>", "content": [{"type": "text", "text": "No response requested."}]}})) is None
    assert f(json.dumps({"type": "assistant", "message": {"content": [{"type": "thinking", "thinking": "..."}, {"type": "tool_use", "name": "Bash"}]}})) is None
    assert f(json.dumps({"type": "user", "message": {"content": "ciao"}})) is None
    assert f("non json") is None
    due = json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "Uno."}, {"type": "text", "text": "Due."}]}})
    assert f(due) == "Uno.\nDue."


def test_sessione_interattiva_esclude_automazioni_e_attivita_pianificate(tmp_path):
    def scrivi(nome, *righe):
        p = tmp_path / nome
        p.write_text("\n".join(json.dumps(r) for r in righe), encoding="utf-8")
        return p
    assert voce_hook.sessione_interattiva(scrivi("a.jsonl", {"type": "user", "entrypoint": "claude-desktop", "message": {"content": "ciao"}})) is True
    assert voce_hook.sessione_interattiva(scrivi("b.jsonl", {"type": "user", "entrypoint": "cli", "message": {"content": [{"type": "text", "text": "ciao"}]}})) is True
    assert voce_hook.sessione_interattiva(scrivi("c.jsonl", {"type": "user", "entrypoint": "sdk-cli", "message": {"content": "ciao"}})) is False
    assert voce_hook.sessione_interattiva(scrivi("d.jsonl", {"type": "user", "entrypoint": "claude-desktop",
        "message": {"content": '<scheduled-task name="controllo" file="/x">\nfai'}})) is False
    assert voce_hook.sessione_interattiva(scrivi("e.jsonl", {"type": "queue-operation"}, {"type": "user", "isMeta": True, "message": {"content": "Stop hook feedback"}},
        {"type": "user", "message": {"content": "primo vero messaggio"}})) is True
    assert voce_hook.sessione_interattiva(tmp_path / "manca.jsonl") is True   # nel dubbio la voce non si toglie


def _seguitore(tmp_path, monkeypatch, attiva=True):
    monkeypatch.setattr(voce_hook, "BASE", tmp_path / "casa")
    (tmp_path / "casa").mkdir(exist_ok=True)
    progetti = tmp_path / "progetti" / "-Users-sal-casa"
    progetti.mkdir(parents=True, exist_ok=True)
    lette, tracce, stato = [], [], {"attiva": attiva}
    seg = voce_hook.SeguiRegistro(
        cartella=tmp_path / "progetti", leggi=lambda t, o: lette.append((t, o)),
        attiva=lambda: stato["attiva"], traccia_fn=tracce.append)
    return seg, progetti, lette, stato


def _aggiungi(percorso, *righe):
    with open(percorso, "a", encoding="utf-8") as f:
        for r in righe:
            f.write(r + "\n")


def test_seguitore_legge_il_blocco_appena_scritto_non_il_passato(tmp_path, monkeypatch):
    seg, progetti, lette, _ = _seguitore(tmp_path, monkeypatch)
    chat = progetti / "sessione-1.jsonl"
    _aggiungi(chat, _riga_assistente("Vecchio messaggio di ieri."))
    assert seg.giro() == 0                      # la chat c'era gia': si parte dalla fine
    _aggiungi(chat, _riga_assistente("Controllo i file prima di cominciare il lavoro vero."),
              json.dumps({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Bash"}]}}))
    assert seg.giro() == 1
    assert lette == [("Controllo i file prima di cominciare il lavoro vero.", {"id": "sessione-1", "nome": "Claude"})]
    assert seg.giro() == 0                      # niente da rileggere


def test_seguitore_una_chat_nuova_si_legge_dall_inizio(tmp_path, monkeypatch):
    seg, progetti, lette, _ = _seguitore(tmp_path, monkeypatch)
    _aggiungi(progetti / "vecchia.jsonl", _riga_assistente("Passato."))
    seg.giro()
    seg._ultimo_elenco = -100
    _aggiungi(progetti / "nuova.jsonl", _riga_assistente("Primo blocco della chat nuova."))
    assert seg.giro() == 1 and lette[0][1]["id"] == "nuova"


def test_seguitore_con_la_voce_spenta_non_legge_ne_rilegge_dopo(tmp_path, monkeypatch):
    seg, progetti, lette, stato = _seguitore(tmp_path, monkeypatch, attiva=False)
    chat = progetti / "s.jsonl"
    _aggiungi(chat, _riga_assistente("Prima."))
    seg.giro()
    _aggiungi(chat, _riga_assistente("Scritto a voce spenta."))
    assert seg.giro() == 0
    stato["attiva"] = True
    assert seg.giro() == 0 and lette == []      # accendere la voce non legge il passato
    _aggiungi(chat, _riga_assistente("Scritto a voce accesa."))
    assert seg.giro() == 1


def test_seguitore_non_legge_le_chat_di_sfondo(tmp_path, monkeypatch):
    seg, progetti, lette, _ = _seguitore(tmp_path, monkeypatch)
    chat = progetti / "routine.jsonl"
    _aggiungi(chat, json.dumps({"type": "user", "entrypoint": "sdk-cli", "message": {"content": "esegui"}}))
    seg.giro()
    _aggiungi(chat, _riga_assistente("Lavoro notturno di una automazione."))
    assert seg.giro() == 0 and lette == []


def test_seguitore_riga_a_meta_si_completa_al_giro_dopo(tmp_path, monkeypatch):
    seg, progetti, lette, _ = _seguitore(tmp_path, monkeypatch)
    chat = progetti / "s.jsonl"
    _aggiungi(chat, _riga_assistente("Prima."))
    seg.giro()
    riga = _riga_assistente("Questo blocco arriva in due pezzi, uno alla volta.")
    with open(chat, "a", encoding="utf-8") as f:
        f.write(riga[:40])
    assert seg.giro() == 0
    with open(chat, "a", encoding="utf-8") as f:
        f.write(riga[40:] + "\n")
    assert seg.giro() == 1 and lette[0][0].startswith("Questo blocco arriva")


def test_seguitore_e_gancio_non_leggono_due_volte_lo_stesso_testo(tmp_path, monkeypatch):
    seg, progetti, lette, _ = _seguitore(tmp_path, monkeypatch)
    chat = progetti / "s.jsonl"
    _aggiungi(chat, _riga_assistente("Prima."))
    seg.giro()
    finale = "Il lavoro e' finito, i test sono verdi e resta soltanto la pubblicazione sul pacchetto."
    assert voce_hook.reclama_lettura("s", finale) is True       # il gancio e' arrivato per primo
    _aggiungi(chat, _riga_assistente(finale))
    assert seg.giro() == 0 and lette == []


def test_seguitore_porta_piu_blocchi_arrivati_insieme_in_una_sola_lettura(tmp_path, monkeypatch):
    seg, progetti, lette, _ = _seguitore(tmp_path, monkeypatch)
    chat = progetti / "s.jsonl"
    _aggiungi(chat, _riga_assistente("Prima."))
    seg.giro()
    _aggiungi(chat, _riga_assistente("Primo blocco nuovo."), _riga_assistente("Secondo blocco nuovo."))
    assert seg.giro() == 2
    assert lette[0][0] == "Primo blocco nuovo.\n\nSecondo blocco nuovo."


def test_seguitore_legge_in_coda_non_sostituisce(tmp_path, monkeypatch):
    chiamate = []
    monkeypatch.setattr(voce_hook, "parla", lambda testo, origine=None, accoda=False: chiamate.append(accoda))
    seg = voce_hook.SeguiRegistro(cartella=tmp_path)
    seg.leggi("Un blocco.", {"id": "s", "nome": "Claude"})
    assert chiamate == [True]


def test_seguitore_parte_con_l_app_ed_e_spegnibile_da_config():
    sorgente = (REPO_ROOT / "mac" / "detta.py").read_text(encoding="utf-8")
    assert 'cfg.get("voce_mentre_scrive", True)' in sorgente
    assert "voce_hook.SeguiRegistro(" in sorgente
    config = json.loads((REPO_ROOT / "mac" / "config.json").read_text(encoding="utf-8"))
    assert config["voce_mentre_scrive"] is True and config["verifica_consegna"] is True
    assert config["verifica_consegna_app"] == ["Claude"]


def test_i_nomi_quartz_dei_combo_si_caricano_prima_dei_thread_che_li_usano():
    """Quartz e' un import pigro: due thread che caricano lo stesso nome insieme si pestano
    (KeyError 'CGEventSourceFlagsState', 02/10/2026) e il thread dei combo muore in silenzio."""
    sorgente = (REPO_ROOT / "mac" / "detta.py").read_text(encoding="utf-8")
    principale = sorgente.split('if __name__ == "__main__":', 1)[1]
    caricamento = principale.index("getattr(Quartz, _nome)")
    assert "CGEventSourceFlagsState" in principale[:caricamento]
    assert caricamento < principale.index("target=worker_combo_mani_libere")
    assert caricamento < principale.index("target=worker_combo_voce")


# --- P-190: mani libere che scrivono da sole (17/10/2026) ---
# Lo spegnimento automatico dei 10 minuti deve contare solo i testi incollati
# davvero: una registrazione partita dal rumore e scartata non lo rimanda.

class _OrologioFinto:
    """time finto per worker_mani_libere: sleep avanza il tempo e muove la scena."""

    def __init__(self, scena, fine_sec):
        self.t = 1000.0
        self.inizio = self.t
        self.scena = scena
        self.fine = self.inizio + fine_sec

    def monotonic(self):
        return self.t

    def time(self):
        return self.t

    def sleep(self, dt):
        self.t += dt
        if self.t >= self.fine:
            raise _FineScena()
        self.scena(self.t - self.inizio)


class _FineScena(Exception):
    pass


def _gira_mani_libere(tmp_path, scena_volume, incollati_sec=(), minuti=12, accesa=True):
    """Esegue il vero worker_mani_libere di mac/detta.py con orologio, microfono e
    registro finti. Ritorna (flag ancora accesa?, minuto dello spegnimento, righe di log)."""
    import ast
    import queue
    sorgente = REPO_ROOT / "mac" / "detta.py"
    funzione = next(n for n in ast.parse(sorgente.read_text(encoding="utf-8")).body
                    if isinstance(n, ast.FunctionDef) and n.name == "worker_mani_libere")
    flag = tmp_path / "MANI_LIBERE_ON"
    if accesa:
        flag.touch()
    righe = []

    class _Registro:
        def info(self, msg, *a):
            righe.append(msg % a if a else msg)

        warning = info

    spenta = {"min": None}
    incollati = sorted(incollati_sec)
    spazio = {
        "cfg": {"mani_libere_soglia_voce": 0.018, "mani_libere_soglia_stop": 0.013,
                "mani_libere_autospegnimento_min": 10},
        "mani_libere_attive": flag.exists,
        "FLAG_MANI_LIBERE_ON": flag,
        "FLAG_PARLANDO": tmp_path / "PARLANDO",
        "comandi_audio": queue.Queue(),
        "suono": lambda nome: None,
        "logging": type("L", (), {"getLogger": staticmethod(lambda *_: _Registro())}),
        "registrando": False,
        "volume_corrente": 0.0,
        "ultimo_testo_incollato": 0.0,
        "orecchio_vivo": None,  # 31/10/2026: qui il volume; l'orecchio ha le sue prove
    }

    def scena(trascorsi):
        spazio["volume_corrente"] = scena_volume(trascorsi)
        while incollati and trascorsi >= incollati[0]:
            incollati.pop(0)
            spazio["ultimo_testo_incollato"] = orologio.t
        if spenta["min"] is None and not flag.exists():
            spenta["min"] = trascorsi / 60

    orologio = _OrologioFinto(scena, minuti * 60)
    spazio["time"] = orologio
    exec(compile(ast.Module(body=[funzione], type_ignores=[]), str(sorgente), "exec"), spazio)
    with pytest.raises(_FineScena):
        spazio["worker_mani_libere"]()
    return flag.exists(), spenta["min"], righe


def _rumore_ogni_30_secondi(trascorsi):
    """Un colpo, una voce dalla stanza: un secondo sopra soglia ogni mezzo minuto."""
    return 0.05 if trascorsi % 30 < 1.0 else 0.002


def test_mani_libere_si_spengono_anche_se_il_rumore_fa_partire_registrazioni(tmp_path):
    accesa, minuto, righe = _gira_mani_libere(tmp_path, _rumore_ogni_30_secondi, minuti=12)
    assert not accesa, "il rumore ha tenuto accese le mani libere oltre i 10 minuti"
    assert 10 <= minuto < 10.6
    assert any("auto-spegnimento" in r for r in righe)


def test_mani_libere_restano_accese_finche_si_detta_davvero(tmp_path):
    # fratello: chi detta davvero ogni 3 minuti non viene spento; dall'ultimo
    # testo incollato (minuto 9) partono i 10 minuti.
    accesa, minuto, _ = _gira_mani_libere(
        tmp_path, _rumore_ogni_30_secondi, incollati_sec=(180, 360, 540), minuti=21)
    assert not accesa
    assert 19 <= minuto < 19.6


def test_mani_libere_accese_lasciano_una_riga_nel_registro_da_qualsiasi_parte(tmp_path):
    # Il pulsante della Scrivania e `./voce mani on` toccano solo il file: la riga la
    # scrive l'ascolto, cosi' chi diagnostica vede quando e da quanto sono accese.
    _, _, righe = _gira_mani_libere(tmp_path, lambda t: 0.0, minuti=1)
    assert any(r.startswith("mani libere: ATTIVE") for r in righe)


# --- Fase 0: `voce diagnosi` su Mac finti (P-190, 17/10/2026) ---
# I comandi di macOS sono sostituiti da copioni finti messi davanti nel PATH:
# la diagnosi vera gira su un computer che non e' quello della prova.

def _mac_finto(tmp_path, ram_gb=16, macos="15.3", arm=1, liberi_gb=100,
               python="3 12 arm64", clt=True):
    casa = tmp_path / "casa"
    bin_finti = tmp_path / "bin"
    casa.mkdir()
    bin_finti.mkdir()
    copioni = {
        "sysctl": f'''case "$2" in
  hw.optional.arm64) echo {arm} ;;
  machdep.cpu.brand_string) echo "{'Apple M1' if arm else 'Intel Core i5'}" ;;
  hw.memsize) echo {ram_gb * 1024 ** 3} ;;
esac''',
        "sw_vers": f"echo {macos}",
        "df": f'echo "Filesystem 1024-blocks Used Available Capacity Mounted"; echo "/dev/finto 999 1 {liberi_gb * 1048576} 1% /"',
        "xcode-select": "exit 0" if clt else "exit 2",
        "python3": f'echo "{python}"',
        "curl": "exit 0",
        "defaults": "exit 1",
        "launchctl": "exit 0",
        "pgrep": "echo 4242",
        "top": "exit 0",
    }
    for nome, corpo in copioni.items():
        f = bin_finti / nome
        f.write_text("#!/bin/bash\n" + corpo + "\n")
        f.chmod(0o755)
    env = {"HOME": str(casa), "PATH": f"{bin_finti}:/usr/bin:/bin:/usr/sbin:/sbin", "LANG": "C"}
    return casa, env


def _diagnosi(env):
    r = subprocess.run(["bash", str(REPO_ROOT / "mac" / "voce"), "diagnosi"],
                       env=env, capture_output=True, text=True, timeout=60)
    return r.returncode, r.stdout


def test_diagnosi_mac_coi_requisiti_dice_che_la_voce_va(tmp_path):
    _, env = _mac_finto(tmp_path)
    codice, testo = _diagnosi(env)
    assert codice == 0, testo
    assert "ESITO: la Voce va bene per questo computer." in testo


def test_diagnosi_mac_da_8_gb_dice_che_la_voce_non_va_e_perche(tmp_path):
    _, env = _mac_finto(tmp_path, ram_gb=8)
    codice, testo = _diagnosi(env)
    assert codice == 1, testo
    assert "ESITO: la Voce non va per questo computer." in testo
    assert "16 GB di memoria (ne ha 8)" in testo
    assert "resta in memoria accanto alla tua AI" in testo  # cosa fa l'app


def test_diagnosi_fratelli_intel_macos_vecchio_disco_pieno(tmp_path):
    for i, (opzioni, attesa) in enumerate((
        ({"arm": 0}, "chip Apple Silicon"),
        ({"macos": "13.6"}, "macOS 14 o successivo"),
        ({"liberi_gb": 4}, "10 GB liberi sul disco (ne ha 4)"),
    )):
        cartella = tmp_path / str(i)
        cartella.mkdir()
        _, env = _mac_finto(cartella, **opzioni)
        codice, testo = _diagnosi(env)
        assert codice == 1, testo
        assert attesa in testo


def test_diagnosi_python_vecchio_e_software_che_sistema_l_ai(tmp_path):
    # numpy 2.4.6 vuole Python 3.11: il 3.9 degli strumenti di Apple non basta
    _, env = _mac_finto(tmp_path, python="3 9 arm64")
    codice, testo = _diagnosi(env)
    assert codice == 2, testo
    assert "prima l'AI sistema" in testo and "Python 3.11" in testo


def test_diagnosi_voce_installata_con_mani_libere_accese_lo_dice(tmp_path):
    casa, env = _mac_finto(tmp_path)
    voce = casa / "VoiceDettaturaMac"
    (voce / ".venv" / "bin").mkdir(parents=True)
    (voce / ".venv" / "bin" / "python").write_text("#!/bin/bash\n")
    (voce / ".venv" / "bin" / "python").chmod(0o755)
    (voce / "VERSION").write_text("1.3.0-rc.31\n")
    (voce / "MANI_LIBERE_ON").touch()
    import datetime
    ora = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    (voce / "voce.log").write_text(
        f"{ora},1 INFO incollato (app bersaglio: ChatGPT)\n"
        f"{ora},2 INFO invio automatico premuto (attesa 2.5s)\n"
        f"{ora},3 INFO combo mani libere: ON\n")
    codice, testo = _diagnosi(env)
    assert codice == 0, testo
    assert "versione 1.3.0-rc.31" in testo
    assert "mani libere: ACCESE dal" in testo and "voce mani off" in testo
    assert "1 testi incollati, 1 invii automatici" in testo
    assert "1 accensioni mani libere" in testo
    assert "servono 2 GB" in testo  # aggiornamento: programmi e modello ci sono gia'


def test_installer_sotto_requisito_non_parte_e_non_tocca_niente(tmp_path):
    casa, env = _mac_finto(tmp_path, ram_gb=8)
    r = subprocess.run(["bash", str(REPO_ROOT / "mac" / "install.sh")], env=env,
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "Installazione non avviata" in r.stdout
    assert not (casa / "VoiceDettaturaMac").exists()
    assert not (casa / "Desktop").exists()


def test_invio_di_sal_mentre_il_testo_compare_conta_come_si():
    # Sal, 30/10/2026: «vedo che succede qualcosa e non invia, mi rimane la chat
    # aperta»: l'Invio premuto mentre il testo atterrava (tra riferimento e fine
    # incolla) cadeva su una casella vuota e poi annullava l'Invio automatico.
    f = voce_lib.invio_di_sal_durante_incolla
    assert f("enter", "enter", 10.3, 10.0, 10.7) is True      # Invio durante l'incolla: si manda
    assert f("enter", "enter", 10.0, 10.0, 10.7) is False     # pressione prima del riferimento: non conta
    assert f("enter", "enter", 10.8, 10.0, 10.7) is False     # Invio dopo l'incolla: e' gia' partito a mano
    assert f("a", "enter", 10.3, 10.0, 10.7) is False         # un altro tasto: annulla come oggi
    assert f("clic", "enter", 10.3, 10.0, 10.7) is False      # un clic: annulla come oggi
    assert f(None, "enter", 10.3, 10.0, 10.7) is False


def test_invio_automatico_mac_manda_se_sal_ha_premuto_invio_durante_l_incolla():
    sorgente = (REPO_ROOT / "mac" / "detta.py").read_text(encoding="utf-8")
    corpo = sorgente.split("def _incolla_messaggio", 1)[1].split("\ndef ", 1)[0]
    assert "fine_incolla = time.monotonic()" in corpo
    assert "invio_di_sal_durante_incolla(" in corpo
    assert "Invio di Sal arrivato mentre il testo compariva" in corpo
    # una nuova dettatura vince sempre: il controllo sta prima
    assert corpo.index("if tasto_premuto or registrando:") < corpo.index("invio_di_sal_durante_incolla(")


@pytest.mark.parametrize('sistema', ['mac', 'windows'])
def test_invio_premuto_mentre_il_testo_compare_manda_la_frase(sistema, tmp_path, caplog):
    """Sal, 30/10/2026: l'Invio premuto mentre il testo atterrava cadeva sulla
    casella vuota e l'Invio automatico si annullava: la frase restava li'."""
    import logging
    from types import SimpleNamespace
    p = _percorso_consegna_completo(sistema, tmp_path)
    orologio = [100.0]
    incolla_vera = p.spazio['incolla']
    def incolla_con_invio_di_sal(testo, **kw):
        incolla_vera(testo, **kw)
        orologio[0] += 0.4                       # mentre il testo compare...
        p.spazio['ultima_pressione_utente'] = orologio[0]   # ...Sal preme Invio
        p.spazio['ultimo_tasto_utente'] = 'enter'
        orologio[0] += 0.2
    p.spazio['incolla'] = p.spazio['paste_text'] = incolla_con_invio_di_sal
    p.spazio['time'] = SimpleNamespace(monotonic=lambda: orologio[0], sleep=lambda s: orologio.__setitem__(0, orologio[0] + s))
    p.spazio['ritardo_invio'] = lambda *a: 2.0
    p.coda.apri('sola')
    p.coda.completa('sola', 'Frase.', p.bersaglio)
    with caplog.at_level(logging.INFO):
        p.consegna()
    assert p.inviati == ['Frase.']
    assert "Invio di Sal arrivato mentre il testo compariva" in caplog.text
    assert "ANNULLATO" not in caplog.text
    assert len(p.controlli) == 1  # il controllo di consegna parte come per l'Invio normale


@pytest.mark.parametrize('sistema', ['mac', 'windows'])
def test_invio_poi_altro_tasto_mentre_il_testo_compare_annulla_ancora(sistema, tmp_path, caplog):
    """L'ultimo gesto vince: Invio e poi un altro tasto (o un clic) = Sal sta correggendo."""
    import logging
    from types import SimpleNamespace
    p = _percorso_consegna_completo(sistema, tmp_path)
    orologio = [100.0]
    incolla_vera = p.spazio['incolla']
    def incolla_poi_tasto(testo, **kw):
        incolla_vera(testo, **kw)
        orologio[0] += 0.3
        p.spazio['ultima_pressione_utente'] = orologio[0]
        p.spazio['ultimo_tasto_utente'] = 'enter'
        orologio[0] += 0.1
        p.spazio['ultima_pressione_utente'] = orologio[0]
        p.spazio['ultimo_tasto_utente'] = 'a'
    p.spazio['incolla'] = p.spazio['paste_text'] = incolla_poi_tasto
    p.spazio['time'] = SimpleNamespace(monotonic=lambda: orologio[0], sleep=lambda s: orologio.__setitem__(0, orologio[0] + s))
    p.spazio['ritardo_invio'] = lambda *a: 2.0
    p.coda.apri('sola')
    p.coda.completa('sola', 'Frase.', p.bersaglio)
    with caplog.at_level(logging.INFO):
        p.consegna()
    assert p.inviati == []
    assert "ANNULLATO" in caplog.text


# === 31/10/2026: tre migliorie ispirate a Handy (github.com/cjpais/Handy, MIT) ===
# 1. Orecchio: Silero VAD per mani libere e prima di Whisper.
# 2. Esc annulla la dettatura, senza arrivare all'app davanti.
# 3. Menu Voce: copia e ritrascrivi l'ultima dettatura, solo in memoria.

def _modello_finto(voce=lambda frame: float(np.abs(frame).max()) > 0.02):
    """Silero finto: voce = 0,9, altrimenti 0,05. Registra cosa riceve."""
    chiamate = []

    def modello(ingresso, stato):
        chiamate.append(ingresso.copy())
        return (0.9 if voce(ingresso[0, voce_lib.CONTESTO_ORECCHIO:]) else 0.05), stato + 1
    modello.chiamate = chiamate
    return modello


def _audio_a_tratti(*tratti):
    """[(secondi, ampiezza)] -> audio a 16 kHz: 0 = silenzio, >0 = voce (per il modello finto)."""
    pezzi = []
    for secondi, ampiezza in tratti:
        n = int(round(secondi * 16000))
        pezzi.append(np.full(n, ampiezza, dtype="float32") * np.where(np.arange(n) % 2, 1, -1))
    return np.concatenate(pezzi)


def test_orecchio_misure_di_handy_in_frame_da_32_ms():
    assert voce_lib.FRAME_ORECCHIO == 512
    assert voce_lib.frame_da_ms(60) == 2          # 60 ms di voce per dire «c'e' voce»
    assert voce_lib.frame_da_ms(450) == 14        # 450 ms prima e dopo (448 ms)
    assert voce_lib.frame_da_ms(1400) == 44       # silenzio che chiude le mani libere
    orecchio = voce_lib.Orecchio.da_config({}, modello=_modello_finto())
    assert (orecchio.soglia, orecchio.attacco, orecchio.prima, orecchio.dopo) == (0.3, 2, 14, 14)


def test_orecchio_un_frame_solo_non_e_voce_due_di_fila_si():
    assert voce_lib.c_e_voce_umana([0.1, 0.9, 0.1, 0.9, 0.1]) is False
    assert voce_lib.c_e_voce_umana([0.1, 0.3, 0.3, 0.1]) is True     # soglia compresa
    assert voce_lib.c_e_voce_umana([0.29] * 50) is False
    assert voce_lib.c_e_voce_umana([]) is False


def test_flusso_orecchio_stesse_probabilita_a_pezzi_diversi_e_contesto_di_silero():
    audio = _audio_a_tratti((0.5, 0.0), (0.4, 0.1), (0.7, 0.0))
    risultati = []
    for misura in (480, 1000, len(audio)):
        modello = _modello_finto()
        flusso = voce_lib.FlussoOrecchio(modello)
        prob = []
        for i in range(0, len(audio), misura):
            prob += flusso.probabilita(audio[i:i + misura])
        risultati.append(prob)
        # ogni frame arriva con i 64 campioni prima, come nel wrapper ufficiale di Silero
        assert all(c.shape == (1, 576) for c in modello.chiamate)
        assert np.array_equal(modello.chiamate[1][0, :64], audio[512 - 64:512])
    assert risultati[0] == risultati[1] == risultati[2]
    assert len(risultati[0]) == len(audio) // 512


def test_maschera_accorcia_solo_i_silenzi_lunghi_e_tiene_i_margini():
    prob = [0.05] * 40 + [0.9] * 10 + [0.05] * 60 + [0.9] * 5 + [0.05] * 20 + [0.05] * 5
    n = len(prob) * 512 + 100                       # 100 campioni oltre l'ultimo frame
    tieni = voce_lib.maschera_voce(n, prob)
    frame = tieni[:len(prob) * 512].reshape(-1, 512)
    per_frame = frame.all(axis=1)
    assert (frame.all(axis=1) | ~frame.any(axis=1)).all()  # si taglia a frame interi
    assert per_frame[40:50].all() and per_frame[110:115].all()   # la voce resta tutta
    assert per_frame[26:40].all() and not per_frame[25]           # 14 frame prima (448 ms)
    assert per_frame[50:64].all() and not per_frame[64]           # 14 frame dopo
    assert per_frame[96:110].all() and not per_frame[95]
    assert per_frame[115:129].all() and not per_frame[129]
    assert tieni[-100:].all()                                    # oltre l'ultimo frame: si tiene
    # il silenzio interno di 60 frame (1,9 s) diventa 28 frame (896 ms)
    assert per_frame[50:110].sum() == 28


def test_orecchio_niente_voce_niente_whisper_e_silenzi_accorciati():
    orecchio = voce_lib.Orecchio.da_config({}, modello=_modello_finto())
    muto, prob = orecchio.prepara(_audio_a_tratti((3.0, 0.0)))
    assert muto is None and prob
    # un colpo da 20 ms dentro un solo frame da 32 ms: sotto i 60 ms non e' voce
    colpo, _ = orecchio.prepara(_audio_a_tratti((31 * 512 / 16000, 0.0), (0.02, 0.5), (1.0, 0.0)))
    assert colpo is None
    audio = _audio_a_tratti((2.0, 0.0), (1.0, 0.1), (3.0, 0.0), (1.0, 0.1), (2.0, 0.0))
    pronto, _ = orecchio.prepara(audio)
    assert pronto is not None
    voce = np.abs(audio) > 0.05
    assert int((np.abs(pronto) > 0.05).sum()) == int(voce.sum())   # nessun campione di voce perso
    # 2 s di voce + 448 ms all'inizio, 896 ms al posto dei 3 s in mezzo, 448 ms alla fine
    assert len(pronto) / 16000 == pytest.approx(2.0 + 4 * 0.448, abs=0.07)


def test_orecchio_vivo_parte_sulla_voce_e_si_ferma_dopo_il_silenzio():
    vivo = voce_lib.Orecchio.da_config({}, modello=_modello_finto()).vivo(1400)
    vivo.accendi()
    for _ in range(10):
        vivo.ascolta(np.zeros((480, 1), dtype="float32"))
    assert not vivo.attacco()
    vivo.ascolta(_audio_a_tratti((0.07, 0.1)).reshape(-1, 1))
    assert vivo.attacco() and vivo.silenzio_di_fila == 0
    for _ in range(40):
        vivo.ascolta(np.zeros((480, 1), dtype="float32"))     # 1,2 s: ancora frase
    assert not vivo.silenzio()
    for _ in range(10):
        vivo.ascolta(np.zeros((480, 1), dtype="float32"))     # 1,5 s: finita
    assert vivo.silenzio()
    vivo.spegni()
    assert not vivo.acceso and vivo.voce_di_fila == vivo.silenzio_di_fila == 0


def test_mani_libere_con_l_orecchio_contano_la_voce_non_il_volume(tmp_path):
    """Il rumore forte (una porta, la tastiera) non le accende; la voce piano si'.
    Si fermano dopo 1,4 s senza voce, come prima. Volume e voce qui sono opposti apposta."""
    import ast
    import queue
    from types import SimpleNamespace
    VOCE, RUMORE = 0.01, 0.2   # voce piano (sotto la soglia di volume 0,018), rumore forte
    vivo = voce_lib.Orecchio.da_config({}, modello=_modello_finto(
        voce=lambda frame: abs(float(np.abs(frame).mean()) - VOCE) < 1e-4)).vivo(1400)
    flag = tmp_path / "MANI_LIBERE_ON"
    flag.touch()
    comandi = []

    def scena(t):
        if 1.0 <= t < 2.0:
            return RUMORE           # porta che sbatte: volume altissimo, nessuna voce
        if 3.0 <= t < 4.0:
            return VOCE             # Sal parla piano
        return 0.0

    orologio = _OrologioFinto(lambda t: None, 7.0)
    spazio = {
        "cfg": {"mani_libere_soglia_voce": 0.018, "mani_libere_soglia_stop": 0.013,
                "mani_libere_silenzio_sec": 1.4, "mani_libere_autospegnimento_min": 10},
        "mani_libere_attive": flag.exists, "FLAG_MANI_LIBERE_ON": flag,
        "FLAG_PARLANDO": tmp_path / "PARLANDO",
        "comandi_audio": SimpleNamespace(put=lambda c: comandi.append((round(orologio.t - orologio.inizio, 2), c))),
        "suono": lambda nome: None,
        "logging": SimpleNamespace(getLogger=lambda *_: SimpleNamespace(info=lambda *a: None)),
        "registrando": False, "volume_corrente": 0.0, "ultimo_testo_incollato": 0.0,
        "orecchio_vivo": vivo, "time": orologio,
    }

    def scena_viva(t):   # il callback audio: 50 ms di microfono a ogni giro
        valore = scena(t)
        spazio["volume_corrente"] = valore
        if vivo.acceso:
            vivo.ascolta(np.full((800, 1), valore, dtype="float32"))
    orologio.scena = scena_viva
    sorgente = REPO_ROOT / "mac" / "detta.py"
    funzione = next(n for n in ast.parse(sorgente.read_text(encoding="utf-8")).body
                    if isinstance(n, ast.FunctionDef) and n.name == "worker_mani_libere")
    exec(compile(ast.Module(body=[funzione], type_ignores=[]), str(sorgente), "exec"), spazio)
    with pytest.raises(_FineScena):
        spazio["worker_mani_libere"]()
    (t_start, c_start), (t_stop, c_stop) = comandi
    assert c_start == "start" and 3.0 < t_start <= 3.2       # 60 ms di voce + il giro da 50 ms
    assert c_stop == "stop" and 5.35 <= t_stop <= 5.55       # 1,4 s senza voce
    flag.unlink()
    orologio.fine += 1.0
    with pytest.raises(_FineScena):
        spazio["worker_mani_libere"]()
    assert not vivo.acceso                                   # spente: niente microfono all'orecchio


def test_whisper_non_parte_senza_voce_e_riceve_l_audio_accorciato(caplog):
    from types import SimpleNamespace
    ricevuti = []
    spazio = dict(cfg={'modello': 'locale', 'lingua': 'it'}, logging=logging, FREQ=16000,
                  time=__import__('time'),
                  mlx_whisper=SimpleNamespace(transcribe=lambda audio, **kw:
                      ricevuti.append(audio) or {'text': 'Ciao.', 'segments': []}),
                  ORECCHIO=voce_lib.Orecchio.da_config({}, modello=_modello_finto()))
    _dal_sorgente('mac', ['_whisper_grezzo'], spazio)
    with caplog.at_level(logging.INFO):
        assert spazio['_whisper_grezzo'](_audio_a_tratti((4.0, 0.0))) == ""
        assert ricevuti == []                                   # sul silenzio niente «Grazie.»
        assert "nessuna voce" in caplog.text
        assert spazio['_whisper_grezzo'](_audio_a_tratti((2.0, 0.0), (1.0, 0.1), (2.0, 0.0))) == "Ciao."
        assert len(ricevuti[0]) < 5 * 16000                     # accorciato prima di Whisper
        assert spazio['_whisper_grezzo'](np.zeros(16000, dtype='float32'), None, False) == "Ciao."
        assert len(ricevuti[1]) == 16000                        # il riscaldamento salta l'orecchio


def test_un_guasto_dell_orecchio_non_costa_la_dettatura():
    from types import SimpleNamespace

    class Rotto:
        def prepara(self, audio):
            raise RuntimeError("onnx")
    ricevuti = []
    spazio = dict(cfg={'modello': 'locale', 'lingua': 'it'}, logging=logging, FREQ=16000,
                  time=__import__('time'), ORECCHIO=Rotto(),
                  mlx_whisper=SimpleNamespace(transcribe=lambda audio, **kw:
                      ricevuti.append(audio) or {'text': 'Ciao.', 'segments': []}))
    _dal_sorgente('mac', ['_whisper_grezzo'], spazio)
    audio = np.full(16000, 0.04, dtype='float32')
    assert spazio['_whisper_grezzo'](audio) == "Ciao." and len(ricevuti[0]) == 16000


def test_scaldare_il_motore_salta_l_orecchio():
    sorgente = (REPO_ROOT / 'mac' / 'detta.py').read_text(encoding='utf-8')
    corpo = sorgente.split("def _scalda_modello", 1)[1].split("\ndef ", 1)[0]
    assert "_whisper_grezzo, np.zeros(FREQ, dtype=np.float32), GLOSSARIO_PROMPT, False" in corpo


def test_interruttori_nuovi_nel_config_del_prodotto_e_onnxruntime_bloccato():
    cfg = json.loads((REPO_ROOT / 'mac' / 'config.json').read_text(encoding='utf-8'))
    assert cfg["orecchio"] is True and cfg["esc_annulla"] is True
    righe = (REPO_ROOT / 'mac' / 'requirements.txt').read_text(encoding='utf-8').split()
    assert "onnxruntime==1.27.0" in righe
    assert not any(r.startswith("torch") for r in righe)
    sorgente = (REPO_ROOT / 'mac' / 'detta.py').read_text(encoding='utf-8')
    assert 'if cfg.get("orecchio", True):' in sorgente
    assert 'if cfg.get("esc_annulla", True):' in sorgente


def test_modello_silero_ufficiale_v6_2_3():
    import hashlib
    modello = REPO_ROOT / 'mac' / 'silero_vad.onnx'
    if not modello.exists():
        pytest.skip("modello non presente in questa copia")
    assert modello.stat().st_size == 2327524
    assert hashlib.sha256(modello.read_bytes()).hexdigest() == (
        "1a153a22f4509e292a94e67d6f9b85e8deb25b4988682b7e174c65279d8788e3")
    assert "Silero Team" in (REPO_ROOT / 'mac' / 'silero_vad_LICENSE.txt').read_text(encoding='utf-8')


def _orecchio_vero():
    pytest.importorskip("onnxruntime")
    if not (REPO_ROOT / 'mac' / 'silero_vad.onnx').exists():
        pytest.skip("modello non presente")
    return voce_lib.Orecchio.da_config({}, modello=voce_lib.ModelloOrecchio(REPO_ROOT / 'mac' / 'silero_vad.onnx'))


def _parlato_sintetico(tmp_path, frase="Buongiorno, questa è una prova della dettatura."):
    """Voce italiana di macOS (Alice) a 16 kHz: una persona che parla, ripetibile."""
    import shutil
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


def test_silero_vero_sente_una_persona_e_non_silenzio_o_rumore(tmp_path):
    orecchio = _orecchio_vero()
    rng = np.random.default_rng(0)
    for nome, audio in {
        "silenzio": np.zeros(3 * 16000, dtype="float32"),
        "fruscio": (rng.standard_normal(3 * 16000) * 0.01).astype("float32"),
        "rumore forte": (rng.standard_normal(3 * 16000) * 0.2).astype("float32"),
        "ronzio 50 Hz": (0.05 * np.sin(2 * np.pi * 50 * np.arange(3 * 16000) / 16000)).astype("float32"),
    }.items():
        assert orecchio.prepara(audio)[0] is None, nome
    parlato = _parlato_sintetico(tmp_path)
    pausa = np.zeros(3 * 16000, dtype="float32")
    audio = np.concatenate([pausa, parlato, pausa, parlato, pausa])
    pronto, prob = orecchio.prepara(audio)
    assert pronto is not None
    # la voce resta tutta: ogni frame sopra soglia e' nei campioni tenuti
    tieni = voce_lib.maschera_voce(len(audio), prob)
    voce = np.repeat(np.array(prob) >= 0.3, 512)[:len(audio)]
    assert not (voce & ~tieni).any()
    assert len(pronto) < len(audio) - 4 * 16000           # 9 s di pause diventano meno di 3


# --- Esc annulla ---

def test_esc_dentro_la_dettatura_si_trattiene_e_annulla_fuori_passa():
    esc = voce_lib.EscAnnulla()
    assert esc.evento(True, False, False, False, 1.0) == (False, False)   # nessuna dettatura: all'app
    assert esc.evento(False, False, False, False, 1.1) == (False, False)
    assert esc.evento(True, False, False, True, 2.0) == (True, True)      # dettatura: trattenuto e buttata
    assert esc.serve(2.5)
    assert esc.evento(True, True, False, False, 2.6) == (True, False)     # tenuto premuto: le ripetizioni no
    assert esc.evento(False, False, False, False, 2.7) == (True, False)   # e nemmeno il rilascio
    assert not esc.serve(2.8)
    assert esc.evento(True, True, False, False, 3.0) == (False, False)    # ripetizione orfana: passa


def test_esc_con_ctrl_o_option_resta_del_sistema_e_un_rilascio_perso_non_blocca():
    esc = voce_lib.EscAnnulla()
    assert esc.evento(True, False, True, True, 1.0) == (False, False)
    assert esc.evento(True, False, False, True, 2.0) == (True, True)
    assert not esc.serve(2.0 + esc.SCADENZA_SEC)                          # filtro mai acceso per sempre
    assert esc.evento(True, False, False, False, 9.0) == (False, False)   # pressione nuova, fuori: passa


def test_coda_esc_butta_tutto_cio_che_non_e_incollato_e_nessun_invio():
    coda = voce_lib.CodaDettature()
    assert coda.annulla() is False and not coda.aperta()
    consegne = []
    coda.apri('prima')
    coda.apri('seconda')
    coda.completa('prima', 'Gia trascritta.', 'chat')
    assert coda.aperta() and coda.annulla() is True
    assert coda.annullato('seconda')
    coda.completa('seconda', 'Arrivata dopo Esc.', 'chat')
    chiusi = []
    coda.consegna_pronte(lambda *a: consegne.append(a), chiusi.append)
    assert consegne == [] and chiusi == ['prima', 'seconda']
    assert not coda.aperta() and not coda.annullato('seconda')


def test_coda_esc_dopo_una_ripresa_non_manda_l_invio_sospeso():
    coda = voce_lib.CodaDettature()
    consegne = []

    def consegna(testo, bersaglio, revisione):
        consegne.append(testo)
        return True               # Invio sospeso: Sal ha ripreso a parlare
    coda.apri('prima')
    coda.completa('prima', 'Prima.', 'chat')
    coda.consegna_pronte(consegna, lambda _: None)
    coda.apri('ripresa')
    coda.annulla()                # Esc durante la ripresa
    coda.completa('ripresa', '', 'chat')
    coda.consegna_pronte(consegna, lambda _: None)
    assert consegne == ['Prima.']  # nessun Invio vuoto per la frase prima


def test_coda_aperta_fino_all_incolla_non_durante_l_attesa_dell_invio():
    coda = voce_lib.CodaDettature()
    stati = []

    def consegna(testo, bersaglio, revisione):
        stati.append(coda.aperta())   # sta cercando la casella: Esc butta ancora
        coda.incollato()
        stati.append(coda.aperta())   # testo incollato: Esc torna all'app
        return False
    coda.apri('t')
    coda.completa('t', 'Testo.', 'chat')
    coda.consegna_pronte(consegna, lambda _: None)
    assert stati == [True, False]


def test_esc_mentre_cerca_la_casella_niente_incolla_e_niente_invio(tmp_path, caplog):
    p = _percorso_consegna_completo('mac', tmp_path)
    riattiva = p.spazio['riattiva_bersaglio']

    def riattiva_e_esc(target, *a):
        riattiva(target, *a)
        p.coda.annulla()          # Sal preme Esc mentre la Voce porta il cursore nella chat
    p.spazio['riattiva_bersaglio'] = riattiva_e_esc
    p.coda.apri('t')
    p.coda.completa('t', 'Non deve arrivare.', p.bersaglio)
    with caplog.at_level(logging.INFO):
        p.consegna()
    assert p.campo == [] and p.inviati == []
    assert "annullata con Esc" in caplog.text
    assert p.spazio['ultime_dettature'].disponibili() == (False, False)


def test_esc_durante_l_incolla_ferma_l_invio(tmp_path, caplog):
    p = _percorso_consegna_completo('mac', tmp_path)
    incolla = p.spazio['incolla']

    def incolla_ed_esc(testo, **kw):
        incolla(testo, **kw)
        p.coda.annulla()          # Esc mentre il Cmd+V e' gia' partito: il testo resta, l'Invio no
    p.spazio['incolla'] = incolla_ed_esc
    p.spazio['ritardo_invio'] = lambda *a: 2.0
    p.coda.apri('t')
    p.coda.completa('t', 'Resta scritta.', p.bersaglio)
    with caplog.at_level(logging.INFO):
        p.consegna()
    assert ''.join(p.campo).strip() == 'Resta scritta.' and p.inviati == []
    assert "ANNULLATO (Esc)" in caplog.text


def test_esc_mentre_registra_chiude_senza_whisper_e_la_pill_lo_dice(tmp_path):
    m = _avvio_mac(tmp_path)
    s = m.spazio
    conclusi = []
    s.update(ultime_dettature=voce_lib.UltimeDettature(),
             _concludi_dettatura=lambda token, *a, **kw: conclusi.append(token),
             ferma_e_trascrivi=lambda: pytest.fail("Whisper non deve partire"))
    _dal_sorgente('mac', ['annulla_dettatura'], s)
    s['su_pressione']('cmd_r')
    m.suona(0.5, 0.1, 480)
    m.lavora()
    assert s['registrando'] is True
    s['coda_dettature'].annulla()
    s['comandi_audio'].put("annulla")   # quello che fa il filtro di Esc
    m.lavora()
    assert s['registrando'] is False and conclusi == ['turno']
    assert ('avviso', 'Dettatura annullata', 1.5) in list(m.eventi.queue)
    assert "dettatura annullata con Esc: niente incolla, niente Invio" in m.log
    s['su_rilascio']('cmd_r')            # il tasto si molla dopo: nessuna trascrizione
    s['ferma_e_trascrivi'] = lambda: None
    m.lavora()


def test_esc_prima_di_whisper_niente_trascrizione(tmp_path):
    p = _percorso_consegna_completo('mac', tmp_path)
    spazio = p.spazio
    spazio.update(np=np, BASE=tmp_path, salva_audio_recente=lambda *a, **kw: pytest.fail("niente lavoro"),
                  _trascrivi_con_sessione=lambda *a: pytest.fail("Whisper non deve partire"),
                  _registra_attesa=lambda _: None, _concludi_dettatura=p.coda.completa)
    _dal_sorgente('mac', ['_trascrivi_e_incolla', 'TrascrizioneIncompleta', '_avvisa_errore_audio'], spazio)
    p.coda.apri('t')
    p.coda.annulla()
    spazio['_trascrivi_e_incolla'](np.full(16000, 0.04, dtype='float32'), *p.bersaglio, token_turno='t')
    p.consegna()
    assert p.campo == [] and p.inviati == [] and not p.coda.aperta()


def _filtro_esc(finestra=True, registrazione_fa=1.0):
    """La callback vera del filtro con Quartz finto: torna (callback, coda, comandi)."""
    from types import SimpleNamespace
    GIU, SU, SPENTO = 10, 11, 0xFFFFFFFE
    campi = {"tasto": 1, "ripetuto": 2}
    Q = SimpleNamespace(
        kCGEventKeyDown=GIU, kCGKeyboardEventKeycode=campi["tasto"],
        kCGKeyboardEventAutorepeat=campi["ripetuto"],
        kCGEventFlagMaskControl=1 << 18, kCGEventFlagMaskAlternate=1 << 19,
        CGEventGetIntegerValueField=lambda ev, campo: ev[campo],
        CGEventGetFlags=lambda ev: ev.get("flags", 0),
        CGEventTapEnable=lambda tap, acceso: None,
    )
    coda = voce_lib.CodaDettature()
    if finestra:
        coda.apri('t')
    comandi = []
    spazio = dict(Quartz=Q, time=__import__('time'), _TAP_DISABILITATO=(SPENTO,), VK_ESC=voce_lib.VK_ESC,
                  esc_annulla=voce_lib.EscAnnulla(), rubinetto_esc=None, coda_dettature=coda,
                  registrando=False, comandi_audio=SimpleNamespace(put=comandi.append),
                  FINESTRA_ESC_MAX_SEC=120,
                  _ultima_registrazione=__import__('time').monotonic() - registrazione_fa)
    _dal_sorgente('mac', ['_su_evento_esc', 'finestra_esc_aperta'], spazio)
    evento = lambda tasto, ripetuto=0, flags=0: {1: tasto, 2: ripetuto, "flags": flags}
    return spazio['_su_evento_esc'], coda, comandi, evento, GIU, SU


def test_filtro_esc_trattiene_solo_esc_durante_la_dettatura():
    filtro, coda, comandi, evento, GIU, SU = _filtro_esc()
    lettera = evento(0)
    assert filtro(None, GIU, lettera, None) is lettera                 # gli altri tasti passano sempre
    assert filtro(None, GIU, evento(53), None) is None                 # Esc: all'app non arriva
    assert comandi == ["annulla"] and coda.annullato('t')
    assert filtro(None, GIU, evento(53, ripetuto=1), None) is None     # tenuto premuto
    assert filtro(None, SU, evento(53), None) is None
    fuori, _, comandi_fuori, evento, GIU, _ = _filtro_esc(finestra=False)
    esc = evento(53)
    assert fuori(None, GIU, esc, None) is esc and comandi_fuori == []  # fuori dalla dettatura: e' dell'app


def test_filtro_esc_una_coda_appesa_non_toglie_esc_alle_app_per_sempre():
    """Un avvio fallito puo' lasciare la coda aperta: dopo due minuti senza registrazioni
    Esc torna all'app, invece di essere trattenuto ovunque."""
    filtro, _, comandi, evento, GIU, _ = _filtro_esc(registrazione_fa=121.0)
    esc = evento(53)
    assert filtro(None, GIU, esc, None) is esc and comandi == []


def test_filtro_esc_un_errore_lascia_passare_il_tasto():
    filtro, _, _, _, GIU, _ = _filtro_esc()
    rotto = {"flags": 0}                       # manca il codice del tasto: la lettura fallisce
    assert filtro(None, GIU, rotto, None) is rotto


def test_filtro_esc_acceso_solo_nella_dettatura_e_prima_dell_incolla():
    sorgente = (REPO_ROOT / 'mac' / 'detta.py').read_text(encoding='utf-8')
    assert 'Quartz.kCGEventTapOptionDefault' in sorgente           # attivo: puo' togliere il tasto
    assert sorgente.count('Quartz.kCGEventTapOptionDefault') == 1  # uno solo, quello di Esc
    avvio = sorgente[sorgente.index('if __name__ == "__main__":'):]
    assert '"kCGKeyboardEventAutorepeat"' in avvio                 # nomi Quartz caricati prima dei thread
    assert avvio.index('"CGEventTapCreate"') < avvio.index('target=worker_rubinetto_esc')
    avvio = sorgente.split("def avvia_registrazione", 1)[1].split("\ndef ", 1)[0]
    assert "esegui_sicuro(apri_rubinetto_esc)" in avvio
    incolla = sorgente.split("def _incolla_messaggio", 1)[1].split("\ndef ", 1)[0]
    assert incolla.index("coda_dettature.consegna_annullata()") < incolla.index("incolla(testo")
    assert incolla.index("incolla(testo") < incolla.index("coda_dettature.incollato()")


def test_avviso_con_la_sua_durata_nella_pill():
    import queue
    from types import SimpleNamespace
    eventi, testi, visibile, ora = queue.Queue(), [], [False], [100.0]
    pannello = SimpleNamespace(orderFrontRegardless=lambda: visibile.__setitem__(0, True),
                              orderOut_=lambda _: visibile.__setitem__(0, False))

    class Elemento:
        def __getattr__(self, nome):
            return lambda *a, **kw: testi.append(a[0]) if nome == 'setStringValue_' else None
    spazio = dict(queue=queue, eventi=eventi, registrando=False,
                  time=SimpleNamespace(monotonic=lambda: ora[0]), pannello=pannello,
                  posiziona_pannello=lambda: None, aggiorna_indicatore_voce=lambda: None,
                  brand=Elemento(), etichetta=Elemento(), onda=Elemento(),
                  marchio_in_evidenza=lambda *a, **kw: None, marchio_entra=lambda: None,
                  punto_pulsa=lambda _: None, mascotte_ferma=lambda: None,
                  stop_se_registrazione_troppo_lunga=lambda: None, punto_segue_voce=lambda _: None,
                  volume_corrente=0.0, listener=None, esegui_sicuro=lambda f: f(),
                  aggiorna_rubinetto_esc=lambda: None)
    classe = next(n for n in ast.parse((REPO_ROOT / 'mac' / 'detta.py').read_text()).body
                  if isinstance(n, ast.ClassDef) and n.name == 'GestorePannello')
    metodo = next(n for n in classe.body if isinstance(n, ast.FunctionDef) and n.name == 'tick_')
    exec(compile(ast.Module(body=[metodo], type_ignores=[]), 'detta.py', 'exec'), spazio)
    ui = SimpleNamespace(stato='nascosto', _tick=1, _aggiorna_mini=lambda: None)
    eventi.put(('avviso', 'Dettatura annullata', 1.5))
    eventi.put('nascosto')                 # la coda si chiude subito: l'avviso resta
    spazio['tick_'](ui, None)
    assert visibile[0] and 'Dettatura annullata' in testi
    ora[0] += 1.0
    spazio['tick_'](ui, None)
    assert visibile[0]
    ora[0] += 0.6
    spazio['tick_'](ui, None)
    assert not visibile[0]                 # «brevemente»: 1,5 s, non i 4 degli errori


# --- Menu Voce: ultime dettature ---

def test_ultime_dettature_solo_pezzi_con_testo_in_ordine_di_registrazione():
    ultime = voce_lib.UltimeDettature()
    assert ultime.disponibili() == (False, False)
    ultime.pezzo("1:300", "audio-B", "Poi questo.")
    ultime.pezzo("1:100", "audio-A", "Prima questo.")
    ultime.pezzo("1:200", "audio-muto", "")           # scartato: non fa parte del testo
    ultime.consegnata("Prima questo. Poi questo.")
    assert ultime.ultima() == ("Prima questo. Poi questo.", ["audio-A", "audio-B"])
    ultime.pezzo("1:400", "audio-buttato", "Buttato.")
    ultime.annulla_in_corso()                          # Esc
    ultime.consegnata("")                              # niente incollato: resta l'ultima vera
    assert ultime.ultima()[0] == "Prima questo. Poi questo."
    assert not any(isinstance(v, (str, os.PathLike)) and os.path.sep in str(v)
                   for v in vars(ultime).values())     # nessun file: solo memoria


def test_menu_ultime_dettature_spente_finche_non_ce_n_e_una():
    ultime = voce_lib.UltimeDettature()
    app = _menu_voce_simulato({"rileggibile": False, "preferita": None, "conversazioni": []}, ultime)
    app.aggiorna()
    *_, separatore, copia, ritrascrivi = app.indicatore.menu.elementi
    assert separatore.separatore
    assert copia.titolo == "Copia l’ultima dettatura" and not copia.attivo
    assert ritrascrivi.titolo == "Ritrascrivi l’ultima" and not ritrascrivi.attivo
    ultime.pezzo("1:1", np.zeros(10), "Ciao.")
    ultime.consegnata("Ciao.")
    app.aggiorna()                                     # il menu si rifa' da solo
    *_, copia, ritrascrivi = app.indicatore.menu.elementi
    assert copia.attivo and ritrascrivi.attivo
    copia.seleziona()
    ritrascrivi.seleziona()
    assert app.chiamate == [("copia",), ("ritrascrivi",)]
    assert all(lavoro.daemon for lavoro in app.lavori)  # mai sul thread del menu


def _menu_azioni(ultime, trascrivi=lambda audio: audio):
    import queue
    import threading
    appunti, eventi, righe = [], queue.Queue(), []
    spazio = dict(ultime_dettature=ultime, eventi=eventi, trascrivi=trascrivi,
                  e_allucinazione=voce_lib.e_allucinazione, _lock_trascrizione=threading.Lock(),
                  _negli_appunti=appunti.append,
                  logging=type("L", (), {"getLogger": staticmethod(lambda *_: type("R", (), {
                      "info": staticmethod(lambda m, *a: righe.append(m % a)),
                      "exception": staticmethod(lambda m, *a: righe.append(m))})())}))
    _dal_sorgente('mac', ['copia_ultima_dettatura', 'ritrascrivi_ultima'], spazio)
    return spazio, appunti, eventi, righe


def test_copia_l_ultima_dettatura_va_negli_appunti_e_il_testo_non_va_nel_registro():
    ultime = voce_lib.UltimeDettature()
    ultime.consegnata("Una frase privata.")
    spazio, appunti, _, righe = _menu_azioni(ultime)
    spazio['copia_ultima_dettatura']()
    assert appunti == ["Una frase privata."]
    assert righe and all("privata" not in r for r in righe)


def test_ritrascrivi_l_ultima_unisce_i_pezzi_mette_negli_appunti_e_lo_dice_la_pill():
    ultime = voce_lib.UltimeDettature()
    ultime.pezzo("1:1", "Prima parte.", "x")
    ultime.pezzo("1:2", "Grazie.", "x")          # un pezzo che oggi esce fantasma: non entra
    ultime.pezzo("1:3", "Seconda parte.", "x")
    ultime.consegnata("x")
    spazio, appunti, eventi, righe = _menu_azioni(ultime)
    spazio['ritrascrivi_ultima']()
    assert appunti == ["Prima parte. Seconda parte."]
    avvisi = [e[1] for e in list(eventi.queue)]
    assert avvisi[0].startswith("⏳") and "Appunti" in avvisi[-1]
    assert all("parte" not in r for r in righe)


def test_ritrascrivi_senza_voce_o_con_errore_lo_dice_e_non_tocca_gli_appunti():
    ultime = voce_lib.UltimeDettature()
    ultime.pezzo("1:1", "", "x")
    ultime.consegnata("x")
    spazio, appunti, eventi, _ = _menu_azioni(ultime)
    spazio['ritrascrivi_ultima']()
    assert appunti == [] and list(eventi.queue)[-1][1] == "Niente da ritrascrivere"

    def rotto(audio):
        raise RuntimeError("motore")
    spazio, appunti, eventi, _ = _menu_azioni(ultime, rotto)
    spazio['ritrascrivi_ultima']()
    assert appunti == [] and list(eventi.queue)[-1][1] == "Ritrascrizione fallita"


def test_la_consegna_vera_ricorda_testo_e_audio_dell_ultima_dettatura(tmp_path):
    p = _pipeline_due_pressioni('mac', tmp_path, {'audio-1': 'Prima.', 'audio-2': 'Seconda.'})
    p.coda.apri('1:1')
    p.coda.apri('1:2')
    p.spazio['_trascrivi_con_sessione'] = lambda audio, sessione: {'audio-1': 'Prima.', 'audio-2': 'Seconda.'}[audio]
    args = p.bersaglio
    p.spazio['_trascrivi_e_incolla']('audio-2', *args, token_turno='1:2')
    p.spazio['_trascrivi_e_incolla']('audio-1', *args, token_turno='1:1')
    p.consegna()
    assert p.inviati == ['Prima. Seconda.']
    assert p.spazio['ultime_dettature'].ultima() == ('Prima. Seconda.', ['audio-1', 'audio-2'])


def test_incolla_e_menu_condividono_il_lucchetto_degli_appunti():
    sorgente = (REPO_ROOT / 'mac' / 'detta.py').read_text(encoding='utf-8')
    for funzione in ("def incolla", "def _negli_appunti"):
        corpo = sorgente.split(funzione, 1)[1].split("\ndef ", 1)[0]
        assert "with _lock_appunti:" in corpo
