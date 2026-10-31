# Changelog Voce

## 1.3.0-rc.35 - 31/10/2026 — l'orecchio, Esc che annulla, le ultime dettature nel menu (Mac e Windows)

Tre idee dall'app open source Handy (github.com/cjpais/Handy, MIT), motore Whisper invariato.
Candidata: Windows e' provato solo con prove automatiche, non su un PC vero.

- **Orecchio.** Silero VAD (`silero_vad.onnx` v6.2.3, MIT, 2,3 MB, su onnxruntime 1.27.0,
  niente torch) dice ogni 32 ms se c'e' una persona che parla. Prima di Whisper: senza voce
  non si trascrive e non si incolla niente (il «Grazie.» sul silenzio); i silenzi lunghi si
  accorciano lasciando 450 ms per lato. Sul Mac guida anche le mani libere (partono sulla
  voce, non sul volume); Windows non ha le mani libere. Prova Mac sul vero Whisper e su 30
  audio veri: 0 parole perse nei tratti tolti; sul silenzio e sul rumore sintetici fantasmi
  da 35 a 0. `"orecchio": false` torna a prima.
- **Esc annulla.** Mentre registri, o finche' il testo non e' comparso, Esc butta la
  dettatura: niente testo, niente Invio, e in quel momento Esc non arriva all'app davanti
  (in Claude non ferma l'agente). Mac: acceso, provato su questo Mac. **Windows: spento di
  serie** (`"esc_annulla": false`) finche' l'hook di tastiera non si vede girare su un PC
  vero; codice e prove ci sono.
- **Menu Voce: «Copia l’ultima dettatura» e «Ritrascrivi l’ultima».** Testo e audio solo in
  memoria; la ritrascrizione passa dal motore principale col glossario e va negli Appunti.
  Mac nel menu della barra, Windows nel menu Voce della finestra Voce AI.
- Entrano anche i cantieri non rilasciati: il microfono del Mac non perde piu' blocchi mentre
  Whisper lavora (solo Mac); riaprire il microfono mentre la frase prima si trascrive e
  l'Invio premuto mentre il testo compare (Mac e Windows); pill e microfonino che tornano
  dopo un cambio di schermi (P-105, solo Mac: su Windows valutato, nessuna modifica).
- Prove: 591 prima del gemellaggio Windows, 621 dopo, tutte verdi (`python -m pytest tests`).
- Non provato su un PC Windows vero: hook che trattiene Esc, velocita' dell'orecchio su un
  portatile x64, copia del modello da `install.ps1`, menu e pill in Tk.

## 1.3.0-rc.34 - 23/10/2026

Solo testo, nessun cambio di funzionamento (P-200): nessun nome di cliente nel pacchetto.
I casi si citano con data e riga P (P-078, P-085) o come idea di una cliente con la data;
nelle prove i percorsi Windows usano un nome finto.

## 1.3.0-rc.33 - 20/10/2026

Solo testo: nome del Passo 1 aggiornato a «Centro di Comando», nessun cambio di funzionamento.

## 1.3.0-rc.32 - 17/10/2026 — prima la diagnosi, e le mani libere non scrivono piu' da sole per sempre

Da una segnalazione Challenge del 16/10/2026 (P-190, P-191): «scrive messaggi da sola senza senso».

- **Fase 0 prima di installare.** `voce diagnosi` (Mac, solo bash e comandi di macOS,
  sola lettura) controlla chip, macOS, memoria, spazio, Python, strumenti di Apple,
  internet, app per dettare gia' presenti e la Voce gia' installata (versione,
  servizio, mani libere, voce agenti, registro delle ultime 24 ore, memoria). Gira anche
  dal pacchetto appena estratto. `ESITO` in una riga: va / non va e perche' / prima l'AI
  sistema il software. `install.sh` fa la stessa diagnosi e sotto requisito non tocca
  niente. Windows: stessi requisiti e comandi PowerShell nella Fase 0 di
  `windows/INSTALLA_CON_AI.md` (nessun PowerShell provato qui: da provare su un PC vero).
- **Requisiti** (fonti aperte il 17/10/2026, pacchetto misurato):
  - Mac Apple Silicon e macOS 14+: MLX, https://ml-explore.github.io/mlx/build/html/install.html
    («Using Apple silicon», «macOS >= 14.0», «native Python >= 3.10»); `pip download` di
    mlx 0.32.4 non trova ruote per macOS 13. Riconoscere il chip: https://support.apple.com/en-us/116943
  - Python 3.11+: numpy 2.4.6 (versione bloccata nei requisiti) dichiara `>=3.11`,
    https://pypi.org/project/numpy/2.4.6/ ; il `python3` di Apple in `/usr/bin` e' «usually
    older», https://docs.python.org/3/using/mac.html ; Windows 10 e successivi,
    https://docs.python.org/3/using/windows.html
  - Windows solo x64: ctranslate2 (motore di faster-whisper) non ha ruote `win_arm64`
    su PyPI (`pip download`, 17/10/2026).
  - 16 GB di memoria: standard della casa per Centro di Comando + Ecosistema; casi P-088 (Mac da
    8 GB lento) e P-126 (modello in swap).
  - 10 GB liberi (2 GB per un aggiornamento): misurato su un ambiente pulito, programmi
    1,3 GB (torch 590 MB, mlx 234 MB), modello 1,5 GB (turbo, Mac fino a 16 GB) o 2,9 GB
    (large-v3); Windows circa 76 MB di ruote + modello medium 1,4 GB. Il resto e' margine
    per lo swap e le cache di macOS.
- **Spegnimento automatico vero.** Le mani libere si spengono dopo 10 minuti senza testi
  incollati davvero: prima il conto ripartiva a ogni registrazione, anche partita dal
  rumore e scartata, e in una stanza rumorosa non si spegnevano mai (e senza quiete non
  scattava neanche il riavvio per memoria). Una registrazione in corso non si taglia.
  Prova rossa sul codice di prima, verde dopo (`test_mani_libere_si_spengono_*`).
- **Registro leggibile senza il debug.** Righe sempre scritte: `mani libere: ATTIVE (gia'
  accese all'avvio | accese adesso)` da qualsiasi strada (tasti, pulsante della
  Scrivania, `./voce mani on`), `mani libere: SPENTE`, `mani libere: ascolto partito dal
  volume`. Windows scrive ora sempre `incollato (programma bersaglio: ...)`, solo il
  programma e mai il titolo della finestra.
- **Guide.** Fase 0, prova di chiusura (dettatura in pochi secondi, poi due minuti senza
  testi scritti da soli, `Mani libere: SPENTE`) e sezione «Se la Voce scrive da sola»
  accanto a «Se la Voce è lenta», su Mac e Windows; `EMAIL_CONSEGNA.md` le richiama.
- Gesto Cmd + Option e pulsante «Voce Attiva Tutto» invariati: li decide Sal.
- Entrano anche i due cantieri dell'11 e 12/10/2026 qui sotto (suite completa verde).
- Prove: 509 verdi (`python -m pytest tests`).

### Cantiere 12/10/2026 incluso — affidabilita' della dettatura

- Mac e Windows avvisano quando l'audio e' interrotto/non valido e conservano il
  testo affidabile sospendendo l'Invio del messaggio incompleto.
- La progressiva recupera i segmenti vuoti/sospetti con un passaggio sull'audio
  intero; gli altri percorsi mantengono motore, soglie e tempi precedenti.
- Diagnosi del testo separata fra output Whisper e correzioni, solo a debug acceso.
- Test comportamentali nelle suite esistenti; dettagli e limiti nei changelog di
  sistema. Entra nella rc.32.

## 1.3.0-rc.31 - 02/10/2026

Da una cosa costruita da una cliente (02/10/2026) sopra la nostra Voce, adattata alla nostra.

- La voce legge mentre l'agente scrive. Con la voce accesa, Claude Code viene
  letto un blocco di testo alla volta, appena l'agente lo ha scritto, e non solo
  a lavoro finito: un testo scritto prima di un lavoro lungo si sente subito.
  L'app segue in sola lettura i registri locali di Claude Code
  (`voce_hook.SeguiRegistro`, un thread di `detta.py`); legge le chat in cui si
  parla con l'agente, non le automazioni di sfondo (`sdk-cli`, attivita'
  pianificate). I blocchi arrivati mentre ne parla un altro si accodano in ordine
  (`parla(..., accoda=True)`, tetto 8.000 caratteri) invece di sostituirsi: la
  risposta finale, come prima, sostituisce l'attesa. Il gancio di fine risposta
  resta e non rilegge cio' che e' gia' stato letto (`reclama_lettura`: il primo
  che arriva segna, il secondo tace; finestra due minuti, testi brevi doppioni
  solo se identici). Stesso interruttore di sempre (`VOICE_ON`); chiave
  `voce_mentre_scrive` per spegnerla. Con Codex e Antigravity non cambia niente.
  Mac e Windows.
