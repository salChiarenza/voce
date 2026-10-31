# Installa Voce LeaderAI su Mac

Voce arriva dall'unico pacchetto Mac + Windows pubblicato su GitHub, sempre
all'ultima versione: https://github.com/salChiarenza/voce/releases/latest/download/Voce.zip
Vale per chi la installa per la prima volta e per chi l'ha
gia' installata e ha un problema. Il percorso ha tre momenti, tutti dell'agente:

1. Fase 0: diagnosi in sola lettura, prima di installare qualsiasi cosa;
2. l'agente sceglie `mac/` ed esegue l'installer (nuova installazione o aggiornamento);
3. lo stesso agente lavora sulla cartella installata, completa la diagnosi, prova e chiude.

Al proprietario restano le conferme di macOS, l'importazione del Comando Rapido e la prova con il microfono.

## Fase 0: diagnosi, prima di installare

1. Scarica tu il pacchetto Voce da https://github.com/salChiarenza/voce/releases/latest/download/Voce.zip
   in una cartella temporanea ed estrailo: sono pochi MB e qui si legge soltanto.
2. Esegui `bash mac/voce diagnosi` dalla cartella estratta. Non scrive niente e non
   scarica niente: controlla chip, versione di macOS, memoria, spazio libero, Python,
   strumenti di Apple, internet, app per dettare gia' presenti e, se c'e', la Voce
   gia' installata (versione, servizio, mani libere, voce agenti, registro, memoria).
3. Leggi la riga `ESITO`:
   - `la Voce va bene per questo computer.` (uscita 0): prosegui con la missione qui sotto;
   - `la Voce non va per questo computer.` (uscita 1): non installare niente. Di' al
     proprietario, in una riga, perche' non va, cosa fa l'app e cosa servirebbe,
     con le parole della riga `ESITO`. Fine del lavoro sulla Voce;
   - `prima l'AI sistema: ...` (uscita 2): sistemalo tu e rilancia la diagnosi.
     Python 3.11 o successivo si installa dal programma ufficiale di python.org per
     macOS (la password del Mac la inserisce il proprietario); gli strumenti di Apple
     con `xcode-select --install` (il proprietario conferma la finestra).
4. Se la diagnosi mostra la Voce gia' installata con mani libere ACCESE, testi
   incollati senza che il proprietario detti, o lentezza, applica prima
   «Se la Voce scrive da sola» o «Se la Voce è lenta» (in fondo a questo file),
   poi aggiorna con il pacchetto nuovo.

Requisiti (fonti nel CHANGELOG, versione 1.3.0-rc.32): Mac con chip Apple Silicon
(M1 o successivo), macOS 14 o successivo, 16 GB di memoria, 10 GB liberi sul disco
(2 GB per un aggiornamento), Python 3.11 o successivo nativo, internet la prima volta.
L'installer rifa' la stessa diagnosi e non parte se un requisito manca.

## Missione unica dell'agente

1. Scarica tu il pacchetto Voce da https://github.com/salChiarenza/voce/releases/latest/download/Voce.zip
   in una cartella temporanea; il proprietario non fa da tramite.
2. Verifica che il pacchetto contenga `VERSION`, `mac/` e `windows/`: le due
   versioni devono restare insieme anche se su questo computer ne installi una.
3. Estrai il pacchetto, entra in `mac` e verifica la versione dichiarata.
4. Esegui `install.sh` e resta sulla finestra fino al messaggio `Installazione completata`.
5. L'installer crea l'app «Voce LeaderAI» e il servizio di macOS: la Voce parte da sola a ogni accesso e non apre finestre.
   Le richieste di macOS compaiono a schermo durante `install.sh` (`voce permessi`): chiedi al proprietario di
   concedere a «Voce LeaderAI» (non al Terminale, non a Python) Microfono, Accessibilita' e Monitoraggio input,
   indicando con precisione cosa cliccare.
6. Se l'installazione si interrompe, leggi il messaggio nella finestra, correggi la causa ed esegui di nuovo `install.sh`.

Aggiornamento: se Voce e' gia' installata, riscarica l'ultima versione dallo stesso
link, estraila e rilancia l'installazione. L'installer conserva la configurazione
personale.

L'installer crea o aggiorna:

```text
~/VoiceDettaturaMac
```

e aggiunge sulla Scrivania:

- `Voce Dettatura.command`, riavvio del servizio;
- `Voce Attiva Tutto.command`, un clic per avviare se serve e commutare voce agenti e
  mani libere.

I due launcher si richiudono da soli. Il riavvio della Voce, per te e per ogni agente, e' sempre
`./voce riavvia` nella cartella installata: mai una finestra del Terminale lasciata aperta.

## Continuazione automatica dopo l'installazione

