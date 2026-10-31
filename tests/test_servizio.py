"""La Voce e' un servizio di macOS: LaunchAgent + app «Voce LeaderAI».

Caso del 01/10/2026: la Voce viveva dentro una finestra del Terminale e a ogni riavvio degli
agenti ne restava una aperta. Ora la gestisce macOS (parte al login, riparte da sola) e i
permessi sono dell'app, non del Terminale ne' di chi lancia il comando.

Prove: i riavvii interni di detta.py, l'unica istanza, la modalita' --permessi, il lanciatore
compilato (vero, se c'e' clang), il comando `voce riavvia` / `voce permessi` e l'installer.
"""
import ast
import json
import logging
import os
import plistlib
import re
import shutil
import signal
import subprocess
import sys
import time
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
MAC = REPO_ROOT / "mac"
DETTA = MAC / "detta.py"


# --- detta.py: funzioni estratte senza importare l'app (richiede schermo, microfono, modello) ---

def _da_detta(nomi, **globali):
    albero = ast.parse(DETTA.read_text(encoding="utf-8"))
    corpo = [n for n in albero.body if isinstance(n, ast.FunctionDef) and n.name in nomi]
    assert {n.name for n in corpo} == set(nomi), nomi
    spazio = {"os": os, "sys": sys, "subprocess": subprocess, "logging": logging, "time": time,
              "json": json, "__file__": str(DETTA), **globali}
    exec(compile(ast.Module(body=corpo, type_ignores=[]), str(DETTA), "exec"), spazio)
    return spazio


class _Uscita(Exception):
    def __init__(self, codice):
        self.codice = codice


def _os_finto(**extra):
    base = types.SimpleNamespace(path=os.path, environ={}, getpid=lambda: 100, getppid=lambda: 200,
                                 kill=lambda *a: None)
    base._exit = lambda codice: (_ for _ in ()).throw(_Uscita(codice))
    for k, v in extra.items():
        setattr(base, k, v)
    return base


def test_riavvio_interno_sotto_servizio_esce_e_basta():
    lanciati = []
    finto_subprocess = types.SimpleNamespace(Popen=lambda *a, **k: lanciati.append(a))
    spazio = _da_detta(["riavvia_processo"], SOTTO_SERVIZIO=True, os=_os_finto(), subprocess=finto_subprocess)
    with pytest.raises(_Uscita) as e:
        spazio["riavvia_processo"]("audio incantato")
    assert e.value.codice == 0
    assert lanciati == [], "una copia lanciata a mano e il rilancio di launchd darebbero due istanze"


def test_riavvio_interno_fuori_dal_servizio_resta_quello_di_prima():
    lanciati = []
    finto_subprocess = types.SimpleNamespace(Popen=lambda *a, **k: lanciati.append(a))
    spazio = _da_detta(["riavvia_processo"], SOTTO_SERVIZIO=False, os=_os_finto(), subprocess=finto_subprocess)
    with pytest.raises(_Uscita):
        spazio["riavvia_processo"]("audio incantato")
    assert len(lanciati) == 1


def test_la_costante_del_servizio_viene_dall_ambiente():
    testo = DETTA.read_text(encoding="utf-8")
    assert 'SOTTO_SERVIZIO = os.environ.get("VOCE_SERVIZIO") == "1"' in testo
    assert '"VOCE_SERVIZIO": "1"' in (MAC / "voce").read_text(encoding="utf-8")


def test_unica_istanza_non_uccide_il_padre_ne_il_lanciatore():
    comandi = {
        200: "/Users/x/Applications/Voce LeaderAI.app/Contents/MacOS/Voce LeaderAI /v/bin/python /v/detta.py",
        300: "/Users/x/Applications/Voce LeaderAI.app/Contents/MacOS/Voce LeaderAI /v/bin/python /v/detta.py",
        400: "/Library/Frameworks/Python.framework/Versions/3.14/Resources/Python.app/Contents/MacOS/Python detta.py",
    }
    uccisi = []

    def esegui(args, **k):
        if args[0] == "pgrep":
            return types.SimpleNamespace(stdout="100\n200\n300\n400\n")
        return types.SimpleNamespace(stdout=comandi[int(args[-1])])

    spazio = _da_detta(["unica_istanza"], LANCIATORE_APP="Voce LeaderAI.app/",
                       os=_os_finto(kill=lambda pid, sig: uccisi.append(pid)),
                       subprocess=types.SimpleNamespace(run=esegui))
    spazio["unica_istanza"]()
    assert uccisi == [400]


def test_modalita_permessi_sta_prima_di_ogni_cosa_che_tocca_l_istanza_viva():
    testo = DETTA.read_text(encoding="utf-8")
    ingresso = testo.index('"--permessi" in sys.argv')
    assert ingresso < testo.index("import numpy as np")
    assert ingresso < testo.index("unica_istanza()\n    FLAG_TURNO_UTENTE")


