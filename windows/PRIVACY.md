# Privacy

Voce LeaderAI per Windows e' uno strumento gratuito sperimentale. La versione
esatta installata e' riportata nel file `VERSION`.

## Dati trattati

L'app registra audio solo mentre tieni premuto il tasto di dettatura.

L'audio viene passato al motore di trascrizione locale installato sul PC. Il testo trascritto viene incollato nell'app in cui stai lavorando.

## Cosa non facciamo

- Non leggiamo le tue dettature.
- Non salviamo un archivio delle tue dettature.
- Non controlliamo il tuo schermo.
- Non inviamo audio o testo a server di Sal Chiarenza o LeaderAI.

## Testo immediato

Windows incolla il testo locale di Whisper con glossario e sostituzioni. Claude
Code e Codex non vengono chiamati durante la dettatura.

Se il proprietario aggiunge `"debug_dettature": true`, il log locale conserva
i testi grezzi e l'apprendimento giornaliero puo' proporre correzioni tramite
il suo agente. Il comportamento e' disattivato nella configurazione standard.

## Voce AI delle risposte

Quando il proprietario la attiva, Voce legge il testo prodotto da Claude Code
o Codex con la voce sintetica del sistema. L'accensione lo dichiara a voce e
la finestra aperta identifica `Voce AI`. L'audio viene riprodotto al momento:
Voce non lo registra, non lo salva e non crea un file da distribuire.

## Permessi richiesti

Windows puo' chiedere accesso al microfono o mostrare avvisi di sicurezza per script e file scaricati.

Il microfono serve per ascoltare la voce mentre premi il tasto.

## Nota importante

Il progetto usa dipendenze open source e un modello di trascrizione scaricato al primo avvio. La prima installazione richiede internet per scaricare quei componenti.
