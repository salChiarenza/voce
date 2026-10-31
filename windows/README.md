# Voce LeaderAI per Windows (candidata)

Dettatura locale per Windows: tieni premuto `Ctrl destro`, parli, rilasci, e il testo viene scritto dove hai il cursore.

Mentre parli, in basso al centro compare la pill **LeaderAI.** (il punto verde cresce con la voce e pulsa mentre trascrive) con la barra di lineette verdi ad arco "a sorriso" che si muovono col volume. L'overlay non ruba il focus: continui a scrivere dove sei.

Risorsa della community **AI con Sal**.

La versione esatta è nel file `../VERSION` e viene copiata nella cartella
installata.


## Riprendere mentre trascrive

Puoi rilasciare il tasto e ripremerlo mentre compare «Trascrivo…»: i pezzi
restano nello stesso messaggio, nell'ordine in cui li hai dettati. L'Invio
aspetta tutte le registrazioni e tutte le trascrizioni, anche se l'ultimo
pezzo finisce prima del primo. Se riprendi quando il testo e' gia' incollato,
si sospende l'Invio e la nuova frase si aggiunge con lo spazio necessario.
Se ripremi entro mezzo secondo dal rilascio continua la stessa registrazione.
Una ripresa senza niente di usabile (un tocco, silenzio, una frase-fantasma)
non duplica il testo e non ferma il messaggio: il resto arriva e parte, e la
pill ti chiede di ripetere. Le destinazioni diverse restano separate. Un
guasto (motore in errore, audio interrotto) lascia disponibile il testo
valido e sospende l'Invio automatico per evitare una frase incompleta.
Contratto provato in `tests/test_mac.py` su entrambi i motori; la voce in
uscita resta bloccata fino alla conclusione del messaggio. Cantiere locale
12/09/2026: queste modifiche sono entrate nel rilascio successivo.

## Stato

Versione Windows brandizzata, allineata nell'aspetto e nel comportamento alla versione Mac (pill + marchio + sorriso, due tasti, voce agenti). L'aggiornamento conserva la configurazione personale e collega davvero la lettura delle risposte a Claude Code/Codex. Va provata su un PC Windows reale prima di considerarla stabile.

## Requisiti

- Windows 10 o 11 a 64 bit su processore Intel o AMD: il motore di trascrizione
  non esiste per Windows su ARM.