- Controllo di consegna. Dopo l'Invio automatico verso Claude Code si cerca il
  messaggio nel registro (fino a 3 s); se manca, si ripreme Invio e poi si
  reincolla e si invia di nuovo. Vale per la dettatura a tasto premuto e per le
  mani libere. Sul modello della cliente, con tre guardie in piu' contro il messaggio
  doppio: il registro esiste solo per le chat di Claude Code, quindi il recupero
  scatta solo se quell'app, nella mezz'ora, ha gia' consegnato un messaggio visto
  nel registro (altrimenti scrive l'esito nel log e basta); conta solo cio' che
  e' stato scritto dopo l'Invio (una frase uguale di prima non vale); non si
  interviene se la persona ha ripreso la tastiera, sta dettando o e' andata in
  un'altra app. Controlla l'app indicata in `verifica_consegna_app` (di serie
  `Claude`; su Windows il programma, non il browser). Chiavi `verifica_consegna`,
  `verifica_consegna_storico_min`. Mac e Windows.
- **Non incluso, per ora** (idee della stessa cliente, 02/10/2026, registrate
  nel foglio `Idee e miglioramenti`): i tre strati delle mani libere. 1) anti-eco
  a monte con Voice Processing di Apple (un piccolo programma Swift che apre il
  microfono come FaceTime e toglie dall'ingresso cio' che esce dalle casse);
  2) impronta vocale del proprietario (Resemblyzer, 10 frasi di registrazione) per
  scartare video, altre persone e la voce sintetica; 3) interruzione mentre
  l'agente parla con un rilevatore di voce neurale (Silero) e un varco dopo la
  fine della voce. Motivo: tre dipendenze nuove (Swift, Resemblyzer, Silero),
  una registrazione guidata e una taratura sui numeri, per un problema che
  riguarda solo chi tiene le mani libere accese con le casse; la nostra Voce ha
  gia' la pausa mentre l'agente parla e l'interruzione a soglia. Si riprendono
  se arrivano casi veri di eco o di rumori scambiati per parlato.
