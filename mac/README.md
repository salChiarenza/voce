# Voce LeaderAI per Mac

Dettatura locale per Mac: tieni premuto un tasto, parli, rilasci, e il testo viene scritto dove hai il cursore.

Risorsa della community **AI con Sal**.

La versione esatta è nel file `../VERSION` e viene copiata nella cartella
installata.


## Riprendere mentre trascrive

Puoi rilasciare il tasto e ripremerlo mentre compare «Trascrivo…»: i pezzi
restano nello stesso messaggio, nell'ordine in cui li hai dettati. L'Invio
aspetta tutte le registrazioni e tutte le trascrizioni, anche se l'ultimo
pezzo finisce prima del primo. Se riprendi quando il testo e' gia' incollato,
si sospende l'Invio e la nuova frase si aggiunge con lo spazio necessario.
La registrazione parte da quando premi, anche se il Mac sta ancora
trascrivendo; se ripremi entro mezzo secondo dal rilascio continua la stessa.
Una ripresa senza niente di usabile (un tocco, silenzio, una frase-fantasma)
non duplica il testo e non ferma il messaggio: il resto arriva e parte, e la
pill ti chiede di ripetere. Le destinazioni diverse restano separate. Un
guasto (motore in errore, audio interrotto) lascia disponibile il testo
valido e sospende l'Invio automatico per evitare una frase incompleta.
Contratto provato in `tests/test_mac.py` su entrambi i motori; la voce in
uscita resta bloccata fino alla conclusione del messaggio. Cantiere locale
12/09/2026: queste modifiche sono entrate nel rilascio successivo.

## Cosa fa

- Detti testo in email, documenti, browser, ChatGPT, Claude, Codex e app simili.
- Usa una piccola barra verde mentre ascolta.
- Gira sul Mac con trascrizione locale.
- Glossario personale: i tuoi nomi e brand escono scritti giusti (`glossario` in `config.json`).
- Detta pulito (opzionale): fuori dalle chat AI, il Comando Rapido Apple prova
  per massimo 2 secondi a sistemare punteggiatura e ripensamenti. Se fallisce,
  arriva subito il grezzo. In ChatGPT, Claude e Codex la pulizia viene sempre
  saltata; l'agente non viene mai avviato durante una dettatura.
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
- macOS 14 o successivo.
- 16 GB di memoria: il modello resta in memoria accanto alla tua AI.
- 10 GB liberi sul disco per la prima installazione (programmi 1,3 GB, modello
  1,5 GB fino a 16 GB di memoria oppure 2,9 GB oltre); 2 GB per un aggiornamento.
- Python 3.11 o successivo, nativo (quello di python.org va bene).
- Connessione internet al primo avvio per scaricare dipendenze e modello di trascrizione.

`./voce diagnosi` controlla tutto in sola lettura, anche dal pacchetto appena
estratto: dice se la Voce va per questo computer e, se no, perche'. L'installer
fa lo stesso controllo e non parte se un requisito manca.

Il primo download puo' essere pesante: il modello Whisper viene scaricato una volta, poi resta sul computer.

## Installazione

### Metodo unico: pacchetto da GitHub + installazione con Claude Code o Codex

Segui il percorso in:

```text
INSTALLA_CON_AI.md
```

Il tuo agente scarica l'unico pacchetto Mac + Windows da
https://github.com/salChiarenza/voce/releases/latest/download/Voce.zip, sceglie
`mac/`, esegue `mac/install.sh` e continua dalla cartella locale. Conserva cio'
che hai personalizzato, ripara la parte locale, collega la voce e chiude con
una prova finale.

L'installer applica la fotocopia funzionale di Sal e conserva glossario,
sostituzioni apprese e preferenza di log. macOS chiede un solo gesto umano:
quando si apre Comandi Rapidi, clicca **Aggiungi comando rapido**. L'agente
esegue poi `voce_hook.py --check-profile` e chiude solo con
`FOTOCOPIA_SAL_OK` e una prova audio reale.

### Installazione

