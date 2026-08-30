"""Voce in uscita: legge un testo con la voce di sistema macOS.

La lettura in corso si finisce SEMPRE: una nuova risposta non la uccide piu'
(caso 30/08/2026: tre risposte in 21 secondi, solo l'ultima arrivava in fondo).
Il testo nuovo va in attesa e, se nel frattempo ne arrivano altri, vince
l'ultimo: mai minuti di audio arretrato. L'unico stop immediato resta la
dettatura (barge-in da detta.py) e --stop.

A leggere e' un processo "lettore" separato e sganciato dal chiamante
(start_new_session): l'hook di fine risposta ha un timeout di 10 secondi e
non deve restare vivo per la durata dell'audio. Il lettore e' unico grazie a
un flock del kernel: si libera da solo alla morte del processo, quindi non
esistono lock stantii da rubare (ne' le corse che ne derivano).

Uso:
  parla.py "testo"    mette il testo in lettura (dopo l'eventuale lettura in corso)
  parla.py -          legge il testo da stdin
  parla.py --stop     ferma subito la lettura e svuota l'attesa
  parla.py --lettore  (interno) legge l'attesa fino a svuotarla, poi esce
"""
import fcntl
import os
import signal
import subprocess
import sys
from pathlib import Path

from voce_lib import BASE, carica_config, pulisci_per_voce, FLAG_PARLANDO

LETTURA_PENDENTE = BASE / "LETTURA_PENDENTE"  # prossimo testo: vince l'ultimo arrivato
LETTORE_LOCK = BASE / "LETTORE_LOCK"          # flock del lettore unico (mai eliminato)
LETTORE_PID = BASE / "LETTORE_PID"            # pid del lettore, per lo stop mirato

_fd_lock = None  # tenuto aperto dal lettore: il flock vive quanto il processo


