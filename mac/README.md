# Voce LeaderAI per Mac

Dettatura locale per Mac: tieni premuto un tasto, parli, rilasci, e il testo viene scritto dove hai il cursore.

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
- macOS recente.
- Python 3 disponibile sul Mac.
- Connessione internet al primo avvio per scaricare dipendenze e modello di trascrizione.

Il primo download puo' essere pesante: il modello Whisper viene scaricato una volta, poi resta sul computer.

## Installazione

### Metodo unico: pacchetto LeaderAI + installazione con Claude Code o Codex

Segui il percorso in:

```text
INSTALLA_CON_AI.md
```

Il tuo agente prende dal modulo App l'unico pacchetto Mac + Windows, sceglie
`mac/`, esegue `mac/install.sh` e continua dalla cartella locale. Conserva cio'
che hai personalizzato, ripara la parte locale, collega la voce e chiude con
una prova finale.

L'installer applica la fotocopia funzionale di Sal e conserva glossario,
sostituzioni apprese e preferenza di log. macOS chiede un solo gesto umano:
quando si apre Comandi Rapidi, clicca **Aggiungi comando rapido**. L'agente
esegue poi `voce_hook.py --check-profile` e chiude solo con
`FOTOCOPIA_SAL_OK` e una prova audio reale.

### Installazione

1. Apri Claude Code o Codex e fagli leggere l'email di consegna.
2. L'agente apre il pacchetto Voce collegato nel modulo App e sceglie `mac/`.
3. L'agente esegue `mac/install.sh` e legge `INSTALLA_CON_AI.md` nella cartella installata.
4. Concedi soltanto i permessi macOS richiesti e prova microfono, tasti e voce.
5. L'agente ripara gli errori recuperabili e chiude con il collaudo reale.

L'installer crea la cartella:

```text
~/VoiceDettaturaMac
```

e aggiunge due launcher sulla Scrivania:

- `Voce Dettatura.command`: avvio semplice della dettatura;
- `Voce Attiva Tutto.command`: avvia Voce e commuta insieme voce agenti e
  mani libere, come il controllo rapido usato da Sal.

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
ricontrolla il testo con la mappa aggiornata; poi si riavvia dal launcher o
da Terminal con i permessi gia' concessi. La verifica del ripasso, anche
quando due modelli concordano, non sostituisce questa prova.

### Dettare

1. Apri `Voce Dettatura.command`.
2. Tieni premuto `Cmd destro`.
3. Parla.
4. Rilascia il tasto.

Il testo viene scritto dove hai il cursore.

- `Option + freccia sinistra`: accende o spegne Voce AI; all'accensione dichiara che le risposte sono audio sintetico.
- `Cmd destro + Option`: accende o spegne la modalità mani libere.
- `Voce Attiva Tutto.command`: controllo rapido per accendere o spegnere voce
  agenti e mani libere insieme.

## Permessi macOS

macOS puo' chiedere:

- Microfono
- Accessibilita'
- Monitoraggio input

Sono permessi necessari per ascoltare la voce, leggere la scorciatoia da tastiera e incollare il testo.

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

## Privacy

La dettatura gira localmente sul Mac. Il progetto non invia le tue dettature a Sal Chiarenza o LeaderAI. La pulizia opzionale usa Apple Intelligence secondo la configurazione del Comando Rapido; dettagli in `PRIVACY.md`.

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
Il carattere del logo `Onest.ttf` e' © The Onest Project Authors, con licenza
SIL Open Font License 1.1 (https://openfontlicense.org).