1. Apri Claude Code o Codex e dagli il link https://github.com/salChiarenza/voce/releases/latest/download/Voce.zip.
2. L'agente scarica il pacchetto Voce, lo estrae e sceglie `mac/`.
3. L'agente esegue `mac/install.sh` e legge `INSTALLA_CON_AI.md` nella cartella installata.
4. Concedi soltanto i permessi macOS richiesti e prova microfono, tasti e voce.
5. L'agente ripara gli errori recuperabili e chiude con il collaudo reale.

L'installer crea la cartella:

```text
~/VoiceDettaturaMac
```

e aggiunge due launcher sulla Scrivania:

- `Voce Dettatura.command`: riavvia il servizio della Voce;
- `Voce Attiva Tutto.command`: avvia Voce se serve e commuta insieme voce agenti e
  mani libere, come il controllo rapido usato da Sal.

I due launcher aprono per un attimo una finestra del Terminale e la richiudono da soli.

## La Voce e' un servizio di macOS

Voce non vive in una finestra del Terminale: e' un servizio dell'utente (LaunchAgent
`~/Library/LaunchAgents/com.leaderai.voce.plist`) che macOS avvia all'accesso e rilancia
da solo se si ferma. Non apre mai finestre, per nessuno: ne' per te, ne' per un agente.

- **Riavvio: `./voce riavvia`** (dalla cartella installata). La prima volta crea app e servizio;
  poi riavvia il servizio, controlla che non stia partendo una dettatura, e stampa nuovo PID,
  riga «avvio dettatura» nel registro e tastiera attiva.
- **L'app «Voce LeaderAI»** (`~/Applications/Voce LeaderAI.app`) e' un piccolo lanciatore
  compilato con firma ad-hoc: macOS attribuisce a lei i permessi. Il servizio avvia l'app, e
  l'app avvia il Python della `.venv` con `detta.py` dal suo percorso.
- **L'app non si ricompila a ogni modifica della Voce.** Il codice sta in `detta.py` e negli altri
  file, fuori dall'app: aggiornarli (anche con un nuovo pacchetto) non tocca l'app, quindi i permessi
  restano. Si ricrea solo se manca o la firma non regge, e in quel caso i permessi vanno
  concessi di nuovo.
- **Permessi:** `./voce permessi` porta a schermo le richieste di macOS per «Voce LeaderAI»
  (Microfono: OK; Accessibilita' e Monitoraggio input: «Apri Impostazioni di Sistema» e accendi
  «Voce LeaderAI»). `./voce permessi stato` legge e basta.
- **Riavvii interni:** se la Voce deve ripartire (audio incantato, cambio microfono, memoria),
  esce e launchd la rilancia: una sola istanza.
- **Fermarla davvero:** `launchctl bootout gui/$(id -u)/com.leaderai.voce`; tornera' all'accesso
  successivo o con `./voce riavvia`.

## Uso rapido

### Correzioni delle parole

Il glossario aiuta il riconoscitore a scrivere i nomi. Le `sostituzioni`
sono invece regole globali: una coppia si applica a ogni dettatura. Il
controllo giornaliero e il ripasso audio propongono correzioni nel registro
esistente (`voce.log`, righe `proposte da verificare, non applicate`), senza
attivarle o riscrivere il profilo. Sono diagnosi recenti, soggette alla normale
rotazione del registro; non osservano le correzioni manuali del proprietario.

Per aggiungere una correzione, il proprietario indica all'agente la frase
dettata e quella desiderata. L'agente verifica la coppia nel contesto e su
frasi corrette: articoli, pronomi, genere dei verbi e parole valide in altri
contesti non diventano regole globali. Solo la coppia verificata e confermata
va in `sostituzioni`, nel profilo esistente; gli altri valori si conservano.
Per annullarla si elimina quella sola coppia. Prima di renderla attiva si
ricontrolla il testo con la mappa aggiornata; poi si riavvia con `./voce riavvia`. La verifica del ripasso, anche
quando due modelli concordano, non sostituisce questa prova.

### Dettare

