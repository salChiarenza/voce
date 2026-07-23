"""Voce in uscita: legge un testo con la voce di sistema macOS.

Uso:
  parla.py "testo"   legge il testo (interrompe l'eventuale lettura in corso)
  parla.py -         legge il testo da stdin
  parla.py --stop    ferma subito la lettura
"""
import subprocess
import sys
import threading

from voce_lib import carica_config, pulisci_per_voce, FLAG_PARLANDO


def ferma():
    subprocess.run(["pkill", "-x", "say"], check=False)
    subprocess.run(["pkill", "-f", "shortcuts run"], check=False)
    FLAG_PARLANDO.unlink(missing_ok=True)  # anche se interrotta a meta', il segnale si toglie


def _segna_fine_a_processo_finito(p):
    """detta.py (processo separato) usa questo flag per mettere in pausa
    l'ascolto mani-libere mentre l'agente sta parlando: senza, si sentirebbe
    da solo e si inceppa. parla() non aspetta la fine (lo stop deve restare
    possibile), quindi il togliere il flag lo fa questo thread a parte."""
    p.wait()
    FLAG_PARLANDO.unlink(missing_ok=True)


def parla(testo):
    testo = pulisci_per_voce(testo)
    if not testo:
        return
    ferma()  # una voce per volta
    cfg = carica_config()
    FLAG_PARLANDO.touch()
    if cfg["voce"].lower().startswith("siri"):
        # le voci Siri non sono usabili dalle app: si passa dal comando rapido
        p = subprocess.Popen(
            ["shortcuts", "run", cfg.get("comando_voce", "Voce LeaderAI firmato")],
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
    # Il monitor deve restare vivo finche' finisce la voce. Se fosse daemon,
    # l'uscita di questo piccolo processo lo ucciderebbe subito e lascerebbe
    # PARLANDO bloccato, mettendo in pausa il mani-libere per sempre.
    threading.Thread(target=_segna_fine_a_processo_finito, args=(p,), daemon=False).start()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(0)
    if sys.argv[1] == "--stop":
        ferma()
    elif sys.argv[1] == "-":
        parla(sys.stdin.read())
    else:
        parla(" ".join(sys.argv[1:]))
