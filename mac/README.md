# Voice Dettatura Mac v1.0.1

Dettatura locale per Mac: tieni premuto un tasto, parli, rilasci, e il testo viene scritto dove hai il cursore.

Risorsa gratuita per la community **AI con Sal**.

## Cosa fa

- Detti testo in email, documenti, browser, ChatGPT, Claude, Codex e app simili.
- Usa una piccola barra verde mentre ascolta.
- Gira sul Mac con trascrizione locale.
- Include un installer guidato.
- Se macOS resta bloccato mentre chiude il microfono, prova a riavviare da sola la dettatura invece di restare incastrata.

## Requisiti

- Mac con chip Apple Silicon, M1 o successivo.
- macOS recente.
- Python 3 disponibile sul Mac.
- Connessione internet al primo avvio per scaricare dipendenze e modello di trascrizione.

Il primo download puo' essere pesante: il modello Whisper viene scaricato una volta, poi resta sul computer.

## Installazione

### Metodo consigliato: installa con Claude Code o Codex

Apri Claude Code o Codex sul Mac e incolla il prompt che trovi qui:

```text
INSTALLA_CON_AI.md
```

Oppure passa direttamente questo link all'agente (l'app è nella cartella mac/):

```text
https://github.com/salChiarenza/voce
```

L'agente ti guidera' passo passo: controllo Mac, download, installazione, permessi e prova finale.

### Metodo manuale

1. Scarica il file `.zip` dalla release.
2. Estrai lo zip.
3. Apri Terminale nella cartella estratta.
4. Esegui:

```bash
./install.sh
```

L'installer crea la cartella:

```text
~/VoiceDettaturaMac
```

e aggiunge due launcher sulla Scrivania:

- `Voice Dettatura Mac.command`
- `Voice On-Off.command`

## Uso rapido

1. Apri `Voice Dettatura Mac.command`.
2. Tieni premuto `Cmd destro`.
3. Parla.
4. Rilascia il tasto.

Il testo viene scritto dove hai il cursore.

## Permessi macOS

macOS puo' chiedere:

- Microfono
- Accessibilita'
- Monitoraggio input

Sono permessi necessari per ascoltare la voce, leggere la scorciatoia da tastiera e incollare il testo.

## Privacy

La dettatura gira localmente sul Mac. Il progetto non invia le tue dettature a Sal Chiarenza, LeaderAI o server esterni di questo progetto.

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
~/Desktop/Voice Dettatura Mac.command
~/Desktop/Voice On-Off.command
```

## Licenza

MIT. Vedi `LICENSE`.
