# Installa con Claude Code o Codex

Questa e' la strada piu' semplice: l'agente controlla il PC, installa o ripara cio' che manca e chiude solo dopo una prova reale. Tu non devi usare il terminale.

## Le sole azioni del proprietario

1. Apri Claude Code o Codex sul PC Windows.
2. Se il tuo agente supporta `/goal`, manda prima la riga GOAL.
3. Poi copia il testo principale qui sotto e incollalo nell'agente.
4. Quando Windows chiede permessi, SmartScreen o conferme admin, clicca tu: l'agente ti dice cosa fare.
5. Fai la prova finale quando l'agente te la chiede.

## Riga GOAL consigliata

```text
/goal Installa o aggiorna Voce Dettatura per Windows fino a prova reale: autodiagnosi, auto-riparazione, configurazione personale conservata, voce agenti collegata, icona creata, modello scaricato e dettatura funzionante in Blocco note.
```

## Testo principale da copiare

```text
Voglio installare o aggiornare Voce Dettatura per Windows da questo repository:
https://github.com/salChiarenza/voce

Lavora nella cartella windows/.

Prima leggi AGENTS.md della repo. Usa il GOAL operativo come risultato da raggiungere, non come autorizzazione a imporre preferenze opzionali.

Assumi tu la regia tecnica: fai l'autodiagnosi del PC, installa o ripara cio' che manca e chiedimi solo le azioni umane che non puoi fare al posto mio: permessi Windows, conferme SmartScreen/admin e prova fisica.

Questa non e' una reinstallazione da zero. Se Voce esiste gia', aggiornala conservando glossario, sostituzioni, tasti personalizzati, modello scelto, voce scelta e calibrazione del microfono. Non cancellare gli hook o le impostazioni gia' presenti di Claude Code/Codex.

Se e' la prima installazione, prima di applicare le preferenze proponimi con una sola domanda il **Profilo LeaderAI consigliato**:

- Ctrl destro per dettare e tasto Menu per voce on/off;
- detta pulito attivo;
- voce agenti inizialmente spenta;
- ascolto guidato delle voci italiane installate per scegliere quella che io percepisco come piu' naturale.

Spiega in breve il vantaggio e chiedimi se voglio usarlo. E' una raccomandazione, non un obbligo. Se preferisco altro, rispetta la scelta e registrala nel report.

Per rendere l'app realmente funzionante:
1. Verificare compatibilita' Windows, Python 3/runtime, PowerShell, microfono, tasto Ctrl destro, tasto Menu, permessi, rete e spazio.
2. Se Python o una dipendenza software manca ed e' installabile, installala o chiedimi solo il click/conferma necessario.
3. Scaricare o aggiornare il progetto.
4. Entrare nella cartella windows/ ed eseguire install.ps1.
5. Creare o aggiornare l'app, il venv, le dipendenze e l'icona "Voce Dettatura" su Scrivania e Menu Start.
6. Verificare che `voce_hook.py` sia stato copiato nella cartella installata e collegato agli hook `Stop` globali di Claude Code e/o Codex senza cancellare quelli esistenti; usa `voce_hook.py --check-hooks` e correggi se fallisce.
7. Avvisarmi che il primo avvio puo' scaricare il modello di trascrizione e aspettare che finisca.
8. Quando servono permessi microfono o conferme SmartScreen, dimmi con precisione cosa cliccare.
9. Fare una prova reale in Blocco note: tengo premuto Ctrl destro, detto una frase, rilascio, e tu verifichi che il testo compaia e che si veda il pannello salchiarenza.ai con la barra verde a sorriso.
10. Eseguire `voce_hook.py --list-voices`. Se ci sono voci italiane, fammele ascoltare una alla volta con `voce_hook.py --test-voice "NOME"`, suggerisci di scegliere quella percepita come piu' naturale e salva la mia scelta con `voce_hook.py --set-voice "NOME"`. Se non ce ne sono, suggerisci l'aggiunta del pacchetto voce italiano di Windows e chiedimi conferma prima di aprire le Impostazioni.
11. Provare davvero il tasto Menu on/off e la lettura di una risposta completa dell'agente con la voce scelta. Non dichiarare la voce agenti funzionante solo perche' il file esiste.

Se trovi un errore software, prova a correggerlo e riprova. Fermati solo se manca un requisito hardware o un permesso che devo concedere io.

Alla fine dammi un report breve:
- installazione completata si/no;
- icona creata si/no;
- dettatura Ctrl destro funzionante si/no;
- voce agenti tasto Menu funzionante si/no;
- hook risposta di Claude Code/Codex collegato e verificato si/no;
- voce italiana Windows ascoltata davvero si/no;
- configurazione personale precedente conservata si/no/non presente;
- Profilo LeaderAI consigliato accettato/modificato e voce scelta;
- eventuali problemi non recuperabili.
```

## Cosa fara' l'agente

- Controlla il PC.
- Ripara cio' che manca se e' software recuperabile.
- Scarica il repository ed esegue l'installer.
- Crea l'icona "Voce Dettatura" su Scrivania e Menu Start.
- Ti guida nei permessi e negli eventuali avvisi Windows.
- Fa una prova finale di dettatura.

## Come si usa

1. Clicca l'icona **Voce Dettatura** (Scrivania o Menu Start).
2. Si apre una piccola finestra: la Voce e' accesa.
3. In qualsiasi programma tieni premuto **Ctrl destro**, parla, rilascia.
4. In basso compare la pill **salchiarenza.ai** con la barra verde a sorriso; il testo viene scritto dove hai il cursore.
5. Per spegnerla, chiudi quella finestra.

## Se si blocca davvero

Scrivi nella community AI con Sal:

- modello del PC;
- versione Windows;
- quale passaggio resta bloccato;
- cosa vedi a schermo;
- report finale dell'agente.