Dopo il messaggio `Installazione completata`, prosegui nella stessa sessione:
entra nella cartella locale qui sotto e completa subito la missione di diagnosi
e prova. Il percorso usa un solo messaggio iniziale. Al proprietario chiedi
soltanto i gesti fisici e le conferme di macOS nel momento in cui servono.

## Missione locale di diagnosi e collaudo

L'agente lavora sulla cartella locale gia' installata:

```text
~/VoiceDettaturaMac
```

Obiettivo: portare Voce fino a una prova reale come fotocopia funzionale
dell'app di Sal, conservando glossario, sostituzioni apprese e preferenza di
log del proprietario.

1. Verifica compatibilita' del Mac, sistema operativo, Python, microfono, permessi e spazio.
2. Verifica la presenza di `VERSION`, `detta.py`, `parla.py`, `voce_hook.py`, `voce_lib.py`, `config.json`, `.venv` e `Voce LeaderAI firmato.shortcut`.
3. Controlla che l'aggiornamento abbia applicato voce, tasti, tempi, toggle,
   modalita' e soglie della fotocopia Sal e abbia conservato glossario,
   sostituzioni apprese e preferenza di log.
4. Esegui la verifica sintattica dei file Python con l'interprete della cartella `.venv`.
5. Esegui `voce_hook.py --check-hooks` con l'interprete della cartella `.venv`. Il
   controllo AVVIA il comando scritto nella configurazione (`--ping`): vale solo
   `configurato e funzionante`; `NON FUNZIONA` dice perche'. Ripara la
   configurazione locale e ripeti la verifica.
6. Verifica che `Voce Dettatura.command` e `Voce Attiva Tutto.command` siano presenti sulla Scrivania e che il
   servizio giri: `launchctl print gui/$(id -u)/com.leaderai.voce` e `./voce permessi stato`. L'app
   `~/Applications/Voce LeaderAI.app` non si ricompila mai da sola: se serve ricrearla, i permessi si rifanno.
7. Verifica `Voce LeaderAI firmato` in Comandi Rapidi e guida il proprietario
   nel clic `Aggiungi comando rapido` quando richiesto. Esegui poi
   `voce_hook.py --check-profile` con l'interprete della cartella `.venv`.
   Il risultato deve essere `FOTOCOPIA_SAL_OK`.
8. Guida la prova reale in un campo di testo con Cmd destro e verifica il pannello `LeaderAI.`.
9. Prova Option + freccia sinistra per la voce, tenuti premuti un secondo (un
   tocco non deve fare niente): l'accensione deve dire
   `Voce AI` e `audio sintetico`, mentre la pill e il menu devono mostrare
   `AI`. Prova anche Cmd destro + Option per la modalita' mani libere, poi
   spegnile con lo stesso gesto: `./voce mani` deve rispondere `Mani libere: SPENTE`.
10. Per Codex fai aprire `/hooks` al proprietario, verifica il comando
    `voce_hook.py` e chiedi la fiducia esplicita se richiesta.
11. Prova una risposta completa dell'agente e verifica che venga letta davvero
    con la stessa voce di Sal: `--check-hooks` avvia il comando di collegamento e
    `--check-profile` prova la configurazione, mentre l'ascolto prova l'esecuzione
    autorizzata. Se all'accensione la voce dice `Attenzione: il collegamento non
    funziona`, riesegui `--install-hooks` e `--check-hooks`.
12. Quando macOS richiede microfono, accessibilita' o monitoraggio input, indica al proprietario il gesto preciso e riprendi il collaudo subito dopo.
13. Ripara gli errori software locali recuperabili, ripeti la prova interessata e chiudi quando gli esiti sono verificati.
14. Prova di chiusura, sempre: una dettatura con Cmd destro arriva nel campo di testo
    in pochi secondi; poi, per due minuti in cui il proprietario non detta, il registro
    non scrive testi da solo:

    ```bash
    date '+%Y-%m-%d %H:%M:%S'   # segna l'ora d'inizio, poi aspetta due minuti
    awk -v dal="ORA SEGNATA" 'substr($0,1,19) >= dal' voce.log \
      | grep -E "incollato \(app bersaglio|invio automatico premuto" || echo "NESSUN TESTO DA SOLO"
    ```

    Il secondo comando, dopo i due minuti e con l'ora segnata al posto di `ORA SEGNATA`, deve stampare `NESSUN TESTO DA SOLO`. Infine `./voce mani` deve dire
    `Mani libere: SPENTE`: si chiude sempre con le mani libere spente.

## Fotocopia funzionale di Sal

Il profilo Mac da applicare e verificare comprende:

- `Voce LeaderAI firmato` con Siri `Voce 2`;
- voce interna `com.apple.siri.natural.Francesca`, velocita' `0.5`, tono `1.0`;
- Cmd destro per dettare;
- Option + freccia sinistra per la voce, tenuti premuti un secondo;
- Cmd destro + Option per le mani libere;
- detta pulito Apple attivo fuori dalle chat AI, con tetto di 2 secondi e
  nessun ripiego interattivo su Claude Code/Codex;
- Invio automatico dopo `2.5` secondi sia a voce ON sia a voce OFF;
- soglia mani libere `0.018` e soglia stop `0.013`;
- voce agenti e mani libere inizialmente spente.

Glossario, sostituzioni apprese e preferenza di log restano del proprietario.

## Conferma finale

Mostra al proprietario:

- versione e cartella installata;
- launcher creati;
- dettatura con Cmd destro;
- pannello `LeaderAI.`;
- voce agenti provata e mani libere provate, poi lasciate SPENTE (`./voce mani`);
- prova dei due minuti: `NESSUN TESTO DA SOLO`;
- una riga per il proprietario: «Le mani libere (Cmd destro + Option, o il pulsante
  Voce Attiva Tutto) scrivono e inviano da sole tutto quello che sentono. Si spengono
  con lo stesso gesto, da sole dopo 10 minuti senza dettature, o chiedendo alla tua AI
  di spegnerle.»;
- avviso `Voce AI` e `audio sintetico` verificato all'accensione;
- collegamento configurato a Claude Code o Codex e prova audio reale;
- `FOTOCOPIA_SAL_OK`;
- dati personali precedenti conservati;
- gesti umani richiesti e completati durante la prova.

Apri con `Perfetto, l'ho fatto. Tutto completato e funzionante.` soltanto dopo
che tutte le prove sono passate. Poi chiudi il
lavoro sul computer del proprietario.

