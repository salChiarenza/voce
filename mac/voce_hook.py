"""Hook Stop: se la voce è attiva (flag VOICE_ON), legge ad alta voce l'ultima risposta.

Input su stdin (JSON):
- Claude Code e Codex: "last_assistant_message", con ripiego sul transcript.
- "session_id" identifica la conversazione anche nella stessa cartella.
Non deve mai bloccare l'agente: ogni errore esce in silenzio con exit 0.
"""
import json
import os
import plistlib
import shlex
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

from voce_lib import BASE, carica_config, voce_attiva, estrai_ultima_risposta
from parla import parla


def traccia(messaggio):
    """Riga nel registro di Voce a ogni fine risposta.

    Senza questa riga un hook che non parte e uno che parla sono identici visti
    da fuori: il silenzio si scambia per un guasto dell'audio (caso 01/08/2026,
    stessa lezione della corsia di pulizia che cadeva senza dirlo)."""
    try:
        from datetime import datetime

        istante = datetime.now().strftime("%Y-%m-%d %H:%M:%S,%f")[:-3]
        with open(BASE / "voce.log", "a", encoding="utf-8") as registro:
            registro.write(f"{istante} INFO voce agenti: {messaggio}\n")
    except Exception:
        pass  # il registro non deve mai fermare la risposta


VOICE_APP_MARKERS = (
    "VoiceDettaturaMac",
    "VoiceDettaturaWindows",
    "/tools/voce/",
    "\\tools\\voce\\",
)

PERSONAL_CONFIG_KEYS = (
    "glossario",
    "sostituzioni",
    "debug_dettature",
)
SHORTCUT_DB = Path.home() / "Library" / "Shortcuts" / "Shortcuts.sqlite"
SPEAK_TEXT_ACTION = "is.workflow.actions.speaktext"


