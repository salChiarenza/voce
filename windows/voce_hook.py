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
import tempfile
from contextlib import contextmanager
from pathlib import Path

BASE = Path(__file__).resolve().parent
FLAG_VOICE_ON = BASE / "VOICE_ON"   # se esiste, la voce in uscita e' accesa
FLAG_TURNO_UTENTE = BASE / "TURNO_UTENTE"  # Sal sta ancora dettando/inviando
CFG_PATH = BASE / "config.json"
PID_FILE = BASE / "voce_pid"  # condiviso con lo stop dell'app
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


def pulisci_per_voce(testo):
    """Prepara l'ascolto integrale: pause, tabelle e riferimenti leggibili.

    Nessun riassunto o modello: si cambia soltanto la presentazione. Il
    risultato e' idempotente, anche se hook e lettore lo preparano entrambi.
    Come prima, il contenuto dei blocchi di codice non viene pronunciato.
    """
    def nome_file(percorso):
        percorso = percorso.strip().strip("<>")
        if percorso.startswith("file://"):
            percorso = percorso[7:]
        if not re.match(r"^(?:/|~/|[A-Za-z]:[\\/]|\\\\)", percorso):
            return percorso
        riga = re.search(r":(\d+)(?::(\d+))?$", percorso)
        posizione = ""
        if riga:
            posizione = ", riga " + riga[1]
            if riga[2]:
                posizione += ", colonna " + riga[2]
            percorso = percorso[:riga.start()]
        return re.split(r"[\\/]", percorso.rstrip("/\\"))[-1] + posizione

    def inline(riga):
        def link(m):
            etichetta, destinazione = m[1], m[2].strip().strip("<>")
            etichetta = nome_file(etichetta)
            file = nome_file(destinazione)
            if file != destinazione:
                if file.split(", riga ", 1)[0].casefold() == etichetta.casefold():
                    return file
                return etichetta + ", file " + file
            return etichetta

        riga = re.sub(r"!\[[^\]]*\]\((?:<[^>]*>|[^)\n]*)\)", "", riga)
        riga = re.sub(r"\[([^\]]+)\]\((<[^>\n]+>|[^)\n]+)\)", link, riga)
        riga = re.sub(r"(`+)(.*?)\1", lambda m: nome_file(m[2]), riga)
        # Conserva la punteggiatura dopo un URL: serve a sentire la pausa.
        riga = re.sub(
            r"https?://[^\s<>]+",
            lambda m: "collegamento" + m[0][len(m[0].rstrip(".,;:!?)]}")):],
            riga,
        )
        riga = re.sub(
            r"([\"'])((?:[A-Za-z]:[\\/]|\\\\|~?/)[A-Za-z_][^\"'\n]+)\1",
            lambda m: m[1] + nome_file(m[2]) + m[1], riga,
        )
        # Percorsi nudi senza spazi; quelli con spazi sono gia' gestiti nei
        # link e nel codice inline. La radice alfabetica esclude le date.
        riga = re.sub(
            r"(?<![\w:/\\])(?:[A-Za-z]:[\\/]|\\\\|~?/)[A-Za-z_][^\s<>\"'`]*",
            lambda m: nome_file(m[0].rstrip(".,;!?)]}"))
            + m[0][len(m[0].rstrip(".,;!?)]}")):],
            riga,
        )
        # I delimitatori interni alle parole (report_2026_09.md) sono dati.
        riga = re.sub(
            r"(?<!\w)(\*{1,3}|_{1,3})(?=\S)(.+?)(?<=\S)\1(?!\w)",
            r"\2", riga,
        )
        return re.sub(r"\s+", " ", riga).strip()

    def frase(riga):
        riga = riga.strip()
        if riga and riga.rstrip("\"'»)]}")[-1:] not in ".!?…,:;":
            riga += "."
        return riga

    def celle(riga):
        riga = riga.strip()
        if riga.startswith("|"):
            riga = riga[1:]
        if riga.endswith("|") and not riga.endswith("\\|"):
            riga = riga[:-1]
        return [c.strip().replace("\\|", "|") for c in re.split(r"(?<!\\)\|", riga)]

    # Una fence aperta protegge anche il codice incompleto; una fence di
    # altro tipo dentro il blocco non puo' chiuderla per errore.
    righe, fence = [], None
    for riga in testo.splitlines():
        if fence:
            if re.fullmatch(r"\s{0,3}" + re.escape(fence[0]) + "{" + str(len(fence)) + r",}\s*", riga):
                fence = None
            continue
        apertura = re.match(r"^\s{0,3}(`{3,}|~{3,})(.*)$", riga)
        if apertura:
            righe.extend(["", "codice omesso.", ""])
            if not apertura[2].rstrip().endswith(apertura[1]):
                fence = apertura[1]
            continue
        if re.match(r"^\s*:::writing\b", riga) or re.fullmatch(r"\s*:::\s*", riga):
            righe.append("")
            continue
        righe.append(riga)

    parti, paragrafo = [], []

    def chiudi_paragrafo(pausa=True):
        if paragrafo:
            contenuto = " ".join(paragrafo)
            parti.append(frase(contenuto) if pausa else contenuto)
            paragrafo.clear()

    i = 0
    while i < len(righe):
        riga = righe[i].strip()
        if i + 1 < len(righe) and "|" in riga:
            intestazioni, separatori = celle(riga), celle(righe[i + 1])
            if (len(intestazioni) == len(separatori)
                    and all(re.fullmatch(r":?-{3,}:?", c) for c in separatori)):
                chiudi_paragrafo()
                intestazioni = [inline(c) for c in intestazioni]
                i += 2
                inizio_dati = i
                while i < len(righe) and "|" in righe[i] and righe[i].strip():
                    valori = celle(righe[i])
                    lettura = []
                    for n in range(max(len(intestazioni), len(valori))):
                        etichetta = intestazioni[n] if n < len(intestazioni) else ""
                        etichetta = etichetta or f"Colonna {n + 1}"
                        valore = inline(valori[n]) if n < len(valori) else ""
                        lettura.append(etichetta + ": " + (valore or "vuoto"))
                    parti.append(frase("; ".join(lettura)))
                    i += 1
                if i == inizio_dati:
                    parti.append(frase("; ".join(intestazioni)))
                continue
        if not riga:
            chiudi_paragrafo()
        elif re.match(r"^(?:#{1,6}\s|[-*•>]\s|\d+[.)]\s)", riga):
            chiudi_paragrafo()
            riga = re.sub(r"^(?:#{1,6}|[-*•>])\s+", "", riga)
            riga = re.sub(r"\s+#+$", "", riga)
            parti.append(frase(inline(riga)))
        else:
            paragrafo.append(inline(riga))
        i += 1
    chiudi_paragrafo(pausa=False)
    return " ".join(p for p in parti if p)


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
        PID_FILE.write_text(str(p.pid), encoding="utf-8")
    except OSError:
        pass
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
    finally:
        if attendi:
            try:
                if PID_FILE.read_text(encoding="utf-8").strip() == str(p.pid):
                    PID_FILE.unlink()
            except OSError:
                pass


