# Voce LeaderAI per Mac

Dettatura locale per Mac: tieni premuto un tasto, parli, rilasci, e il testo viene scritto dove hai il cursore.

Risorsa gratuita per la community **AI con Sal**.

La versione esatta dell'archivio è nel file `../VERSION` e viene copiata nella
cartella installata.

## Cosa fa

- Detti testo in email, documenti, browser, ChatGPT, Claude, Codex e app simili.
- Usa una piccola barra verde mentre ascolta.
- Gira sul Mac con trascrizione locale.
- Glossario personale: i tuoi nomi e brand escono scritti giusti (`glossario` in `config.json`).
- Detta pulito (opzionale): le dettature lunghe passano dal tuo agente AI (Claude Code o Codex) che toglie ripetizioni e ripensamenti e sistema la punteggiatura. Si spegne con `"detta_pulito": false`.
- Fotocopia funzionale di Sal: il Mac riceve lo stesso Comando Rapido Siri
  collaudato da Sal, distribuito come `Voce LeaderAI firmato.shortcut`, e gli
  stessi tasti, tempi, toggle e soglie. Il collaudo verifica anche voce
  interna, velocita' e tono.
- Aggiornamento vero: conserva glossario, sostituzioni e calibrazione gia' presenti, aggiorna la parte di prodotto e collega automaticamente la voce delle risposte a Claude Code e/o Codex senza cancellare gli altri collegamenti.
- Sorgente unica: il codice in questa cartella e' lo stesso codice usato ogni giorno da Sal; non esiste piu' una seconda copia interna da riallineare.
- Include un installer guidato.
- Se macOS resta bloccato mentre chiude il microfono, prova a riavviare da sola la dettatura invece di restare incastrata.

## Requisiti

- Mac con chip Apple Silicon, M1 o successivo.
- macOS recente.
- Python 3 disponibile sul Mac.
- Connessione internet al primo avvio per scaricare dipendenze e modello di trascrizione.

Il primo download puo' essere pesante: il modello Whisper viene scaricato una volta, poi resta sul computer.

## Installazione

### Metodo consigliato: launcher locale + collaudo con Claude Code o Codex

Segui il percorso in:

```text
INSTALLA_CON_AI.md
```

Scarica la versione verificata, apri la cartella `mac/` e fai doppio clic su `Installa Voce.command`. L'installer copia anche le istruzioni nella cartella locale. Da quel momento l'agente controlla il Mac, conserva cio' che hai personalizzato, ripara la parte locale, collega la voce e chiude con una prova finale.

L'installer applica la fotocopia funzionale di Sal e conserva glossario,
sostituzioni apprese e preferenza di log. macOS chiede un solo gesto umano:
quando si apre Comandi Rapidi, clicca **Aggiungi comando rapido**. L'agente
esegue poi `voce_hook.py --check-profile` e chiude solo con
`FOTOCOPIA_SAL_OK` e una prova audio reale.

### Installazione

1. Scarica il file `.zip` dalla versione esatta indicata da Sal.
2. Estrai lo zip.
3. Apri la cartella `mac/`.
4. Fai doppio clic su `Installa Voce.command`.
5. Attendi il messaggio `Installazione completata`.
6. Torna nel tuo agente e chiedigli di leggere `~/VoiceDettaturaMac/INSTALLA_CON_AI.md` e completare il collaudo locale.

L'installer crea la cartella:

```text
~/VoiceDettaturaMac
```

e aggiunge due launcher sulla Scrivania:

- `Voce Dettatura.command`: avvio semplice della dettatura;
- `Voce Attiva Tutto.command`: avvia Voce e commuta insieme voce agenti e
  mani libere, come il controllo rapido usato da Sal.

## Uso rapido

1. Apri `Voce Dettatura.command`.
2. Tieni premuto `Cmd destro`.
3. Parla.
4. Rilascia il tasto.

Il testo viene scritto dove hai il cursore.

- `Option + freccia sinistra`: accende o spegne la voce delle risposte.
- `Cmd destro + Option`: accende o spegne la modalità mani libere.
- `Voce Attiva Tutto.command`: controllo rapido per accendere o spegnere voce
  agenti e mani libere insieme.

## Permessi macOS

macOS puo' chiedere:

- Microfono
- Accessibilita'
- Monitoraggio input

Sono permessi necessari per ascoltare la voce, leggere la scorciatoia da tastiera e incollare il testo.

## Privacy

La dettatura gira localmente sul Mac. Il progetto non invia le tue dettature a Sal Chiarenza, LeaderAI o server esterni di questo progetto. Col detta pulito attivo, il testo passa dal TUO agente AI (vedi `PRIVACY.md`).

Leggi anche `PRIVACY.md`.

## Limiti

- Versione gratuita e sperimentale.
- Supporto individuale gratuito fuori perimetro.
- Pensata per Mac Apple Silicon.
- Se qualcosa non funziona, segnala il problema nella community AI con Sal indicando modello Mac, versione macOS e passaggio bloccato.

## Disinstallazione

Chiudi il launcher e cancella:

```text
~/VoiceDettaturaMac
~/Desktop/Voce Dettatura.command
~/Desktop/Voce Attiva Tutto.command
```

## Licenza

MIT. Vedi `LICENSE`.
