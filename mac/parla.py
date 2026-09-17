"""Voce in uscita: legge un testo con la voce di sistema macOS.

La lettura in corso si finisce SEMPRE. Ogni conversazione conserva la sua
ultima risposta in attesa: le altre conversazioni non la sovrascrivono.
Si puo' seguirne una sola, oppure ascoltare tutte in ordine di arrivo.
L'unico stop immediato resta la dettatura (barge-in da detta.py) e --stop.
La cronologia locale conserva fino a otto conversazioni e permette di
rileggere l'ultima risposta anche dopo uno stop.

A leggere e' un processo "lettore" separato e sganciato dal chiamante
(start_new_session): l'hook di fine risposta ha un timeout di 10 secondi e
non deve restare vivo per la durata dell'audio. Il lettore e' unico grazie a
un flock del kernel: si libera da solo alla morte del processo, quindi non
esistono lock stantii da rubare (ne' le corse che ne derivano).

Uso:
  parla.py "testo"    mette il testo in lettura (dopo l'eventuale lettura in corso)
  parla.py -          legge il testo da stdin
  parla.py --stop     ferma subito la lettura e svuota l'attesa
  parla.py --rileggi  rilegge l'ultima risposta (della conversazione scelta)
  parla.py --conversazioni  elenca le conversazioni disponibili in JSON
  parla.py --segui ID|tutte  sceglie la conversazione dalla prossima lettura
  parla.py --lettore  (interno) legge l'attesa fino a svuotarla, poi esce
"""
import fcntl
import json
import os
import signal
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

from voce_lib import (
    BASE, carica_config, pulisci_per_voce, FLAG_PARLANDO, FLAG_TURNO_UTENTE,
)

LETTURA_PENDENTE = BASE / "LETTURA_PENDENTE"  # coda e ultima risposta, private/locali
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
    svuota_pendenti()
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


def _prendi_lock(attendi=False):
    """Un solo lettore per volta: flock esclusivo non bloccante. Il kernel lo
    libera da solo quando il processo muore, comunque muoia: non esistono
    lock stantii ne' corse a rubarli. Il file NON va mai eliminato: un flock
    su un file ricreato sarebbe un lock su un altro inode."""
    global _fd_lock
    fd = os.open(LETTORE_LOCK, os.O_CREAT | os.O_RDWR)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | (0 if attendi else fcntl.LOCK_NB))
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


def lettore(attendi=False):
    """Legge l'attesa fino a svuotarla, una voce per volta, poi esce.

    PARLANDO resta alzato per tutta la corsa, anche tra un testo e il
    successivo: l'ascolto mani-libere non deve riarmarsi in un buco tra due
    letture e scambiare la voce sintetica per Sal (detta.py riga ~1048)."""
    precedente = None
    while True:
        if not _prendi_lock(attendi=attendi):
            return  # c'e' gia' un lettore in corsa: leggera' lui
        attendi = False  # attesa ammessa solo al primo avvio dopo uno stop
        try:
            LETTORE_PID.write_text(str(os.getpid()), encoding="utf-8")
            while True:
                if FLAG_TURNO_UTENTE.exists():
                    svuota_pendenti()
                    _traccia("risposta scartata: turno vocale di Sal ancora aperto")
                    return
                risposta = prendi_pendente(con_origine=True)
                if risposta is None:
                    break
                testo = risposta["testo"]
                if risposta["nome"] and risposta["id"] != precedente:
                    nome = risposta["nome"].rstrip(".:!?")
                    testo = f"{nome}.\n\n{testo}"
                precedente = risposta["id"]
                FLAG_PARLANDO.touch()
                _traccia(f"lettura iniziata ({len(testo)} caratteri)")
                _leggi_adesso(testo)
        finally:
            FLAG_PARLANDO.unlink(missing_ok=True)
            if _pid_lettore() == os.getpid():
                LETTORE_PID.unlink(missing_ok=True)
            _rilascia_lock()
        if not ha_pendenti():
            return
        # un testo e' arrivato nell'attimo in cui uscivamo: un altro giro
        # (se intanto e' gia' partito un lettore nuovo, il lock ci dira' di no)


def _avvia_lettore_se_serve():
    in_corsa = _lettore_in_corsa()
    if in_corsa and _pid_lettore() is not None:
        return  # il lettore in corsa passera' da solo al testo in attesa
    # ferma() rimuove il PID dopo SIGTERM. Per pochi istanti il vecchio
    # processo puo' avere ancora il lock: a rilasciarlo aspetta IL FIGLIO,
    # mai la dettatura. Il lock conserva sempre una sola voce effettiva.
    modalita = "--lettore-attendi" if in_corsa else "--lettore"
    # argv[0] deve restare il percorso operativo (symlink compreso): e' da li'
    # che voce_lib ricava la cartella dei flag (vedi _base_operativa)
    copione = BASE / "parla.py"
    if not copione.exists():
        copione = Path(__file__)
    subprocess.Popen(
        [sys.executable, str(copione), modalita],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True,  # sopravvive all'hook (timeout 10s) e al terminale
    )


def parla(testo, origine=None):
    if FLAG_TURNO_UTENTE.exists():
        svuota_pendenti()
        _traccia("risposta scartata: turno vocale di Sal ancora aperto")
        return
    testo = pulisci_per_voce(testo)
    if not testo:
        return
    scrivi_pendente(testo, origine=origine)
    if ha_pendenti():
        _avvia_lettore_se_serve()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(0)
    if sys.argv[1] == "--stop":
        ferma()
    elif sys.argv[1] == "--rileggi":
        if not rileggi_ultima():
            print("Non c'e' ancora una risposta da rileggere.", file=sys.stderr)
            sys.exit(1)
    elif sys.argv[1] == "--conversazioni":
        print(json.dumps(elenco_conversazioni(), ensure_ascii=False))
    elif sys.argv[1] == "--segui":
        if len(sys.argv) != 3 or not scegli_conversazione(
            None if sys.argv[2] == "tutte" else sys.argv[2]
        ):
            print("Conversazione non trovata. Usa --conversazioni per vedere le disponibili.", file=sys.stderr)
            sys.exit(1)
    elif sys.argv[1] == "--lettore":
        lettore()
    elif sys.argv[1] == "--lettore-attendi":
        lettore(attendi=True)
    elif sys.argv[1] == "-":
        parla(sys.stdin.read())
    else:
        parla(" ".join(sys.argv[1:]))
