# Privacy

Voice Dettatura Mac v1.0 e' uno strumento gratuito sperimentale.

## Dati trattati

L'app registra audio solo mentre tieni premuto il tasto di dettatura.

L'audio viene passato al motore di trascrizione locale installato sul Mac. Il testo trascritto viene incollato nell'app in cui stai lavorando.

## Cosa non facciamo

- Non leggiamo le tue dettature.
- Non salviamo un archivio delle tue dettature.
- Non controlliamo il tuo schermo.
- Non inviamo audio o testo a server di Sal Chiarenza o LeaderAI.

## Detta pulito (opzionale)

Se in `config.json` c'e' `"detta_pulito": true`, le dettature lunghe vengono passate all'agente AI gia' installato dal proprietario (Claude Code o Codex) per togliere ripetizioni e sistemare la punteggiatura. Sul Mac, se esiste il Comando Rapido "Voce Pulita", la pulizia usa prima Apple Intelligence: di default il testo va a **Private Cloud Compute** (cloud privato Apple, dati non conservati da Apple); scegliendo "Su dispositivo" nel comando resta tutto sul Mac. In riserva il testo viaggia verso il servizio del TUO agente, col TUO account e le sue condizioni — non verso server di Sal Chiarenza o LeaderAI. Per una dettatura al 100% locale: `"detta_pulito": false`.

## Permessi richiesti

macOS puo' chiedere microfono, accessibilita' e monitoraggio input.

Servono per:

- ascoltare la voce quando premi il tasto;
- riconoscere la scorciatoia da tastiera;
- incollare il testo dove hai il cursore.

## Nota importante

Il progetto usa dipendenze open source e un modello di trascrizione scaricato al primo avvio. La prima installazione richiede internet per scaricare quei componenti.