## Se la Voce è lenta

Una dettatura che passa da 1-3 secondi a 15 o più quasi sempre non è colpa di
Voce: un altro programma occupa la memoria del Mac, spesso un calcolo
abbandonato da un agente, e macOS manda il modello su disco.

L'AI del proprietario:

1. guarda chi occupa la memoria: `top -l 1 -o mem -n 10`;
2. se è un calcolo rimasto aperto da un agente e nessuna sessione lo usa più, lo chiude;
3. altrimenti dice al proprietario, in una riga, quale programma chiudere.

Dopo aver chiuso il programma esegui `./voce riavvia` e rifai una dettatura.
Voce si riavvia da sola se resta lenta. Sui Mac con 16 GB di RAM o meno usa già
da sola il motore leggero; se serve un altro motore, `modello` in
`config.local.json` comanda sempre. Il motore scelto è scritto in `voce.log`.

## Se la Voce scrive da sola

Testi che compaiono e partono da soli in una chat (frasi brevi, parole che il
proprietario non ha detto) arrivano quasi sempre dalle mani libere accese: con
le mani libere la Voce scrive e invia tutto quello che sente nella stanza. Si
accendono con Cmd + Option premuti insieme, anche dentro scorciatoie come
Cmd + Option + freccia, o col pulsante `Voce Attiva Tutto` della Scrivania, e
restano accese anche dopo un riavvio del Mac.

L'AI del proprietario, nella cartella installata:

1. `./voce mani`: se dice `ATTIVE`, la causa e' questa. `./voce mani off` e
   `./voce mani` deve dire `Mani libere: SPENTE`;
2. legge il registro, righe sempre scritte:

   ```bash
   grep -E "mani libere|incollato \(app bersaglio|invio automatico premuto|registrazione avviata" voce.log | tail -40
   ```

   `incollato (app bersaglio: ...)` e `invio automatico premuto` sono i testi
   scritti e inviati; `mani libere: ascolto partito dal volume` subito prima
   vuol dire che li hanno scritti le mani libere; `combo mani libere: ON` e'
   l'accensione coi tasti; `mani libere: ATTIVE (gia' accese all'avvio)` vuol
   dire che erano rimaste accese da prima. Le righe `grezzo:` esistono solo col
   registro dettagliato (`debug_dettature`), spento di serie: non cercarle;
3. se le mani libere erano spente e i testi compaiono lo stesso: controlla che
   giri un solo programma (`pgrep -fl "detta\.py"`, la diagnosi lo conta), che non
   ci sia un'altra app per dettare attiva (la diagnosi le elenca) e chiedi al
   proprietario se il Cmd destro resta incastrato;
4. ripara cio' che si disfa da solo: spegne le mani libere, chiude un calcolo
   rimasto aperto da un agente (vedi «Se la Voce è lenta»), `./voce riavvia`.
   Gesti e tasti non si cambiano nel codice installato: il prossimo aggiornamento
   li riscriverebbe e la Voce non sarebbe piu' quella di LeaderAI. Se un gesto
   scatta per sbaglio, scrivilo nella conferma finale;
5. chiude con la prova di chiusura (punto 14 della missione locale) e dice al
   proprietario in una riga cosa e' successo e come si spengono le mani libere.

Dalla versione 1.3.0-rc.32 le mani libere si spengono da sole dopo 10 minuti senza testi
incollati davvero, anche se nella stanza c'e' rumore.