# --- una voce per volta, conversazioni separate e ultima risposta rileggibile ---
# Specchio del Mac: una sola risposta in attesa per ciascuna conversazione;
# fonti diverse restano in fila e si puo' scegliere quale ascoltare.

FINESTRA_DOPPIONE_SEC = 8.0
ULTIMA_LETTURA = BASE / "ULTIMA_LETTURA"
LETTURA_PENDENTE = BASE / "LETTURA_PENDENTE"  # coda e ultima risposta, private/locali
LETTORE_LOCK = BASE / "LETTORE_LOCK"          # lock del lettore unico (mai eliminato)

_fd_lock = None  # tenuto aperto dal lettore: il lock vive quanto il processo


def origine_risposta(dati: dict) -> dict:
    """Identita' Stop documentata: session_id; mai la cartella come task.
    I nomi sono descrizioni della fonte, non titoli inventati delle chat."""
    import hashlib
    import posixpath
    import uuid

    def stringa(chiave):
        valore = dati.get(chiave)
        return valore.strip() if isinstance(valore, str) else ""

    transcript = posixpath.normpath(stringa("transcript_path").replace("\\", "/"))
    if transcript == ".":
        transcript = ""
    identita = stringa("session_id")
    if not identita:
        identita = ("transcript:" + hashlib.sha256(transcript.encode()).hexdigest()
                    if transcript else "senza-origine:" + uuid.uuid4().hex)
    percorso = transcript.lower()
    if "/.codex/" in percorso or (stringa("model") and stringa("turn_id")):
        agente = "ChatGPT"
    elif "/.claude/" in percorso:
        agente = "Claude"
    else:
        agente = "Agente"
    return {"id": identita, "nome": agente}


