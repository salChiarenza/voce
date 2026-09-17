"""Test delle funzioni pure della versione Mac di Voce."""
import json
import os
import plistlib
import sqlite3
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "mac"))
import voce_lib
import voce_hook
import parla


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
                                    "command": "python /Users/sal/leaderai/tools/voce/voce_hook.py",
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

def _menu_voce_simulato(stato):
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
    }
    sorgente = REPO_ROOT / "mac" / "detta.py"
    albero = ast.parse(sorgente.read_text(encoding="utf-8"))
    aggiorna = next(n for n in albero.body
                    if isinstance(n, ast.FunctionDef) and n.name == "aggiorna_indicatore_menu")
    gestore = next(n for n in albero.body
                  if isinstance(n, ast.ClassDef) and n.name == "GestorePannello")
    gestore.body = [n for n in gestore.body if isinstance(n, ast.FunctionDef)
                   and n.name in {"rileggiVoce_", "scegliConversazione_"}]
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
    replay, _, tutte = app.indicatore.menu.elementi
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
    tutte, fonte_a, fonte_b = app.indicatore.menu.elementi[2:]
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
    prima, seconda, senza_nome = app.indicatore.menu.elementi[3:]
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
        "Apri `/Users/sal/Documenti/Report finale.pdf` e "
        "[controllo](</Users/sal/leaderai/tools/verifica.py:12>). "
        "Su Windows usa `C:\\Users\\Sal\\Documenti\\Report finale.pdf`. "
        "L'altro file è /Users/sal/leaderai/docs/STATUS.md."
    )
    pulito = voce_lib.pulisci_per_voce(testo)
    assert "/Users/" not in pulito and "C:\\" not in pulito
    assert pulito.count("Report finale.pdf") == 2
    assert "controllo" in pulito and "verifica.py" in pulito and "riga 12" in pulito
    assert "STATUS.md" in pulito


def test_pulisci_per_voce_file_etichettato_non_ripete_il_nome():
    pulito = voce_lib.pulisci_per_voce(
        "Apri [verifica.py](/Users/sal/tools/verifica.py:12)."
    )
    assert pulito == "Apri verifica.py, riga 12."


def test_pulisci_per_voce_percorsi_quotati_con_spazi_e_windows_nudo():
    pulito = voce_lib.pulisci_per_voce(
        'Apri "/Users/sal/My Documents/Report finale.pdf". '
        "Poi C:\\Users\\Sal\\Documenti\\REPORT.md. Non cambiare il rapporto costo/beneficio."
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
        "- Apri `/Users/sal/relazioni/report_2026-09-05.md`\n\n"
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
        "transcriptPath": "/Users/sal/.gemini/antigravity/brain/abc-123/.system_generated/logs/transcript.jsonl",
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
    assert voce_lib.ritardo_invio({}, False, True) == 1.0
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
                            passate=[None], finestra=(0, 33, 1512, 949), casella_a_fuoco=(100, 900, 1300, 60))

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
                           "_ricorda_casella", "_punto_ricordato", "_chiedi_albero_electron"))
        or (isinstance(n, ast.Assign)
            and any(getattr(t, "id", "") in ("AX_ATTESA_RISVEGLIO_SEC", "AX_GIRI_RISVEGLIO", "_caselle_ricordate")
                    for t in n.targets))
    ]
    exec(compile(ast.Module(body=nodi, type_ignores=[]), str(path), "exec"), spazio)
    app = SimpleNamespace(processIdentifier=lambda: 41474, localizedName=lambda: "Claude")

    def chiama(passate, focus_dopo_attesa=False, focus=False):
        stato.passate, stato.focus_dopo_attesa, stato.focus = passate, focus_dopo_attesa, focus
        stato.attese, stato.giri, stato.click = [], [], []
        return spazio["metti_cursore_in_casella"](app)

    stato.chiama = chiama
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
    )
    path = REPO_ROOT / "mac" / "detta.py"
    nodi = [n for n in ast.parse(path.read_text()).body
            if isinstance(n, ast.FunctionDef) and n.name in ("_sveglia_accessibilita", "_chiedi_albero_electron")]
    exec(compile(ast.Module(body=nodi, type_ignores=[]), str(path), "exec"), spazio)
    app = SimpleNamespace(processIdentifier=lambda: 1, localizedName=lambda: "Antigravity")
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


def _percorso_consegna(sistema, tmp_path, seconda_durante_incolla=False, *, casella=True, chat=True):
    import ast
    import logging
    import queue
    import threading
    from types import SimpleNamespace
    coda = _coda_dettature(sistema)
    app = SimpleNamespace(localizedName=lambda: 'ChatGPT')
    bersaglio = (app, None) if sistema == 'mac' else 42
    campo, inviati, chiusi = [], [], []
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
    tastiera = SimpleNamespace(press=premi, release=lambda _: None)
    tempo = SimpleNamespace(monotonic=lambda: 100.0, sleep=lambda _: None)
    spazio = dict(
        logging=logging, threading=threading, coda_dettature=coda,
        time=tempo, eventi=queue.Queue(), cfg={'invio_automatico': True},
        CFG={}, INVIO_AUTOMATICO=True, registrando=False, recording=False,
        tasto_premuto=False, key_down=False, ultima_pressione_utente=0,
        Key=SimpleNamespace(enter='enter'), tastiera=tastiera,
        keyboard_controller=tastiera, incolla=incolla, paste_text=incolla,
        esegui_sicuro=lambda f, *a, **kw: f(*a, **kw),
        riattiva_bersaglio=lambda *a: None, metti_cursore_in_casella=lambda *a: casella,
        voce_attiva=lambda: False, destinazione_agente=lambda *a: chat,
        nome_finestra=lambda _: 'ChatGPT', ritardo_invio=lambda *a: 0,
        chiudi_turno_utente=chiusi.append, _nascondi_o_arma=lambda: None,
        suono=lambda _: None, winsound=None,  # avviso "incollato alla cieca"
    )
    path = REPO_ROOT / ('mac/detta.py' if sistema == 'mac' else 'windows/voice_dettatura_windows.py')
    nodi = [n for n in ast.parse(path.read_text()).body
            if isinstance(n, ast.FunctionDef) and n.name in ('_incolla_messaggio', '_consegna_dettature')]
    exec(compile(ast.Module(body=nodi, type_ignores=[]), str(path), 'exec'), spazio)
    return coda, bersaglio, spazio['_consegna_dettature'], campo, inviati, chiusi


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
                  _concludi_dettatura=coda.completa,
                  _nascondi_o_arma=lambda: None)
    nome = 'ferma_e_trascrivi' if sistema == 'mac' else 'stop_recording'
    path = REPO_ROOT / ('mac/detta.py' if sistema == 'mac' else 'windows/voice_dettatura_windows.py')
    nodi = [n for n in ast.parse(path.read_text()).body
            if isinstance(n, ast.FunctionDef) and n.name == nome]
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
