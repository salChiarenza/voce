# Privacy

Voce LeaderAI per Mac e' uno strumento gratuito sperimentale. La versione
esatta installata e' riportata nel file `VERSION`.

## Dati trattati

L'app registra audio solo mentre tieni premuto il tasto di dettatura.

L'audio viene passato al motore di trascrizione locale installato sul Mac. Il testo trascritto viene incollato nell'app in cui stai lavorando.

## Cosa non facciamo

- Non leggiamo le tue dettature.
- Non salviamo un archivio delle tue dettature.
- Non controlliamo il tuo schermo.
- Non inviamo audio o testo a server di Sal Chiarenza o LeaderAI.

## Detta pulito (opzionale)

Se in `config.json` c'e' `"detta_pulito": true`, fuori da ChatGPT, Claude e Codex le dettature lunghe possono passare dal Comando Rapido "Voce Pulita". Apple Intelligence puo' lavorare su dispositivo o tramite **Private Cloud Compute**, secondo la scelta nel Comando Rapido. La prova dura al massimo 2 secondi; se non riesce, viene usato subito il testo locale di Whisper. Claude Code e Codex non vengono mai chiamati come ripiego durante una dettatura. Per evitare anche il passaggio Apple: `"detta_pulito": false`.

Se il proprietario attiva `"debug_dettature": true`, il log locale conserva i
testi grezzi e l'apprendimento giornaliero puo' proporre correzioni tramite il
suo agente. Il comportamento e' disattivato nella configurazione standard.

## Audio conservato (opzionale)

Se il proprietario imposta `"conserva_audio_n"` a un numero maggiore di zero,
le ultime dettature (fino a quel numero) restano come file audio nella
cartella locale `audio_recenti/`: servono a riascoltare le frasi capite male
e a migliorare glossario e sostituzioni su casi veri. I file restano sul
computer, non vengono inviati a nessuno e i piu' vecchi si eliminano da soli.
Nella configurazione standard l'opzione e' spenta e non viene salvato nulla.

## Voce AI delle risposte

Quando il proprietario la attiva, Voce legge il testo prodotto da Claude Code
o Codex con la voce sintetica del sistema. L'accensione lo dichiara a voce e
l'indicatore visibile mostra `AI`. L'audio viene riprodotto al momento: Voce
non lo registra, non lo salva e non crea un file da distribuire.

## Permessi richiesti

macOS puo' chiedere microfono, accessibilita' e monitoraggio input.

Servono per:

- ascoltare la voce quando premi il tasto;
- riconoscere la scorciatoia da tastiera;
- incollare il testo dove hai il cursore.

## Nota importante

Il progetto usa dipendenze open source e un modello di trascrizione scaricato al primo avvio. La prima installazione richiede internet per scaricare quei componenti.