def gia_letto_da_poco(testo: str, origine=None) -> bool:
    """Doppioni della stessa conversazione, anche con hook concorrenti."""
    import hashlib
    import time

    impronta = hashlib.sha1(testo.encode("utf-8")).hexdigest()
    adesso = time.time()
    identita = (origine or {}).get("id", "generale")
    fd = None
    try:
        fd = os.open(str(ULTIMA_LETTURA) + ".lock", os.O_CREAT | os.O_RDWR, 0o600)
        if os.name == "nt":
            import msvcrt
            if os.fstat(fd).st_size == 0:
                os.write(fd, b"0")
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_EX)
        try:
            dati = json.loads(ULTIMA_LETTURA.read_text(encoding="utf-8"))
            if not isinstance(dati, dict):
                dati = {}
        except (OSError, ValueError):
            dati = {}  # vecchio formato hash/orario: la prima risposta riparte
        precedente = dati.get(identita, {})
        if (isinstance(precedente, dict) and precedente.get("hash") == impronta
                and 0 <= adesso - float(precedente.get("tempo", 0)) < FINESTRA_DOPPIONE_SEC):
            return True
        dati = {k: v for k, v in dati.items() if isinstance(v, dict)
                and isinstance(v.get("tempo"), (int, float))
                and 0 <= adesso - v["tempo"] < FINESTRA_DOPPIONE_SEC}
        dati[identita] = {"hash": impronta, "tempo": adesso}
        dati = dict(sorted(dati.items(), key=lambda x: x[1]["tempo"])[-32:])
        temporaneo = ULTIMA_LETTURA.with_name(ULTIMA_LETTURA.name + f".{os.getpid()}.tmp")
        try:
            with open(os.open(temporaneo, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600),
                      "w", encoding="utf-8") as f:
                json.dump(dati, f, ensure_ascii=False)
            os.replace(temporaneo, ULTIMA_LETTURA)
        finally:
            temporaneo.unlink(missing_ok=True)
    except Exception:
        return False  # un errore della guardia non deve cancellare la risposta
    finally:
        if fd is not None:
            os.close(fd)
    return False


def _stato_vuoto():
    return {"versione": 1, "sequenza": 0, "preferita": None,
            "fonti": {}, "ultima": None, "ripeti": None}


def _origine(origine=None):
    origine = origine if isinstance(origine, dict) else {}
    identita = str(origine.get("id") or "generale").strip()[:512] or "generale"
    nome = " ".join(str(origine.get("nome") or "").split())[:120]
    return {"id": identita, "nome": nome}


def _carica_stato(pendente):
    try:
        testo = pendente.read_text(encoding="utf-8")
    except FileNotFoundError:
        return _stato_vuoto()
    if not testo.strip():
        return _stato_vuoto()
    try:
        stato = json.loads(testo)
    except (ValueError, TypeError):
        stato = None
    if isinstance(stato, dict) and "versione" in stato:
        if stato.get("versione") != 1 or not isinstance(stato.get("fonti"), dict):
            return _stato_vuoto()  # mai leggere ad alta voce uno stato incompatibile
        return stato
    # Aggiornamento dalla vecchia coda, che conteneva solo testo piano.
    stato = _stato_vuoto()
    _deposita(stato, testo, _origine())
    return stato


