# Email di consegna Voce

Questa e' la fonte unica del testo usato per consegnare Voce a un cliente.
L'installer e l'email evolvono insieme: ogni cambiamento che tocca il modo di
arrivare sul computer del cliente, il launcher, i permessi, la cartella locale
o il collaudo aggiorna anche questo file nello stesso commit.

La cronologia Git conserva i miglioramenti. I dati del singolo cliente restano
nel testo mostrato a Sal e nella copia Gmail inviata.

## Regola fissa: consegna gestita dall'agente

Voce arriva sul computer del cliente attraverso il suo agente, che prende la
struttura dalla repo pubblica ed esegue l'installer. Il proprietario dà le
conferme di sistema e fa la prova con il microfono.

La consegna chiude sempre allo stesso modo: l'agente del cliente legge
`INSTALLA_CON_AI.md` nella cartella installata, completa la missione di
diagnosi e collaudo e mostra una sola conferma finale riuscita.

## Dati da compilare e verificare

Prima di mostrare l'email a Sal, sostituisci tutti i campi tra parentesi quadre:

- `[NOME]`: nome del destinatario;
- `[EMAIL_DESTINATARIO]`: indirizzo verificato del destinatario;
- `[AGENTE_CLIENTE]`: Claude Code oppure Codex, verificato sul computer;
- `[CARTELLA_MADRE]`: cartella dell'Ecosistema del cliente, letta dal suo
  stato o da un suo rapporto, in forma portabile;
- `[FIRMA_AGENTE]`: agente LeaderAI che ha preparato e verificato la consegna.

Percorsi standard:

- Windows: `%USERPROFILE%\VoiceDettaturaWindows`;
- Mac: `~/VoiceDettaturaMac`.

Un percorso personalizzato entra nell'email dopo una verifica sul computer o in
un rapporto precedente del cliente.

## Formato di invio

Il blocco email e' scritto in Markdown ed e' la fonte unica per entrambe le
parti del messaggio:

- il corpo HTML e il fallback `text/plain` nascono dallo stesso testo;
- il connettore Gmail riceve il blocco Markdown;
- `tools/gmail/gmail_send.py` riceve insieme `--body-file` e `--html-file`;
- il comando che il cliente incolla nel suo agente resta testo semplice, uguale
  in entrambe le parti, così si copia senza sorprese di formattazione;
- il comando da incollare sta fra due righe di trattini e contiene soltanto le
  istruzioni dirette all'agente. Le frasi rivolte alla persona restano fuori dal
  blocco, così il confine di cosa copiare resta visibile a occhio.

Prima della composizione apri `commerciale/INDEX.md`, lo stato del cliente e
verifica quale agente tiene il filo. Cerca poi Gmail con:

```text
in:sent newer_than:1d to:[EMAIL_DESTINATARIO]
```

Confronta oggetto, sistema, versione e scopo. Il nuovo invio parte quando la
ricerca conferma che quella consegna e' ancora da eseguire.

## Email Windows

**Oggetto prima consegna:** `Voce Windows: installazione guidata`

**Oggetto per una versione corretta:** `Voce Windows: istruzioni aggiornate`

```text
Ciao [NOME],

installiamo Voce: parli e il testo si scrive da solo, dentro [AGENTE_CLIENTE] e
in qualsiasi finestra.

Apri [AGENTE_CLIENTE] nella cartella [CARTELLA_MADRE] e copia soltanto il testo
fra le due righe:

------------------------------------------------------------
Installa o aggiorna Voce LeaderAI dalla repo pubblica
https://github.com/salChiarenza/voce, usando la cartella windows. Leggi prima
AGENTS.md e poi windows/INSTALLA_CON_AI.md. Esegui tu diagnosi, installazione,
riparazione e prova reale. Quando trovi un errore del software, applica una
correzione locale sicura, ripeti la prova e prosegui.

La prova finale comprende tutto: l'icona apre Voce; Ctrl destro scrive il
parlato; il pannello salchiarenza.ai si vede; il suono di avvio e fine
dettatura si sente; il tasto Menu attiva la voce; una risposta completa
dell'agente viene letta ad alta voce.

Con una prova ancora aperta, continua nella stessa missione. Chiedimi soltanto
il gesto fisico o la conferma di Windows che serve, poi riprendi subito. Chiudi
con una sola conferma finale quando tutte le prove funzionano davvero. Salva le
prove sul mio computer e archivia questa email.
------------------------------------------------------------

[AGENTE_CLIENTE] gestisce tutto il lavoro. Tieni il microfono collegato e resta
disponibile per le conferme di Windows che ti chiedera' lui.

A presto,

Sal & [FIRMA_AGENTE]
```

## Email Mac

**Oggetto prima consegna:** `Voce Mac: installazione guidata`

**Oggetto per una versione corretta:** `Voce Mac: istruzioni aggiornate`