def _pid_lettore():
    try:
        return int(LETTORE_PID.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def _processo_vivo(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True  # esiste ma non e' nostro: comunque vivo
    return True


def _e_lettore(pid):
    """Vero se quel pid e' davvero un lettore di Voce: il pid nel file puo'
    essere stato riusato dal sistema per un processo qualunque, e a un
    innocente non si manda SIGTERM."""
    try:
        esito = subprocess.run(
            ["ps", "-o", "command=", "-p", str(pid)],
            capture_output=True, text=True, timeout=5,
        )
    except Exception:
        return False
    return "--lettore" in (esito.stdout or "")


def ferma():
    """Stop immediato: niente attesa, niente voce. PRIMA si svuota l'attesa
    (un lettore appena nato che non trova niente esce da solo), poi si spegne
    il lettore in corsa, poi i processi audio, poi i flag."""
    LETTURA_PENDENTE.unlink(missing_ok=True)
    pid = _pid_lettore()
    if pid is not None and _processo_vivo(pid) and _e_lettore(pid):
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
    subprocess.run(["pkill", "-x", "say"], check=False)
    subprocess.run(["pkill", "-f", "shortcuts run"], check=False)
    LETTORE_PID.unlink(missing_ok=True)
    FLAG_PARLANDO.unlink(missing_ok=True)


def scrivi_pendente(testo, pendente=None):
    """Deposita il testo in attesa in modo atomico: chi arriva dopo sovrascrive
    (vince l'ultimo), chi preleva non vede mai un file scritto a meta'."""
    pendente = pendente or LETTURA_PENDENTE
    provvisorio = pendente.with_name(f"{pendente.name}.{os.getpid()}.tmp")
    provvisorio.write_text(testo, encoding="utf-8")
    os.replace(provvisorio, pendente)


def prendi_pendente(pendente=None):
    """Preleva il testo in attesa (None se non c'e'). Il prelievo e' un rename
    atomico: un deposito che arriva nello stesso istante non va mai perso
    (sovrascriverebbe il file in attesa, non quello gia' prelevato)."""
    pendente = pendente or LETTURA_PENDENTE
    in_corso = pendente.with_name(pendente.name + ".presa")
    try:
        os.replace(pendente, in_corso)
    except FileNotFoundError:
        return None
    testo = in_corso.read_text(encoding="utf-8")
    in_corso.unlink(missing_ok=True)
    return testo or None


def _prendi_lock():
    """Un solo lettore per volta: flock esclusivo non bloccante. Il kernel lo
    libera da solo quando il processo muore, comunque muoia: non esistono
    lock stantii ne' corse a rubarli. Il file NON va mai eliminato: un flock
    su un file ricreato sarebbe un lock su un altro inode."""
    global _fd_lock
    fd = os.open(LETTORE_LOCK, os.O_CREAT | os.O_RDWR)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        return False
    _fd_lock = fd
    return True


def _rilascia_lock():
    global _fd_lock
    if _fd_lock is not None:
        try:
            os.close(_fd_lock)  # chiudere rilascia il flock
        except OSError:
            pass
        _fd_lock = None


def _lettore_in_corsa():
    """Vero se un lettore tiene il lock in questo momento (prova non
    bloccante, senza fidarsi di pid scritti su file)."""
    try:
        fd = os.open(LETTORE_LOCK, os.O_CREAT | os.O_RDWR)
    except OSError:
        return False  # non si sa: si prova a spawnare, decidera' il lock
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return True
        fcntl.flock(fd, fcntl.LOCK_UN)
        return False
    finally:
        os.close(fd)


def _traccia(messaggio):
    """Riga nel registro di Voce: senza, una lettura uccisa e una mai partita
    sono identiche viste da fuori (lezione dell'analisi del 30/08/2026)."""
    try:
        from datetime import datetime
        istante = datetime.now().strftime("%Y-%m-%d %H:%M:%S,%f")[:-3]
        with open(BASE / "voce.log", "a", encoding="utf-8") as registro:
            registro.write(f"{istante} INFO lettore: {messaggio}\n")
    except Exception:
        pass  # il registro non ferma mai la voce


def _leggi_adesso(testo):
    """Una lettura intera, sincrona, ma con un tetto: uno `shortcuts run`
    incantato (classe di guasto gia' vista nella corsia di pulizia) non deve
    tenere il lock per sempre e ammutolire tutte le risposte successive.
    Il tetto e' proporzionale al testo (~15 caratteri/secondo la voce Siri,
    margine 4x, pavimento 60s): una lettura sana non lo tocca mai."""
    cfg = carica_config()
    if cfg["voce"].lower().startswith("siri"):
        # le voci Siri non sono usabili dalle app: si passa dal comando rapido
        comando = ["shortcuts", "run", cfg.get("comando_voce", "Voce LeaderAI firmato")]
    else:
        comando = ["say", "-v", cfg["voce"], "-r", str(cfg.get("velocita", 195)), "-f", "-"]
    tetto = max(60, len(testo) // 4)
    try:
        subprocess.run(
            comando, input=testo.encode("utf-8"), timeout=tetto,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
        )
    except subprocess.TimeoutExpired:
        _traccia(f"lettura incantata oltre il tetto di {tetto}s: uccisa")
        subprocess.run(["pkill", "-x", "say"], check=False)
        subprocess.run(["pkill", "-f", "shortcuts run"], check=False)


def lettore():
    """Legge l'attesa fino a svuotarla, una voce per volta, poi esce.

    PARLANDO resta alzato per tutta la corsa, anche tra un testo e il
    successivo: l'ascolto mani-libere non deve riarmarsi in un buco tra due
    letture e scambiare la voce sintetica per Sal (detta.py riga ~1048)."""
    while True:
        if not _prendi_lock():
            return  # c'e' gia' un lettore in corsa: leggera' lui
        try:
            LETTORE_PID.write_text(str(os.getpid()), encoding="utf-8")
            while True:
                testo = prendi_pendente()
                if testo is None:
                    break
                FLAG_PARLANDO.touch()
                _traccia(f"lettura iniziata ({len(testo)} caratteri)")
                _leggi_adesso(testo)
        finally:
            FLAG_PARLANDO.unlink(missing_ok=True)
            if _pid_lettore() == os.getpid():
                LETTORE_PID.unlink(missing_ok=True)
            _rilascia_lock()
        if not LETTURA_PENDENTE.exists():
            return
        # un testo e' arrivato nell'attimo in cui uscivamo: un altro giro
        # (se intanto e' gia' partito un lettore nuovo, il lock ci dira' di no)


def _avvia_lettore_se_serve():
    if _lettore_in_corsa():
        return  # il lettore in corsa passera' da solo al testo in attesa
    # argv[0] deve restare il percorso operativo (symlink compreso): e' da li'
    # che voce_lib ricava la cartella dei flag (vedi _base_operativa)
    copione = BASE / "parla.py"
    if not copione.exists():
        copione = Path(__file__)
    subprocess.Popen(
        [sys.executable, str(copione), "--lettore"],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True,  # sopravvive all'hook (timeout 10s) e al terminale
    )


def parla(testo):
    testo = pulisci_per_voce(testo)
    if not testo:
        return
    scrivi_pendente(testo)
    _avvia_lettore_se_serve()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(0)
    if sys.argv[1] == "--stop":
        ferma()
    elif sys.argv[1] == "--lettore":
        lettore()
    elif sys.argv[1] == "-":
        parla(sys.stdin.read())
    else:
        parla(" ".join(sys.argv[1:]))
