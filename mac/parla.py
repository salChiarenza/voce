"""Voce in uscita: legge un testo con la voce di sistema macOS.

Uso:
  parla.py "testo"   legge il testo (interrompe l'eventuale lettura in corso)
  parla.py -         legge il testo da stdin
  parla.py --stop    ferma subito la lettura
"""
import subprocess
import sys

from voce_lib import carica_config, pulisci_per_voce


def ferma():
    subprocess.run(["pkill", "-x", "say"], check=False)
    subprocess.run(["pkill", "-f", "shortcuts run"], check=False)


def parla(testo):
    testo = pulisci_per_voce(testo)
    if not testo:
        return
    ferma()  # una voce per volta
    cfg = carica_config()
    if cfg["voce"].lower().startswith("siri"):
        # le voci Siri non sono usabili dalle app: si passa dal comando rapido
        p = subprocess.Popen(
            ["shortcuts", "run", cfg.get("comando_voce", "Voce Siri")],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    else:
        p = subprocess.Popen(
            ["say", "-v", cfg["voce"], "-r", str(cfg.get("velocita", 195)), "-f", "-"],
            stdin=subprocess.PIPE,
        )
    p.stdin.write(testo.encode())
    p.stdin.close()  # non aspettiamo la fine: lo stop resta possibile


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(0)
    if sys.argv[1] == "--stop":
        ferma()
    elif sys.argv[1] == "-":
        parla(sys.stdin.read())
    else:
        parla(" ".join(sys.argv[1:]))