@pytest.mark.parametrize("stato, atteso", [
    ({"accessibilita": False, "ascolto_tastiera": False, "microfono": False}, 1),
    ({"accessibilita": True, "ascolto_tastiera": True, "microfono": False}, 1),
    ({"accessibilita": True, "ascolto_tastiera": True, "microfono": True}, 0),
])
def test_modalita_permessi_solo_stato_legge_e_basta(stato, atteso, capsys):
    spazio = _da_detta(["_modalita_permessi"], _stato_permessi=lambda: dict(stato))
    assert spazio["_modalita_permessi"](["detta.py", "--permessi", "--solo-stato"]) == atteso
    assert json.loads(capsys.readouterr().out.splitlines()[-1]) == stato


# --- lanciatore compilato: prova vera ---

@pytest.fixture(scope="module")
def lanciatore(tmp_path_factory):
    if not shutil.which("clang"):
        pytest.skip("clang non disponibile")
    exe = tmp_path_factory.mktemp("lanciatore") / "Voce LeaderAI"
    r = subprocess.run(["clang", "-O2", "-Wall", "-o", str(exe), str(MAC / "voce_launcher.c")],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return exe


def _finto_python(cartella, corpo):
    python = cartella / "python-finto"
    python.write_text("#!/bin/sh\n" + corpo + "\n")
    python.chmod(0o755)
    (cartella / "detta.py").write_text("")
    return python, cartella / "detta.py"


def test_lanciatore_propaga_l_esito_del_figlio(lanciatore, tmp_path):
    python, script = _finto_python(tmp_path, "exit 7")
    assert subprocess.run([str(lanciatore), str(python), str(script)]).returncode == 7


def test_lanciatore_figlio_ucciso_da_un_segnale_esce_con_128_piu_il_segnale(lanciatore, tmp_path):
    python, script = _finto_python(tmp_path, "kill -9 $$")
    assert subprocess.run([str(lanciatore), str(python), str(script)]).returncode == 128 + 9


def test_lanciatore_passa_gli_argomenti_al_figlio(lanciatore, tmp_path):
    prova = tmp_path / "argomenti.txt"
    python, script = _finto_python(tmp_path, f'echo "$@" > {prova}')
    subprocess.run([str(lanciatore), str(python), str(script), "--permessi", "--solo-stato"], check=True)
    assert prova.read_text().split() == [str(script), "--permessi", "--solo-stato"]


def test_lanciatore_non_e_un_lanciatore_di_programmi_qualsiasi(lanciatore, tmp_path):
    python, _ = _finto_python(tmp_path, "exit 0")
    altro = tmp_path / "altro.py"
    altro.write_text("")
    assert subprocess.run([str(lanciatore), str(python), str(altro)], capture_output=True).returncode == 64
    assert subprocess.run([str(lanciatore), "/bin/echo", str(tmp_path / "detta.py")],
                          capture_output=True).returncode == 64
    assert subprocess.run([str(lanciatore)], capture_output=True).returncode == 64


def test_lanciatore_inoltra_la_terminazione_e_aspetta_il_figlio(lanciatore, tmp_path):
    avviato = tmp_path / "avviato"
    python, script = _finto_python(tmp_path, f"trap 'exit 42' TERM\ntouch {avviato}\nwhile true; do sleep 0.1; done")
    processo = subprocess.Popen([str(lanciatore), str(python), str(script)])
    try:
        for _ in range(100):
            if avviato.exists():
                break
            time.sleep(0.05)
        assert avviato.exists()
        processo.send_signal(signal.SIGTERM)
        assert processo.wait(timeout=10) == 42
    finally:
        if processo.poll() is None:
            processo.kill()


# --- comando `voce`: codice Python dentro lo script ---

def _codice_voce():
    testo = (MAC / "voce").read_text(encoding="utf-8")
    return re.search(r"<<'PYEOF'\n(.*?)\nPYEOF\n", testo, re.S).group(1)


def _spazio_voce(tmp_path, monkeypatch, comando="riavvia", **sostituzioni):
    cartella = tmp_path / "voce"
    cartella.mkdir(exist_ok=True)
    sorgente = tmp_path / "mac"
    sorgente.mkdir(exist_ok=True)
    (sorgente / "voce").write_text("")
    (sorgente / "voce_launcher.c").write_text("int main(void){return 0;}\n")
    if not (cartella / "voce").exists():
        (cartella / "voce").symlink_to(sorgente / "voce")
    monkeypatch.setattr(sys, "argv", ["-", comando, str(cartella), "/venv/bin/python"])
    codice = _codice_voce().rsplit("\nsys.exit(", 1)[0]
    spazio = {"__name__": "voce_prova"}
    exec(compile(codice, "voce", "exec"), spazio)
    spazio.update(sostituzioni)
    return spazio


def test_il_comando_non_apre_mai_il_terminale():
    testo = (MAC / "voce").read_text(encoding="utf-8")
    assert "osascript" not in testo and "do script" not in testo and not re.search(r"\bTerminal\b", testo)


def test_il_servizio_parte_al_login_riparte_da_solo_e_avvia_l_app(tmp_path, monkeypatch):
    s = _spazio_voce(tmp_path, monkeypatch)
    piano = plistlib.loads(plistlib.dumps(s["plist_servizio"]()))
    assert piano["Label"].startswith("com.leaderai.")
    assert piano["RunAtLoad"] is True and piano["KeepAlive"] is True
    assert piano["LimitLoadToSessionType"] == "Aqua"
    app, python, script = piano["ProgramArguments"]
    assert app.endswith("Voce LeaderAI.app/Contents/MacOS/Voce LeaderAI")
    assert python == "/venv/bin/python" and script == str(tmp_path / "voce" / "detta.py")
    assert piano["StandardOutPath"] == str(tmp_path / "voce" / "voce.log")
    assert piano["EnvironmentVariables"]["VOCE_SERVIZIO"] == "1"
    assert "/usr/bin" in piano["EnvironmentVariables"]["PATH"].split(":")


def test_l_app_si_crea_una_volta_sola_e_non_si_ricompila(tmp_path, monkeypatch):
    app = tmp_path / "Applications" / "Voce LeaderAI.app"
    exe = app / "Contents" / "MacOS" / "Voce LeaderAI"
    chiamate = []

    def esegui(args, **k):
        chiamate.append(args[0])
        if args[0] == "clang":
            Path(args[args.index("-o") + 1]).write_text("binario")
            return types.SimpleNamespace(returncode=0, stdout="", stderr="")
        if args[0] == "codesign" and "--verify" in args:
            return types.SimpleNamespace(returncode=0 if exe.exists() else 1, stdout="", stderr="")
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")

    s = _spazio_voce(tmp_path, monkeypatch, APP=app, APP_EXE=exe,
                     subprocess=types.SimpleNamespace(run=esegui))
    s["assicura_app"]()
    assert chiamate == ["clang", "codesign"], "compila e firma"
    info = plistlib.loads((app / "Contents" / "Info.plist").read_bytes())
    assert info["CFBundleIdentifier"] == "com.leaderai.voce"
    assert info["NSMicrophoneUsageDescription"], "senza il testo d'uso macOS non mostra la richiesta del microfono"
    chiamate.clear()
    s["assicura_app"]()
    assert chiamate == ["codesign"], "gia' creata e firmata: solo la verifica, nessuna ricompilazione"


def test_dettatura_in_corso_non_si_riavvia(tmp_path, monkeypatch):
    s = _spazio_voce(tmp_path, monkeypatch)
    cartella = tmp_path / "voce"
    ora = time.strftime("%Y-%m-%d %H:%M:%S")
    vecchio = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() - 3600))

    def registro(*righe):
        (cartella / "voce.log").write_text("\n".join(righe) + "\n")

    registro(f"{ora},100 INFO registrazione avviata")
    assert s["dettatura_in_corso"]([1]) is True
    registro(f"{ora},100 INFO registrazione avviata", f"{ora},900 INFO registrazione fermata")
    assert s["dettatura_in_corso"]([1]) is False
    registro(f"{vecchio},100 INFO registrazione avviata")  # incantata da un'ora: non blocca per sempre
    assert s["dettatura_in_corso"]([1]) is False
    registro(f"{ora},100 INFO registrazione avviata")
    assert s["dettatura_in_corso"]([]) is False  # nessuna app viva: niente da proteggere
    registro()
    (cartella / "TURNO_UTENTE").write_text("x")
    assert s["dettatura_in_corso"]([1]) is True


