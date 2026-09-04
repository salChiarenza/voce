# Changelog

## 1.3.0-rc.11 - 04/09/2026 — quattro migliorie dai registri veri

Quattro interventi nati dai log reali 27/08→04/09 (1.422 dettature), fatti da quattro agenti in parallelo e fusi lo stesso giorno. Da provare a voce vera su Mac; Windows su PC reale.

### trascrizione mentre parli
- Dato reale (log 27/08→04/09): 1.422 dettature, 517 oltre i 30s e 181
  oltre i 60s. Whisper partiva solo al rilascio del tasto, quindi l'attesa
  cresceva col parlato: 27s = 2,7s, 66s = 14,5s, 90s = 17s prima
  dell'incolla. Sal detta monologhi lunghi e aspettava a fine frase.
- Trascrizione progressiva (`trascrizione_progressiva: true`, tetto
  `trascrizione_progressiva_blocco_sec: 12`): mentre tieni premuto, un
  thread di sottofondo (`SessioneProgressiva`) trascrive i segmenti gia'
  chiusi; al rilascio resta da trascrivere solo la coda dall'ultimo taglio,
  cosi' l'attesa dipende dalla coda e non dalla lunghezza totale.
- Dove si taglia (`trova_taglio` in `voce_lib.py`): solo su una pausa vera,
  volume per blocco sotto soglia per almeno 0,5s di fila, e solo quando il
  segmento aperto ha superato i 12s. Dentro una pausa non c'e' nessuna
  parola da spezzare; senza pause (parlato continuo) non si taglia e si
  torna al passaggio unico. Sotto i 12s di audio niente cambia.
- Coerenza tra i pezzi: ogni segmento riceve come `initial_prompt` il
  glossario di sempre piu' gli ultimi ~200 caratteri del segmento prima
  (`prompt_con_contesto`), cosi' nomi e punteggiatura non cambiano da un
  pezzo all'altro. I pezzi vengono rincollati da `unisci_segmenti` (spazi
  singoli, mai due segni attaccati, maiuscola dopo il punto, iniziale
  minuscola dopo una frase lasciata a meta' salvo nomi del glossario e sigle).
- Il post-processing e' lo stesso di oggi, una volta sola sul testo unito:
  eco del glossario, sostituzioni, punteggiatura dettata, guardia
  anti-allucinazione e anti-non-parlato. Un pezzo che da solo e' una
  frase-fantasma (coda cortissima) viene scartato prima dell'unione.
