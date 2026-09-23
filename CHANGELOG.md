# Changelog Voce

## 1.3.0-rc.22 - 23/09/2026

- La pill porta il logo LeaderAI. al posto di salchiarenza.ai, e il punto
  verde del logo e' vivo: si accende quando la pill compare, cresce e si
  illumina con la voce mentre parli, pulsa mentre trascrive. Mac e Windows,
  305 prove verdi.

## 1.3.0-rc.21 - 20/09/2026

- ChatGPT (e ogni pagina) in Chrome: la casella ora si trova. Chrome mostra
  la pagina ad Accessibility solo se un programma chiede l'interfaccia
  estesa: senza, la Voce vedeva solo barre e pulsanti e incollava alla cieca
  (44 volte in un giorno). Ora la chiede al tasto premuto, una volta, per i
  browser della famiglia Chrome. L'indirizzo della scheda si legge dalla
  finestra col focus via Accessibility (AppleScript rispondeva «about:blank»
  mentre Sal era su ChatGPT in un'altra finestra): la chat viene
  riconosciuta come chat AI. Solo Mac. 211 prove verdi.

## 1.3.0-rc.20 - 20/09/2026

- Il ritorno alla chat (rc.17) non cambia mai monitor. Con il Samsung sopra il
  Mac, una pagina Chrome senza casella leggibile per un attimo faceva tornare
  il testo nell'app Claude sul monitor sotto: «continua a mettermi dove
  vuole». Ora, se la chat di riserva sta su un altro monitor, il testo resta
  dov'e' (negli Appunti, con l'avviso). Un monitor solo: nulla cambia. Solo
  Mac. 209 prove verdi.

## 1.3.0-rc.19 - 20/09/2026

- Due monitor, due programmi: il testo va al programma che sta sul monitor
  della pill. Dopo la rc.18 restava il caso vero di Sal: Chrome sul Samsung,
  l'app Claude con il focus sul monitor piccolo, e la dettatura compariva
  nel piccolo. Ora, se il programma davanti non ha finestre sul monitor del
  mouse e un altro ce l'ha, il bersaglio e' quello. Un monitor solo: nulla
  cambia. Solo Mac. 207 prove verdi.

## 1.3.0-rc.18 - 20/09/2026

- Con due monitor il testo va dove sta la pill. La pill segue il mouse; il
  testo andava dove stava l'ultimo cursore, anche sull'altro schermo (Samsung
  collegato, dettatura finita nella chat rimasta sul monitor piccolo). Ora,
  se l'app ha una finestra con casella sul monitor del mouse, il cursore va
  li'. Con un monitor solo nulla cambia. Solo Mac: su Windows la pill sta
  sul monitor principale, il caso non si presenta. 206 prove Mac verdi.

## 1.3.0-rc.17 - 18/09/2026

- Se davanti non c'e' dove scrivere (Gmail, Finder, una pagina qualunque), il
  testo torna nell'ultima chat AI dove stavi dettando, invece di finire nel
  vuoto. Mac e Windows, 292 prove verdi.

## 1.3.0-rc.16 - 17/09/2026

- Nelle chat AI l'Invio automatico parte dopo 2 secondi invece di 1: il
  tempo di vedere il testo e premere uno spazio per correggerlo. Mac e
  Windows.

## 1.3.0-rc.15 - 17/09/2026

- La finestra si sveglia mentre parli: al tasto premuto Voce tocca l'app
  davanti e le chiede di accendere l'albero Accessibility, cosi' al rilascio
  la casella e' gia' visibile (Antigravity ci metteva fino a 3,5 secondi).
  Attesa di riserva fino a due secondi. Mac e Windows, 286 prove verdi.

## 1.3.0-rc.14 - 17/09/2026

- La memoria delle caselle sopravvive ai riavvii: file accanto all'app, Mac
  e Windows. 282 prove verdi.

## 1.3.0-rc.13 - 17/09/2026

- Se la finestra dell'app resta "addormentata" per Accessibility anche dopo
  i giri di attesa, Voce clicca da sola dove stava la casella di scrittura
  l'ultima volta in quella finestra e scrive, invece di incollare alla cieca
  con l'avviso sonoro. Mac e Windows; memoria aggiornata a ogni dettatura
  riuscita. 279 prove verdi.

## 1.3.0-rc.12 - 17/09/2026

Versione consegnabile che raccoglie il cantiere locale dal 05/09 (voci sotto),
gia' in uso quotidiano sul Mac di Sal dal 13/09. Non ancora attestati: l'ascolto
reale dentro Antigravity dopo il riavvio dell'app e la prova su PC Windows reale.

- Cursore automatico, secondo giro (17/09/2026): nell'app Claude 2.110.x
  l'albero Accessibility si accende solo dopo il primo tocco, e la dettatura
  finiva "alla cieca" con l'avviso sonoro anche col cursore gia' nella chat.
  Se il primo giro e' vuoto, Mac e Windows aspettano mezzo secondo e
  riguardano una volta prima di dire "nessuna casella". Casi coperti dalla
  suite; prova vera sul log delle dettature successive.
- Antigravity (13/09/2026): la voce degli agenti parla anche dentro
  Antigravity di Google. L'hook Stop si collega in `~/.gemini/config/hooks.json`
  (formato suo: gestore -> eventi), il payload in camelCase viene tradotto nei
  nostri nomi e il lettore riconosce il suo `transcript.jsonl` (`source: MODEL`).
  La dettatura tratta Antigravity e Gemini come chat AI: grezzo immediato e
  Invio dopo 1 secondo, come con Claude e ChatGPT. Prima il testo passava dalla
  pulizia con pausa da documento e nessuna risposta veniva letta. Provato sul
  transcript reale di Sal; pacchetto Drive invariato.
- Dettature riprese (12/09): se si ricomincia mentre un pezzo trascrive,
  si aspetta la fine di tutti i pezzi, si uniscono nell'ordine di registrazione
  e si preme Invio una sola volta. Una nuova pressione sospende anche l'Invio
  gia' in attesa; la ripresa senza parole lo completa senza reincollare.
  Clipboard serializzata, finestre diverse separate, errore di trascrizione
  conserva il testo valido senza inviare un messaggio parziale. Prove gemelle
  Mac/Windows; attivazione locale distinta dal prossimo pacchetto Drive.
- Il turno di chi parla ora ha precedenza fino alla fine dell'Invio
  automatico. Se una risposta del turno precedente arriva mentre la
  dettatura e' ancora aperta, viene scartata e non parte sopra la voce; una
  trascrizione vecchia non puo' riaprire l'audio durante un turno piu' nuovo.
- La voce apre ogni risposta soltanto con il nome dell'assistente: `ChatGPT`
  per Codex e `Claude` per Claude Code. Non pronuncia piu' il progetto o
  `LeaderAI` come parte del nome.
- Tre migliorie della voce: testo preparato per l’ascolto, riascolto
  dell’ultima risposta e code distinte con scelta della conversazione.
  Menu Mac e finestra Windows mostrano nome e anteprima; la cronologia
  locale e’ limitata a otto conversazioni e dichiarata nella privacy.

- Apprendimento Mac e Windows: le ipotesi degli arbitri restano proposte
  nel registro esistente. Il controllo giornaliero e il ripasso non possono
  piu' alterare sostituzioni attive su disco o in memoria.
- Correzioni verificate conservate nel profilo e annullabili una alla volta;
  documentato il controllo della frase reale e di frasi corrette prima di
  rendere globale una coppia. Nessuna nuova dipendenza o archivio.
- Collaudi di regressione su parole comuni, tipi JSON e parita' dei due
  percorsi. Tasti, tempi, invio e timbro della voce conservati.
- Pacchetto Drive e versione distribuita invariati; rilascio separato.

Questo file registra le versioni dell'unico prodotto Voce. I dettagli tecnici
restano nei changelog [`mac/`](mac/CHANGELOG.md) e
[`windows/`](windows/CHANGELOG.md).

## 1.3.0-rc.11 - 04/09/2026

- Mac e Windows restano disponibili insieme nello stesso prodotto e nello
  stesso pacchetto Drive; la prova hardware cambia l'etichetta di stabilita',
  non la disponibilita' della versione.
- Trascrizione progressiva sui discorsi lunghi, mezzo secondo di coda al
  rilascio, Invio piu' rapido nelle chat AI e tetto anti-incanto legato allo
  stato reale del tasto, specchiati sui due sistemi.
- Il ripasso notturno prova gli agenti disponibili in sequenza e registra
  l'errore vero quando nessuno risponde.
- La consegna visibile parte dal modulo App di LeaderAI Ecosystem e da un solo
  pacchetto Google Drive. Ogni modifica aggiorna e prova prima Drive; GitHub
  riceve soltanto il backup successivo.

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