- Mac: un avvio poteva lasciare spento il gesto Option + freccia (due thread caricavano
  insieme lo stesso nome di Quartz, uno moriva con `KeyError`). Ora i nomi si caricano
  prima dei thread.
- 52 prove nuove (Mac e Windows): riconoscimento nel registro, decisione di recupero,
  accodamento, accordo tra gancio e seguitore, chat di sfondo escluse. Le prove
  della repo non scrivono piu' file nella cartella del prodotto.
- Questa versione porta anche i quattro interventi del 01/10/2026 gia' in repo e
  mai pubblicati (P-078, P-085, P-088, P-117), qui sotto.

### Interventi del 01/10/2026 inclusi in questa versione

- Una frase da fine-video non passa piu' per parlato vero (P-117). Il 28/09 12
  secondi di parlato di Sal sono usciti da Whisper come «Grazie a tutti per
  aver guardato il video, vi ringrazio per avermi seguito...» e sono partiti
  da soli in chat: la rete delle frasi-fantasma confrontava solo la frase
  intera, e quella era appena piu' lunga. Ora confronta i pezzi: un testo
  fatto solo di formule da fine-video che parla del video (o ripete tre volte
  di fila una frase nota) si scarta; una frase vera che le contiene resta. Sui 2.556
  dettati veri dei registri di Sal scarta soltanto quello del 28/09. Se
  Whisper la inventa su un parlato vero (almeno 3 secondi, energia da
  parlato), un secondo passaggio senza glossario recupera cio' che hai detto:
  e' il prompt a farla inventare. Sui registri di Sal succede 3 volte su
  2.602 dettature; i colpi e i rumori brevi, che sono i fantasmi di ogni
  giorno, non ne hanno diritto. Mac e Windows.
