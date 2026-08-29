# Changelog Voce

Questo file registra le versioni dell'unico prodotto Voce. I dettagli tecnici
restano nei changelog [`mac/`](mac/CHANGELOG.md) e
[`windows/`](windows/CHANGELOG.md).

## 1.3.0-rc.8 - 29/08/2026

- Tolto l'eco del glossario: su audio corto Whisper poteva ricopiare il
  suggerimento in testa alla frase ("non lo so, mi arrendo" diventato
  "Glossario, mi arrendo.", caso reale scoperto grazie all'audio conservato
  di rc.7). La parola "Glossario" e i nomi ricopiati in apertura ora vengono
  rimossi; il corpo della frase non si tocca. Mac e Windows insieme.

## 1.3.0-rc.7 - 29/08/2026

- Cursore automatico: se nella finestra bersaglio nessuna casella di testo ha
  il focus, l'app mette da sola il cursore nella casella di scrittura (quella
  in basso) prima di incollare. Si detta passando di finestra in finestra
  senza mai prendere il mouse. Le caselle in alto (barra degli indirizzi,
  campi di ricerca) non vengono mai prese; senza una casella sicura non tocca
  niente. Interruttore: `cursore_automatico`.
- Audio conservato opzionale (`conserva_audio_n`, spento di default): le
  ultime dettature restano come file locali in `audio_recenti/` con rotazione
  automatica, per riascoltare le frasi capite male e tarare glossario e
  sostituzioni su casi veri. `PRIVACY.md` aggiornata: niente cambia nella
  configurazione standard.
- L'apprendimento giornaliero delle sostituzioni parte anche se il processo
  resta acceso per giorni (prima solo all'avvio).

## Consegna - 27/08/2026

- L'email mostra un solo blocco delimitato da copiare nell'agente del cliente.
- Lo stesso agente prende la repo, installa, ripara e prova Voce nella medesima
  sessione: durante il lavoro non richiede un secondo messaggio al proprietario.
- Le email reali hanno mostrato installazioni chiuse con funzioni ancora aperte.
  Il modello ora elenca la prova completa: avvio, dettatura, pannello, suoni e
  risposta dell'agente letta ad alta voce. Una prova aperta mantiene viva la
  stessa missione.
- Tolta la promessa fissa dei 20 minuti: il tempo dipende da download, permessi
  e riparazioni; alla persona si chiede soltanto di restare disponibile per le
  conferme e la prova fisica.
- Il controllo di release blocca il ritorno del vecchio passaggio intermedio.

## 1.3.0-rc.6 - 04/08/2026

- L'agente del cliente prende la struttura dalla repo pubblica, esegue
  l'installer e chiude il collaudo; al proprietario restano le conferme di
  sistema e la prova con il microfono.
- Il modello di consegna e le istruzioni Mac e Windows partono dalla repo; un
  test impedisce di riaffidare alla persona passaggi tecnici di consegna.
- La consegna si chiude sul computer del proprietario con una sola conferma
  finale dopo tutte le prove; nessun file
  o rapporto separato viene creato.
- Voce AI dichiara all'accensione che le risposte sono audio sintetico.
- Sul Mac lo stato attivo mostra `AI`; su Windows lo indica la finestra.
- Privacy e collaudo chiariscono che l'audio e' riprodotto al momento e non
  viene registrato, salvato o esportato.
- La consegna richiede ora anche `AI_ACT_CHECK_OK`.

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
