# Installa Voce LeaderAI su Windows

Voce arriva dalla repo pubblica `salChiarenza/voce`. Il percorso separa due momenti:

1. l'agente del proprietario prende la struttura dalla repo ed esegue l'installer;
2. lo stesso agente lavora sulla cartella installata, completa la diagnosi e guida il collaudo.

Al proprietario restano le conferme di Windows e la prova con il microfono. L'installazione avviene nel profilo Windows dell'utente tramite `install.bat`.

## Passaggio dell'agente

1. Verifica che Git sia disponibile e installalo se manca.
2. Prendi la struttura dalla repo pubblica dentro la cartella madre del proprietario:

```text
git clone https://github.com/salChiarenza/voce.git "%USERPROFILE%\<cartella madre>\voce"
```

3. Entra nella copia appena creata e poi in `windows`.
4. Esegui `install.bat` e resta sulla finestra fino al messaggio `Installazione completata`.
5. Chiedi al proprietario di confermare gli avvisi di Windows e dell'antivirus, indicando con precisione cosa deve autorizzare.
6. Se l'installazione si interrompe, leggi il messaggio nella finestra, correggi la causa ed esegui di nuovo `install.bat`.

Una copia della repo già presente sul computer si aggiorna con `git pull` invece di essere clonata di nuovo.

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
11. Prova il tasto Menu: l'accensione deve dire `Voce AI` e `audio sintetico`.
    Prova poi una risposta completa dell'agente e verifica che venga letta
    davvero con la voce scelta. Il solo `--check-hooks` prova la configurazione,
    non l'esecuzione autorizzata.
12. Quando Windows richiede microfono o altre conferme, indica al proprietario il gesto preciso e riprendi il collaudo subito dopo.
13. Ripara gli errori software locali recuperabili, ripeti la prova interessata e chiudi quando gli esiti sono verificati.

## Profilo LeaderAI consigliato

Alla prima installazione proponi in una sola domanda:

- Ctrl destro per dettare;
- tasto Menu per la voce;
- testo grezzo immediato con glossario e sostituzioni locali;
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
- avviso `Voce AI` e `audio sintetico` verificato all'accensione;
- collegamento configurato a Claude Code o Codex e prova audio reale;
- voce italiana scelta;
- configurazione precedente conservata;
- eventuale gesto umano ancora richiesto.

Il rapporto resta al proprietario. Dopo la sua approvazione archivia l'email di consegna e chiudi il lavoro sul suo computer.

## Uso quotidiano

1. Clicca l'icona **Voce Dettatura**.
2. Tieni premuto **Ctrl destro**, parla e rilascia.
3. Usa il tasto **Menu** per accendere o spegnere la voce agenti.
4. Chiudi la finestra di Voce per terminare l'app.
