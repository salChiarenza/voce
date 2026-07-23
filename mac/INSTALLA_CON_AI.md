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

e aggiunge i launcher di Voce sulla Scrivania.

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

Obiettivo: portare Voce fino a una prova reale, conservando la configurazione personale esistente.

1. Verifica compatibilita' del Mac, sistema operativo, Python, microfono, permessi e spazio.
2. Verifica la presenza di `detta.py`, `parla.py`, `voce_hook.py`, `voce_lib.py`, `config.json`, `.venv` e `Voce LeaderAI firmato.shortcut`.
3. Controlla che l'aggiornamento abbia conservato glossario, sostituzioni, tasti, modello, voce scelta e calibrazione gia' presenti.
4. Esegui la verifica sintattica dei file Python con l'interprete della cartella `.venv`.
5. Esegui `voce_hook.py --check-hooks` con l'interprete della cartella `.venv`; ripara il collegamento locale se il controllo fallisce e ripeti la verifica.
6. Verifica che i launcher siano presenti sulla Scrivania.
7. Se il proprietario sceglie il Profilo LeaderAI, verifica `Voce LeaderAI firmato` in Comandi Rapidi e guidalo nel clic `Aggiungi comando rapido` quando richiesto.
8. Guida la prova reale in un campo di testo con Cmd destro e verifica il pannello `salchiarenza.ai`.
9. Prova Option + freccia sinistra per la voce e Cmd destro + Option per la modalita' mani libere.
10. Prova una risposta completa con la voce scelta.
11. Quando macOS richiede microfono, accessibilita' o monitoraggio input, indica al proprietario il gesto preciso e riprendi il collaudo subito dopo.
12. Ripara gli errori software locali recuperabili, ripeti la prova interessata e chiudi quando gli esiti sono verificati.

## Profilo LeaderAI consigliato

Alla prima installazione proponi in una sola domanda:

- `Voce LeaderAI firmato` con Siri `Voce 2`;
- Cmd destro per dettare;
- Option + freccia sinistra per la voce;
- Cmd destro + Option per le mani libere;
- detta pulito attivo;
- voce agenti e mani libere inizialmente spente.

Applica la scelta del proprietario e registrala nel rapporto.

## Rapporto finale

Mostra al proprietario:

- versione e cartella installata;
- launcher creati;
- dettatura con Cmd destro;
- pannello `salchiarenza.ai`;
- voce agenti e mani libere;
- collegamento a Claude Code o Codex;
- voce scelta;
- configurazione precedente conservata;
- eventuale gesto umano ancora richiesto.

Dopo l'approvazione del proprietario, invia davvero il rapporto a `sal@salchiarenza.ai` e archivia l'email di consegna.