- Su Windows, con poca memoria, Voce sceglie da sola il modello piu' piccolo
  (P-088, solo Windows). Sotto i 6 GB di RAM usa `small` al posto di `medium`;
  la scelta e' del prodotto e `voice.log` dice quale modello carica. Sul Mac la
  stessa correzione e' gia' uscita con la rc.30 (motore leggero sotto i 16 GB) e
  resta quella.
- La voce che legge le risposte non si accende piu' per sbaglio (P-085).
  Durante la call di una cliente Voce ha cominciato a leggere ogni risposta
  (quattro letture in sette minuti): Option + freccia sinistra accendeva la voce
  al primo tocco, ma e' anche il «vai alla parola prima» di ogni campo di
  testo, quindi chi corregge una frase la accendeva senza saperlo. Ora il gesto
  conta solo se **tenuto premuto un secondo** (`voce_tenuta_sec`, mai sotto
  mezzo secondo); un tocco, anche ripetuto, non fa niente. Vale anche per
  Maiusc+Option+freccia (selezionare le parole): il gesto vuole solo Option e
  freccia. Windows gemella: il tasto Menu, tenuto un secondo. Cambia anche per
  Sal: la voce si accende e si spegne tenendo premuto, non toccando.
- Su Windows Voce non leggeva le risposte ad alta voce, e nessuno se ne
  accorgeva (P-078). Dal 28/07 al 22/09 il gancio di fine turno e' fallito 410
  volte su 410 sul PC di una cliente: il comando era scritto con i percorsi
  senza virgolette, Claude Code su Windows lo lancia con Git Bash, e Git Bash
  toglie le barre rovesciate. Il controllo diceva «configurato» perche' il
  percorso nel file c'era. Ora Claude Code si collega senza shell (`command` +
  `args`, niente da togliere) e il controllo AVVIA il comando: «configurato e
  funzionante» o «NON FUNZIONA» col motivo, e l'installatore si ferma. Se il
  collegamento si rompe di nuovo, la voce lo dice a voce nel momento in cui la
  accendi. Il gancio di Windows scrive una riga a ogni fine risposta, come il
  Mac; con una Claude Code troppo vecchia per il nuovo collegamento (prima
  della 2.1.139) il controllo dice di aggiornarla. Sul Mac il comando era gia' giusto, ma il controllo era lo stesso: ora
  avvia anche li'. Un aggiornamento ripara da solo i collegamenti rotti.

## 1.3.0-rc.30 - 01/10/2026

- Sui Mac con 16 GB di RAM o meno Voce sceglie da sola il motore leggero
  (`whisper-large-v3-turbo`, 1,5 GB in memoria invece di 2,9 GB): il motore
  pieno non entra nel tetto del 25% della RAM di un Mac da 8 GB e su uno da
  16 GB ne fissa oltre un quinto, quindi appena un altro programma occupa la
  memoria ogni dettatura rallenta. Sopra i 16 GB non cambia niente. Se la
  persona ha scritto `modello` nel suo `config.local.json` vince la sua scelta;
  chiavi opzionali `modello_mac_piccoli` e `ram_mac_piccoli_gb` (default turbo
  e 16). Il motore scelto e il motivo restano in `voce.log`. Solo Mac.

- Istruzioni per l'AI del proprietario (`mac/README.md` e
  `mac/INSTALLA_CON_AI.md`): sezione «Se la Voce è lenta». Guarda chi occupa
  la memoria, chiude il calcolo rimasto aperto da un agente oppure dice alla
  persona quale programma chiudere. Windows: le difese di memoria per ora ci
  sono solo su Mac.

- Nel pacchetto c'e' anche `voce riavvia` (solo Mac): riavvia la dettatura
  senza lasciare finestre del Terminale aperte, controlla che non si stia
  dettando e che il nuovo processo abbia la tastiera, e lascia invariati
  voce e mani libere.