@contextmanager
def _stato_protetto(pendente=None):
    """Transazione tra hook, pannello e lettore. Il lock e' su un file stabile;
    il JSON si sostituisce atomicamente, senza esporre testi o file parziali.
    Il medesimo protocollo viene specchiato su Windows con msvcrt."""
    pendente = Path(pendente or LETTURA_PENDENTE)
    lock = pendente.with_name(pendente.name + ".lock")
    fd = os.open(lock, os.O_CREAT | os.O_RDWR, 0o600)
    temporaneo = None
    bloccato = False
    try:
        os.chmod(lock, 0o600)
        if os.name == "nt":
            import msvcrt
            if os.fstat(fd).st_size == 0:
                os.write(fd, b"0")
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_EX)
        bloccato = True
        stato = _carica_stato(pendente)
        prima = json.dumps(stato, ensure_ascii=False)
        yield stato
        dopo = json.dumps(stato, ensure_ascii=False)
        if dopo != prima:
            out_fd, temporaneo = tempfile.mkstemp(
                prefix=pendente.name + ".", suffix=".tmp", dir=pendente.parent,
            )
            with os.fdopen(out_fd, "w", encoding="utf-8") as output:
                output.write(dopo)
            os.replace(temporaneo, pendente)
            temporaneo = None
    finally:
        if temporaneo:
            Path(temporaneo).unlink(missing_ok=True)
        if bloccato:
            if os.name == "nt":
                import msvcrt
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def _deposita(stato, testo, origine):
    identita = origine["id"]
    fonti = stato["fonti"]
    precedente = fonti.get(identita, {})
    stato["sequenza"] += 1
    ordine = precedente.get("ordine") if precedente.get("in_attesa") else stato["sequenza"]
    fonti[identita] = {
        "nome": origine["nome"] or precedente.get("nome", ""),
        "testo": testo, "in_attesa": True, "ordine": ordine,
        "aggiornata": stato["sequenza"],
    }
    while len(fonti) > 8:
        # Prima le storie gia' ascoltate, poi l'attesa piu' vecchia.
        # La scelta esplicita dell'utente non sparisce per nuovi arrivi.
        eliminabile = min(
            (i for i in fonti if i not in (identita, stato.get("preferita"))),
            key=lambda i: (bool(fonti[i].get("in_attesa")), fonti[i]["aggiornata"]),
        )
        del fonti[eliminabile]


def scrivi_pendente(testo, pendente=None, origine=None):
    """Una sola ultima risposta per conversazione; fonti diverse restano in fila."""
    if not isinstance(testo, str) or not testo.strip():
        return
    with _stato_protetto(pendente) as stato:
        _deposita(stato, testo, _origine(origine))


def _prossima(stato):
    preferita = stato.get("preferita")
    ripeti = stato.get("ripeti")
    if ripeti and (preferita is None or ripeti["id"] == preferita):
        return ripeti, True
    candidati = [
        (identita, fonte) for identita, fonte in stato["fonti"].items()
        if fonte.get("in_attesa") and (
            preferita is None or identita == preferita or identita == "generale"
        )  # gli annunci dell'app passano anche mentre si segue una conversazione
    ]
    if not candidati:
        return None, False
    identita, fonte = min(candidati, key=lambda coppia: coppia[1]["ordine"])
    return {"id": identita, "nome": fonte["nome"], "testo": fonte["testo"]}, False


def prendi_pendente(pendente=None, con_origine=False):
    """Preleva una lettura consentita dalla selezione e ne conserva il recupero."""
    with _stato_protetto(pendente) as stato:
        risposta, ripetizione = _prossima(stato)
        if risposta is None:
            return None
        if ripetizione:
            stato["ripeti"] = None
            fonte = stato["fonti"].get(risposta["id"])
            if fonte and fonte.get("testo") == risposta["testo"]:
                fonte["in_attesa"] = False  # stessa risposta, una sola lettura
        else:
            stato["fonti"][risposta["id"]]["in_attesa"] = False
        # Gli annunci generali dei toggle non sostituiscono l'ultima risposta
        # di un agente. Le chiamate legacy mantengono comunque il recupero.
        ultima = stato.get("ultima")
        if risposta["id"] != "generale" or not ultima or ultima["id"] == "generale":
            stato["ultima"] = dict(risposta)
        return dict(risposta) if con_origine else risposta["testo"]


def ha_pendenti(pendente=None):
    """Vero solo per letture ammesse: il file resta anche a coda svuotata."""
    with _stato_protetto(pendente) as stato:
        return _prossima(stato)[0] is not None


def svuota_pendenti(pendente=None):
    """Barge-in/stop: cancella l'attesa, conserva cronologia e selezione."""
    with _stato_protetto(pendente) as stato:
        for fonte in stato["fonti"].values():
            fonte["in_attesa"] = False
        stato["ripeti"] = None


