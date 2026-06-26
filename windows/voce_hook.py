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
import re
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
FLAG_VOICE_ON = BASE / "VOICE_ON"   # se esiste, la voce in uscita e' accesa
CFG_PATH = BASE / "config.json"


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


def parla(testo: str) -> None:
    """Legge il testo con la voce italiana di Windows (System.Speech via PowerShell)."""
    testo = pulisci_per_voce(testo)
    if not testo:
        return
    try:
        rate = int(json.loads(CFG_PATH.read_text(encoding="utf-8")).get("voce_rate", 0))
    except Exception:
        rate = 0
    script = (
        "$ErrorActionPreference='SilentlyContinue';"
        "Add-Type -AssemblyName System.Speech;"
        "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer;"
        "$v=$s.GetInstalledVoices()|"
        "?{$_.Enabled -and $_.VoiceInfo.Culture.Name -like 'it*'}|"
        "select -First 1;"
        "if($v){$s.SelectVoice($v.VoiceInfo.Name)};"
        "$s.Volume=100;"
        "$s.Rate=" + str(rate) + ";"
        "$t=[Console]::In.ReadToEnd();"
        "if($t){$s.Speak($t)}"
    )
    p = subprocess.Popen(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        p.stdin.write(testo.encode("utf-8"))
        p.stdin.close()
    except Exception:
        pass


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
        parla(testo)


if __name__ == "__main__":
    main()
    sys.exit(0)
