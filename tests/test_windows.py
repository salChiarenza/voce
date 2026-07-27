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
                isinstance(target, ast.Name) and target.id == "_FRASI_FANTASMA"
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
