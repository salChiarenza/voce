# Voice Dettatura Windows v1.1

Dettatura locale per Windows: tieni premuto `F8`, parli, rilasci, e il testo viene scritto dove hai il cursore.

Mentre parli, in basso al centro compare la pill **salchiarenza.ai** con la barra di lineette verdi ad arco "a sorriso" che si muovono col volume. L'overlay non ruba il focus: continui a scrivere dove sei.

Risorsa gratuita per la community **AI con Sal**.

## Stato

Versione Windows brandizzata, allineata nell'aspetto alla versione Mac (pill + marchio + sorriso). Va provata su un PC Windows reale prima di considerarla stabile.

## Metodo consigliato: installa con Claude Code o Codex

Apri Claude Code o Codex sul PC Windows e incolla questo link:

```text
https://github.com/salChiarenza/voice-dettatura-windows
```

Poi scrivi:

```text
Guidami passo passo per installare Voice Dettatura Windows v1.0 beta.
```

L'agente ti guidera' in controllo PC, download, installazione, permessi microfono e prova finale.

## Installazione manuale

1. Scarica lo zip dalla release.
2. Estrai lo zip.
3. Doppio click su `install.bat`.
4. Segui le istruzioni.

L'installer crea:

```text
%USERPROFILE%\VoiceDettaturaWindows
```

e un'icona cliccabile **Voce Dettatura** sulla Scrivania e nel Menu Start.

## Uso

1. Clicca l'icona **Voce Dettatura** (Scrivania o Menu Start). Si apre una piccola finestra: la Voce e' accesa.
2. In qualsiasi programma tieni premuto `F8`.
3. Parla.
4. Rilascia `F8`.

In basso compare la pill **salchiarenza.ai** con la barra verde a sorriso e il testo viene scritto dove hai il cursore. Per spegnerla, chiudi quella finestra.

## Privacy

La dettatura gira localmente sul PC. Il progetto non invia le tue dettature a Sal Chiarenza, LeaderAI o server esterni di questo progetto.

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
