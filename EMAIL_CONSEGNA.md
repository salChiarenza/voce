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
- `[CARTELLA_LOCALE]`: percorso creato dall'installer;
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
  in entrambe le parti, così si copia senza sorprese di formattazione.

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

con questa email attivi Voce su Windows: parli e il testo si scrive da solo,
dentro [AGENTE_CLIENTE] e in qualsiasi finestra. Il lavoro lo fa il tuo
[AGENTE_CLIENTE], tu confermi e provi il microfono.

Apri [AGENTE_CLIENTE] nella cartella [CARTELLA_MADRE] e incolla questo
messaggio:

Installa Voce LeaderAI su questo computer Windows.

Prendi la struttura dalla repo pubblica salChiarenza/voce con questo comando,
dentro la cartella madre:
git clone https://github.com/salChiarenza/voce.git "[CARTELLA_MADRE]\voce"

Poi esegui windows\install.bat da quella cartella e resta sulla finestra fino
al messaggio "Installazione completata". L'installazione crea la cartella
[CARTELLA_LOCALE] e aggiunge l'icona Voce Dettatura sulla Scrivania.

Leggi integralmente INSTALLA_CON_AI.md che trovi nella cartella windows e
completa la sezione "Missione locale di diagnosi e collaudo".

Guidami soltanto nei gesti fisici e nelle conferme di Windows. Verifica Git,
Python e gli altri componenti richiesti, installa da solo quello che serve e
riprendi da dove ti eri fermato. Quando Windows o l'antivirus chiedono
un'autorizzazione, dimmi con precisione cosa devo confermare.

Chiudi mostrando a me il risultato: icona, Ctrl destro che avvia la dettatura,
pannello salchiarenza.ai, tasto Menu, voce italiana e una risposta letta
davvero ad alta voce. Apri con "Perfetto, l'ho fatto. Tutto completato e
funzionante.", poi archivia questa email.

Da li' in poi detti tenendo premuto il Ctrl di destra: parli, rilasci, il testo
compare dove stai scrivendo. Se usi Codex, durante il collaudo aprirai anche
/hooks per verificare e autorizzare il comando Voce.

A presto,

Sal & [FIRMA_AGENTE]
```

## Email Mac

**Oggetto prima consegna:** `Voce Mac: installazione guidata`

**Oggetto per una versione corretta:** `Voce Mac: istruzioni aggiornate`

```text
Ciao [NOME],

con questa email attivi Voce sul Mac: parli e il testo si scrive da solo,
dentro [AGENTE_CLIENTE] e in qualsiasi finestra. Il lavoro lo fa il tuo
[AGENTE_CLIENTE], tu confermi e provi il microfono.

Apri [AGENTE_CLIENTE] nella cartella [CARTELLA_MADRE] e incolla questo
messaggio:

Installa Voce LeaderAI su questo Mac.

Prendi la struttura dalla repo pubblica salChiarenza/voce con questo comando,
dentro la cartella madre:
git clone https://github.com/salChiarenza/voce.git "[CARTELLA_MADRE]/voce"

Poi esegui mac/install.sh da quella cartella e resta sulla finestra fino al
messaggio di installazione completata. L'installazione crea la cartella
[CARTELLA_LOCALE] e i launcher Voce Dettatura e Voce Attiva Tutto.

Leggi integralmente INSTALLA_CON_AI.md che trovi nella cartella mac e completa
la sezione "Missione locale di diagnosi e collaudo".

Guidami soltanto nei gesti fisici e nelle conferme di macOS, compresi
microfono, accessibilita' e importazione del Comando Rapido. Verifica Git,
Python e gli altri componenti richiesti, installa da solo quello che serve e
riprendi da dove ti eri fermato.

Chiudi mostrando a me il risultato: launcher Voce Dettatura e Voce Attiva
Tutto, Cmd destro, pannello salchiarenza.ai, stessi tempi e toggle della
versione di Sal, esito FOTOCOPIA_SAL_OK sul Comando Rapido e una risposta letta
davvero con la stessa voce. Apri con "Perfetto, l'ho fatto. Tutto completato e
funzionante.", poi archivia questa email.

Da li' in poi detti tenendo premuto il Cmd di destra: parli, rilasci, il testo
compare dove stai scrivendo. Se usi Codex, durante il collaudo aprirai anche
/hooks per verificare e autorizzare il comando Voce.

A presto,

Sal & [FIRMA_AGENTE]
```

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
