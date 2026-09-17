# Voce LeaderAI per Windows (candidata)

Dettatura locale per Windows: tieni premuto `Ctrl destro`, parli, rilasci, e il testo viene scritto dove hai il cursore.

Mentre parli, in basso al centro compare la pill **salchiarenza.ai** con la barra di lineette verdi ad arco "a sorriso" che si muovono col volume. L'overlay non ruba il focus: continui a scrivere dove sei.

Risorsa gratuita per la community **AI con Sal**.

La versione esatta è nel file `../VERSION` e viene copiata nella cartella
installata.


## Riprendere mentre trascrive

Puoi rilasciare il tasto e ripremerlo mentre compare «Trascrivo…»: i pezzi
restano nello stesso messaggio, nell'ordine in cui li hai dettati. L'Invio
aspetta tutte le registrazioni e tutte le trascrizioni, anche se l'ultimo
pezzo finisce prima del primo. Se riprendi quando il testo e' gia' incollato,
si sospende l'Invio e la nuova frase si aggiunge con lo spazio necessario.
Un tocco senza parole non duplica il testo e non lascia sospeso il messaggio.
Le destinazioni diverse restano separate. Un errore lascia disponibile il
testo valido e sospende l'Invio automatico per evitare una frase incompleta.
Contratto provato in `tests/test_mac.py` su entrambi i motori; la voce in
uscita resta bloccata fino alla conclusione del messaggio. Cantiere locale
12/09/2026: queste modifiche entrano in Drive col prossimo rilascio.

## Stato

Versione Windows brandizzata, allineata nell'aspetto e nel comportamento alla versione Mac (pill + marchio + sorriso, due tasti, voce agenti). L'aggiornamento conserva la configurazione personale e collega davvero la lettura delle risposte a Claude Code/Codex. Va provata su un PC Windows reale prima di considerarla stabile.

## Metodo unico: pacchetto LeaderAI + installazione con Claude Code o Codex

Segui il percorso in:

```text
INSTALLA_CON_AI.md
```

L'agente prende dal collegamento Google Drive del modulo App l'unico pacchetto
Voce, entra nella cartella `windows/`, esegue `windows\install.bat` e continua
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

1. Apri Claude Code o Codex e fagli leggere l'email di consegna.
2. L'agente apre il pacchetto Voce collegato nel modulo App e sceglie `windows/`.
3. L'agente esegue `windows\install.bat` e legge `INSTALLA_CON_AI.md` nella cartella installata.
4. Concedi soltanto i permessi Windows richiesti e prova microfono, tasti e voce.
5. L'agente ripara gli errori recuperabili e chiude con il collaudo reale.

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
5. Usa il tasto `Menu` per accendere o spegnere Voce AI, se configurata; all'accensione dichiara che le risposte sono audio sintetico.

In basso compare la pill **salchiarenza.ai** con la barra verde a sorriso e il testo viene scritto dove hai il cursore. Per spegnerla, chiudi quella finestra.

In piu': glossario personale (`glossario` in `config.json`) e sostituzioni locali per scrivere correttamente nomi e brand. Il testo grezzo viene incollato subito: Claude Code e Codex non vengono chiamati durante la dettatura.

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