- La pill resta su "ascolto" per tutta la registrazione: "Trascrivo…"
  compare solo al rilascio, sulla coda. Il callback audio e il thread
  tastiera non fanno nulla di nuovo (un solo `append` in piu' per blocco);
  Whisper resta uno per volta sotto `_lock_trascrizione`, incluso lo scaldo
  del modello. Un errore in sottofondo riporta al passaggio unico su tutto
  l'audio, senza perdere niente.
- Limiti: da provare a voce vera su Mac (soglia di pausa 0,010 rms
  calibrata sulle misure del 01/08, eventuale eco del contesto nel prompt,
  coerenza delle frasi a cavallo di un taglio); Windows da provare su PC
  reale. Interruttore a `false` = comportamento identico a prima.

### il ripasso notturno taceva il suo errore
Segnalazione del 04/09: "22 righe `audio conservato` nel registro ma
`audio_recenti/` vuota, e il ripasso notturno non impara mai". Verifica sui
dati veri della macchina di Sal, non a memoria.

- Gli audio NON spariscono. Alle 07:53 la cartella operativa
  `tools/voce/audio_recenti/` conteneva esattamente 30 WAV (= `conserva_audio_n`),
  28 di oggi + 2 di ieri, uno per ogni riga `audio conservato` del registro;
  i piu' vecchi li toglie la rotazione a N, come da progetto. Nella cartella
  sorgente della repo (`mac/audio_recenti`) non c'e' niente, ed e' giusto
  cosi': `BASE` e' la cartella operativa (symlink), `.gitignore` la esclude.
  Chi ha guardato una cartella vuota ha guardato quella sbagliata. Per
  togliere l'ambiguita' la riga `audio conservato:` ora scrive il percorso
  intero del file, non solo il nome.
- Il ripasso notturno "non produce niente" per una causa provata, non per
  soglie: l'arbitro (`claude --model haiku -p ...`) esce con codice 1 e stampa
  su stdout `Failed to authenticate: OAuth session expired and could not be
  refreshed`. `ripassa_audio_conservati` ignorava il codice di uscita, dava
  quel testo a `estrai_json`, otteneva `{}` e scriveva "N disaccordi, nessuna
  correzione sicura": 5 notti su 5 (21, 20, 23, 20, 33 disaccordi), stesso
  esito riprodotto oggi coi 30 WAV veri (33 disaccordi, rc=1 in 4 secondi).
  Anche l'apprendimento giornaliero dal registro (`impara_sostituzioni`)
  inghiottiva lo stesso errore: mai una riga `imparate` da fine agosto.
- Nuova funzione pura `risposta_arbitro(returncode, stdout, stderr)`: coppie
  solo se l'agente ha risposto davvero; uscita non zero o risposta senza JSON
  diventano l'errore reale nel registro (`ripasso audio: N disaccordi,
  arbitro fallito (agente uscito con codice 1: Failed to authenticate ...)`,
  `apprendimento sostituzioni: agente fallito (...)`). Cosi' il registro dice
  cosa riparare. Rimedio umano sulla macchina di Sal: `claude login` dal
  Terminal (la sessione OAuth della CLI e' scaduta; il codice non puo' farlo).
- Test: `test_risposta_arbitro_smaschera_agente_fallito`,
  `test_ripasso_arbitro_fallito_lo_dice_nel_registro`.
- **Nessun agente imposto, catena di arbitri**: regola di Sal (04/09): l'app
  non deve dipendere da Claude, i clienti hanno Claude oppure ChatGPT/Codex.
  Il codice gia' sceglieva "Claude se c'e', altrimenti Codex", ma se il primo
  era installato e rotto non provava il secondo: sul Mac di Sal Claude CLI ha
  la sessione OAuth scaduta e Codex CLI e' troppo vecchio per il suo modello,
  quindi 5 notti a vuoto. Ora `comandi_agente()` elenca tutti gli agenti
  presenti e `chiedi_arbitro()` li prova in ordine fermandosi al primo che
  risponde; apprendimento e ripasso notturno passano da li' e il registro
  dice CHI ha fallito e perche' (`claude: ...; codex: ...`).

### Invio automatico al ritmo delle chat AI
- **Pausa pre-Invio piu' corta nelle chat AI**: dai log veri 30/08→04/09 il
  40% degli Invii automatici veniva ANNULLATO (137 su 363 il 30/08, 92 su
  239 l'01/09, 10 su 22 il 04/09): in ChatGPT, Claude, Codex e Claude Code
  Sal vede il testo incollato, non aspetta i 2,5s pensati per i documenti e
  preme Invio a mano, e quel tasto annulla l'Invio dell'app. Il ritardo era
  piu' lungo del suo ritmo. Nuova chiave
  `invio_automatico_ritardo_chat_ai_sec` (default 1.0), usata SOLO quando il
  bersaglio e' una chat AI (stesso riconoscimento di `destinazione_agente`,
  nessun rilevamento nuovo) e la voce agenti e' spenta. A voce accesa resta
  `invio_automatico_ritardo_conversazione_sec`; fuori dalle chat AI resta
  `invio_automatico_ritardo_sec` (2,5s: nei documenti serve tempo per
  correggere). La scelta vive in `ritardo_invio()` di `voce_lib.py`,
  testata su tutti e tre i rami; l'annullamento su tasto premuto o nuova
  dettatura e' identico a prima, e il log dell'Invio riporta l'attesa usata.

### tetto 90s legato al tasto
- Caso reale (log 04/09 06:41): Sal dettava da 90 secondi col tasto-detta
  ancora fisicamente premuto e l'airbag anti-incanto (`max_registrazione_sec`
  = 90) ha fermato la registrazione tagliandogli la frase (159 parole). Sal
  detta spesso monologhi lunghi: 181 dettature su 1.422 superano i 60s.
  Causa: il tetto a tempo era cieco sul tasto, nato per il rilascio perso da
  pynput ma applicato anche alla dettatura vera. Cosa cambia: il tetto dei
  90s scatta SOLO se il tasto-detta non e' piu' fisicamente giu' secondo il
  sistema (Quartz, `_cmd_giu()`, la stessa lettura del combo mani libere);
  finche' Cmd e' giu' si continua a registrare. Resta un tetto DURO separato,
  `max_registrazione_tasto_sec` (300s), che ferma comunque per il tasto
  incastrato. La decisione vive in `voce_lib.stop_anti_incanto` (testata) ed
  e' usata sia dal timer del pannello sia da `watchdog_audio`. Il VAD
  mani-libere non cambia: li' il tasto non c'entra e vale il tetto di prima.

## 1.3.0-rc.10 - 04/09/2026 — mezzo secondo di coda al rilascio

- Richiesta di Sal: mollando Cmd destro un pelo prima di finire la frase,
  l'ultima sillaba andava persa. Ora al rilascio il microfono resta in
  ascolto ancora `0.5s` (`coda_rilascio_sec`) prima di chiudere e
  trascrivere: lo stream e' sempre aperto e il callback continua ad
  accodare blocchi, quindi l'attesa vive nel worker audio (`stop_coda`),
  mai nel thread tastiera. Vale solo per la dettatura manuale: il VAD
  mani-libere ha gia' la sua pausa di silenzio e l'anti-incanto resta
  immediato. Mezzo secondo, non uno intero: un secondo pieno si pagherebbe
  su ogni dettatura come ritardo prima dell'incolla.

## 1.3.0-rc.9 - 30/08/2026 — la voce agenti arriva in fondo

La voce agenti si troncava a meta' lettura. Analisi del 30/08 sui log veri:
tre cause, tutte con lo stesso effetto (audio mozzato, mai ripreso).

- Doppio evento di fine risposta (10 letture doppie su 26 misurate): l'hook
  ora ricorda impronta sha1 e istante dell'ultima risposta letta e scarta la
  ripetizione identica entro 8 secondi (`gia_letto_da_poco`, file di stato
  `ULTIMA_LETTURA`), tracciandola nel registro.
- Una nuova risposta uccideva la lettura in corso (`parla()` faceva
  `ferma()` cieco: tre risposte in 21 secondi, solo l'ultima arrivava in
  fondo). Ora `parla()` deposita il testo in `LETTURA_PENDENTE` e un processo
  "lettore" unico legge una voce per volta fino a svuotare l'attesa: la
  lettura in corso si finisce SEMPRE, e tra i testi arrivati nel frattempo
  vince l'ultimo (mai minuti di audio arretrato). Il flag `PARLANDO` resta
  alzato per tutta la corsa, cosi' il mani-libere non si riarma nei buchi
  tra due letture.
- Il lettore unico e' garantito da un flock del kernel (`LETTORE_LOCK`):
  si libera da solo alla morte del processo, comunque muoia, quindi non
  esistono lock stantii da rubare ne' le corse che ne derivano (trovate
  dalla revisione avversaria sulla prima stesura a file-pid).
- Ogni lettura ha un tetto proporzionale al testo (~4x la durata stimata,
  pavimento 60s): uno `shortcuts run` incantato — classe di guasto gia'
  vista nella corsia di pulizia — viene ucciso e si passa oltre, invece di
  tenere il lock per sempre e ammutolire tutte le risposte successive.
- Il lettore e' sganciato (`start_new_session`) e l'hook torna subito:
  il timeout di 10s dell'hook Stop non puo' piu' toccare l'audio.
- Il barge-in resta immediato: la dettatura (tasto o mani libere) e
  `parla.py --stop` zittiscono subito e svuotano l'attesa; il toggle voce
  annuncia lo stato senza mettersi in coda dietro una lettura lunga.
- Ogni lettura iniziata lascia una riga nel registro ("lettore: lettura
  iniziata"): una lettura uccisa e una mai partita non sono piu' identiche
  viste da fuori.
- Punteggiatura dettata (`converti_punteggiatura_dettata`): "punto
  esclamativo", "punto interrogativo", "punto e virgola", "puntini di
  sospensione", "a capo"/"vai a capo"/"nuova riga" detti a voce diventano
  segni veri, su ogni destinazione (Whisper virgole e domande le mette a
  orecchio, l'esclamativo in italiano quasi mai). Solo comandi
  inequivocabili: "punto" e "virgola" da soli restano parole; con l'articolo
  davanti ("il punto esclamativo") non si tocca; "venirne a capo" resta un
  idioma. Dopo ! ? e a-capo la frase riparte maiuscola.

## 1.3.0-rc.9 (bis) - 30/08/2026 — la dettatura capisce meglio e non perde frasi

- Modello: da `whisper-large-v3-turbo` a `whisper-large-v3-mlx`. Il
  riconfronto promesso in rc.7 e' stato fatto sugli audio reali conservati
  (30 dettature vere di Sal del 30/08): 20 su 30 diverse, il grande vince
  nettamente ("salchiarenza.ai" dove turbo scriveva sigle a caso, "LeaderAI"
  vs "lead-ray", "esclamativi" vs "sclamativi", punteggiatura piu' ricca).
  Costo misurato: 1,71s vs 0,77s a dettatura, accettato: la richiesta di
  Sal e' la comprensione, non il decimo di secondo.
- Incolla alla cieca: quando il cursore automatico legge la finestra e
  caselle di testo NON ce ne sono, prima la frase veniva incollata nel
  vuoto e PERSA (il ripristino degli Appunti la cancellava — caso reale
  14:49 del 30/08). Ora in quel caso il testo resta negli Appunti (Cmd+V
  dove serve), suona un avviso diverso ("Basso") e l'Invio automatico non
  parte: un Invio su un focus ignoto puo' essere un bottone qualunque.
- Glossario personale arricchito dai casi veri del giorno (PEC, dettatura,
  call) e sostituzioni per gli errori ricorrenti visti nei log.
- Cursore automatico anche nei documenti (`casella_ammissibile`): prima
  tutto cio' che stava nella parte alta della finestra veniva rifiutato per
  non scrivere nella barra degli indirizzi, ma cosi' l'area documento di
  Note/TextEdit/Word (che parte dall'alto) restava fuori e girando pagina
  la dettatura non scriveva. Ora un'area alta almeno meta' finestra e' un
  documento e si prende; le barre restano fuori perche' basse di statura.
- Ripasso notturno degli audio conservati (`voce_lib.py --ripasso`): una
  volta al giorno, insieme all'apprendimento esistente, un processo a parte
  (sganciato, bassa priorita') ritrascrive le dettature conservate con un
  secondo riconoscitore (`modello_ripasso`, default turbo), le passa dalla
  stessa pulizia del vivo e, dove i due modelli non sono d'accordo, fa
  scegliere all'agente locale nel contesto della frase. Le correzioni sicure
  entrano da sole nelle sostituzioni personali: piu' la usi, piu' ti capisce.
  Attivo solo con `conserva_audio_n` > 0 (l'audio resta sul computer).

## 1.3.0-rc.8 - 29/08/2026 — via l'eco del glossario

Aggiornata nello stesso giorno: nel cursore automatico il tetto di ricerca
sale da 600 a 4000 elementi (misurati ~15.000/secondo: il tempo resta la
cintura vera) e nei browser, quando il focus sta sulla pagina (AXWebArea),
la ricerca parte dentro la pagina saltando la struttura del browser. Caso
reale 13:17: su Gmail in vista elenco l'app ha detto correttamente "nessuna
casella di testo nella finestra" — li' una casella non esiste; il tetto
basso pero' avrebbe potuto tagliare pagine grandi con una casella vera.

- `rimuovi_eco_glossario`: su audio corto Whisper puo' ricopiare il prompt
  del glossario in testa alla trascrizione (caso reale 13:10: "non lo so, mi
  arrendo" -> "Glossario, mi arrendo."; l'audio conservato di rc.7 ha
  permesso di ritrascriverlo e confermare la causa). "Glossario" seguito da
  `:`/`,`/`.` in apertura e gli eventuali nomi ricopiati vengono rimossi
  prima delle sostituzioni; un eco puro diventa testo vuoto e si scarta.
  "Glossario" nel corpo della frase, o seguito da una parola normale, resta.

## 1.3.0-rc.7 - 29/08/2026 — il click nella casella lo fa l'app

- Cursore automatico via Accessibility: al momento dell'incolla, se nell'app
  bersaglio nessuna casella di testo ha il focus, l'app trova la casella di
  scrittura della finestra frontale (la piu' in basso), le da' il focus e
  solo se serve fa un click del programma, riportando poi il puntatore
  dov'era. Le caselle nella parte alta della finestra non vengono mai prese:
  provato su Chrome il 29/08, senza questo filtro il testo sarebbe finito
  nella barra degli indirizzi. Ricerca con tetto di 600 elementi e 0,5s
  (misurata: 0,04s su Claude e ChatGPT); se non trova una casella sicura non
  tocca niente, come prima. Interruttore: `cursore_automatico`.
- Audio conservato opzionale (`conserva_audio_n`, default 0 = spento): le
  ultime N dettature restano come WAV in `audio_recenti/`, solo sul computer,
  con rotazione automatica; a opzione spenta non si salva nulla. Serve a
  riascoltare le frasi capite male e tarare glossario e sostituzioni su casi
  veri invece che a memoria.
- Apprendimento sostituzioni: controllo ogni ora col gate giornaliero
  interno. Prima partiva solo all'avvio, e con un processo che vive giorni
  non girava quasi mai (stesso difetto della corsia Apple risolto in rc.4).
- Modello misurato su questo Mac (29/08): turbo 0,64s vs large-v3 1,66s a
  parita' di trascrizione sulla clip di prova. Si resta su turbo; il
  riconfronto si fara' sugli audio reali conservati.

## Consegna - 27/08/2026 — una sola missione fino alla prova

- Il messaggio per l'agente sta fra due righe di trattini: il proprietario vede
  con precisione cosa copiare.
- Dopo l'installazione lo stesso agente prosegue nella medesima sessione fino
  alla prova reale: eliminato il secondo messaggio che il proprietario doveva
  reinviare all'agente.

## 1.3.0-rc.6 - 03/08/2026 — Voce AI riconoscibile

- All'accensione dichiara che le risposte dell'agente sono audio sintetico.
- Pill e barra dei menu mostrano `AI` quando la lettura e' attiva.
- Privacy e collaudo registrano che l'audio e' effimero e non viene salvato.
- La missione chiude con una sola conferma finale dopo tutte le prove, priva di
  file o rapporti separati.

## 1.3.0-rc.5 - 01/08/2026 — testo immediato e significato protetto

Il log reale ha separato i due problemi: Whisper trascriveva in `0.4-1.7s`,
ma dopo un rifiuto Apple la riserva Claude teneva la frase ferma fino a `20s`.
Inoltre la pulizia Apple aveva trasformato OpenAI in LeaderAI e cancellato
intere parti di alcune frasi senza superare la vecchia soglia di sicurezza.

- ChatGPT, Claude e Codex, sia come app sia nelle schede Chrome/Safari, usano
  sempre il grezzo immediato.
- Fuori dalle chat agente resta solo la corsia Apple, con tetto `2s`; errore,
  rifiuto o controllo fallito portano subito al grezzo. Nessun agente viene
  piu' avviato durante una dettatura.
- La guardia blocca una variazione di parole oltre il 25% e qualsiasi nome del
  glossario aggiunto senza una forma davvero simile nel grezzo.

## 1.3.0-rc.4 - 01/08/2026 — la pulizia non resta lenta per giorni

Misure sui log del 25/07-01/08 (495 dettature): la trascrizione e' veloce
(mediana `0.6s`), la lentezza sta tutta nella pulizia del testo. Attesa dal
rilascio del tasto al testo incollato: mediana `1.9s` nei giorni buoni, ma
`7.2s` oggi con punte a `28.3s`.

Causa: gli interruttori delle corsie di pulizia sapevano solo spegnersi.

- La corsia veloce (Comando Rapido Apple, mediana `1.3s`) si spegneva dopo 2
  fallimenti di fila **fino al riavvio del processo**. Il processo di Sal e'
  rimasto in piedi 2 giorni e 16 ore: 27/07 e 29/07 si e' spenta e da li' ogni
  dettatura e' passata dall'agente lento, con 12 timeout da `20s` il solo 29/07.
- Peggio: `SHORTCUT_PULIZIA` veniva cercato **una volta sola all'avvio** e
  azzerato per sempre se in quell'istante non c'era. Il 25, 26 e 28/07 la
  corsia veloce non e' stata usata nemmeno una volta: 123 pulizie tutte lente.
- `corsia_utilizzabile()` / `registra_esito_corsia()`: ora lo spegnimento e'
  una **pausa di 10 minuti**, poi si riprova. Vale per entrambe le corsie, e
  anche per il Comando Rapido assente all'avvio (puo' comparire dopo).
- `pulisci_con_agente()` ora torna `None` quando fallisce, come gia' faceva
  `pulisci_con_shortcut()`. Prima tornava il grezzo, quindi un timeout da 20s
  era indistinguibile da un successo e nessun contatore poteva accorgersene.
  Il grezzo resta garantito dal chiamante (`pulito or testo`).

## 1.3.0-rc.3 - 01/08/2026 — il microfono abbassato non ferma piu' l'app

Caso reale del 01/08/2026: il volume d'ingresso di sistema e' sceso da solo a
`36/100` mentre Sal dettava. Il parlato arrivava a rms `0.0012-0.0014` contro
una `SOGLIA_VOCE` di `0.004`, quindi ogni dettatura veniva scartata in
silenzio. Niente era rotto: l'app non sentiva piu'.

- `diagnosi_audio_muto()` in `voce_lib.py` separa le due cause che il log
  confondeva sotto lo stesso "volume sotto soglia": guadagno d'ingresso basso
  contro stream CoreAudio incantato.
- `ripara_guadagno_ingresso()` rialza il volume d'ingresso a `75` e **non**
  riavvia il processo: contro un guadagno abbassato il riavvio non serviva,
  produceva solo un ciclo di riavvii inutili.
- `allinea_volume_ingresso()` fa lo stesso controllo all'avvio.
- La pill mostra `🎤 Alzo il microfono…`: prima la dettatura spariva senza
  spiegazione a schermo.
- `airbag_stream_muto()` resta per lo stream morto, ma non e' piu' l'unica
  rete: guardava solo le dettature oltre i 3 secondi e le prove di Sal erano
  da 0,5 e 1,2 secondi, quindi non poteva vedere nulla.
- Livelli scelti su misure vere nella stanza di Sal (rumore ambiente): a `36`
  dava `0.0021`, a `75` `0.0062-0.0074`, a `100` `0.0120` — cioe' sopra
  `SOGLIA_VOCE` e vicino alla soglia mani libere `0.018`, con il VAD che si
  sarebbe auto-innescato. Da qui minimo `60`, target `75`.

## 1.3.0-rc.2 - 29/07/2026 — fotocopia funzionale di Sal

- Il profilo Mac distribuito coincide con quello effettivamente usato da Sal:
  Siri `Voce 2`, voce interna `com.apple.siri.natural.Francesca`, velocita'
  `0.5`, tono `1.0`, stessi tasti, stessi toggle e stessi tempi.
- Corretto l'Invio a voce ON da `0.3s` a `2.5s`; corrette le soglie mani
  libere da `0.010` / `0.005` a `0.018` / `0.013`.
- Il merge di aggiornamento riallinea il comportamento standard e conserva
  solo glossario, sostituzioni apprese e preferenza di log.
- `voce_hook.py --check-profile` legge in sola lettura il Comando Rapido
  installato e produce `FOTOCOPIA_SAL_OK` soltanto quando voce, velocita' e
  tono coincidono.
- Aggiunto un gate locale che confronta i parametri pubblici con l'app viva di
  Sal e blocca future derive.

## 1.3.0-rc.1 - 27/07/2026 — repo cliente autosufficiente

- La stessa sorgente usata ogni giorno da Sal e' ora accompagnata nella repo da
  versione unica, prove automatiche, installazione conservativa e modello di
  consegna.
- L'installer copia `VERSION` nella cartella cliente; la missione locale ne
  verifica la presenza prima del collaudo.
- L'aggiornamento conserva tutte le scelte gia' presenti; il Profilo LeaderAI
  viene proposto dall'agente dopo l'installazione e non e' piu' imposto dal
  launcher.
- Il controllo rapido `Voce Attiva Tutto.command` usato da Sal e' ora
  ripetibile anche nell'installazione cliente.
- Il collaudo Codex include revisione da `/hooks` e una risposta realmente
  letta ad alta voce.
- La versione resta candidata finche' importazione, primo avvio, permessi,
  dettatura e voce non vengono riprovati partendo dall'archivio su un secondo
  Mac.

## Non rilasciato - 27/07/2026 — conversazione veloce anche tramite symlink

- Corretto il percorso runtime dell'app viva di Sal: quando Python avviava
  `detta.py` o `voce_hook.py` attraverso i symlink di `tools/voce`, poteva
  cercare `VOICE_ON`, `MANI_LIBERE_ON` e `config.local.json` nella repo fisica.
  L'app non riconosceva quindi la conversazione attiva e aggiungeva fino a
  3-4 secondi di detta pulito. Ora conserva la cartella realmente invocata e
  salta la pulizia come previsto, mantenendo la pausa personale di Sal prima
  dell'Invio per rileggere o aggiungere una seconda frase.

## Non rilasciato - 23/07/2026 — pre-invio completo

- L'email di consegna usa un link cliccabile nell'HTML e conserva l'URL esteso
  nel fallback testuale.
- Aggiunti verifica dell'agente che tiene il cliente, controllo Gmail Sent
  prima e dopo l'invio, conferma di una sola copia, tono, firma e controllo
  degli em dash.

## Non rilasciato - 23/07/2026 — email di consegna versionata

- Aggiunto `EMAIL_CONSEGNA.md` nella radice della repo come fonte unica dell'email Mac e Windows: link esatto, percorso a clic, conferme del sistema, passaggio all'agente locale, ramo di recupero e collaudo.
- Ogni miglioramento dell'esperienza di installazione aggiorna app, istruzioni ed email nello stesso commit; la cronologia Git conserva l'evoluzione.

## Superato il 04/08/2026 — passaggio di sicurezza locale

- Questo percorso trasferiva al proprietario un passaggio tecnico ed e' stato ritirato. La consegna corrente parte dalla repo ed e' eseguita interamente dal Claude Code o Codex del cliente.
- `install.sh` copia `INSTALLA_CON_AI.md` nella cartella locale, cosi' l'agente trova la missione completa dopo il passaggio umano.
- Alla persona restano soltanto conferme macOS e prova reale.

## Non rilasciato - 17/07/2026 (27) — stessa voce naturale della versione di Sal

- La prima installazione separa ora requisiti tecnici e **Profilo LeaderAI consigliato**: Siri `Voce 2`, tasti e detta pulito vengono proposti in una sola domanda, non imposti. Un'alternativa scelta dal proprietario viene configurata, provata e riportata nel report.
- Rinominato il Comando Rapido TTS in **`Voce LeaderAI firmato`**.
- La distribuzione Mac include il file Apple firmato `Voce LeaderAI firmato.shortcut`, esportato dal comando realmente collaudato da Sal con Siri `Voce 2`.
- Config pubblico allineato alla versione Sal: `"voce": "Siri (Voce 2)"` e `"comando_voce": "Voce LeaderAI firmato"`.
- Installer e missione agente aprono il file firmato solo se manca, chiedono all'umano il solo click Apple `Aggiungi comando rapido` e chiudono con una prova audio reale. Vietato il fallback silenzioso ad Alice.
- L'aggiornamento non riparte piu' da zero: conserva glossario, sostituzioni, tasti e calibrazione; monta `voce_hook.py` negli hook globali di Claude Code/Codex senza cancellare quelli esistenti e ne verifica la presenza.
- Corrette le istruzioni consegnabili sul comando reale: voce agenti = `Option + freccia sinistra`, mani libere = `Cmd destro + Option`. Rimossi i riferimenti errati ad Alt destro.
- Corretto il segnale `PARLANDO`: il monitor resta vivo fino alla fine dell'audio e rimuove sempre il flag, evitando che il mani libere resti in pausa dopo una risposta vocale.
- Eliminata la doppia sorgente Mac: l'app viva di Sal usa questi stessi file tramite symlink; solo `config.local.json` conserva dati personali e calibrazione fuori dalla distribuzione. Una modifica al prodotto e' quindi gia' nella repo, senza copia manuale.

## Non rilasciato - 09/07/2026 (26)

- **L'airbag "audio fuori scala" ora si ripara da solo se la corruzione persiste**: il primo episodio si scarta e basta (transitorio che si riassorbe), dal **secondo di fila** l'app si riavvia da sola con lo stesso riavvio pulito del cambio device — niente dettature a vuoto finche' non riavvii a mano. Policy pura `aggiorna_scarti_fuori_scala` in `voce_lib.py`, testata. *(Su Windows non serve: li' lo stream si apre fresco a ogni dettatura, basta lo scarto.)*

## Non rilasciato - 09/07/2026 (25)

- **Airbag "audio fuori scala"**: se una dettatura arriva con rms > 1.0 — fisicamente impossibile per uno stream float32 sano, i sample vivono in [-1, 1] — l'audio e' corrotto (CoreAudio ha rimappato il device sotto lo stream sempre-aperto) e si scarta invece di trascriverlo (caso reale 09/07: ~20s a rms 3-4, Whisper allucinava "KFC is a…" e l'invio automatico spediva la spazzatura agli agenti). Il transitorio si riassorbe da solo in pochi secondi; niente riavvio. Funzione pura `audio_fuori_scala` in `voce_lib.py`, testata. *(Gemellata su Windows lo stesso giorno.)*

## Non rilasciato - 08/07/2026 (24)

- **Airbag "stream muto"**: se una dettatura lunga (≥3s) arriva quasi muta (caso reale: 12s di parlato a rms 0.0016 dopo la comparsa del "Microfono di iPhone" via Continuity), lo stream CoreAudio sempre-aperto si e' incantato e l'app si riavvia da sola, come gia' fa per il cambio device. Il watchdog per nome-device non bastava: PortAudio congela la lista dispositivi all'avvio, quindi non vedeva il cambio. Cooldown 10 min su file: se il riavvio non risolve (mic muto davvero), niente loop. I tocchi corti senza parlato restano silenzio legittimo. *(Da gemellare su Windows: li' manca anche lo scarto-per-soglia; collaudo su PC reale prima di dichiararla.)*

## Non rilasciato - 06/07/2026 (23)

- **L'Invio automatico si annulla se tocchi la tastiera o stai gia' ridettando**: durante la pausa pre-Invio, qualsiasi tasto premuto o una nuova registrazione in corso bloccano l'Enter (caso reale: Sal voleva aggiungere una seconda frase e la prima e' partita da sola). Il testo resta incollato e parte con l'Invio del turno successivo, tutto insieme.

## Non rilasciato - 06/07/2026 (22)

- **`voce mani on|off`**: lo script `voce` ora comanda anche le mani libere, e `voce` senza argomenti mostra lo stato di entrambe. Cosi' l'agente puo' eseguire "spegni il microfono" al volo (`voce mani off`) invece di spiegare i tasti.

## Non rilasciato - 06/07/2026 (21) — protezioni mani libere

- **Auto-spegnimento dopo inattivita'** (`mani_libere_autospegnimento_min`, default 10): mani libere dimenticata accesa = telefonate/persone/video trascritti e inviati in chat. Dopo N minuti senza dettature si spegne da sola con suono. Verificato dal vivo (timeout di prova: spenta e loggata). `0` = disattivato.
- **Filtro anti-non-parlato**: Whisper dichiara per segmento quanto e' sicuro che sia voce (`no_speech_prob`) e quanto e' confidente (`avg_logprob`). Musica/rumore/sottofondo con no_speech alto E confidenza bassa vengono scartati prima di diventare testo in chat (`soglia_no_speech` 0.6, `soglia_confidenza` -1.0).

## Non rilasciato - 06/07/2026 (20)

- **La pulizia si salta anche a mani libere ON, non solo a voce ON**: caso reale — Sal usava mani libere con la voce agenti spenta, la pulizia girava e il modello Apple ha RIASSUNTO il dettato invece di correggerlo (35 parole grezze intere ridotte a meta': "si e' mangiato le parole" era la pulizia, non il microfono). Il criterio "sono in conversazione con l'agente" ora e' `voce ON || mani libere ON`.

## Non rilasciato - 06/07/2026 (19)

- **Toggle mani libere: suoni immediati invece dell'annuncio parlato**: il TTS ("Mani libere attivate", via Shortcuts/Siri) teneva il microfono sordo ~4s tra latenza, durata e periodo di grazia — quello che si diceva subito dopo il combo andava perso (caso reale: l'"Ok" di Sal ignorato). Ora: ON = suono "Glass", OFF = suono "Bottle", si puo' parlare immediatamente. Lo stato visivo lo danno il microfonino flottante e l'icona nella barra menu.

## Non rilasciato - 06/07/2026 (18) — mani libere: frasi intere, non spezzate

- **Pre-registrazione (~1s)**: il VAD parte quando gia' stai parlando — senza anello di pre-buffer la prima parola andava persa ("mi ha preso solo una parte"). Ora la registrazione parte dai blocchi audio appena precedenti allo start. Vale anche per la dettatura manuale (innocuo: il pre-roll e' silenzio).
- **Isteresi a due soglie**: innesco a `mani_libere_soglia_voce` (0.010), stop solo sotto `mani_libere_soglia_stop` (0.005, meta') per `mani_libere_silenzio_sec` (1.4s, era 0.9): chi parla piano (rms 0.012-0.015 misurato) non viene piu' tagliato nelle pause naturali. Attivazione piu' rapida (0.2s).

## Non rilasciato - 06/07/2026 (17) — combo modificatori riscritto sui flag di sistema

- **Cmd+Option ora si legge dai flag Quartz, non dagli eventi pynput**: log alla mano, la tastiera fisica di Sal NON generava alcun evento pynput quando i due modificatori venivano premuti insieme (con eventi sintetici funzionava, con le dita no — zero righe nel log). Nuovo `worker_combo_mani_libere`: polling 0.05s su `CGEventSourceFlagsState` (stato di sistema, sempre vero qualunque tastiera); debounce per hold; chiude la dettatura manuale se era appena partita. Vale per qualsiasi Cmd + qualsiasi Option (destri o sinistri). Anche il combo voce (Option+freccia sinistra) ora verifica Option dai flag di sistema invece che da pynput. Rimossi ALT_KEYS/alt_premuto e il log diagnostico temporaneo.

## Non rilasciato - 06/07/2026 (16)

- **Fix: spegnere mani libere mentre il VAD registra chiudeva male**: la registrazione restava aperta (pill fissa sullo schermo) finche' non scattava l'anti-incanto dei 90s — percepita come "resta sempre attivo". Ora il worker chiude la registrazione appena la modalita' si spegne.
- I toggle voce/mani libere ora scrivono una riga nel log ("combo voce: ...", "combo mani libere: ON/OFF"): diagnosi immediata quando un combo fisico non risponde.

## Non rilasciato - 06/07/2026 (15)

- **Microfonino mani-libere sempre visibile e vivo**: quando la modalita' e' attiva, in basso (a destra del centro, fuori dall'ingombro della pill) resta un piccolo 🎙️ flottante che pulsa col volume — piu' forte parli, piu' grande e opaco. Sparisce quando la modalita' si spegne. Risolve "non si intuisce se e' attivo": lo stato ora ha un segno vivo sullo schermo, non solo l'icona statica nella barra menu.

## Non rilasciato - 06/07/2026 (14)

- **Voce agenti = Option + freccia sinistra** (scelto e provato da Sal: freccia attaccata a Option sulla sua tastiera, nessuna interferenza). Sostituisce il long-press di Option (~1s), poco scopribile. Rimossa la chiave `tasto_voce_hold_sec`. Verificati 4 casi: toggle ON/OFF, freccia da sola neutra, Cmd+Option (mani libere) invariato.

## Non rilasciato - 06/07/2026 (13)

- **Rimossa la pillola-lampo "Mani libere attive"**: ricompariva a ogni fine dettatura (2.5s), ridondante e fastidiosa ora che lo stato e' sempre visibile nell'icona della barra menu. La pillola ora appare solo durante ascolto/trascrizione, come per la dettatura col tasto. Rimossa la chiave config `mani_libere_pillola_sec`.

## Non rilasciato - 06/07/2026 (12)

- **Icona di stato nella barra dei menu**: la pillola e' un lampo, quindi non c'era modo di sapere se mani libere/voce fossero accese senza provare a parlare. Ora in alto a destra compare 🎙️ (mani libere attiva) e/o 🔊 (voce agenti accesa); niente di attivo = nessuna icona. Aggiornata ogni ~0.5s dal tick del pannello.

## Non rilasciato - 06/07/2026 (11) — tasti DEFINITIVI

- **Mani libere = Cmd destro + Option tenuti insieme** (era la scelta di Sal fin dall'inizio; Option+meno inoltre digitava un "–" in chat a ogni attivazione — solo modificatori, niente caratteri sporchi). Ordine indifferente: Option→Cmd non avvia la dettatura; Cmd→Option annulla la dettatura appena partita (audio < 0.4s scartato dal gate). Voce agenti resta Option tenuto ~1s da solo. Verificati 4 casi: entrambi gli ordini del combo, long-press voce, Cmd hold normale.

## Non rilasciato - 06/07/2026 (10)

- **Voce agenti: da Option+punto a Option TENUTO ~1s** (`tasto_voce_hold_sec`): Option+punto apre la sezione laterale dell'app di Sal — conflitto trovato al primo uso reale. Ora: tieni Option da solo ~1s e rilascia = toggle voce; tocco breve = niente; Option usato per comporre caratteri o per il combo meno = niente. Mani libere resta Option+meno. Verificati tutti e 4 i casi (long-press ON, tocco breve neutro, combo meno senza interferenza sulla voce, long-press OFF).

## Non rilasciato - 06/07/2026 (9) — tasti scelti da Sal (superati dalla v10 per conflitto app)

- **Option+punto = voce agenti, Option+meno = mani libere** (tasti tutti vicini in basso a destra sulla sua tastiera). Option da solo torna NEUTRO (niente piu' toggle su alt_r: deve poter far parte del combo senza commutare). Rimossi il combo Ctrl+Option e la chiave config `tasto_voce`. Riconoscimento sul carattere composto ("…", "–"), stabile su ogni layout: la prova fisica di Sal di ieri sera confermava che questi char arrivano correttamente (il fallimento di allora era un problema diverso, gia' risolto: `Key.alt` generico non tracciato). Verificato in accensione E spegnimento per entrambi con eventi a carattere forzato.

## Non rilasciato - 06/07/2026 (8)

- **Soglia d'innesco mani libere separata e più alta** (`mani_libere_soglia_voce`, default 0.012): il VAD usava la soglia-voce generale (0.004) e partiva sul rumore ambiente (caso reale: rms 0.0046 → Whisper allucinava "ARRAB ARRAB" sul nulla, incollato in chat). Il parlato vero sta a 0.02-0.06: con 0.012 il rumore non innesca più, la voce sì. Il gate finale sull'intero audio resta invariato.

## Non rilasciato - 06/07/2026 (7)

- **Fix annuncio "Mani libere attivate" mai sentito**: all'accensione il flag si attivava PRIMA dell'annuncio; il VAD partiva sul rumore ambiente e `avvia_registrazione()` (che zittisce la voce come prima cosa) uccideva l'annuncio appena partito — Sal non sentiva mai la conferma e la coda audio diventava un "Yeah." allucinato incollato in chat. Ora: annuncio prima (crea `PARLANDO` in modo sincrono), flag dopo — il worker aspetta la fine dell'annuncio prima di armarsi.
- **Periodo di grazia dopo la voce** (`mani_libere_grazia_dopo_voce_sec`, default 0.7s): quando l'agente smette di parlare, il VAD non riparte all'istante — la coda audio delle casse non viene scambiata per Sal.
- **Frasi-fantasma inglesi**: "Yeah.", "Yes", "Thank you", "Thanks for watching", "Bye" aggiunte al filtro allucinazioni (Whisper le inventa su code audio/rumore anche con lingua italiana). Confronto sempre sull'intera stringa: dentro frasi vere non scattano. Test aggiornati (46).

## Non rilasciato - 06/07/2026 (6)

- **Pillola "mani libere" ora e' un lampo, non fissa**: Sal ha lo schermo piccolo e la pillola "🎙️ Mani libere attive" restava sempre visibile — troppo invadente. Ora compare 2.5s (`mani_libere_pillola_sec`) e poi si nasconde da sola; un vero ascolto la fa ricomparire normalmente (onda, "Trascrivo…", ecc.).
- Rimossi dal Desktop i due lanciatori separati (`Voce Dettatura.command`, `Voce On-Off.command`): resta solo `Voce Attiva Tutto.command`.

## Non rilasciato - 06/07/2026 (5) — incidente reale, secondo caso

- **Fix allucinazione a ripetizione senza spazi**: dopo il fix di stanotte su "мент" ripetuto, un nuovo caso reale — "Ecologia" seguito da centinaia di "版" (cinese) SENZA spazi tra i caratteri. Lo split per parole vedeva tutto come "1 parola sola" (log: "trascritto: 1 parole"), quindi il controllo non scattava. Aggiunto un secondo controllo a livello di CARATTERE (regex su run ripetuti): cattura anche le scritture senza spazi tra parole (cinese, giapponese...) dove il conteggio per parole non si accorge di niente. Test aggiunto (46 totali).

## Non rilasciato - 06/07/2026 (4)

- **Mani libere ora e' un flag su file, come la voce agenti**: prima era una variabile in memoria dentro `detta.py`, commutabile solo dal combo da tastiera. Ora `MANI_LIBERE_ON` (gemello di `VOICE_ON`): un lanciatore esterno (Desktop `.command`) puo' accenderla con un click, non solo il combo. Nuova `mani_libere_attive()` in `voce_lib.py`. Verificato: creare/cancellare il file da fuori il processo accende/spegne davvero l'ascolto (trigger reale su un suono di prova).
- Un solo lanciatore Desktop (personale di Sal, non nel repo): avvia `detta.py` se non gira, accende voce + mani libere insieme; un secondo click spegne tutto. Verificato avvio a freddo (processo non ancora partito) e toggle a caldo.

## Non rilasciato - 06/07/2026 (3)

- **Pillola "armata" mentre le mani libere sono accese**: prima la pill spariva del tutto tra un turno e l'altro (stato "nascosto"), quindi Sal non aveva modo di vedere se la modalità era davvero attiva senza parlare. Ora, con mani libere ON, resta visibile una pillola ferma "🎙️ Mani libere attive" finché non parte un vero ascolto (poi torna l'onda come sempre) o non si spegne la modalità. Compare subito al momento del combo, non solo al primo turno.
- Log diagnostico aggiunto (v11 di stanotte, ora confermato utile): traccia sempre parole trascritte, incolla ed invio, anche quando la pulizia viene saltata in conversazione — prima quei log sparivano proprio quando servivano di più.

## Non rilasciato - 06/07/2026 (2)

- **Mani libere ora e' un combo di due modificatori**: Sal ha chiesto due tasti insieme (non uno) per evitare attivazioni accidentali su un tasto che usera' spesso. `Ctrl destro + Option destro` tenuti insieme = mani libere ON/OFF; `Option destro` da solo (senza Ctrl) resta voce agenti ON/OFF, invariato. Niente lettera da comporre come nei vecchi combo Option+punto/meno (abbandonati): solo lo stato giu'/su di due modificatori, molto piu' affidabile. Verificato con eventi sintetici: Option da solo accende la voce; Ctrl+Option insieme (senza toccare la voce) accende le mani libere, confermato da un trigger reale su un suono di prova; entrambi si spengono allo stesso modo. Rimossa la chiave config `tasto_mani_libere` (non piu' un tasto singolo).

## Non rilasciato - 06/07/2026 (1) — incidente reale corretto

- **Fix allucinazione a ripetizione**: un audio di 1.7s (mani libere, rumore ambiente) ha prodotto centinaia di "мент" ripetuto, incollato per intero nella chat di Sal — `e_allucinazione()` filtrava solo frasi-fantasma italiane note (grazie, sottotitoli...), non un collasso a ripetizione generico. Nuova `_ripetizione_patologica()`: scarta il testo se una singola parola copre ≥60% delle parole totali (soglia minima 8 parole) — funziona in qualunque lingua/alfabeto, non solo italiano. Non tocca ripetizioni legittime del parlato reale ("no no no, non intendevo..."). Test aggiunti (45). **Non ancora portato su Windows** (non ha nessun filtro allucinazioni oggi, gap preesistente).

## Non rilasciato - 05/07/2026 (12)

- **Abbandonati i combo Option+tasto: tornati a tasti singoli.** Anche col riconoscimento a carattere (v11) i combo restavano inaffidabili nell'uso reale di Sal (log diagnostico: nessun evento arrivava per il suo tentativo fisico, probabile timing troppo stretto per una pressione umana Option+lettera). Voce agenti ON/OFF torna un tasto singolo (`tasto_voce`, default `alt_r`, come da sempre); mani libere ora e' anch'essa un tasto singolo dedicato (`tasto_mani_libere`, default `ctrl_r`) — stesso identico meccanismo di debounce hold/release del tasto voce, gia' proveto affidabile da mesi. Verificato con eventi sintetici sul tasto reale (non piu' char composto): ON e OFF confermati per la voce.

## Non rilasciato - 05/07/2026 (11)

- **Fix riconoscimento combo Option+tasto**: la prima versione usava il codice fisico del tasto (vk), tarato sulla tastiera US — sulla tastiera italiana reale di Sal i vk erano completamente diversi (verificato dal log diagnostico). Ora si riconosce dal CARATTERE che macOS compone con Option giù (`…` per Option+punto, `–` per Option+meno): stabile su qualunque tastiera fisica, non serve più indovinare i vk. Confermato con eventi sintetici a carattere forzato (`CGEventKeyboardSetUnicodeString`) che accende e spegne in entrambi i versi.

## Non rilasciato - 05/07/2026 (10)

- **Modalità mani libere (ascolto continuo)**: nuovo combo `Option+-` accende/spegne l'ascolto a soglia di volume, senza tenere premuto nessun tasto — parte da sola sopra soglia, si ferma da sola al silenzio, si mette in pausa mentre l'agente parla (flag `PARLANDO` condiviso con `parla.py`). Riusa tutta l'infrastruttura esistente (stream sempre aperto, `avvia_registrazione`/`ferma_e_trascrivi`, pill).
- **Voce agenti ON/OFF ora è `Option+.`** (prima tasto singolo `alt_r`): stesso interruttore, cambiato solo il modo di premerlo. Nuove chiavi config: `tasto_voce_combo` (era `tasto_voce`), `tasto_mani_libere_combo`, `mani_libere_attivazione_sec`, `mani_libere_silenzio_sec`.
- Sensibile al rumore ambiente per costruzione (soglia di volume, non riconoscimento vocale): può accendersi da sola su rumori forti. Non ancora portato su Windows.

## Non rilasciato - 05/07/2026 (9)

- **Pulizia saltata in conversazione**: misurato dal log che la trascrizione Whisper e' gia' velocissima nell'uso reale (0.6-1.3s per 10-25s di audio); il vero collo di bottiglia era "detta pulito" (1-3s extra su quasi ogni turno, perche' quasi tutto supera `pulizia_min_parole`). A voce ON (conversazione con l'agente) ora si salta: l'agente capisce benissimo il parlato grezzo, la velocita' conta più della forma. A voce OFF resta attiva. Nuova chiave `pulizia_in_conversazione` (default `false`) per chi la vuole comunque sempre attiva.

## Non rilasciato - 05/07/2026 (8)

- **Pausa pre-Invio consapevole del contesto**: a voce ON (conversazione vera con l'agente, botta e risposta) la pausa prima dell'Invio scende da 2.5s a `invio_automatico_ritardo_conversazione_sec` (default 0.3s); a voce OFF (dettatura su testo/email/social) resta 2.5s per dare tempo di correggere. Stesso interruttore di sempre, nessuna voce/stile toccati.

## Non rilasciato - 05/07/2026 (7)

- **Indagati i fallimenti della corsia veloce (Apple Intelligence)**: confermato in diretta che il modello rifiuta in blocco le richieste con parolacce ("Il modello non può fornire una risposta a questa richiesta"). Le parolacce vengono ora mascherate prima di mandarle al Comando Rapido e rimesse a posto nel risultato — corsia agente non toccata, non ha questo problema. Log ora dice il motivo esatto di ogni fallimento (returncode/timeout/vuoto/pulizia_sospetta), non solo "FALLITA". Trovata anche una seconda causa (frasi innocue tipo "Ho ricevuto la PEC." rifiutate in modo deterministico ma imprevedibile): e' un filtro opaco lato Apple, non risolvibile da qui — il fallback all'agente locale la assorbe già correttamente.

## Non rilasciato - 05/07/2026 (6)

- **Rotazione log a 7 giorni**: con `debug_dettature: true` il log contiene il grezzo di ogni dettatura in chiaro (conversazioni, call). Prima si accumulava senza limiti; ora `TimedRotatingFileHandler` tiene solo gli ultimi 7 giorni. L'apprendimento automatico (`impara_sostituzioni`) legge solo le righe recenti: nessun impatto.

## Non rilasciato - 05/07/2026 (5)

- **Fix testo sulla scheda sbagliata dello stesso browser**: il fix "riattiva app-bersaglio" lavorava a livello di app — se il bersaglio e il punto d'arrivo erano due SCHEDE della stessa finestra Chrome/Safari (es. Instagram e ChatGPT), non se ne accorgeva. Ora per Chrome e Safari (via AppleScript) si memorizza anche l'URL della scheda attiva al momento dello stop e si ripristina prima di incollare. Richiede permesso "Automazione" (una tantum, come microfono/accessibilità). Altri browser: resta solo il fix a livello app.

## Non rilasciato - 05/07/2026 (4)

- **Pausa prima dell'Invio automatico**: partiva 0.1s dopo l'incolla, troppo veloce per correggere il testo appena dettato. Nuova chiave `invio_automatico_ritardo_sec` in `config.json` (default 2.5s).

## Non rilasciato - 05/07/2026 (3)

- **Etichetta "● ON" torna a dire il vero**: dopo aver scollegato invio automatico/bordo verde dal toggle voce agenti, l'etichetta li seguiva ancora e restava sempre "ON" anche a voce spenta. Ora il bordo verde segue `invio_automatico` (sempre acceso), l'etichetta "● ON" segue il tasto voce agenti vero (`voce_attiva()`): nascosta a voce OFF.

## Non rilasciato - 05/07/2026 (2)

- **Invio automatico e stile verde sempre attivi**: prima dipendevano dal toggle "voce agenti" (VOICE_ON) — con la voce spenta niente indicatore verde ne' Invio dopo l'incolla. Ora `invio_automatico` e lo stile della pill sono indipendenti da quel toggle, che resta solo per la lettura ad alta voce delle risposte.

## Non rilasciato - 05/07/2026

- **Fix blocco ricorrente (deadlock CoreAudio)**: ogni dettatura apriva e chiudeva il microfono (`stream.start/stop/close`); la chiusura andava a volte in deadlock su un mutex della HAL di CoreAudio e la dettatura restava incastrata (recuperata solo da un riavvio forzato del processo). Ora il microfono si apre **una sola volta** all'avvio e resta sempre acceso: avvio/stop registrazione sono solo un flag, mai più stop/close per dettatura. Contropartita gestita: se il device di input cambia (es. colleghi le AirPods) un watchdog se ne accorge e riavvia il processo da solo, senza mai richiamare stop/close sul device vecchio.
- **Fix testo incollato sulla finestra sbagliata**: se una dettatura lunga (pulizia inclusa) richiedeva qualche secondo e nel frattempo Sal cambiava app/pagina, il testo finiva incollato dove si trovava il focus a fine elaborazione, non dove aveva parlato. Ora l'app-bersaglio viene memorizzata al momento dello stop e riattivata prima di incollare, sempre.

## Non rilasciato - 03/07/2026

- **Fix eco glossario nel detta pulito**: il modellino Apple del Comando Rapido eseguiva alla lettera la vecchia regola 5 ("Scrivi correttamente questi nomi: …") e appendeva l'intero glossario in coda al testo dettato. Regola riformulata ("Se nel testo compare uno di questi nomi… Non aggiungere mai nomi che chi parla non ha detto") + nuova guardia `pulizia_sospetta`: la pulizia viene scartata (si tiene il grezzo) se aggiunge ≥2 nomi del glossario mai dettati o se collassa il testo sotto un terzo delle parole. Vale per corsia veloce e agente, Mac e Windows. Test aggiornati (43).

## Non rilasciato - 02/07/2026

- **Apprendimento automatico**: una volta al giorno, all'avvio, Voce rilegge le ultime dettature grezze dal log (solo se `debug_dettature: true`), chiede all'agente locale le parole trascritte male in modo ricorrente e aggiorna da sola le `sostituzioni` (senza mai toccare quelle messe a mano). Marcatore `APPRENDIMENTO_ULTIMO`.

- **Corsia veloce detta pulito (Mac)**: se esiste il Comando Rapido "Voce Pulita" (modello Apple Intelligence (di default su Private Cloud Compute, il cloud privato Apple: gratis, niente token, dati non conservati da Apple; dall'editor del comando si può scegliere "Su dispositivo"), ponte puro creato dal kit al Passo 3-bis), la pulizia corre in ~1s senza consumare token; l'agente resta come riserva. Prompt di pulizia riscritto (regole numerate su riga singola): ora risolve bene i ripensamenti anche col modello on-device.

- **Glossario**: nuova chiave `glossario` in `config.json`, passata a Whisper come `initial_prompt` — nomi propri e brand (clienti, LeaderAI, Systeme.io…) escono scritti giusti. Più mappa `sostituzioni` ("sbagliato → giusto", parola intera, case-insensitive) per gli errori ricorrenti.
- **Detta pulito**: le dettature lunghe (≥ `pulizia_min_parole`, default 15) passano dall'agente già sul PC (`claude -p --model haiku`, riserva `codex exec`) che toglie ripetizioni, ripensamenti e intercalari e sistema la punteggiatura. Stato "✨ Sistemo…" sulla pill. Fallback totale: se l'agente manca, sbaglia o supera `pulizia_timeout_sec` (20s), si incolla il testo grezzo.
- Pulizia più veloce: `claude -p` parte "spoglio" (`--tools "" --strict-mcp-config --setting-sources "" --no-session-persistence`): ~2-3s in meno a chiamata, misurato; timeout portato a 20s (la chiamata reale sta sui 9-15s).
- Nuovi test sulla logica pura (glossario, sostituzioni, soglia pulizia, fallback agente).

## Non rilasciato - 27/06/2026

- Istruzioni `INSTALLA_CON_AI.md` riscritte come missione autonoma: l'agente del cliente fa autodiagnosi, auto-riparazione e prova reale, con `/goal` come aiuto opzionale.
- README allineato alla consegna con testo-istruzioni e prova reale, non guida passo-passo tecnica.

## v1.0.1 - 21/06/2026

- Aggiunto watchdog anti-blocco su CoreAudio/PortAudio: se macOS resta incastrato mentre chiude il microfono, l'app si riavvia da sola.
- Rafforzato il timeout anti-incanto fuori dal pannello grafico.
- Aggiunta funzione testabile per i timeout di sicurezza.

## v1.0.0 - 21/06/2026

- Prima versione pubblica per Mac.
- Dettatura locale con tasto `Cmd destro`.
- Pill verde con brand `salchiarenza.ai`.
- Timeout anti-incanto sulle registrazioni troppo lunghe.
- Installer guidato con launcher sulla Scrivania.
- Istruzioni semplificate per installazione guidata con Claude Code o Codex.
