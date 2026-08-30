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
    monkeypatch.setattr(parla.subprocess, "Popen", lambda *a, **k: avvii.append(a))
    monkeypatch.setattr(parla.subprocess, "run", lambda c, **k: comandi.append(c))

    parla.parla("prima risposta")
    parla.parla("seconda risposta")

    assert pendente.read_text(encoding="utf-8") == "seconda risposta"  # vince l'ultima
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


def test_prendi_pendente_vince_l_ultimo(tmp_path):
    pendente = tmp_path / "LETTURA_PENDENTE"
    parla.scrivi_pendente("risposta vecchia", pendente)
    parla.scrivi_pendente("risposta nuova", pendente)

    assert parla.prendi_pendente(pendente) == "risposta nuova"
    assert parla.prendi_pendente(pendente) is None  # l'attesa e' un posto solo


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

    assert not flag.exists() and not pendente.exists() and not lock.exists()
    assert ["pkill", "-x", "say"] in comandi


def test_voce_attiva_segue_il_flag(tmp_path, monkeypatch):
    flag = tmp_path / "VOICE_ON"
    monkeypatch.setattr(voce_lib, "FLAG_VOICE_ON", flag)
    assert voce_lib.voce_attiva() is False
    flag.touch()
    assert voce_lib.voce_attiva() is True


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
    assert voce_lib.destinazione_agente("Mail", "") is False
    assert voce_lib.destinazione_agente("Google Chrome", "https://example.com") is False


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


def test_impara_sostituzioni_aggiorna_il_config(tmp_path):
    log = tmp_path / "voce.log"
    log.write_text("x INFO grezzo: il giornato di oggi\nx INFO grezzo: apri il giornato\n")
    config = tmp_path / "config.json"
    config.write_text('{"sostituzioni": {}}')
    comando = ["/bin/sh", "-c", 'echo \'{"giornato": "giornale"}\'']
    nuove = voce_lib.impara_sostituzioni(log, config, comando, timeout=10)
    assert nuove == {"giornato": "giornale"}
    import json
    assert json.loads(config.read_text())["sostituzioni"] == {"giornato": "giornale"}


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
