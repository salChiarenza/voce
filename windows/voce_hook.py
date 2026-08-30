"""Hook Stop (opzionale): se la voce e' accesa, legge ad alta voce l'ultima risposta.

E' lo script che Claude Code / Codex chiamano quando l'agente finisce di rispondere,
quindi vive in un file a parte dall'app sempre accesa. Sta in piedi da solo: non
importa nulla dall'app, cosi' resta leggero e non carica audio/modelli.

Input su stdin (JSON):
- Claude Code: campo "transcript_path" -> ultimo messaggio dell'assistente dal JSONL.
- Codex: campo "last_assistant_message" -> usato direttamente.
Non deve mai bloccare l'agente: ogni errore esce in silenzio con exit 0.
"""
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
FLAG_VOICE_ON = BASE / "VOICE_ON"   # se esiste, la voce in uscita e' accesa
CFG_PATH = BASE / "config.json"
VOICE_APP_MARKERS = (
    "VoiceDettaturaMac",
    "VoiceDettaturaWindows",
    "/tools/voce/",
    "\\tools\\voce\\",
)


def unisci_config(default_path: str, current_path: str) -> None:
    """Aggiorna il prodotto senza azzerare dati personali e calibrazione."""
    default_file, current_file = Path(default_path), Path(current_path)
    defaults = json.loads(default_file.read_text(encoding="utf-8"))
    current = {}
    if current_file.exists():
        current = json.loads(current_file.read_text(encoding="utf-8"))
        shutil.copy2(current_file, current_file.with_name("config.pre-aggiornamento.json"))
    # I nuovi default aggiungono solo cio' che manca. Tutte le scelte gia'
    # presenti restano: voce, tasti, modello, detta pulito, ritardi,
    # glossario e calibrazione. Il profilo LeaderAI e' consigliato, non imposto.
    merged = dict(defaults)
    merged.update(current)
    if "brand" in defaults:
        merged["brand"] = defaults["brand"]
    current_file.parent.mkdir(parents=True, exist_ok=True)
    temp = current_file.with_suffix(".tmp")
    temp.write_text(json.dumps(merged, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temp.replace(current_file)


def _comando_hook() -> str:
    parti = [sys.executable, str(Path(__file__).resolve())]
    if os.name == "nt":
        return subprocess.list2cmdline(parti)
    return " ".join(shlex.quote(p) for p in parti)


def _e_hook_voce(command: str) -> bool:
    return "voce_hook.py" in command and any(marker in command for marker in VOICE_APP_MARKERS)


def _leggi_json(path: Path) -> dict:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Configurazione non valida: {path}")
    return data


def collega_hook(settings_path: Path) -> None:
    """Aggiunge il nostro Stop hook senza cancellare quelli gia' presenti."""
    data = _leggi_json(settings_path)
    hooks = data.setdefault("hooks", {})
    stops = hooks.setdefault("Stop", [])
    if not isinstance(stops, list):
        raise ValueError(f"Sezione hooks.Stop non valida: {settings_path}")
    puliti = []
    for gruppo in stops:
        if not isinstance(gruppo, dict) or not isinstance(gruppo.get("hooks"), list):
            puliti.append(gruppo)
            continue
        elementi = [
            h for h in gruppo["hooks"]
            if not (isinstance(h, dict) and _e_hook_voce(str(h.get("command", ""))))
        ]
        if elementi:
            nuovo = dict(gruppo)
            nuovo["hooks"] = elementi
            puliti.append(nuovo)
    puliti.append({"hooks": [{"type": "command", "command": _comando_hook(), "timeout": 10}]})
    hooks["Stop"] = puliti
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    if settings_path.exists():
        shutil.copy2(settings_path, settings_path.with_name(settings_path.name + ".pre-voce.bak"))
    settings_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def hook_collegato(settings_path: Path) -> bool:
    try:
        data = _leggi_json(settings_path)
    except Exception:
        return False
    for gruppo in data.get("hooks", {}).get("Stop", []):
        if not isinstance(gruppo, dict):
            continue
        for hook in gruppo.get("hooks", []):
            if isinstance(hook, dict) and str(Path(__file__).resolve()) in str(hook.get("command", "")):
                return True
    return False


def _agente_presente(nome: str) -> bool:
    return shutil.which(nome) is not None or (Path.home() / f".{nome}").exists()


def installa_hook_agenti() -> list[tuple[str, Path]]:
    home = Path.home()
    collegati: list[tuple[str, Path]] = []
    if _agente_presente("claude"):
        path = home / ".claude" / "settings.json"
        collega_hook(path)
        collegati.append(("Claude Code", path))
    if _agente_presente("codex"):
        path = home / ".codex" / "hooks.json"
        collega_hook(path)
        collegati.append(("Codex", path))
    if not collegati:
        raise RuntimeError("Non trovo Claude Code o Codex da collegare.")
    for nome, path in collegati:
        print(f"{nome}: configurazione voce scritta in {path}")
        if nome == "Codex":
            print("Codex: apri /hooks, verifica il comando Voce e concedi fiducia.")
    return collegati


def controlla_hook_agenti() -> bool:
    home = Path.home()
    trovati = []
    for nome, presente, path in (
        ("Claude Code", _agente_presente("claude"), home / ".claude" / "settings.json"),
        ("Codex", _agente_presente("codex"), home / ".codex" / "hooks.json"),
    ):
        if presente:
            ok = hook_collegato(path)
            stato = "configurato" if ok else "NON configurato"
            print(f"{nome}: {stato}")
            if nome == "Codex" and ok:
                print("Codex: la prova reale richiede fiducia da /hooks e una risposta letta ad alta voce.")
            trovati.append(ok)
    return bool(trovati) and all(trovati)


def voce_attiva() -> bool:
    return FLAG_VOICE_ON.exists()


def pulisci_per_voce(testo: str) -> str:
    testo = re.sub(r"```.*?```", " codice omesso. ", testo, flags=re.DOTALL)
    testo = re.sub(r"`([^`]*)`", r"\1", testo)
    testo = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", testo)
    testo = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", testo)
    testo = re.sub(r"https?://\S+", " ", testo)
    testo = re.sub(r"^#{1,6}\s*", "", testo, flags=re.MULTILINE)
    testo = re.sub(r"[*_]{1,3}([^*_\n]+)[*_]{1,3}", r"\1", testo)
    testo = re.sub(r"^\s*[-*•>]\s+", "", testo, flags=re.MULTILINE)
    return re.sub(r"\s+", " ", testo).strip()


def estrai_ultima_risposta(transcript_path: str) -> str:
    """Ultimo messaggio testuale dell'assistente da un transcript JSONL di Claude Code."""
    ultimo = ""
    with open(transcript_path, encoding="utf-8") as f:
        for riga in f:
            riga = riga.strip()
            if not riga:
                continue
            try:
                voce = json.loads(riga)
            except json.JSONDecodeError:
                continue
            if voce.get("type") != "assistant":
                continue
            contenuto = voce.get("message", {}).get("content", [])
            testi = [
                b.get("text", "")
                for b in contenuto
                if isinstance(b, dict) and b.get("type") == "text"
            ]
            if testi:
                ultimo = "\n".join(testi)
    return ultimo


def _ps_string(valore: str) -> str:
    """Stringa PowerShell letterale, sicura anche con apostrofi nel nome."""
    return "'" + valore.replace("'", "''") + "'"


def script_tts(rate: int, voice_name: str = "") -> str:
    """Script System.Speech: usa la voce italiana scelta, oppure la prima disponibile."""
    return (
        "$ErrorActionPreference='SilentlyContinue';"
        "Add-Type -AssemblyName System.Speech;"
        "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer;"
        "$wanted=" + _ps_string(voice_name) + ";"
        "$voices=@($s.GetInstalledVoices()|"
        "?{$_.Enabled -and $_.VoiceInfo.Culture.Name -like 'it*'});"
        "$v=$null;"
        "if($wanted){$v=$voices|?{$_.VoiceInfo.Name -eq $wanted}|select -First 1};"
        "if(-not $v){$v=$voices|select -First 1};"
        "if($v){$s.SelectVoice($v.VoiceInfo.Name)};"
        "$s.Volume=100;"
        "$s.Rate=" + str(int(rate)) + ";"
        "$t=[Console]::In.ReadToEnd();"
        "if($t){$s.Speak($t)}"
    )


def script_lista_voci() -> str:
    """Script PowerShell che restituisce in JSON le voci italiane installate."""
    return (
        "$ErrorActionPreference='Stop';"
        "Add-Type -AssemblyName System.Speech;"
        "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer;"
        "$s.GetInstalledVoices()|"
        "?{$_.Enabled -and $_.VoiceInfo.Culture.Name -like 'it*'}|"
        "%{[PSCustomObject]@{name=$_.VoiceInfo.Name;culture=$_.VoiceInfo.Culture.Name;"
        "gender=$_.VoiceInfo.Gender.ToString();age=$_.VoiceInfo.Age.ToString()}}|"
        "ConvertTo-Json -Compress"
    )


def voci_italiane() -> list[dict]:
    """Elenca le voci italiane installate; lista vuota se Windows non ne espone."""
    esito = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script_lista_voci()],
        capture_output=True, text=True, check=False,
    )
    if esito.returncode != 0 or not esito.stdout.strip():
        return []
    try:
        data = json.loads(esito.stdout)
    except json.JSONDecodeError:
        return []
    if isinstance(data, dict):
        return [data]
    return data if isinstance(data, list) else []


