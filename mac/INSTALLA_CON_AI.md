# Installa Voce LeaderAI su Mac

Voce arriva dall'unico pacchetto Mac + Windows collegato nel modulo App di
LeaderAI Ecosystem. Il percorso separa due momenti:

1. l'agente del proprietario apre il pacchetto, sceglie `mac/` ed esegue l'installer;
2. lo stesso agente lavora sulla cartella installata, completa la diagnosi e guida il collaudo.

Al proprietario restano le conferme di macOS, l'importazione del Comando Rapido e la prova con il microfono.

## Missione unica dell'agente

1. Apri il collegamento Google Drive ricevuto nell'email e scarica tu il
   pacchetto Voce in una cartella temporanea; il proprietario non fa da tramite.
2. Verifica che il pacchetto contenga `VERSION`, `mac/` e `windows/`: le due
   versioni devono restare insieme anche se su questo computer ne installi una.
3. Estrai il pacchetto, entra in `mac` e verifica la versione dichiarata.
4. Esegui `install.sh` e resta sulla finestra fino al messaggio `Installazione completata`.
5. Chiedi al proprietario di concedere microfono e accessibilita' quando macOS li richiede, indicando con precisione cosa deve autorizzare.
6. Se l'installazione si interrompe, leggi il messaggio nella finestra, correggi la causa ed esegui di nuovo `install.sh`.

Se Voce e' gia' installata, usa il nuovo pacchetto come aggiornamento e conserva
la configurazione personale prevista dall'installer.

L'installer crea o aggiorna:

```text
~/VoiceDettaturaMac
```

e aggiunge sulla Scrivania:

- `Voce Dettatura.command`, avvio semplice;
- `Voce Attiva Tutto.command`, un clic per avviare e commutare voce agenti e
  mani libere.

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
5. Esegui `voce_hook.py --check-hooks` con l'interprete della cartella `.venv`; ripara la configurazione locale se il controllo fallisce e ripeti la verifica.
6. Verifica che `Voce Dettatura.command` e `Voce Attiva Tutto.command` siano presenti sulla Scrivania.
7. Verifica `Voce LeaderAI firmato` in Comandi Rapidi e guida il proprietario
   nel clic `Aggiungi comando rapido` quando richiesto. Esegui poi
   `voce_hook.py --check-profile` con l'interprete della cartella `.venv`.
   Il risultato deve essere `FOTOCOPIA_SAL_OK`.
8. Guida la prova reale in un campo di testo con Cmd destro e verifica il pannello `salchiarenza.ai`.
9. Prova Option + freccia sinistra per la voce: l'accensione deve dire
   `Voce AI` e `audio sintetico`, mentre la pill e il menu devono mostrare
   `AI`. Prova anche Cmd destro + Option per la modalita' mani libere.
10. Per Codex fai aprire `/hooks` al proprietario, verifica il comando
    `voce_hook.py` e chiedi la fiducia esplicita se richiesta.
11. Prova una risposta completa dell'agente e verifica che venga letta davvero
    con la stessa voce di Sal: `--check-hooks` e `--check-profile` provano la
    configurazione, mentre l'ascolto prova l'esecuzione autorizzata.
12. Quando macOS richiede microfono, accessibilita' o monitoraggio input, indica al proprietario il gesto preciso e riprendi il collaudo subito dopo.
13. Ripara gli errori software locali recuperabili, ripeti la prova interessata e chiudi quando gli esiti sono verificati.

## Fotocopia funzionale di Sal

Il profilo Mac da applicare e verificare comprende:

- `Voce LeaderAI firmato` con Siri `Voce 2`;
- voce interna `com.apple.siri.natural.Francesca`, velocita' `0.5`, tono `1.0`;
- Cmd destro per dettare;
- Option + freccia sinistra per la voce;
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
- pannello `salchiarenza.ai`;
- voce agenti e mani libere;
- avviso `Voce AI` e `audio sintetico` verificato all'accensione;
- collegamento configurato a Claude Code o Codex e prova audio reale;
- `FOTOCOPIA_SAL_OK`;
- dati personali precedenti conservati;
- gesti umani richiesti e completati durante la prova.

Apri con `Perfetto, l'ho fatto. Tutto completato e funzionante.` soltanto dopo
che tutte le prove sono passate. Poi archivia l'email di consegna e chiudi il
lavoro sul computer del proprietario.