1. La Voce e' gia' attiva (parte da sola all'accesso); se non risponde, `./voce riavvia`.
2. Tieni premuto `Cmd destro`.
3. Parla.
4. Rilascia il tasto.

Il testo viene scritto dove hai il cursore.

- `Option + freccia sinistra` tenuti premuti per un secondo: accendono o spengono Voce AI; all'accensione dichiara che le risposte sono audio sintetico. Un tocco non fa niente, apposta: Option + freccia serve anche a spostarsi di parola mentre scrivi (`voce_tenuta_sec` in `config.json`, mai sotto mezzo secondo).
- `Cmd destro + Option`: accende o spegne la modalità mani libere. Con le mani libere la Voce
  scrive e invia da sola tutto quello che sente; si spengono con lo stesso gesto, con
  `./voce mani off`, oppure da sole dopo 10 minuti senza testi incollati (anche col rumore).
- `Esc` mentre registri, o finche' il testo non e' comparso: butta la dettatura. Niente
  testo, niente Invio, la pill dice «Dettatura annullata». In quel momento Esc non arriva
  all'app davanti (in Claude non ferma l'agente); appena il testo e' comparso torna il
  solito Esc. Si spegne con `"esc_annulla": false` in `config.json`.
- Menu **Voce** in alto, in fondo: **Copia l’ultima dettatura** rimette negli Appunti
  l'ultimo testo incollato; **Ritrascrivi l’ultima** ritrascrive il suo audio col motore
  principale e il glossario, in un passaggio unico, e mette il risultato negli Appunti (la
  pill lo dice). Testo e audio stanno solo in memoria: dopo un riavvio non ci sono piu'.
- `./voce grinch on|off`: mostra o nasconde la mascotte accanto alla pill
  (solo se in `config.local.json` c'è la chiave `mascotte` con un PNG; di
  serie non c'è e la pill resta com'è).
- `Voce Attiva Tutto.command`: controllo rapido per accendere o spegnere voce
  agenti e mani libere insieme.

### L'orecchio: sente le persone, non i rumori