## 1.3.0-rc.29 - 01/10/2026

- Voce resta veloce anche quando un altro programma divora la RAM (solo Mac,
  01/10/2026: con 98 GB occupati altrove ogni dettatura passava da 1-3 s a
  15-17 s perche' macOS mandava il modello in swap). Il modello resta
  residente in RAM (`mx.set_wired_limit`, tetto = memoria del modello + 512 MB,
  mai oltre il 25% della RAM; chiave opzionale `memoria_fissa_mb`) e, se
  l'app supera `riavvio_oltre_mb` (default 4500) o fa tre trascrizioni di fila
  oltre 8 s, si riavvia da sola con `os.execv`, solo a riposo e dopo 30 s di
  silenzio. Il motivo resta in `voce.log`.

- Mascotte opzionale accanto alla pill (solo Mac, spenta di serie): con la
  chiave `mascotte` in `config.local.json` un pupazzo grande si appoggia al
  fianco sinistro della pill e, come sulla sua molla, si muove con la voce
  senza mai deformarsi: a ogni picco un saltello e un'oscillazione che si
  smorza, tra i picchi un dondolio appena accennato, mentre trascrive un
  dondolio lento. Interruttore `voce grinch on|off` (flag
  `MASCOTTE_ON`), letto a ogni comparsa della pill, senza riavvio. Senza la
  chiave la pill resta identica.

## 1.3.0-rc.28 - 24/09/2026

- Il punto verde di «LeaderAI.» torna della misura del logo ufficiale: era un
  terzo dell'altezza delle lettere, ora un quarto, come nel marchio. Sal: «il
  puntino è troppo grande». Mac e Windows, 328 prove verdi.

## 1.3.0-rc.27 - 23/09/2026

- La memoria di Voce non cresce piu' a ogni dettatura. Il motore teneva da
  parte senza limite i blocchi gia' usati: sul Mac di Sal 80 dettature di
  lunghezze diverse portavano l'app da 4,3 a 12,3 GB. Ora c'e' un tetto di
  mezzo giga: le stesse 80 dettature restano a 3,7 GB e la dettatura non
  rallenta. Il peso fisso resta il modello grande (2,9 GB), scelto per
  scrivere bene i nomi. Solo Mac, 326 prove verdi.

## 1.3.0-rc.26 - 23/09/2026

- Un clic o un tasto ferma l'Invio automatico anche mentre il testo compare.
  Prima il clic che mette il cursore nel testo non era ascoltato affatto, e i
  tasti premuti nel mezzo secondo in cui il testo arrivava non contavano: il
  23/09 una frase e' partita mentre Sal la stava correggendo. Ora conta ogni
  gesto della persona, mai quelli del programma. Mac e Windows, 323 prove verdi.

## 1.3.0-rc.25 - 23/09/2026

- App ChatGPT per Mac: la casella di scrittura ora si trova. L'app e' costruita
  su Chromium e mostra la pagina solo se glielo si chiede: la notte del 23/09
  12 dettature su 12 erano partite col suono d'avviso. Ora Voce lo chiede a
  ogni app costruita su Chromium, non solo ai browser che conosce. Il registro
  dice anche quale tasto ferma l'Invio automatico. Solo Mac, 316 prove verdi.

## 1.3.0-rc.24 - 23/09/2026

- LeaderAI resta sempre in risalto: mentre trascrive il logo si ingrandisce al
  centro della pill e le scritte di stato («Trascrivo…», «Sistemo…») diventano
  piccole e grigie sotto di lui. Mac e Windows, 313 prove verdi.

## 1.3.0-rc.23 - 23/09/2026

- «Trascrivo…» sparisce quando il testo arriva, non piu' dopo l'Invio: la
  trascrizione dura circa 1,5 secondi, ma la scritta restava in media 4,4
  secondi, anche sul testo gia' pronto e appena inviato. Il punto verde del
  logo e' piu' grande e sotto LeaderAI c'e' la firma verde del sito, che si
  disegna da sinistra quando la pill compare. Mac e Windows, 310 prove verdi.

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
