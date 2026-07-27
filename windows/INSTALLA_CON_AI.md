# Installa Voce LeaderAI su Windows

Voce arriva dalla repo pubblica `salChiarenza/voce`. Il percorso separa due momenti:

1. il proprietario sceglie la versione verificata e avvia il launcher locale;
2. Claude Code o Codex lavora sulla cartella installata, completa la diagnosi e guida il collaudo.

Questa separazione rispetta le protezioni che alcuni agenti applicano al download e all'esecuzione di software esterno. L'installazione avviene nel profilo Windows dell'utente tramite `install.bat`.

## Passaggio del proprietario

1. Apri il link alla versione esatta indicata da Sal.
2. Verifica che la pagina GitHub mostri il proprietario `salChiarenza` e la repo `voce`.
3. Scarica il file ZIP indicato.
4. Apri Download ed estrai tutto il contenuto.
5. Entra nella cartella estratta e poi in `windows`.
6. Fai doppio clic su `install.bat`.
7. Conferma l'esecuzione se Windows mostra un avviso.
8. Lascia aperta la finestra fino al messaggio `Installazione completata`.

L'installer crea o aggiorna:

```text
%USERPROFILE%\VoiceDettaturaWindows
```

e aggiunge l'icona **Voce Dettatura** sulla Scrivania e nel Menu Start.

## Messaggio diretto per l'agente dopo l'installazione

Invia questo messaggio direttamente nel tuo Claude Code o Codex:

```text
Ho avviato personalmente il launcher locale di Voce LeaderAI e la finestra di installazione ha terminato il lavoro.

Lavora ora nella cartella locale:
%USERPROFILE%\VoiceDettaturaWindows

Leggi integralmente INSTALLA_CON_AI.md che trovi in quella cartella e completa la sezione "Missione locale di diagnosi e collaudo".

Guidami soltanto nei gesti fisici e nelle conferme Windows. Correggi direttamente gli errori software locali recuperabili e chiudi con il rapporto finale previsto.
```

## Missione locale di diagnosi e collaudo

L'agente lavora sulla cartella locale gia' installata:

```text
%USERPROFILE%\VoiceDettaturaWindows
```

Obiettivo: portare Voce fino a una prova reale, conservando la configurazione personale esistente.

1. Verifica la presenza di `VERSION`, `voice_dettatura_windows.py`, `voce_hook.py`, `config.json`, `.venv` e `Voce Dettatura.bat`.
2. Verifica Python, PowerShell, microfono, tasto Ctrl destro, tasto Menu, rete e spazio disponibile.
3. Controlla che l'aggiornamento abbia conservato glossario, sostituzioni, tasti, modello, voce scelta e calibrazione gia' presenti.
4. Esegui la verifica sintattica dei file Python con l'interprete della cartella `.venv`.
5. Esegui `voce_hook.py --check-hooks` con l'interprete della cartella `.venv`; ripara la configurazione locale se il controllo fallisce e ripeti la verifica.
6. Avvia Voce dall'icona sulla Scrivania.
7. Guida il proprietario nella prova in Blocco note: Ctrl destro tenuto, frase dettata, rilascio, testo inserito e pannello `salchiarenza.ai` visibile con il sorriso verde.
8. Elenca le voci italiane disponibili con `voce_hook.py --list-voices`.
9. Falle ascoltare una alla volta con `voce_hook.py --test-voice "NOME"` e salva quella scelta con `voce_hook.py --set-voice "NOME"`.
10. Per Codex fai aprire `/hooks` al proprietario, verifica il comando
    `voce_hook.py` e chiedi la fiducia esplicita se richiesta.
11. Prova il tasto Menu e una risposta completa dell'agente; verifica che venga
    letta davvero con la voce scelta. Il solo `--check-hooks` prova la
    configurazione, non l'esecuzione autorizzata.
12. Quando Windows richiede microfono o altre conferme, indica al proprietario il gesto preciso e riprendi il collaudo subito dopo.
13. Ripara gli errori software locali recuperabili, ripeti la prova interessata e chiudi quando gli esiti sono verificati.

## Profilo LeaderAI consigliato

Alla prima installazione proponi in una sola domanda:

- Ctrl destro per dettare;
- tasto Menu per la voce;
- detta pulito attivo;
- voce agenti inizialmente spenta;
- scelta guidata della voce italiana percepita come piu' naturale.

Applica la scelta del proprietario e registrala nel rapporto.

## Rapporto finale

Mostra al proprietario:

- versione e cartella installata;
- icona creata;
- dettatura con Ctrl destro;
- pannello `salchiarenza.ai`;
- tasto Menu e voce agenti;
- collegamento configurato a Claude Code o Codex e prova audio reale;
- voce italiana scelta;
- configurazione precedente conservata;
- eventuale gesto umano ancora richiesto.

Dopo l'approvazione del proprietario, invia davvero il rapporto a `sal@salchiarenza.ai` e archivia l'email di consegna.

## Uso quotidiano

1. Clicca l'icona **Voce Dettatura**.
2. Tieni premuto **Ctrl destro**, parla e rilascia.
3. Usa il tasto **Menu** per accendere o spegnere la voce agenti.
4. Chiudi la finestra di Voce per terminare l'app.