Un riconoscitore di voce umana (Silero VAD, idea presa dall'app open source Handy) dice
ogni 32 ms se c'e' una persona che parla. Il volume da solo non lo sa: una porta, la
tastiera o una ventola lo alzano uguale, e su quei secondi Whisper scriveva «Grazie.».

- **Mani libere:** partono con 60 ms di voce e si fermano dopo `mani_libere_silenzio_sec`
  senza voce. Un rumore forte non le accende, una voce piano si'.
- **Prima di Whisper:** se nella registrazione non c'e' voce non si trascrive e non si
  incolla niente (la pill dice «Non ho riconosciuto: ripeti.»). I silenzi lunghi si
  accorciano lasciando 450 ms prima e dopo ogni voce: nessuna parola tagliata. Il filtro
  delle frasi-fantasma resta come seconda rete.
- Valori di Handy, gia' scritti nel codice: soglia 0,3, 60 ms per dire «c'e' voce», 450 ms
  prima e dopo (`orecchio_soglia`, `orecchio_attacco_ms`, `orecchio_prima_ms`,
  `orecchio_dopo_ms` in `config.json` per cambiarli).
- **Per tornare a prima:** `"orecchio": false` in `config.json` e `./voce riavvia` (mani
  libere a volume, Whisper su tutto l'audio). Se il modello non si carica la Voce fa
  da sola lo stesso, e il registro lo dice.
- Nel registro: all'avvio `orecchio: Silero VAD caricato`, a ogni dettatura
  `orecchio: voce, 8.1s -> 6.9s (15 ms)` oppure `orecchio: nessuna voce`.
- Serve `onnxruntime` (in `requirements.txt`, niente torch) e il modello
  `silero_vad.onnx` (Silero VAD v6.2.3, 2,3 MB, licenza MIT in `silero_vad_LICENSE.txt`).

## Permessi macOS

macOS puo' chiedere:

- Microfono
- Accessibilita'
- Monitoraggio input

Sono permessi necessari per ascoltare la voce, leggere la scorciatoia da tastiera e incollare il testo.
Vanno concessi all'app **«Voce LeaderAI»** (non al Terminale, non a Python): `./voce permessi`.

### Ascoltare e rileggere le risposte

La lettura separa titoli, elenchi e righe di tabella con pause; nei percorsi
pronuncia il nome del file e conserva numeri, importi e negazioni. I marcatori
della chat e i blocchi di codice non vengono pronunciati.

Quando inizi un nuovo turno, la voce in corso si ferma. Fino alla fine della
trascrizione e dell'Invio, una risposta precedente arrivata in ritardo viene
scartata: non puo' partire sopra la tua domanda ne' restare in coda dopo.

Nel menu **Voce** nella barra in alto trovi **Rileggi l’ultima risposta**, che riparte dall’inizio anche
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
l'agente lo ha scritto, e non solo a lavoro finito: un testo scritto prima di
un lavoro lungo si sente subito, non dopo dieci minuti. A farlo e' l'app Voce
(`voce_hook.SeguiRegistro`), che segue in sola lettura i registri locali di Claude
Code (`~/.claude/projects`). Legge solo le chat in cui stai parlando con
l'agente: le automazioni e le attivita' pianificate di sfondo restano mute.

- Stesso interruttore di sempre: parla solo a voce accesa; accenderla non rilegge
  il passato.
- Il gancio di fine risposta resta e non rilegge cio' che e' gia' stato letto
  (si accordano su `LETTI_DAL_REGISTRO`, due minuti). Con Codex e Antigravity, che
  non hanno questo registro, la voce parte come prima, alla fine della risposta.
- Per spegnerla: `"voce_mentre_scrive": false` in `config.json` e `./voce riavvia`.
- Il registro non ha mai testo a meta': la voce non puo' partire prima che un
  blocco sia finito. Blocchi brevi, prima di ogni lavoro, la fanno sentire meglio.

### Se un messaggio dettato non arriva

Dopo l'Invio automatico verso Claude Code, Voce controlla nel registro che il
messaggio sia arrivato (fino a 3 secondi). Se manca, ripreme Invio; se manca
ancora, reincolla il testo e invia di nuovo. Vale per la dettatura a tasto
premuto e per le mani libere. Per non mandare un messaggio doppio, Voce
interviene solo se: l'app aveva gia' consegnato un messaggio visto nel registro
nell'ultima mezz'ora (`verifica_consegna_storico_min`), Claude e' ancora davanti e tu non hai ripreso
la tastiera ne' stai dettando. In caso contrario scrive soltanto l'esito nel log
(`consegna: ...`). Controlla solo l'app indicata in `verifica_consegna_app`
(di serie `Claude`); si spegne con `"verifica_consegna": false`.

## Se la Voce è lenta

Una dettatura che passa da 1-3 secondi a 15 o più quasi sempre non è colpa di
Voce: un altro programma occupa la memoria del Mac, spesso un calcolo
abbandonato da un agente, e macOS manda il modello su disco.

L'AI del proprietario:

1. guarda chi occupa la memoria: `top -l 1 -o mem -n 10`;
2. se è un calcolo rimasto aperto da un agente e nessuna sessione lo usa più, lo chiude;
3. altrimenti dice al proprietario, in una riga, quale programma chiudere.

Voce si riavvia da sola se resta lenta. Sui Mac con 16 GB di RAM o meno usa già
da sola il motore leggero; se serve un altro motore, `modello` in
`config.local.json` comanda sempre. Il motore scelto è scritto in `voce.log`.

## Privacy

La dettatura gira localmente sul Mac. Il progetto non invia le tue dettature a Sal Chiarenza o LeaderAI. La pulizia opzionale usa Apple Intelligence secondo la configurazione del Comando Rapido; dettagli in `PRIVACY.md`.

Leggi anche `PRIVACY.md`.

## Limiti

- Versione sperimentale.
- Supporto individuale non incluso.
- Pensata per Mac Apple Silicon.
- Se qualcosa non funziona, segnala il problema nella community AI con Sal indicando modello Mac, versione macOS e passaggio bloccato.

## Disinstallazione

Ferma il servizio, poi cancella:

```text
launchctl bootout gui/$(id -u)/com.leaderai.voce
~/Library/LaunchAgents/com.leaderai.voce.plist
~/Applications/Voce LeaderAI.app
~/VoiceDettaturaMac
~/Desktop/Voce Dettatura.command
~/Desktop/Voce Attiva Tutto.command
```

## Licenza

MIT. Vedi `LICENSE`.
Il carattere del logo `Onest.ttf` e' © The Onest Project Authors, con licenza
SIL Open Font License 1.1 (https://openfontlicense.org).
Il modello `silero_vad.onnx` e' © Silero Team, con licenza MIT
(https://github.com/snakers4/silero-vad, testo in `silero_vad_LICENSE.txt`).
