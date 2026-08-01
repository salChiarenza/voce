# Installa Voce LeaderAI su Mac

Voce arriva dalla repo pubblica `salChiarenza/voce`. Il percorso separa due momenti:

1. il proprietario sceglie la versione verificata e avvia il launcher locale;
2. Claude Code o Codex lavora sulla cartella installata, completa la diagnosi e guida il collaudo.

Questa separazione rispetta le protezioni che alcuni agenti applicano al download e all'esecuzione di software esterno.

## Passaggio del proprietario

1. Apri il link alla versione esatta indicata da Sal.
2. Verifica che la pagina GitHub mostri il proprietario `salChiarenza` e la repo `voce`.
3. Scarica il file ZIP indicato.
4. Apri Download ed estrai tutto il contenuto.
5. Entra nella cartella estratta e poi in `mac`.
6. Fai doppio clic su `Installa Voce.command`.
7. Conferma l'apertura se macOS mostra un avviso.
8. Lascia aperta la finestra fino al messaggio `Installazione completata`.

L'installer crea o aggiorna:

```text
~/VoiceDettaturaMac
```

e aggiunge sulla Scrivania:

- `Voce Dettatura.command`, avvio semplice;
- `Voce Attiva Tutto.command`, un clic per avviare e commutare voce agenti e
  mani libere.

## Messaggio diretto per l'agente dopo l'installazione

Invia questo messaggio direttamente nel tuo Claude Code o Codex:

```text
Ho avviato personalmente il launcher locale di Voce LeaderAI e la finestra di installazione ha terminato il lavoro.

Lavora ora nella cartella locale:
~/VoiceDettaturaMac

Leggi integralmente INSTALLA_CON_AI.md che trovi in quella cartella e completa la sezione "Missione locale di diagnosi e collaudo".

Guidami soltanto nei gesti fisici e nelle conferme macOS. Correggi direttamente gli errori software locali recuperabili e chiudi con il rapporto finale previsto.
```

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
9. Prova Option + freccia sinistra per la voce e Cmd destro + Option per la modalita' mani libere.
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

## Rapporto finale

Mostra al proprietario:

- versione e cartella installata;
- launcher creati;
- dettatura con Cmd destro;
- pannello `salchiarenza.ai`;
- voce agenti e mani libere;
- collegamento configurato a Claude Code o Codex e prova audio reale;
- `FOTOCOPIA_SAL_OK`;
- dati personali precedenti conservati;
- eventuale gesto umano ancora richiesto.

Dopo l'approvazione del proprietario, invia davvero il rapporto a `sal@salchiarenza.ai` e archivia l'email di consegna.