```text
Ciao [NOME],

installiamo Voce: parli e il testo si scrive da solo, dentro [AGENTE_CLIENTE] e
in qualsiasi finestra.

Apri [AGENTE_CLIENTE] nella cartella [CARTELLA_MADRE] e copia soltanto il testo
fra le due righe:

------------------------------------------------------------
Installa o aggiorna Voce LeaderAI dalla repo pubblica
https://github.com/salChiarenza/voce, usando la cartella mac. Leggi prima
AGENTS.md e poi mac/INSTALLA_CON_AI.md. Esegui tu diagnosi, installazione,
riparazione e prova reale. Quando trovi un errore del software, applica una
correzione locale sicura, ripeti la prova e prosegui.

La prova finale comprende tutto: i pulsanti sulla Scrivania aprono Voce; Cmd
destro scrive il parlato; il pannello salchiarenza.ai si vede; il suono di
avvio e fine dettatura si sente; Option + freccia sinistra attiva la voce; Cmd
destro + Option attiva le mani libere; una risposta completa dell'agente viene
letta ad alta voce.

Con una prova ancora aperta, continua nella stessa missione. Chiedimi soltanto
il gesto fisico o l'autorizzazione del Mac che serve, poi riprendi subito.
Chiudi con una sola conferma finale quando tutte le prove funzionano davvero.
Salva le prove sul mio computer e archivia questa email.
------------------------------------------------------------

[AGENTE_CLIENTE] gestisce tutto il lavoro. Tieni il microfono collegato e resta
disponibile per le autorizzazioni del Mac che ti chiedera' lui.

A presto,

Sal & [FIRMA_AGENTE]
```

## Prova di leggibilita' (gate, precede ogni altro controllo)

L'email di consegna separa due livelli: fuori dal blocco la persona vede in una
schermata cosa ottiene, cosa deve fare e cosa le serve; dentro il blocco
l'agente riceve i criteri completi di riuscita. Il testo da copiare e'
delimitato da due righe. I passaggi tecnici vivono in
`INSTALLA_CON_AI.md` dentro la repo, dove li legge l'agente. Lo stesso agente
prosegue fino alla prova finale: il cliente non riceve un secondo messaggio da
copiare durante il lavoro. La parola `finito` vale soltanto quando tutte le
funzioni visibili al cliente sono state provate nella condizione reale.

Prima di ogni invio rispondi a queste tre domande guardando il testo finito:

1. Il destinatario capisce al primo colpo qual e' il suo unico gesto?
2. Le frasi rivolte al destinatario, fuori dal blocco, stanno in una schermata?
3. Il confine del testo da copiare si vede senza doverlo interpretare?
4. Ogni riga aggiunta serve alla persona, oppure ripete quello che l'agente
   trova gia' nella repo?
5. Icona o pulsanti, dettatura, pannello, suoni e risposta letta ad alta voce
   compaiono tutti nella prova finale?

Una risposta negativa si corregge tagliando. I passaggi tecnici delle consegne
passate entrano in `INSTALLA_CON_AI.md` e nell'installer; nell'email restano il
gesto del cliente e le prove visibili che definiscono la chiusura.

## Controllo prima dell'invio

1. Apri `commerciale/INDEX.md`, lo stato cliente e identifica l'agente che
   tiene il filo.
2. Cerca `in:sent newer_than:1d to:[EMAIL_DESTINATARIO]` e confronta oggetto,
   sistema, versione e scopo.
3. Apri lo stato corrente della repo e scegli Windows oppure Mac.
4. Pubblica su `main` la versione da consegnare: quello che il cliente riceve
   e' il contenuto pubblico della repo in quel momento.
5. Leggi la cartella madre del cliente dal suo stato o da un suo rapporto e
   scrivila in forma portabile.
6. Clona la repo pubblica senza credenziali, come fa il cliente, e verifica che
   il launcher e `INSTALLA_CON_AI.md` siano presenti nella cartella del sistema
   scelto.
7. Prova il primo avvio sul sistema previsto oppure dichiara nella scheda del
   cliente cosa resta in carico all'agente del destinatario.
8. Registra `PROVA_DESTINATARIO_OK`.
9. Esegui o aggiorna il controllo AI Act del prodotto: registra ruolo, livello
   di rischio, obblighi di trasparenza e presidio applicato. Registra
   `AI_ACT_CHECK_OK` solo dopo l'esito.
10. Compila tutti i campi del modello e rileggi ogni percorso e ogni comando.
11. Genera HTML e fallback testuale dalla stessa fonte; il comando da incollare
    resta testo semplice e identico nelle due parti.
12. Controlla `tu`, frasi affermative, firma a due nomi e zero em dash.
13. Mostra a Sal destinatario, oggetto e testo integrale.
14. Dopo il suo comando di invio, registra `INVIO_OK` e manda una sola nuova
    email con oggetto autonomo.
15. Rileggi la copia in Sent e conferma una sola nuova email per quella
    consegna.
16. Applica la label `Clienti`, aggiorna la scheda del cliente e verifica la
    sua Inbox.

## Miglioramento continuo

Quando una consegna incontra un ostacolo:

1. raccogli la prova reale, come messaggio, screenshot o codice di uscita;
2. identifica il punto proprietario: email, launcher, installer, istruzioni
   locali oppure ambiente del cliente;
3. correggi il punto proprietario e aggiorna questo file quando cambia
   l'esperienza del destinatario;
4. aggiorna i changelog Mac e Windows;
5. ripeti il percorso completo del destinatario;
6. pubblica su `main` e riparti dalla repo pubblica nell'invio successivo.