def _da_rileggere(stato):
    preferita = stato.get("preferita")
    if preferita is not None:
        fonte = stato["fonti"].get(preferita)
        if fonte and fonte.get("testo"):
            return {"id": preferita, "nome": fonte["nome"], "testo": fonte["testo"]}
        return None
    return stato.get("ultima")


def elenco_conversazioni():
    with _stato_protetto() as stato:
        conversazioni = [
            {"id": identita, "nome": fonte["nome"],
             "anteprima": " ".join(fonte["testo"].split())[:100],
             "in_attesa": bool(fonte.get("in_attesa"))}
            for identita, fonte in sorted(
                stato["fonti"].items(), key=lambda coppia: coppia[1]["aggiornata"], reverse=True,
            )
            if identita != "generale"  # annunci di sistema, non conversazioni
        ]
        return {"preferita": stato.get("preferita"), "conversazioni": conversazioni,
                "rileggibile": bool(_da_rileggere(stato))}


def scegli_conversazione(identita):
    """Vale dalla prossima lettura; non interrompe mai l'audio in corso."""
    with _stato_protetto() as stato:
        if identita is not None and identita not in stato["fonti"]:
            return False
        stato["preferita"] = identita
        if stato.get("ripeti") and identita is not None and stato["ripeti"]["id"] != identita:
            stato["ripeti"] = None
        da_avviare = _prossima(stato)[0] is not None
    if da_avviare:
        _avvia_lettore_se_serve()
    return True


def rileggi_ultima():
    """La conversazione scelta, oppure l'ultima risposta effettivamente iniziata.
    La ripetizione ha un posto separato: una nuova risposta non va persa."""
    with _stato_protetto() as stato:
        risposta = _da_rileggere(stato)
        if not risposta:
            return False
        stato["ripeti"] = dict(risposta)
    _avvia_lettore_se_serve()
    return True


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
    precedente = None
    while True:
        if not _prendi_lock():
            return  # c'e' gia' un lettore in corsa: leggera' lui
        try:
            while True:
                if FLAG_TURNO_UTENTE.exists():
                    svuota_pendenti()
                    return
                risposta = prendi_pendente(con_origine=True)
                if risposta is None:
                    break
                testo = risposta["testo"]
                if risposta["nome"] and risposta["id"] != precedente:
                    nome = risposta["nome"].rstrip(".:!?")
                    testo = f"{nome}.\n\n{testo}"
                precedente = risposta["id"]
                parla(testo, attendi=True, tetto_sec=max(60, len(testo) // 4))
        finally:
            _rilascia_lock()
        if not ha_pendenti():
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


def metti_in_lettura(testo: str, origine=None) -> None:
    """Deposita e torna subito: legge un lettore sganciato, senza troncare
    ne' sovrapporre la lettura eventualmente in corso."""
    if FLAG_TURNO_UTENTE.exists():
        svuota_pendenti()
        return
    testo = pulisci_per_voce(testo)
    if not testo:
        return
    scrivi_pendente(testo, origine=origine)
    if ha_pendenti():
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
        origine = origine_risposta(dati)
        if gia_letto_da_poco(testo, origine):
            return
        metti_in_lettura(testo, origine=origine)


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
    elif len(sys.argv) == 2 and sys.argv[1] == "--rileggi":
        raise SystemExit(0 if rileggi_ultima() else 1)
    elif len(sys.argv) == 2 and sys.argv[1] == "--conversazioni":
        print(json.dumps(elenco_conversazioni(), ensure_ascii=False, indent=2))
    elif len(sys.argv) == 3 and sys.argv[1] == "--segui":
        fonte = None if sys.argv[2] == "tutte" else sys.argv[2]
        raise SystemExit(0 if scegli_conversazione(fonte) else 1)
    elif len(sys.argv) >= 2 and sys.argv[1] == "--test-voice":
        prova = sys.argv[2] if len(sys.argv) == 3 else None
        parla("Prova di Voce AI LeaderAI su Windows. Questo audio e' sintetico.", prova, attendi=True)
    else:
        main()
    sys.exit(0)
