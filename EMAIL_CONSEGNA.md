# Email di consegna Voce

Questa e' la fonte unica del testo usato per consegnare Voce a un cliente.
L'installer e l'email evolvono insieme: ogni cambiamento che modifica download,
launcher, permessi, cartella locale o collaudo aggiorna anche questo file nello
stesso commit.

La cronologia Git conserva i miglioramenti. I dati del singolo cliente restano
nel testo mostrato a Sal e nella copia Gmail inviata.

## Dati da compilare e verificare

Prima di mostrare l'email a Sal, sostituisci tutti i campi tra parentesi quadre:

- `[NOME]`: nome del destinatario;
- `[LINK_ARCHIVIO_VERIFICATO]`: URL esatto del commit o della release provata
  con lo stesso accesso del destinatario;
- `[AGENTE_CLIENTE]`: Claude Code oppure Codex, verificato sul computer;
- `[CARTELLA_LOCALE]`: percorso creato dall'installer;
- `[FIRMA_AGENTE]`: agente LeaderAI che ha preparato e verificato la consegna.

Percorsi standard:

- Windows: `%USERPROFILE%\VoiceDettaturaWindows`;
- Mac: `~/VoiceDettaturaMac`.

Un percorso personalizzato entra nell'email dopo una verifica sul computer o in
un rapporto precedente del cliente.

## Email Windows

**Oggetto prima consegna:** `Voce Windows: installazione guidata`

**Oggetto per una versione corretta:** `Voce Windows: istruzioni aggiornate`

```text
Ciao [NOME],

con questa email installi la versione verificata di Voce Windows e completi le
prove insieme a [AGENTE_CLIENTE].

1. Scarica Voce da questo link:
[LINK_ARCHIVIO_VERIFICATO]

2. Apri Download, seleziona il file ZIP e scegli "Estrai tutto".

3. Apri la cartella estratta, poi apri la cartella windows.

4. Fai doppio clic su install.bat.

5. Se Windows mostra una conferma, scegli "Ulteriori informazioni", poi
"Esegui comunque" e conferma con "Si'".

6. Lascia aperta la finestra fino al messaggio "Installazione completata".
Il primo avvio puo' richiedere piu' tempo per preparare il modello di
trascrizione.

Quando compare "Installazione completata", torna in [AGENTE_CLIENTE] e scrivi:

Ho avviato personalmente il launcher locale di Voce LeaderAI e
l'installazione e' terminata.

Lavora ora nella cartella:
[CARTELLA_LOCALE]

Leggi integralmente INSTALLA_CON_AI.md che trovi nella cartella e completa la
sezione "Missione locale di diagnosi e collaudo".

Guidami nei gesti fisici e nelle conferme Windows. Correggi direttamente gli
errori software locali recuperabili, ripeti le prove e chiudi con il rapporto
finale previsto.

Se la finestra mostra "Installazione interrotta", lasciala aperta e invia
subito questo messaggio a [AGENTE_CLIENTE]:

Analizza il messaggio visibile nella finestra di installazione di Voce. Guidami
nella correzione della causa e indicami quando eseguire di nuovo il doppio clic
su install.bat. Riprendi poi il collaudo dalla cartella
[CARTELLA_LOCALE].

Al termine [AGENTE_CLIENTE] ti mostrera' il rapporto con icona, Ctrl destro,
pannello salchiarenza.ai, tasto Menu, voce italiana e lettura delle risposte.
Dopo la tua conferma, fagli inviare il rapporto a sal@salchiarenza.ai e fagli
archiviare questa email.

A presto,

Sal & [FIRMA_AGENTE]
```

## Email Mac

**Oggetto prima consegna:** `Voce Mac: installazione guidata`

**Oggetto per una versione corretta:** `Voce Mac: istruzioni aggiornate`

```text
Ciao [NOME],

con questa email installi la versione verificata di Voce Mac e completi le
prove insieme a [AGENTE_CLIENTE].

1. Scarica Voce da questo link:
[LINK_ARCHIVIO_VERIFICATO]

2. Apri Download e fai doppio clic sul file ZIP per estrarlo.

3. Apri la cartella estratta, poi apri la cartella mac.

4. Fai doppio clic su "Installa Voce.command".

5. Se macOS mostra una conferma, fai Control-clic sul file, scegli "Apri" e
conferma di nuovo con "Apri".

6. Lascia aperta la finestra fino al messaggio di installazione completata.
Il primo avvio puo' richiedere piu' tempo per preparare il modello di
trascrizione.

Quando l'installazione termina, torna in [AGENTE_CLIENTE] e scrivi:

Ho avviato personalmente il launcher locale di Voce LeaderAI e
l'installazione e' terminata.

Lavora ora nella cartella:
[CARTELLA_LOCALE]

Leggi integralmente INSTALLA_CON_AI.md che trovi nella cartella e completa la
sezione "Missione locale di diagnosi e collaudo".

Guidami nei gesti fisici e nelle conferme macOS. Correggi direttamente gli
errori software locali recuperabili, ripeti le prove e chiudi con il rapporto
finale previsto.

Se la finestra mostra un'interruzione, lasciala aperta e invia subito questo
messaggio a [AGENTE_CLIENTE]:

Analizza il messaggio visibile nella finestra di installazione di Voce. Guidami
nella correzione della causa e indicami quando eseguire di nuovo il doppio clic
su "Installa Voce.command". Riprendi poi il collaudo dalla cartella
[CARTELLA_LOCALE].

Al termine [AGENTE_CLIENTE] ti mostrera' il rapporto con launcher, Cmd destro,
pannello salchiarenza.ai, voce agenti, Comando Rapido e lettura delle risposte.
Dopo la tua conferma, fagli inviare il rapporto a sal@salchiarenza.ai e fagli
archiviare questa email.

A presto,

Sal & [FIRMA_AGENTE]
```

## Controllo prima dell'invio

1. Apri lo stato corrente della repo e scegli Windows oppure Mac.
2. Crea il commit della versione da consegnare.
3. Costruisci l'URL esatto dell'archivio da quel commit o dalla release.
4. Scarica l'archivio con lo stesso accesso del destinatario.
5. Verifica che il launcher e `INSTALLA_CON_AI.md` siano presenti.
6. Prova il primo avvio sul sistema previsto e registra
   `PROVA_DESTINATARIO_OK`.
7. Compila tutti i campi del modello e rileggi ogni link e percorso.
8. Mostra a Sal destinatario, oggetto e testo integrale.
9. Dopo il suo comando di invio, registra `INVIO_OK` e manda una sola nuova
   email con oggetto autonomo.
10. Rileggi la copia in Sent, applica la label `Clienti`, aggiorna la scheda del
    cliente e verifica la sua Inbox.

## Miglioramento continuo

Quando una consegna incontra un ostacolo:

1. raccogli la prova reale, come messaggio, screenshot o codice di uscita;
2. identifica il punto proprietario: email, launcher, installer, istruzioni
   locali oppure ambiente del cliente;
3. correggi il punto proprietario e aggiorna questo file quando cambia
   l'esperienza del destinatario;
4. aggiorna i changelog Mac e Windows;
5. ripeti il percorso completo del destinatario;
6. pubblica un nuovo commit e usa il nuovo link nell'invio successivo.

