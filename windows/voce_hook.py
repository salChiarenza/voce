"""Hook Stop (opzionale): se la voce e' accesa, legge ad alta voce l'ultima risposta.

E' lo script che Claude Code / Codex chiamano quando l'agente finisce di rispondere,
quindi vive in un file a parte dall'app sempre accesa. Sta in piedi da solo: non
importa nulla dall'app, cosi' resta leggero e non carica audio/modelli.

Input su stdin (JSON):
- Claude Code: campo "transcript_path" -> ultimo messaggio dell'assistente dal JSONL.
- Codex: campo "last_assistant_message" -> usato direttamente.
Non deve mai bloccare l'agente: ogni errore esce con exit 0, ma lascia una riga
nel registro (`voice_hook.log`): un gancio che non parte e uno che non ha niente
da leggere non devono sembrare la stessa cosa.
"""
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

BASE = Path(__file__).resolve().parent
FLAG_VOICE_ON = BASE / "VOICE_ON"   # se esiste, la voce in uscita e' accesa
FLAG_TURNO_UTENTE = BASE / "TURNO_UTENTE"  # Sal sta ancora dettando/inviando
CFG_PATH = BASE / "config.json"
PID_FILE = BASE / "voce_pid"  # condiviso con lo stop dell'app
LOG_GANCIO = BASE / "voice_hook.log"  # una riga a ogni fine risposta (file a parte: l'app ruota il suo)
TETTO_LOG_GANCIO = 256 * 1024
VOICE_APP_MARKERS = (
    "VoiceDettaturaMac",
    "VoiceDettaturaWindows",
    "/tools/voce/",
    "\\tools\\voce\\",
)