def seleziona_voce(nome: str) -> None:
    """Salva la voce scelta dal proprietario, dopo averla verificata tra le installate."""
    disponibili = {str(v.get("name", "")) for v in voci_italiane()}
    if nome not in disponibili:
        raise ValueError(f"Voce italiana non installata: {nome}")
    cfg = _leggi_json(CFG_PATH)
    cfg["voce_nome"] = nome
    CFG_PATH.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def parla(testo: str, voice_name: str | None = None, attendi: bool = False,
          tetto_sec: float | None = None) -> None:
    """Legge il testo con la voce italiana di Windows (System.Speech via PowerShell)."""
    testo = pulisci_per_voce(testo)
    if not testo:
        return
    try:
        cfg = json.loads(CFG_PATH.read_text(encoding="utf-8"))
        rate = int(cfg.get("voce_rate", 0))
        configurata = str(cfg.get("voce_nome", ""))
    except Exception:
        rate = 0
        configurata = ""
    script = script_tts(rate, configurata if voice_name is None else voice_name)
    p = subprocess.Popen(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        p.stdin.write(testo.encode("utf-8"))
        p.stdin.close()
        if attendi:
            try:
                p.wait(timeout=tetto_sec)
            except subprocess.TimeoutExpired:
                p.kill()  # voce incantata: non deve bloccare il lettore per sempre
    except Exception:
        pass


# --- una voce per volta: la lettura in corso si finisce, vince l'ultima ---
# Specchio del Mac (mac/parla.py e mac/voce_hook.py, 30/08/2026): l'evento di
# fine risposta puo' arrivare doppio a pochi millisecondi, e piu' risposte
# ravvicinate non devono sovrapporsi ne' troncarsi. Il doppione identico si
# scarta; il testo nuovo va in attesa e, se ne arrivano altri, vince l'ultimo.

FINESTRA_DOPPIONE_SEC = 8.0
ULTIMA_LETTURA = BASE / "ULTIMA_LETTURA"
LETTURA_PENDENTE = BASE / "LETTURA_PENDENTE"  # prossimo testo: vince l'ultimo
LETTORE_LOCK = BASE / "LETTORE_LOCK"          # lock del lettore unico (mai eliminato)

_fd_lock = None  # tenuto aperto dal lettore: il lock vive quanto il processo


def gia_letto_da_poco(testo: str) -> bool:
    """Vero se questo identico testo e' gia' stato mandato in lettura da poco."""
    import hashlib
    import time

    impronta = hashlib.sha1(testo.encode("utf-8")).hexdigest()
    adesso = time.time()
    try:
        precedente, istante = ULTIMA_LETTURA.read_text(encoding="utf-8").split(None, 1)
        doppione = precedente == impronta and (adesso - float(istante)) < FINESTRA_DOPPIONE_SEC
    except Exception:
        doppione = False  # nessuno stato leggibile: si legge, il silenzio e' peggio
    if not doppione:
        try:
            ULTIMA_LETTURA.write_text(f"{impronta} {adesso}", encoding="utf-8")
        except Exception:
            pass
    return doppione


def scrivi_pendente(testo: str, pendente: Path | None = None) -> None:
    """Deposita il testo in attesa in modo atomico: chi arriva dopo sovrascrive
    (vince l'ultimo), chi preleva non vede mai un file scritto a meta'."""
    pendente = pendente or LETTURA_PENDENTE
    provvisorio = pendente.with_name(f"{pendente.name}.{os.getpid()}.tmp")
    provvisorio.write_text(testo, encoding="utf-8")
    os.replace(provvisorio, pendente)


def prendi_pendente(pendente: Path | None = None) -> str | None:
    """Preleva il testo in attesa (None se non c'e'). Il prelievo e' un rename
    atomico: un deposito nello stesso istante non va mai perso."""
    pendente = pendente or LETTURA_PENDENTE
    in_corso = pendente.with_name(pendente.name + ".presa")
    try:
        os.replace(pendente, in_corso)
    except FileNotFoundError:
        return None
    testo = in_corso.read_text(encoding="utf-8")
    in_corso.unlink(missing_ok=True)
    return testo or None


def _blocca_esclusivo(fd) -> bool:
    """Lock esclusivo non bloccante, arbitrato dal kernel: si libera da solo
    alla morte del processo, comunque muoia (niente lock stantii, niente pid
    riusati). Su Windows msvcrt; altrove flock (i test girano anche su Mac).
    NIENTE os.kill su Windows: un segnale qualsiasi TERMINA il processo."""
    try:
        import msvcrt
    except ImportError:
        import fcntl
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            return False
    try:
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        return True
    except OSError:
        return False


def _prendi_lock() -> bool:
    """Un solo lettore per volta. Il file del lock non va mai eliminato: un
    lock su un file ricreato sarebbe un lock su un altro inode."""
    global _fd_lock
    fd = os.open(LETTORE_LOCK, os.O_CREAT | os.O_RDWR)
    if not _blocca_esclusivo(fd):
        os.close(fd)
        return False
    _fd_lock = fd
    return True


def _rilascia_lock() -> None:
    global _fd_lock
    if _fd_lock is not None:
        try:
            os.close(_fd_lock)  # chiudere rilascia il lock
        except OSError:
            pass
        _fd_lock = None


def _lettore_in_corsa() -> bool:
    """Vero se un lettore tiene il lock in questo momento (prova non
    bloccante, senza fidarsi di pid scritti su file)."""
    try:
        fd = os.open(LETTORE_LOCK, os.O_CREAT | os.O_RDWR)
    except OSError:
        return False  # non si sa: si prova a spawnare, decidera' il lock
    try:
        if not _blocca_esclusivo(fd):
            return True
        return False
    finally:
        os.close(fd)  # chiudere rilascia anche l'eventuale lock di prova


def lettore() -> None:
    """Legge l'attesa fino a svuotarla, una voce per volta, poi esce.
    Il tetto proporzionale al testo evita che una voce incantata tenga il
    lock per sempre e ammutolisca tutte le risposte successive."""
    while True:
        if not _prendi_lock():
            return  # c'e' gia' un lettore in corsa: leggera' lui
        try:
            while True:
                testo = prendi_pendente()
                if testo is None:
                    break
                parla(testo, attendi=True, tetto_sec=max(60, len(testo) // 4))
        finally:
            _rilascia_lock()
        if not LETTURA_PENDENTE.exists():
            return
        # un testo e' arrivato nell'attimo in cui uscivamo: un altro giro


def _avvia_lettore_se_serve() -> None:
    if _lettore_in_corsa():
        return  # il lettore in corsa passera' da solo al testo in attesa
    distacco = (  # sganciato dall'hook: sopravvive al suo timeout
        getattr(subprocess, "DETACHED_PROCESS", 0)
        | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        | getattr(subprocess, "CREATE_NO_WINDOW", 0)
    )
    subprocess.Popen(
        [sys.executable, str(Path(__file__).resolve()), "--lettore"],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=distacco,
    )


def metti_in_lettura(testo: str) -> None:
    """Deposita e torna subito: legge un lettore sganciato, senza troncare
    ne' sovrapporre la lettura eventualmente in corso."""
    testo = pulisci_per_voce(testo)
    if not testo:
        return
    scrivi_pendente(testo)
    _avvia_lettore_se_serve()


def main() -> None:
    if not voce_attiva():
        return
    try:
        dati = json.load(sys.stdin)
    except Exception:
        return
    testo = dati.get("last_assistant_message") or ""
    if not testo and dati.get("transcript_path"):
        try:
            testo = estrai_ultima_risposta(dati["transcript_path"])
        except Exception:
            return
    if testo:
        if gia_letto_da_poco(testo):
            return
        metti_in_lettura(testo)


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--merge-config":
        unisci_config(sys.argv[2], sys.argv[3])
    elif len(sys.argv) == 2 and sys.argv[1] == "--install-hooks":
        installa_hook_agenti()
    elif len(sys.argv) == 2 and sys.argv[1] == "--check-hooks":
        raise SystemExit(0 if controlla_hook_agenti() else 1)
    elif len(sys.argv) == 2 and sys.argv[1] == "--list-voices":
        print(json.dumps(voci_italiane(), ensure_ascii=False))
    elif len(sys.argv) == 3 and sys.argv[1] == "--set-voice":
        seleziona_voce(sys.argv[2])
        print(f"Voce scelta: {sys.argv[2]}")
    elif len(sys.argv) == 2 and sys.argv[1] == "--lettore":
        lettore()
    elif len(sys.argv) >= 2 and sys.argv[1] == "--test-voice":
        prova = sys.argv[2] if len(sys.argv) == 3 else None
        parla("Prova di Voce AI LeaderAI su Windows. Questo audio e' sintetico.", prova, attendi=True)
    else:
        main()
    sys.exit(0)
