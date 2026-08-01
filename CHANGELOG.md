# Changelog Voce

Questo file registra le versioni dell'unico prodotto Voce. I dettagli tecnici
restano nei changelog [`mac/`](mac/CHANGELOG.md) e
[`windows/`](windows/CHANGELOG.md).

## 1.3.0-rc.5 - 01/08/2026

- Nelle chat ChatGPT, Claude e Codex il testo grezzo viene incollato subito:
  nessun secondo modello puo' rallentare o cambiare il significato.
- Tolto Claude/Codex dal percorso interattivo di pulizia. Sul Mac resta solo
  il Comando Rapido Apple, massimo 2 secondi; se fallisce arriva il grezzo.
  Su Windows arriva sempre il grezzo con glossario e sostituzioni locali.
- La guardia Apple ora blocca anche frasi ridotte o ampliate oltre il 25% e un
  solo nome del glossario inventato, incluso il caso reale OpenAI -> LeaderAI.

## 1.3.0-rc.4 - 01/08/2026

- La pulizia del testo non resta lenta per giorni: gli interruttori delle
  corsie ora si mettono in **pausa 10 minuti** invece di spegnersi fino al
  riavvio. Su un processo che vive giorni, "spento" voleva dire per sempre.
- Il Comando Rapido non viene piu' cercato solo all'avvio: se compare dopo,
  l'app se ne accorge da sola (25-26-28/07: tre giorni di sola corsia lenta).
- Una corsia che fallisce ora lo dichiara, quindi puo' essere messa in pausa:
  prima un timeout da 20s era indistinguibile da un successo.

## 1.3.0-rc.3 - 01/08/2026

- L'app riconosce e ripara da sola il volume d'ingresso del microfono
  abbassato: prima diventava muta e sembrava rotta, senza dire perche'.
- La diagnosi distingue due guasti che nel log erano identici: guadagno
  d'ingresso basso (si rialza) e stream audio morto (si riavvia). Il vecchio
  rimedio unico, il riavvio, contro il guadagno basso non serviva a nulla.
- Il controllo parte anche all'avvio, cosi' il guasto non si scopre alla prima
  dettatura persa.

## 1.3.0-rc.2 - 29/07/2026

- Corretto il contratto Mac: la consegna e' una fotocopia funzionale dell'app
  viva di Sal, con stessa voce, tasti, tempi, toggle e soglie.
- Riallineati i default pubblici ai valori effettivi: Invio automatico dopo
  `2.5s` anche a voce ON, soglie mani libere `0.018` / `0.013`.
- L'aggiornamento Mac applica lo standard e conserva soltanto glossario,
  sostituzioni apprese e preferenza di log.
- Aggiunto il gate `FOTOCOPIA_SAL_OK`, che legge il Comando Rapido importato e
  blocca voce interna, velocita' o tono differenti.
- Allineato a `2.5s` anche il comportamento di Invio su Windows.

## 1.3.0-rc.1 - 27/07/2026

- Portata nella repo unica la stessa sorgente Mac usata ogni giorno da Sal:
  dettatura, voce agenti, mani libere, detta pulito, protezioni audio e fix del
  percorso runtime quando l'app parte dall'alias LeaderAI.
- Resa ripetibile la consegna: un solo archivio con Mac e Windows, launcher a
  doppio clic, aggiornamento conservativo della configurazione, collegamento
  degli hook Claude Code/Codex, autodiagnosi e collaudo guidato.
- Inclusi il Comando Rapido Mac firmato, la scelta guidata della voce italiana
  su Windows e il modello unico `EMAIL_CONSEGNA.md`.
- Portate nella repo anche le prove automatiche del prodotto: Mac, Windows e
  contratto di release.
- Corretto il merge conservativo: voce, tasti, detta pulito, ritardi e
  calibrazione esistenti non vengono piu' sostituiti dai default.
- Portato nella distribuzione Mac il controllo `Voce Attiva Tutto` usato da
  Sal; il Profilo LeaderAI viene proposto dopo l'installazione e non imposto.
- Specchiate su Windows le protezioni contro allucinazioni/ripetizioni di
  Whisper e Invio automatico durante un nuovo gesto dell'utente.
- Il percorso Codex distingue configurazione da fiducia `/hooks` e richiede
  una prova audio reale.
- Aggiunti versione unica e ponte `CLAUDE.md` portabile anche negli archivi
  estratti su Windows.

### Stato del collaudo

- Mac: sorgente in uso reale da Sal e prove automatiche superate.
- Mac pulito: importazione e primo avvio completi ancora da provare su un
  secondo Mac.
- Windows: logica e percorso di consegna provati automaticamente; tasti,
  microfono e voce reale richiedono il collaudo su un PC Windows.

Finche' le due prove hardware non sono chiuse, questa versione resta
**candidata**. Le consegne usano sempre il tag o il commit esatto verificato,
mai un collegamento generico all'ultima versione.
