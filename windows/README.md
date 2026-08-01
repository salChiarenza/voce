# Voce LeaderAI per Windows (candidata)

Dettatura locale per Windows: tieni premuto `Ctrl destro`, parli, rilasci, e il testo viene scritto dove hai il cursore.

Mentre parli, in basso al centro compare la pill **salchiarenza.ai** con la barra di lineette verdi ad arco "a sorriso" che si muovono col volume. L'overlay non ruba il focus: continui a scrivere dove sei.

Risorsa gratuita per la community **AI con Sal**.

La versione esatta dell'archivio è nel file `../VERSION` e viene copiata nella
cartella installata.

## Stato

Versione Windows brandizzata, allineata nell'aspetto e nel comportamento alla versione Mac (pill + marchio + sorriso, due tasti, voce agenti). L'aggiornamento conserva la configurazione personale e collega davvero la lettura delle risposte a Claude Code/Codex. Va provata su un PC Windows reale prima di considerarla stabile.

## Metodo consigliato: launcher locale + collaudo con Claude Code o Codex

Segui il percorso in:

```text
INSTALLA_CON_AI.md
```

Il proprietario scarica la versione verificata, apre la cartella `windows/` e fa doppio clic su `install.bat`. L'installer lavora nel profilo utente e copia anche le istruzioni nella cartella installata. Da quel momento l'agente controlla il PC, conserva glossario e preferenze, ripara la parte locale, collega la voce delle risposte e chiude con una prova finale. Alla prima installazione elenca e fa ascoltare le voci italiane gia' presenti, suggerisce quella percepita come piu' naturale e salva la scelta del proprietario in `voce_nome`.

Comandi usati dall'agente per la scelta guidata:

```text
voce_hook.py --list-voices
voce_hook.py --test-voice "NOME"
voce_hook.py --set-voice "NOME"
```

## Installazione

1. Scarica lo zip dalla versione esatta indicata da Sal.
2. Estrai lo zip.
3. Doppio click su `install.bat`.
4. Attendi il messaggio `Installazione completata`.
5. Torna nel tuo agente e chiedigli di leggere `%USERPROFILE%\VoiceDettaturaWindows\INSTALLA_CON_AI.md` e completare il collaudo locale.

L'installer crea:

```text
%USERPROFILE%\VoiceDettaturaWindows
```

e un'icona cliccabile **Voce Dettatura** sulla Scrivania e nel Menu Start.

## Uso

1. Clicca l'icona **Voce Dettatura** (Scrivania o Menu Start). Si apre una piccola finestra: la Voce e' accesa.
2. In qualsiasi programma tieni premuto `Ctrl destro`.
3. Parla.
4. Rilascia `Ctrl destro`.
5. Usa il tasto `Menu` per accendere o spegnere la voce agenti, se configurata.

In basso compare la pill **salchiarenza.ai** con la barra verde a sorriso e il testo viene scritto dove hai il cursore. Per spegnerla, chiudi quella finestra.

In piu': glossario personale (`glossario` in `config.json`) e sostituzioni locali per scrivere correttamente nomi e brand. Il testo grezzo viene incollato subito: Claude Code e Codex non vengono chiamati durante la dettatura.

## Privacy

La dettatura gira localmente sul PC. Il progetto non invia le tue dettature a Sal Chiarenza, LeaderAI o server esterni di questo progetto. Vedi `PRIVACY.md`.

Leggi `PRIVACY.md`.

## Limiti

- Versione beta.
- Supporto individuale gratuito fuori perimetro.
- Primo avvio piu' lento: il modello di trascrizione viene scaricato e caricato.
- Alcuni antivirus o SmartScreen possono mostrare avvisi perche' il progetto e' nuovo.

## Disinstallazione

Cancella:

```text
%USERPROFILE%\VoiceDettaturaWindows
Desktop\Voce Dettatura.lnk
Menu Start\Programmi\Voce Dettatura.lnk
```

## Licenza

MIT. Vedi `LICENSE`.