def traccia(messaggio: str) -> None:
    """Una riga nel registro del gancio a ogni fine risposta (gemella del Mac).

    Senza questa riga un gancio che non parte e uno che parla sono identici
    visti da fuori: il silenzio si scambia per un guasto dell'audio (P-078: il
    gancio di Windows e' fallito 410 volte su 410 senza nessun segnale)."""
    try:
        from datetime import datetime

        istante = datetime.now().strftime("%Y-%m-%d %H:%M:%S,%f")[:-3]
        if LOG_GANCIO.exists() and LOG_GANCIO.stat().st_size > TETTO_LOG_GANCIO:
            righe = LOG_GANCIO.read_text(encoding="utf-8", errors="replace").splitlines()
            LOG_GANCIO.write_text("\n".join(righe[len(righe) // 2:]) + "\n", encoding="utf-8")
        with open(LOG_GANCIO, "a", encoding="utf-8") as registro:
            registro.write(f"{istante} INFO voce agenti: {messaggio}\n")
    except Exception:
        pass  # il registro non deve mai fermare la risposta


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
    """Il comando come stringa di shell (Codex). Su Windows e' la forma nativa
    di CreateProcess/cmd: i percorsi senza spazi restano nudi, con le barre
    rovesciate. NON va bene per Claude Code, che lo lancia con Git Bash."""
    parti = [sys.executable, str(Path(__file__).resolve())]
    if os.name == "nt":
        return subprocess.list2cmdline(parti)
    return " ".join(shlex.quote(p) for p in parti)


def _hook_diretto() -> dict:
    """La voce di Claude Code SENZA shell: `command` e' l'eseguibile, `args` i
    suoi argomenti, passati cosi' come sono (documentazione ufficiale, forma
    «exec», da Claude Code 2.1.139).

    P-078: su Windows Claude Code lancia i comandi con Git Bash (con PowerShell
    se Git Bash non c'e'). La stringa di `_comando_hook` ha i percorsi con le
    barre rovesciate e senza virgolette, e Git Bash le toglie: il gancio non e'
    mai partito, 410 volte su 410, senza nessun segnale. Senza shell non c'e'
    niente da togliere, in nessuna delle due."""
    return {
        "type": "command",
        "command": sys.executable,
        "args": [str(Path(__file__).resolve())],
        "timeout": 10,
    }


def _comando_completo(hook: dict) -> str:
    """Il comando di un hook come testo, anche nella forma diretta (command + args)."""
    parti = [str(hook.get("command", ""))]
    argomenti = hook.get("args")
    if isinstance(argomenti, list):
        parti.extend(str(a) for a in argomenti)
    return " ".join(parti)


def _e_hook_voce(command: str, mio: str = "") -> bool:
    """E' un gancio di Voce: `voce_hook.py` in una cartella di Voce, oppure
    esattamente questo file (`mio`, anche se la cartella ha un altro nome)."""
    return "voce_hook.py" in command and (
        any(marker in command for marker in VOICE_APP_MARKERS) or bool(mio and mio in command)
    )


def _leggi_json(path: Path) -> dict:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Configurazione non valida: {path}")
    return data


def collega_hook(settings_path: Path, diretto: bool = False) -> None:
    """Aggiunge il nostro Stop hook senza cancellare quelli gia' presenti.
    `diretto=True` scrive la forma senza shell (Claude Code, vedi _hook_diretto);
    ogni vecchia voce di Voce, in qualunque forma, viene sostituita."""
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
            if not (isinstance(h, dict) and _e_hook_voce(_comando_completo(h), str(Path(__file__).resolve())))
        ]
        if elementi:
            nuovo = dict(gruppo)
            nuovo["hooks"] = elementi
            puliti.append(nuovo)
    nostro = _hook_diretto() if diretto else {"type": "command", "command": _comando_hook(), "timeout": 10}
    puliti.append({"hooks": [nostro]})
    hooks["Stop"] = puliti
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    if settings_path.exists():
        shutil.copy2(settings_path, settings_path.with_name(settings_path.name + ".pre-voce.bak"))
    settings_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def trova_hook_voce(settings_path: Path) -> dict | None:
    """La voce di questo Voce nello Stop hook del file, o None. Riconosce la
    forma a stringa (`command`) e quella diretta (`command` + `args`)."""
    try:
        data = _leggi_json(settings_path)
    except Exception:
        return None
    mio = str(Path(__file__).resolve())
    for gruppo in data.get("hooks", {}).get("Stop", []):
        if not isinstance(gruppo, dict):
            continue
        for hook in gruppo.get("hooks", []):
            if isinstance(hook, dict) and mio in _comando_completo(hook):
                return hook
    return None


def hook_collegato(settings_path: Path) -> bool:
    return trova_hook_voce(settings_path) is not None


def _agente_presente(nome: str) -> bool:
    return shutil.which(nome) is not None or (Path.home() / f".{nome}").exists()


def installa_hook_agenti() -> list[tuple[str, Path]]:
    home = Path.home()
    collegati: list[tuple[str, Path]] = []
    if _agente_presente("claude"):
        path = home / ".claude" / "settings.json"
        collega_hook(path, diretto=True)  # niente shell: Git Bash toglie le barre (P-078)
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


def _su_windows() -> bool:
    return os.name == "nt"


def _agenti_collegabili() -> list[tuple[str, bool, Path]]:
    home = Path.home()
    return [
        ("Claude Code", _agente_presente("claude"), home / ".claude" / "settings.json"),
        ("Codex", _agente_presente("codex"), home / ".codex" / "hooks.json"),
    ]


PROVA_ESECUZIONE_SEC = 10  # lo stesso tetto che l'agente da' al gancio (timeout 10 nella sua configurazione)
VERSIONE_MINIMA_GANCIO_DIRETTO = (2, 1, 139)  # Claude Code: da qui il gancio ha `args` (forma senza shell)


def versione_claude_code() -> tuple[int, int, int] | None:
    """La versione di Claude Code installata (`claude --version`), o None se non
    si legge (non nel PATH, o non risponde): senza versione non si boccia nessuno."""
    percorso = shutil.which("claude")
    if not percorso:
        return None
    try:
        esito = subprocess.run(
            [percorso, "--version"], stdin=subprocess.DEVNULL, capture_output=True,
            text=True, errors="replace", timeout=PROVA_ESECUZIONE_SEC,
        )
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    trovata = re.search(r"(\d+)\.(\d+)\.(\d+)", esito.stdout or "")
    return tuple(int(n) for n in trovata.groups()) if trovata else None


def prova_esecuzione_hook(hook: dict, diretto_richiesto: bool = False) -> tuple[bool, str]:
    """Avvia DAVVERO il comando scritto nella configurazione, come lo avvierebbe
    l'agente, con `--ping`: (funziona, dettaglio).

    P-078: «configurato» e «funziona» sono due cose. Il vecchio controllo
    cercava il percorso nel file e diceva sempre di si, anche per un comando
    che Git Bash non riusciva a lanciare. Qui il comando parte: nella forma
    diretta senza shell (come fa Claude Code), nella forma a stringa con la
    shell del sistema. `diretto_richiesto`: Claude Code su Windows; un comando
    a stringa li' non va bene qualunque cosa risponda la shell di prova."""
    argomenti = hook.get("args")
    if isinstance(argomenti, list):
        comando = [str(hook.get("command", "")), *[str(a) for a in argomenti], "--ping"]
        con_shell = False
    elif diretto_richiesto:
        return False, ("il comando e' scritto per una shell: Claude Code su Windows usa Git Bash, "
                       "che toglie le barre rovesciate dei percorsi; riesegui --install-hooks")
    else:
        comando = str(hook.get("command", "")) + " --ping"
        con_shell = True
    try:
        esito = subprocess.run(
            comando, shell=con_shell, stdin=subprocess.DEVNULL, capture_output=True,
            text=True, errors="replace", timeout=PROVA_ESECUZIONE_SEC,
        )
    except (OSError, ValueError, subprocess.SubprocessError) as errore:
        return False, f"non parte: {errore}"
    if esito.returncode == 0 and "VOCE_HOOK_OK" in esito.stdout:
        return True, "ok"
    righe = (esito.stderr or esito.stdout or "").strip().splitlines()
    return False, f"codice {esito.returncode}: {righe[0][:200] if righe else 'nessuna risposta'}"


def controlla_hook_agenti() -> bool:
    trovati = []
    for nome, presente, path in _agenti_collegabili():
        if not presente:
            continue
        hook = trova_hook_voce(path)
        if hook is None:
            print(f"{nome}: NON configurato")
            trovati.append(False)
            continue
        funziona, dettaglio = prova_esecuzione_hook(
            hook, diretto_richiesto=(nome == "Claude Code" and _su_windows()),
        )
        versione = versione_claude_code() if (nome == "Claude Code" and "args" in hook) else None
        if funziona and versione is not None and versione < VERSIONE_MINIMA_GANCIO_DIRETTO:
            # una Claude Code che non conosce `args` lancerebbe `command` da solo, con la shell:
            # il comando parte nella nostra prova e non nella sua (stesso silenzio di P-078)
            funziona = False
            dettaglio = (f"Claude Code {'.'.join(map(str, versione))} non conosce il collegamento senza shell "
                         f"(serve {'.'.join(map(str, VERSIONE_MINIMA_GANCIO_DIRETTO))} o piu' recente): aggiornalo")
        if funziona:
            print(f"{nome}: configurato e funzionante")
            if nome == "Codex":
                print("Codex: la prova reale richiede fiducia da /hooks e una risposta letta ad alta voce.")
        else:
            print(f"{nome}: configurato ma NON FUNZIONA ({dettaglio})")
        trovati.append(funziona)
    return bool(trovati) and all(trovati)


def avviso_collegamento() -> str:
    """Una frase da dire a voce quando la voce si accende, se il collegamento
    con gli agenti non funziona; stringa vuota se va tutto bene (P-078: un
    guasto che dura due mesi senza che nessuno lo sappia non deve ripetersi).
    Un agente presente ma mai collegato lo dice `--check-hooks`: qui si guarda
    cio' che e' collegato e non parte."""
    guasti, collegati = [], 0
    for nome, presente, path in _agenti_collegabili():
        if not presente:
            continue
        hook = trova_hook_voce(path)
        if hook is None:
            continue
        collegati += 1
        funziona, _ = prova_esecuzione_hook(
            hook, diretto_richiesto=(nome == "Claude Code" and _su_windows()),
        )
        if not funziona:
            guasti.append(nome)
    if guasti:
        return (f"Attenzione: il collegamento con {' e '.join(guasti)} non funziona, "
                "le risposte non verranno lette. Chiedi al tuo agente di ripararlo.")
    if not collegati:
        return ("Attenzione: Voce non e' collegata a nessun agente, le risposte non verranno "
                "lette. Chiedi al tuo agente di collegarla.")
    return ""


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


TETTO_ATTESA_ACCODATA = 8000  # caratteri: oltre, i paragrafi piu' vecchi dell'attesa cadono


def _accoda(precedente, testo):
    """Il testo nuovo dopo quello ancora in attesa della stessa fonte, in ordine.
    Serve alla lettura mentre l'agente scrive: i blocchi arrivano uno dopo l'altro
    e non devono sostituirsi (la risposta finale, invece, sostituisce l'attesa)."""
    unito = precedente["testo"] + "\n\n" + testo
    while len(unito) > TETTO_ATTESA_ACCODATA and "\n\n" in unito:
        unito = unito.split("\n\n", 1)[1]
    return unito


def _deposita(stato, testo, origine, accoda=False):
    identita = origine["id"]
    fonti = stato["fonti"]
    precedente = fonti.get(identita, {})
    if accoda and precedente.get("in_attesa") and precedente.get("testo"):
        testo = _accoda(precedente, testo)
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


def scrivi_pendente(testo, pendente=None, origine=None, accoda=False):
    """Una sola ultima risposta per conversazione; fonti diverse restano in fila.
    Con `accoda` il testo si aggiunge a quello ancora in attesa della stessa fonte."""
    if not isinstance(testo, str) or not testo.strip():
        return
    with _stato_protetto(pendente) as stato:
        _deposita(stato, testo, _origine(origine), accoda=accoda)


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


def metti_in_lettura(testo: str, origine=None, accoda: bool = False) -> None:
    """Deposita e torna subito: legge un lettore sganciato, senza troncare
    ne' sovrapporre la lettura eventualmente in corso."""
    if FLAG_TURNO_UTENTE.exists():
        svuota_pendenti()
        return
    testo = pulisci_per_voce(testo)
    if not testo:
        return
    scrivi_pendente(testo, origine=origine, accoda=accoda)
    if ha_pendenti():
        _avvia_lettore_se_serve()


# --- Voce insieme alla scrittura (02/10/2026, da un'idea di una cliente) ---
# Il gancio di fine risposta legge solo l'ultimo messaggio, a lavoro finito: un testo
# scritto prima di un lavoro lungo restava muto fino alla fine. Claude Code scrive
# ogni blocco di testo in una riga del suo registro appena e' completo: l'app Voce
# (voice_dettatura_windows.py) segue i registri e legge ogni blocco subito. Il gancio resta com'e'
# e per non leggere due volte lo stesso testo i due si accordano su `LETTI_DAL_REGISTRO`.
FINESTRA_LETTO_SEC = 120.0
LETTI_PER_SESSIONE = 20
SOGLIA_TESTO_LUNGO = 40  # sotto questa lunghezza ("Si'.", "Fatto.") il doppione e' solo il testo identico


def cartella_registri_claude() -> Path:
    """Dove Claude Code scrive i registri delle chat (CLAUDE_CONFIG_DIR se impostata)."""
    base = os.environ.get("CLAUDE_CONFIG_DIR")
    return (Path(base) if base else Path.home() / ".claude") / "projects"


def _compatta(testo):
    return " ".join(str(testo or "").split())


def _gia_nei_letti(norma, letti):
    return any(norma == l or (len(norma) >= SOGLIA_TESTO_LUNGO and norma in l) for l in letti)


def reclama_lettura(sessione, testo, adesso=None):
    """Vero se questo testo di questa conversazione lo leggo io; falso se l'ha gia'
    letto l'altro (il gancio o il seguitore del registro) da meno di due minuti.
    Il primo che arriva lo segna: il secondo lo trova e tace."""
    norma = _compatta(testo)
    if not norma:
        return False
    adesso = time.time() if adesso is None else adesso
    registro = BASE / "LETTI_DAL_REGISTRO"
    fd = None
    try:
        fd = os.open(str(registro) + ".lock", os.O_CREAT | os.O_RDWR, 0o600)
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
            dati = json.loads(registro.read_text(encoding="utf-8"))
            if not isinstance(dati, dict):
                dati = {}
        except (OSError, ValueError):
            dati = {}
        dati = {
            k: [v for v in voci if isinstance(v, list) and len(v) == 2 and 0 <= adesso - v[0] < FINESTRA_LETTO_SEC]
            for k, voci in dati.items() if isinstance(voci, list)
        }
        dati = {k: v for k, v in dati.items() if v}
        letti = [v[1] for v in dati.get(sessione, [])]
        if _gia_nei_letti(norma, letti):
            return False
        dati.setdefault(sessione, []).append([adesso, norma])
        dati[sessione] = dati[sessione][-LETTI_PER_SESSIONE:]
        dati = dict(sorted(dati.items(), key=lambda x: x[1][-1][0])[-16:])
        temporaneo = registro.with_name(registro.name + f".{os.getpid()}.tmp")
        try:
            with open(os.open(temporaneo, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600),
                      "w", encoding="utf-8") as f:
                json.dump(dati, f, ensure_ascii=False)
            os.replace(temporaneo, registro)
        finally:
            temporaneo.unlink(missing_ok=True)
        return True
    except Exception:
        return True  # un errore dell'accordo non deve togliere la voce
    finally:
        if fd is not None:
            os.close(fd)


def blocco_di_riga(grezza):
    """Il testo di una riga del registro che e' un blocco scritto dall'assistente
    principale (mai un subagente, mai un messaggio di sistema), altrimenti None."""
    try:
        riga = json.loads(grezza)
    except ValueError:
        return None
    if not isinstance(riga, dict) or riga.get("type") != "assistant" or riga.get("isSidechain") \
            or riga.get("isApiErrorMessage"):
        return None
    messaggio = riga.get("message", {})
    if not isinstance(messaggio, dict) or messaggio.get("model") == "<synthetic>":
        return None
    contenuto = messaggio.get("content", [])
    if not isinstance(contenuto, list):
        return None
    testo = "\n".join(b.get("text", "") for b in contenuto
                      if isinstance(b, dict) and b.get("type") == "text").strip()
    return testo or None


def sessione_interattiva(percorso, righe_max=400):
    """Falso per le chat di sfondo: automazioni (`sdk-cli`) e attivita' pianificate.
    La voce legge quello che l'agente scrive a Sal, non il lavoro che fa da solo di notte."""
    try:
        with open(percorso, encoding="utf-8", errors="replace") as f:
            for _ in range(righe_max):
                grezza = f.readline()
                if not grezza:
                    break
                try:
                    riga = json.loads(grezza)
                except ValueError:
                    continue
                if not isinstance(riga, dict):
                    continue
                if str(riga.get("entrypoint") or "").startswith("sdk"):
                    return False
                if riga.get("type") == "user" and not riga.get("isMeta"):
                    contenuto = riga.get("message", {}).get("content")
                    if isinstance(contenuto, list):
                        contenuto = " ".join(p.get("text", "") for p in contenuto
                                             if isinstance(p, dict) and p.get("type") == "text")
                    return not (isinstance(contenuto, str) and contenuto.lstrip().startswith("<scheduled-task"))
    except OSError:
        pass
    return True


class SeguiRegistro:
    """Segue i registri delle chat di Claude Code e legge ogni blocco di testo appena e' completo."""

    ETA_MAX_FILE_SEC = 6 * 3600   # una chat ferma da sei ore non si guarda
    RINNOVO_ELENCO_SEC = 3.0

    def __init__(self, cartella=None, leggi=None, attiva=None, traccia_fn=None):
        self.cartella = Path(cartella) if cartella else cartella_registri_claude()
        self.leggi = leggi or (lambda testo, origine: metti_in_lettura(testo, origine=origine, accoda=True))
        self.attiva = attiva or voce_attiva
        self.traccia = traccia_fn or traccia
        self.posizioni = {}   # percorso -> (offset, riga incompleta)
        self.interattive = {}  # percorso -> bool
        self._ultimo_elenco = 0.0
        self._file = []
        self._primo_giro = True

    def _elenco(self, ora):
        if ora - self._ultimo_elenco < self.RINNOVO_ELENCO_SEC and not self._primo_giro:
            return self._file
        self._ultimo_elenco = ora
        recenti = []
        try:
            for p in self.cartella.glob("*/*.jsonl"):
                try:
                    if time.time() - p.stat().st_mtime < self.ETA_MAX_FILE_SEC:
                        recenti.append(p)
                except OSError:
                    pass
        except OSError:
            pass
        for p in recenti:
            if p not in self.posizioni:
                # chat gia' aperte all'avvio: dalla fine (il passato non si rilegge);
                # chat nate dopo: dall'inizio
                try:
                    self.posizioni[p] = (p.stat().st_size if self._primo_giro else 0, b"")
                except OSError:
                    pass
        self._primo_giro = False
        self._file = [p for p in recenti if p in self.posizioni]
        return self._file

    def giro(self, ora=None):
        """Un passaggio sui registri: legge i blocchi nuovi. Restituisce quanti ne ha dati alla voce."""
        ora = time.monotonic() if ora is None else ora
        letti = 0
        for p in self._elenco(ora):
            try:
                dim = p.stat().st_size
            except OSError:
                continue
            off, resto = self.posizioni[p]
            if dim < off:
                off, resto = 0, b""
            if dim == off:
                continue
            try:
                with open(p, "rb") as f:
                    f.seek(off)
                    dati = resto + f.read(dim - off)
            except OSError:
                continue
            righe = dati.split(b"\n")
            resto = righe.pop()  # l'ultima puo' essere ancora a meta'
            self.posizioni[p] = (dim, resto)
            blocchi = [b for b in (blocco_di_riga(r.decode("utf-8", "ignore")) for r in righe if r.strip()) if b]
            if not blocchi or not self.attiva():
                continue  # voce spenta: si va avanti senza leggere, riaccesa non rilegge il passato
            if p not in self.interattive:
                self.interattive[p] = sessione_interattiva(p)
            if not self.interattive[p]:
                continue
            sessione = p.stem
            da_leggere = [b for b in blocchi if reclama_lettura(sessione, b)]
            if not da_leggere:
                continue
            testo = "\n\n".join(da_leggere)
            self.traccia(f"leggo mentre scrive: {len(da_leggere)} blocchi ({len(testo)} caratteri)")
            self.leggi(testo, {"id": sessione, "nome": "Claude"})
            letti += len(da_leggere)
        return letti

    def esegui(self, fermo, intervallo=0.4):
        """Il ciclo dell'app: un giro ogni `intervallo` secondi, finche' `fermo` (threading.Event) non scatta."""
        self.traccia("voce insieme alla scrittura: attiva")
        while not fermo.wait(intervallo):
            try:
                self.giro()
            except Exception as errore:
                self.traccia(f"errore nel seguire i registri: {errore!r}")
                fermo.wait(5)


def main() -> None:
    if not voce_attiva():
        traccia("voce spenta, non leggo")
        return
    try:
        dati = json.load(sys.stdin)
    except Exception:
        traccia("chiamata senza dati leggibili")
        return
    testo = dati.get("last_assistant_message") or ""
    sorgente = "messaggio diretto"
    if not testo and dati.get("transcript_path"):
        sorgente = "trascrizione"
        try:
            testo = estrai_ultima_risposta(dati["transcript_path"])
        except Exception:
            traccia("trascrizione illeggibile")
            return
    if testo:
        origine = origine_risposta(dati)
        if gia_letto_da_poco(testo, origine):
            traccia(f"lettura doppia scartata ({len(testo)} caratteri, {sorgente})")
            return
        if not reclama_lettura(origine["id"], testo):
            traccia(f"gia' letta mentre veniva scritta ({len(testo)} caratteri)")
            return
        traccia(f"leggo {len(testo)} caratteri ({sorgente})")
        metti_in_lettura(testo, origine=origine)
    else:
        traccia(f"nessun testo da leggere ({sorgente})")


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--merge-config":
        unisci_config(sys.argv[2], sys.argv[3])
    elif len(sys.argv) == 2 and sys.argv[1] == "--install-hooks":
        installa_hook_agenti()
    elif len(sys.argv) == 2 and sys.argv[1] == "--check-hooks":
        raise SystemExit(0 if controlla_hook_agenti() else 1)
    elif len(sys.argv) == 2 and sys.argv[1] == "--ping":
        print("VOCE_HOOK_OK")  # prova che il comando scritto nella configurazione parte davvero
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