def test_istanze_non_conta_il_lanciatore(tmp_path, monkeypatch):
    comandi = {
        "11": "/Users/x/Applications/Voce LeaderAI.app/Contents/MacOS/Voce LeaderAI /v/bin/python /v/detta.py",
        "12": "/Library/Frameworks/Python.framework/Versions/3.14/Resources/Python.app/Contents/MacOS/Python /v/detta.py",
        "13": "/usr/bin/python3 /v/detta.py --permessi --solo-stato",
    }

    def esegui(args, **k):
        if args[0] == "pgrep":
            return types.SimpleNamespace(stdout="11\n12\n13\n")
        return types.SimpleNamespace(stdout=comandi[args[-1]])

    s = _spazio_voce(tmp_path, monkeypatch, subprocess=types.SimpleNamespace(run=esegui))
    assert s["istanze"]() == [12]


def test_il_passaggio_dalla_voce_a_mano_al_servizio_aspetta_i_permessi():
    testo = _codice_voce()
    assert "if vecchi and not caricato" in testo and "La Voce attuale resta accesa" in testo


def test_l_installer_crea_app_e_servizio_senza_lasciare_finestre():
    install = (MAC / "install.sh").read_text(encoding="utf-8")
    assert "voce_launcher.c" in install
    assert '"$APP_DIR/voce" permessi' in install and '"$APP_DIR/voce" riavvia' in install
    assert "nohup" not in install and 'exec "$PY" detta.py' not in install
    comando = (MAC / "Installa Voce.command").read_text(encoding="utf-8")
    assert '"$SCRIPT_DIR/install.sh"' in comando and "close w saving no" in comando, "la finestra si richiude da sola"
    assert install.count("close w saving no") == 1 and install.count("$CHIUSURA_FINESTRA") == 2
