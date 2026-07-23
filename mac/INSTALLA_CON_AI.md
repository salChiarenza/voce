# Installa con Claude Code o Codex

Questa e' la strada piu' semplice: l'agente controlla il Mac, installa o ripara cio' che manca e chiude solo dopo una prova reale.

## Le sole azioni del proprietario

1. Apri Claude Code o Codex sul tuo Mac.
2. Se il tuo agente supporta `/goal`, manda prima la riga GOAL.
3. Poi copia il testo principale qui sotto e incollalo nell'agente.
4. Quando macOS chiede permessi, clicca tu: microfono, accessibilita' o automazione non possono essere concessi dall'agente.
5. Fai la prova finale quando l'agente te la chiede.

## Riga GOAL consigliata

```text
/goal Installa Voce Dettatura per Mac fino a prova reale: autodiagnosi, auto-riparazione, launcher creati, voce naturale LeaderAI, permessi guidati e dettatura funzionante in un campo di testo.
```

## Testo principale da copiare

```text
Voglio installare o aggiornare Voce Dettatura per Mac da questo repository:
https://github.com/salChiarenza/voce

Lavora nella cartella mac/.

Prima leggi AGENTS.md della repo. Usa il GOAL operativo come risultato da raggiungere, non come autorizzazione a imporre preferenze opzionali.

Assumi tu la regia tecnica: fai l'autodiagnosi del Mac, installa o ripara cio' che manca e chiedimi solo le azioni umane che non puoi fare al posto mio: permessi macOS, conferme di sicurezza e prova fisica.

Questa non e' una reinstallazione da zero. Se Voce esiste gia', aggiornala conservando glossario, sostituzioni, tasti personalizzati e calibrazione del microfono. Non cancellare gli hook o le impostazioni gia' presenti di Claude Code/Codex.

Se e' la prima installazione, prima di applicare le preferenze proponimi con una sola domanda il **Profilo LeaderAI consigliato**:

- `Voce LeaderAI firmato` con Siri `Voce 2`, la configurazione piu' naturale gia' collaudata da Sal;
- Cmd destro per dettare, Option + freccia sinistra per voce on/off, Cmd destro + Option per mani libere;
- detta pulito attivo;
- voce agenti e mani libere inizialmente spente, da attivare quando voglio.

Spiega in breve il vantaggio e chiedimi se voglio usarlo. E' una raccomandazione, non un obbligo. Se preferisco una voce o un comportamento diverso, rispettalo, configura l'alternativa e riportalo alla fine.

Per rendere l'app realmente funzionante:
1. Verificare compatibilita' del Mac, sistema operativo, Python/runtime, microfono, permessi e spazio.
2. Scaricare o aggiornare il progetto.
3. Entrare nella cartella mac/ ed eseguire l'installazione corretta.
4. Installare dipendenze e modello necessari, se mancano.
5. Se accetto il profilo consigliato, installare il file firmato `mac/Voce LeaderAI firmato.shortcut`. Se il comando non compare gia' in `shortcuts list`, apri il file e chiedimi soltanto di cliccare `Aggiungi comando rapido`; poi verifica che il nome esatto compaia nell'elenco. Se scelgo un'alternativa, non impormi questo comando: configura e prova la voce scelta.
6. Se accetto il profilo consigliato, verificare in `config.json` i valori `"voce": "Siri (Voce 2)"` e `"comando_voce": "Voce LeaderAI firmato"`. In caso di aggiornamento conserva glossario, sostituzioni e preferenze personali gia' presenti.
7. Verificare che l'installer abbia collegato `voce_hook.py` agli hook `Stop` globali di Claude Code e/o Codex senza cancellare quelli esistenti; usa `voce_hook.py --check-hooks` e correggi se fallisce.
8. Creare o aggiornare i launcher sulla Scrivania.
9. Quando servono permessi macOS, dimmi con precisione cosa cliccare.
10. Fare una prova reale in un campo di testo: tengo premuto Cmd destro, detto una frase, rilascio, e tu verifichi che il testo compaia dove sta il cursore e che si veda il pannello salchiarenza.ai con la barra verde a sorriso.
11. Attivare la voce agenti con **Option + freccia sinistra** e provare davvero sia `parla.py` sia `voce_hook.py` con una frase completa. Verificare anche **Cmd destro + Option** per la modalita' mani libere. Se ho accettato il profilo LeaderAI, la prova passa dal comando `Voce LeaderAI firmato`; non sostituirlo silenziosamente. Se il Mac non lo supporta, fammi ascoltare un'alternativa e chiedimi quale preferisco.

Se trovi un errore software, prova a correggerlo e riprova. Fermati solo se manca un requisito hardware o un permesso che devo concedere io.

Alla fine dammi un report breve:
- installazione completata si/no;
- launcher creati si/no;
- dettatura Cmd destro funzionante si/no;
- voce agenti Option + freccia sinistra funzionante si/no;
- modalita' mani libere Cmd destro + Option funzionante si/no;
- comando `Voce LeaderAI firmato` presente e voce naturale verificata si/no;
- hook risposta di Claude Code/Codex collegato e verificato si/no;
- configurazione personale precedente conservata si/no/non presente;
- Profilo LeaderAI consigliato accettato/modificato e voce scelta;
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
