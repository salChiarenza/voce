import ast
import importlib.util
import json
import re
from pathlib import Path


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
                                  "SOGLIA_GUASTI_CORSIA", "RIPOSO_CORSIA_SEC")
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