- 16 GB di memoria: il modello resta in memoria accanto alla tua AI.
- 10 GB liberi sul disco per la prima installazione (programmi e modello circa
  2 GB, piu' margine); 2 GB per un aggiornamento.
- Python 3.11 o successivo (quello di python.org va bene).
- Connessione internet al primo avvio per scaricare dipendenze e modello.

Il tuo agente controlla tutto prima di installare (Fase 0 in `INSTALLA_CON_AI.md`):
se il computer non va, te lo dice e non installa niente.

## Metodo unico: pacchetto da GitHub + installazione con Claude Code o Codex

Segui il percorso in:

```text
INSTALLA_CON_AI.md
```

L'agente scarica da https://github.com/salChiarenza/voce/releases/latest/download/Voce.zip
l'unico pacchetto Voce, lo estrae, entra nella cartella `windows/`, esegue `windows\install.bat` e continua
dalla cartella locale. Conserva glossario e preferenze, ripara la parte locale,
collega la voce delle risposte e chiude con una prova finale. Alla prima
installazione elenca e fa ascoltare le voci italiane gia' presenti, suggerisce
quella percepita come piu' naturale e salva la scelta del proprietario in
`voce_nome`.

Comandi usati dall'agente per la scelta guidata:

```text
voce_hook.py --list-voices
voce_hook.py --test-voice "NOME"
voce_hook.py --set-voice "NOME"
```

## Installazione

1. Apri Claude Code o Codex e dagli il link https://github.com/salChiarenza/voce/releases/latest/download/Voce.zip.
2. L'agente scarica il pacchetto Voce, lo estrae e sceglie `windows/`.
3. L'agente esegue `windows\install.bat` e legge `INSTALLA_CON_AI.md` nella cartella installata.
4. Concedi soltanto i permessi Windows richiesti e prova microfono, tasti e voce.
5. L'agente ripara gli errori recuperabili e chiude con il collaudo reale.

Il collegamento a Claude Code e' un comando lanciato senza shell (`command` +
`args` in `~/.claude/settings.json`): con Git Bash un percorso scritto come
stringa perde le barre rovesciate e il gancio non parte. `voce_hook.py
--check-hooks` lo avvia davvero (serve Claude Code 2.1.139 o piu' recente); il gancio scrive una riga a ogni fine risposta
in `voice_hook.log`, e quando accendi la voce, se il collegamento non parte, te
lo dice a voce.

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
5. Tieni premuto un secondo il tasto `Menu` per accendere o spegnere Voce AI, se configurata (un tocco non fa niente: `voce_tenuta_sec` in `config.json`, mai sotto mezzo secondo); all'accensione dichiara che le risposte sono audio sintetico.
6. Nella finestra **Voce AI**, menu **Voce**, in fondo: **Copia l’ultima dettatura** rimette
   negli Appunti l'ultimo testo incollato; **Ritrascrivi l’ultima** ritrascrive il suo audio
   col motore principale e il glossario, in un passaggio unico, e mette il risultato negli
   Appunti (la pill lo dice). Testo e audio stanno solo in memoria: dopo un riavvio non ci
   sono piu'.
7. `Esc` per buttare una dettatura: **spento di serie su Windows**. Con
   `"esc_annulla": true` in `config.json` e riavvio, Esc premuto mentre registri o prima
   che il testo compaia butta la dettatura (niente testo, niente Invio, la pill dice
   «Dettatura annullata») e in quel momento non arriva al programma davanti; appena il
   testo e' comparso torna il solito Esc. Ctrl sinistro, Alt e Win + Esc restano di
   Windows. Si accende ai clienti dopo la prova su un PC vero.

In basso compare la pill **LeaderAI.** (il punto verde cresce con la voce e pulsa mentre trascrive) con la barra verde a sorriso e il testo viene scritto dove hai il cursore. Per spegnerla, chiudi quella finestra.

In piu': glossario personale (`glossario` in `config.json`) e sostituzioni locali per scrivere correttamente nomi e brand. Il testo grezzo viene incollato subito: Claude Code e Codex non vengono chiamati durante la dettatura.

### L'orecchio: sente le persone, non i rumori

Un riconoscitore di voce umana (Silero VAD, lo stesso del Mac, idea presa dall'app open
source Handy) dice ogni 32 ms se c'e' una persona che parla. Prima di Whisper: se nella
registrazione non c'e' voce non si trascrive e non si incolla niente (la pill dice «Non ho
riconosciuto: ripeti.»); i silenzi lunghi si accorciano lasciando 450 ms prima e dopo ogni
voce. Il filtro delle frasi-fantasma e il filtro di faster-whisper restano come prima.

- Valori di Handy: soglia 0,3, 60 ms per dire «c'e' voce», 450 ms prima e dopo
  (`orecchio_soglia`, `orecchio_attacco_ms`, `orecchio_prima_ms`, `orecchio_dopo_ms`).
- Per tornare a prima: `"orecchio": false` in `config.json` e riavvio. Se il modello non
  si carica la Voce trascrive tutto l'audio come prima, e `voice.log` lo dice.
- In `voice.log`: all'avvio `orecchio: Silero VAD caricato`, a ogni dettatura
  `orecchio: voce, 8.1s -> 6.9s (15 ms)` oppure `orecchio: nessuna voce`.
- Serve `onnxruntime` (in `requirements.txt`, gia' usato da faster-whisper) e il modello
  `silero_vad.onnx` (Silero VAD v6.2.3, 2,3 MB, licenza MIT in `silero_vad_LICENSE.txt`),
  copiati dall'installer.

### Correzioni verificate

L'analisi delle dettature e il ripasso degli audio conservati lasciano solo
**proposte da verificare, non applicate** nel registro esistente. Il ripasso
non osserva le tue correzioni manuali; l'accordo fra modelli non basta a
stabilire cosa volevi dire.

Su tua richiesta l'agente confronta la frase originale con quella corretta,
usando l'audio conservato se disponibile o la tua conferma, e verifica che
la coppia non alteri altre frasi corrette. Solo allora aggiunge la coppia
all'elenco verificato `sostituzioni` di `config.json`. Per annullarla rimuove
quella coppia e riavvia Voce; il riavvio rende attive anche le aggiunte.

### Ascoltare e rileggere le risposte

La lettura separa titoli, elenchi e righe di tabella con pause; nei percorsi
pronuncia il nome del file e conserva numeri, importi e negazioni. I marcatori
della chat e i blocchi di codice non vengono pronunciati.

Quando inizi un nuovo turno, la voce in corso si ferma. Fino alla fine della
trascrizione e dell'Invio, una risposta precedente arrivata in ritardo viene
scartata: non puo' partire sopra la tua domanda ne' restare in coda dopo.

Nella finestra **Voce AI**, aprendo il menu **Voce**, trovi **Rileggi l’ultima risposta**, che riparte dall’inizio anche
dopo un’interruzione. Puoi ascoltare **tutte le conversazioni** oppure sceglierne
una dal nome e dall’anteprima. La scelta vale dalla lettura successiva e lascia
finire quella in corso. Le altre risposte restano in attesa; ogni conversazione
conserva soltanto la sua risposta piu’ recente ancora da ascoltare.

La coda conserva sul computer fino a otto conversazioni recenti. Quando le
ascolti tutte, il riascolto recupera l’ultima risposta iniziata; quando ne scegli
una, recupera l’ultima di quella conversazione. Gli annunci degli interruttori
non sostituiscono l’ultima risposta dell’agente.

### La voce legge mentre l'agente scrive

Con la voce accesa, Claude Code viene letto **un blocco alla volta**, appena
l'agente lo ha scritto, e non solo a lavoro finito. A farlo e' l'app (con
`voce_hook.py` accanto), che segue in sola lettura i registri locali di Claude
Code (`%USERPROFILE%\.claude\projects`); legge solo le chat in cui parli con
l'agente, non le automazioni di sfondo. Parla solo a voce accesa e non rilegge il
passato. Il gancio di fine risposta resta e non rilegge cio' che e' gia' stato
letto (`LETTI_DAL_REGISTRO`, due minuti). Codex non ha questo registro: li' la voce
parte alla fine della risposta. Per spegnerla: `"voce_mentre_scrive": false`
in `config.json` e riavvio dell'app.

### Se un messaggio dettato non arriva

Dopo l'Invio automatico verso Claude Code (l'app «Claude», non il browser),
l'app controlla nel registro che il messaggio sia arrivato (fino a 3 secondi).
Se manca, ripreme Invio; se manca ancora, reincolla e invia di nuovo. Interviene
solo se quell'app aveva gia' consegnato un messaggio visto nel registro nell'ultima
mezz'ora, se e' ancora davanti e se non hai ripreso la tastiera; altrimenti scrive
l'esito in `voice.log` (`consegna: ...`). Si spegne con `"verifica_consegna": false`.

## Privacy

La dettatura gira localmente sul PC. Il progetto non invia le tue dettature a Sal Chiarenza, LeaderAI o server esterni di questo progetto. Vedi `PRIVACY.md`.

Leggi `PRIVACY.md`.

## Limiti

- Versione beta.
- Orecchio, Esc e menu delle ultime dettature (31/10/2026) sono provati solo con prove
  automatiche, non ancora su un PC Windows vero; per questo Esc e' spento di serie.
- Supporto individuale non incluso.
- Le difese di memoria di Voce (modello fisso in RAM, riavvio da sola se rallenta, motore leggero sui Mac piccoli) per ora ci sono solo su Mac.
- Primo avvio piu' lento: il modello di trascrizione viene scaricato e caricato.
- Con meno di 6 GB di memoria Voce sceglie da sola il modello `small` invece di
  `medium` e lo scrive in `voice.log` (e' l'unica difesa di memoria che c'e' su
  Windows); `memoria_minima_modello_gb` a 0 in
  `config.json` tiene sempre `medium`.
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
Il modello `silero_vad.onnx` e' © Silero Team, con licenza MIT
(https://github.com/snakers4/silero-vad, testo in `silero_vad_LICENSE.txt`).
