"""Hook Stop: se la voce è attiva (flag VOICE_ON), legge ad alta voce l'ultima risposta.

Input su stdin (JSON):
- Claude Code: campo "transcript_path" -> si estrae l'ultimo messaggio dell'assistente.
- Codex: campo "last_assistant_message" -> si usa direttamente.
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


# Finestra entro cui una seconda chiamata con lo STESSO testo e' un doppione.
# Serve perche' l'evento di fine risposta puo' arrivare due volte a pochi
# millisecondi (misurato il 30/08/2026: 10 letture doppie su 26). Prima della
# coda in parla() il doppione troncava l'audio appena partito; oggi lo
# rileggerebbe per intero una seconda volta. In entrambi i casi va scartato.
FINESTRA_DOPPIONE_SEC = 8.0
ULTIMA_LETTURA = BASE / "ULTIMA_LETTURA"


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


def main():
    if not voce_attiva():
        traccia("voce spenta, non leggo")
        return
    try:
        dati = json.load(sys.stdin)
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
        if gia_letto_da_poco(testo):
            traccia(f"lettura doppia scartata ({len(testo)} caratteri, {origine})")
            return
        traccia(f"leggo {len(testo)} caratteri ({origine})")
        parla(testo)  # deposita e torna subito: legge un lettore sganciato
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