def unisci_config(default_path: str, current_path: str) -> None:
    """Applica la fotocopia funzionale di Sal e conserva solo i dati personali.

    Tasti, voce, tempi, modalita' e soglie sono parte del prodotto Mac: un
    aggiornamento li riallinea ai default verificati. Glossario, sostituzioni
    apprese e scelta di log restano invece del proprietario.
    """
    default_file, current_file = Path(default_path), Path(current_path)
    defaults = json.loads(default_file.read_text(encoding="utf-8"))
    current = {}
    if current_file.exists():
        current = json.loads(current_file.read_text(encoding="utf-8"))
        shutil.copy2(current_file, current_file.with_name("config.pre-aggiornamento.json"))
    merged = dict(defaults)
    for key in PERSONAL_CONFIG_KEYS:
        if key in current:
            merged[key] = current[key]
    current_file.parent.mkdir(parents=True, exist_ok=True)
    temp = current_file.with_suffix(".tmp")
    temp.write_text(json.dumps(merged, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temp.replace(current_file)


def leggi_profilo_shortcut(
    db_path: Path = SHORTCUT_DB,
    shortcut_name: str = "Voce LeaderAI firmato",
) -> dict:
    """Legge in sola lettura voce, velocita' e tono del Comando Rapido vivo."""
    with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
        row = conn.execute(
            "SELECT Z_PK FROM ZSHORTCUT WHERE ZNAME = ?",
            (shortcut_name,),
        ).fetchone()
        if not row:
            raise RuntimeError(f"Comando Rapido assente: {shortcut_name}")
        data = conn.execute(
            "SELECT ZDATA FROM ZSHORTCUTACTIONS WHERE ZSHORTCUT = ?",
            (row[0],),
        ).fetchone()
    if not data:
        raise RuntimeError(f"Azioni assenti nel Comando Rapido: {shortcut_name}")
    for action in plistlib.loads(data[0]):
        if action.get("WFWorkflowActionIdentifier") != SPEAK_TEXT_ACTION:
            continue
        params = action.get("WFWorkflowActionParameters", {})
        return {
            "voce_id": params.get("WFSpeakTextVoice"),
            "velocita": float(params.get("WFSpeakTextRate", 0.5)),
            "tono": float(params.get("WFSpeakTextPitch", 1.0)),
        }
    raise RuntimeError(f"Azione 'Leggi ad alta voce' assente: {shortcut_name}")


def controlla_profilo_shortcut(
    db_path: Path = SHORTCUT_DB,
    cfg: dict | None = None,
) -> dict:
    """Blocca il collaudo se la voce importata differisce dalla fotocopia Sal."""
    cfg = cfg or carica_config()
    profilo = leggi_profilo_shortcut(
        db_path=db_path,
        shortcut_name=cfg.get("comando_voce", "Voce LeaderAI firmato"),
    )
    atteso = {
        "voce_id": cfg.get("voce_shortcut_id"),
        "velocita": float(cfg.get("voce_shortcut_velocita", 0.5)),
        "tono": float(cfg.get("voce_shortcut_tono", 1.0)),
    }
    errori = [
        f"{key}: atteso {atteso[key]!r}, trovato {profilo[key]!r}"
        for key in atteso
        if profilo[key] != atteso[key]
    ]
    if errori:
        raise RuntimeError("Profilo voce diverso dalla fotocopia Sal: " + "; ".join(errori))
    return profilo


def _comando_hook() -> str:
    # Non risolvere i symlink: sulla macchina di Sal il path operativo conserva
    # flag e config locali, pur puntando allo stesso file fisico della repo.
    parti = [sys.executable, str(Path(__file__).absolute())]
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


# Antigravity (Google) non usa la forma di Claude e Codex: il file mappa un
# nome di gestore -> eventi. Schema ufficiale (antigravity.google/docs/hooks,
# letto il 13/09/2026): {"<gestore>": {"enabled": true, "Stop": [{"hooks": [...]}]}}
GESTORE_ANTIGRAVITY = "voce-leaderai"


def collega_hook_antigravity(hooks_path: Path) -> None:
    """Aggiunge il nostro Stop hook ad Antigravity lasciando intatti gli altri."""
    data = _leggi_json(hooks_path)
    gestore = data.get(GESTORE_ANTIGRAVITY)
    if not isinstance(gestore, dict):
        gestore = {}
    gestore["enabled"] = True
    gestore["Stop"] = [{"hooks": [{"type": "command", "command": _comando_hook(), "timeout": 10}]}]
    data[GESTORE_ANTIGRAVITY] = gestore
    hooks_path.parent.mkdir(parents=True, exist_ok=True)
    if hooks_path.exists():
        shutil.copy2(hooks_path, hooks_path.with_name(hooks_path.name + ".pre-voce.bak"))
    hooks_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def hook_antigravity_collegato(hooks_path: Path) -> bool:
    try:
        data = _leggi_json(hooks_path)
    except Exception:
        return False
    for gestore in data.values():
        if not isinstance(gestore, dict) or gestore.get("enabled") is False:
            continue
        for gruppo in gestore.get("Stop", []):
            if not isinstance(gruppo, dict):
                continue
            for hook in gruppo.get("hooks", []):
                if isinstance(hook, dict) and str(Path(__file__).absolute()) in str(hook.get("command", "")):
                    return True
    return False


def hook_collegato(settings_path: Path) -> bool:
    try:
        data = _leggi_json(settings_path)
    except Exception:
        return False
    for gruppo in data.get("hooks", {}).get("Stop", []):
        if not isinstance(gruppo, dict):
            continue
        for hook in gruppo.get("hooks", []):
            if isinstance(hook, dict) and str(Path(__file__).absolute()) in str(hook.get("command", "")):
                return True
    return False


def _agente_presente(nome: str) -> bool:
    return shutil.which(nome) is not None or (Path.home() / f".{nome}").exists()


def _antigravity_presente() -> bool:
    """Antigravity non si riconosce da una cartella `~/.antigravity` come gli
    altri: l'IDE vive in `~/.gemini/antigravity` (o nell'app installata)."""
    return (
        shutil.which("antigravity") is not None
        or (Path.home() / ".gemini" / "antigravity").exists()
        or Path("/Applications/Antigravity.app").exists()
    )


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
    if _antigravity_presente():
        path = home / ".gemini" / "config" / "hooks.json"
        collega_hook_antigravity(path)
        collegati.append(("Antigravity", path))
    if not collegati:
        raise RuntimeError("Non trovo Claude Code, Codex o Antigravity da collegare.")
    for nome, path in collegati:
        print(f"{nome}: configurazione voce scritta in {path}")
        if nome == "Codex":
            print("Codex: apri /hooks, verifica il comando Voce e concedi fiducia.")
        if nome == "Antigravity":
            print("Antigravity: riavvia l'app, gli hook si leggono all'avvio.")
    return collegati


def controlla_hook_agenti() -> bool:
    home = Path.home()
    trovati = []
    for nome, presente, path in (
        ("Claude Code", _agente_presente("claude"), home / ".claude" / "settings.json"),
        ("Codex", _agente_presente("codex"), home / ".codex" / "hooks.json"),
        ("Antigravity", _antigravity_presente(), home / ".gemini" / "config" / "hooks.json"),
    ):
        if presente:
            ok = hook_antigravity_collegato(path) if nome == "Antigravity" else hook_collegato(path)
            stato = "configurato" if ok else "NON configurato"
            print(f"{nome}: {stato}")
            if nome == "Codex" and ok:
                print("Codex: la prova reale richiede fiducia da /hooks e una risposta letta ad alta voce.")
            trovati.append(ok)
    return bool(trovati) and all(trovati)


# Finestra entro cui una seconda chiamata con lo STESSO testo e' un doppione.
# Serve perche' l'evento di fine risposta puo' arrivare due volte a pochi
# millisecondi (misurato il 30/08/2026: 10 letture doppie su 26). Prima della
# coda in parla() il doppione troncava l'audio appena partito; oggi lo
# rileggerebbe per intero una seconda volta. In entrambi i casi va scartato.
def normalizza_payload(dati: dict) -> dict:
    """Stessi dati, un solo nome per campo.

    Claude Code e Codex mandano `last_assistant_message`, `transcript_path`,
    `session_id`. Antigravity manda gli stessi fatti in camelCase
    (`transcriptPath`, `conversationId`) e nessun messaggio pronto: senza
    questa traduzione l'hook partiva, non trovava niente da leggere e taceva
    (caso reale 13/09/2026).
    """
    if not isinstance(dati, dict):
        return {}
    tradotti = dict(dati)
    for straniero, nostro in (
        ("transcriptPath", "transcript_path"),
        ("conversationId", "session_id"),
        ("lastAssistantMessage", "last_assistant_message"),
        ("modelName", "model"),
    ):
        valore = tradotti.get(straniero)
        if isinstance(valore, str) and valore.strip() and not tradotti.get(nostro):
            tradotti[nostro] = valore
    return tradotti


FINESTRA_DOPPIONE_SEC = 8.0
ULTIMA_LETTURA = BASE / "ULTIMA_LETTURA"


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
    elif "/antigravity/" in percorso or "/.gemini/" in percorso:
        agente = "Antigravity"
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


def main():
    if not voce_attiva():
        traccia("voce spenta, non leggo")
        return
    try:
        dati = normalizza_payload(json.load(sys.stdin))
    except Exception:
        traccia("chiamata senza dati leggibili")
        return
    testo = dati.get("last_assistant_message") or ""
    origine = "messaggio diretto"
    if not testo and dati.get("transcript_path"):
        origine = "trascrizione"
        try:
            testo = estrai_ultima_risposta(dati["transcript_path"])
        except Exception:
            traccia("trascrizione illeggibile")
            return
    if testo:
        conversazione = origine_risposta(dati)
        if gia_letto_da_poco(testo, conversazione):
            traccia(f"lettura doppia scartata ({len(testo)} caratteri, {origine})")
            return
        traccia(f"leggo {len(testo)} caratteri ({origine})")
        parla(testo, origine=conversazione)  # deposita e torna subito
    else:
        traccia(f"nessun testo da leggere ({origine})")


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--merge-config":
        unisci_config(sys.argv[2], sys.argv[3])
    elif len(sys.argv) == 2 and sys.argv[1] == "--install-hooks":
        installa_hook_agenti()
    elif len(sys.argv) == 2 and sys.argv[1] == "--check-hooks":
        raise SystemExit(0 if controlla_hook_agenti() else 1)
    elif len(sys.argv) == 2 and sys.argv[1] == "--check-profile":
        try:
            profilo = controlla_profilo_shortcut()
        except Exception as exc:
            print(f"FOTOCOPIA_SAL_NON_PASSA: {exc}")
            raise SystemExit(1)
        print(
            "FOTOCOPIA_SAL_OK: "
            f"voce={profilo['voce_id']}, "
            f"velocita={profilo['velocita']}, tono={profilo['tono']}"
        )
    elif len(sys.argv) == 2 and sys.argv[1] == "--test-voice":
        parla("Prova di Voce AI LeaderAI. Questo audio e' sintetico.")
    else:
        main()
    sys.exit(0)
