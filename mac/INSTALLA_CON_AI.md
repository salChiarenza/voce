# Installa con Claude Code o Codex

Questa e' la strada piu' semplice: l'agente controlla il Mac, installa o ripara cio' che manca e chiude solo dopo una prova reale.

## Cosa devi fare

1. Apri Claude Code o Codex sul tuo Mac.
2. Se il tuo agente supporta `/goal`, manda prima la riga GOAL.
3. Poi copia il testo principale qui sotto e incollalo nell'agente.
4. Quando macOS chiede permessi, clicca tu: microfono, accessibilita' o automazione non possono essere concessi dall'agente.
5. Fai la prova finale quando l'agente te la chiede.

## Riga GOAL consigliata

```text
/goal Installa Voce Dettatura per Mac fino a prova reale: autodiagnosi, auto-riparazione, launcher creati, permessi guidati e dettatura funzionante in un campo di testo.
```

## Testo principale da copiare

```text
Voglio installare o aggiornare Voce Dettatura per Mac da questo repository:
https://github.com/salChiarenza/voce

Lavora nella cartella mac/.

Prima leggi AGENTS.md della repo e tratta la sezione "GOAL OPERATIVO" come missione obbligatoria.

Assumi tu la regia tecnica: fai l'autodiagnosi del Mac, installa o ripara cio' che manca e chiedimi solo le azioni umane che non puoi fare al posto mio: permessi macOS, conferme di sicurezza e prova fisica.

Devi:
1. Verificare compatibilita' del Mac, sistema operativo, Python/runtime, microfono, permessi e spazio.
2. Scaricare o aggiornare il progetto.
3. Entrare nella cartella mac/ ed eseguire l'installazione corretta.
4. Installare dipendenze e modello necessari, se mancano.
5. Creare o aggiornare i launcher sulla Scrivania.
6. Quando servono permessi macOS, dimmi con precisione cosa cliccare.
7. Fare una prova reale in un campo di testo: tengo premuto Cmd destro, detto una frase, rilascio, e tu verifichi che il testo compaia dove sta il cursore e che si veda il pannello salchiarenza.ai con la barra verde a sorriso.
8. Se la voce agenti e' configurata, verificare anche Alt destro on/off.

Se trovi un errore software, prova a correggerlo e riprova. Fermati solo se manca un requisito hardware o un permesso che devo concedere io.

Alla fine dammi un report breve:
- installazione completata si/no;
- launcher creati si/no;
- dettatura Cmd destro funzionante si/no;
- voce agenti Alt destro funzionante si/no;
- eventuali problemi non recuperabili.
```

## Cosa fara' l'agente

- Controlla il Mac.
- Ripara cio' che manca se e' software recuperabile.
- Scarica o aggiorna il repository.
- Esegue l'installer.
- Crea i launcher sulla Scrivania.
- Ti guida nei permessi di macOS.
- Fa una prova finale di dettatura.

## Se si blocca davvero

Scrivi nella community AI con Sal:

- modello del Mac;
- versione macOS;
- quale passaggio resta bloccato;
- cosa vedi a schermo;
- report finale dell'agente.
