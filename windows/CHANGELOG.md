# Changelog

## 1.3.0-rc.8 - 29/08/2026 — via l'eco del glossario

- `rimuovi_eco_glossario` (gemella Mac): la parola "Glossario" e i nomi del
  prompt ricopiati da Whisper in testa alla trascrizione vengono rimossi
  prima del filtro allucinazioni; il corpo della frase non si tocca.

## 1.3.0-rc.7 - 29/08/2026 — il click nella casella lo fa l'app

- Cursore automatico via UI Automation (nuova dipendenza `comtypes`): al
  momento dell'incolla, se nella finestra bersaglio nessuna casella di testo
  ha il focus, l'app mette il cursore nella casella di scrittura (la piu' in
  basso). Le caselle nella parte alta della finestra (barra degli indirizzi,
  campi di ricerca) non vengono mai prese. Qualsiasi intoppo lascia il
  comportamento precedente. Interruttore: `cursore_automatico`. Come il resto
  della versione Windows, va visto girare su un PC reale prima di
  considerarlo stabile.
- Audio conservato opzionale (`conserva_audio_n`, default 0 = spento): come
  sul Mac, WAV locali in `audio_recenti/` con rotazione automatica, per
  tarare glossario e sostituzioni su casi veri.

## Consegna - 27/08/2026 — l'email dice dove finisce il testo da incollare

- Il messaggio per l'agente sta fra due righe di trattini: il confine di cosa
  copiare si vede a occhio. Le frasi rivolte alla persona restano fuori.
- Dopo l'installazione lo stesso agente prosegue nella medesima sessione fino
  alla prova reale: eliminato il secondo messaggio che il proprietario doveva
  reinviare all'agente.
- L'email dichiara in apertura i 20 minuti e il microfono collegato, e avvisa
  che Windows e l'antivirus chiederanno qualche autorizzazione.
- La missione locale tratta l'antivirus come prima causa quando lo scaricamento
  della voce si ferma, con la misura host per host della catena dei certificati.
  Origine: consegna Windows del 28/07/2026 fermata da Avast su questo punto.
- Controllo AI Act aggiornato per questa consegna. Ruolo LeaderAI: fornitore.
  Prodotto: trascrizione vocale locale e lettura ad alta voce delle risposte
  dell'agente, fuori dagli usi ad alto rischio dell'Allegato III. Obbligo di
  trasparenza sull'audio sintetico presidiato dalla 1.3.0-rc.6: all'accensione
  la finestra dichiara `Voce AI` e `audio sintetico`. Audio effimero, elaborato
  sul computer del proprietario, come dichiara `PRIVACY.md`. Esito
  `AI_ACT_CHECK_OK`.

## 1.3.0-rc.6 - 03/08/2026 — Voce AI riconoscibile

- All'accensione dichiara che le risposte dell'agente sono audio sintetico.
- La finestra identifica `Voce AI` quando spiega il tasto Menu.
- Privacy e collaudo registrano che l'audio e' effimero e non viene salvato.
- La missione chiude con una sola conferma finale dopo tutte le prove, priva di
  file o rapporti separati.

## 1.3.0-rc.5 - 01/08/2026 — nessuna attesa interattiva dell'agente

- Tolta la pulizia Claude/Codex dal percorso della dettatura: poteva fermare
  il testo fino a `20s`. Windows non ha il Comando Rapido Apple, quindi incolla
  subito il grezzo con glossario e sostituzioni locali.
- Allineata la guardia di sicurezza Mac/Windows: variazioni oltre il 25% e un
  solo nome del glossario inventato vengono rifiutati.

## 1.3.0-rc.4 - 01/08/2026 — la pulizia non resta lenta per giorni

Riflesso della rete nata sul Mac. Windows non aveva alcun contatore: ogni
dettatura pagava fino a `20s` di timeout, per sempre.

- `corsia_utilizzabile()` / `registra_esito_corsia()` gemelli del Mac, con un
  test di parita' che confronta le due implementazioni caso per caso.
- `pulisci_con_agente()` torna `None` quando fallisce (prima tornava il grezzo
  e il guasto era invisibile). Il chiamante fa `pulito or text`: la dettatura
  non si perde.

## 1.3.0-rc.3 - 01/08/2026 — il microfono abbassato non ferma piu' l'app

Riflesso della stessa rete nata sul Mac il 01/08/2026 (regola di parita':
Mac master, Windows gemello).

- `diagnosi_audio_muto()` decide come sul Mac, con gli stessi numeri: minimo
  `60`, target `75`. Un test di parita' confronta le due funzioni caso per
  caso e fallisce se divergono.
- `ripara_guadagno_ingresso()` e `allinea_volume_ingresso()` leggono e
  rialzano il volume del microfono via Core Audio in C# inline dentro
  PowerShell: sta nel .NET di Windows, quindi **niente pip** sul PC del
  cliente, stessa scelta gia' fatta per il TTS.
- Aggiunta la riga di log mancante quando una dettatura viene scartata sotto
  soglia: prima su Windows spariva senza lasciare traccia da diagnosticare.
- **Da provare su un PC Windows reale**: l'interop Core Audio non e'
  collaudabile da macOS. Ogni errore ricade sul comportamento precedente
  (nessuna riparazione), mai peggio di prima.

## 1.3.0-rc.2 - 29/07/2026 — tempo di invio allineato

- Allineato a `2.5s` il ritardo dell'Invio automatico anche in conversazione,
  come nel profilo operativo Mac di Sal. Tasto e voce restano specifici di
  Windows e vengono collaudati sul PC destinatario.

## 1.3.0-rc.1 - 27/07/2026 — repo cliente autosufficiente

- La repo contiene ora versione unica, prove automatiche, installazione
  conservativa e modello di consegna nello stesso archivio Mac + Windows.
- L'installer copia `VERSION` nella cartella cliente; la missione locale ne
  verifica la presenza prima del collaudo.
- L'aggiornamento conserva tutte le scelte gia' presenti, compresi voce,
  modello, detta pulito, ritardi e calibrazione.
- Specchiate dal Mac le protezioni contro frasi-fantasma/collassi di Whisper e
  contro l'Invio automatico mentre il proprietario preme un tasto o ricomincia
  a dettare.
- Il collaudo Codex include revisione da `/hooks` e una risposta realmente
  letta ad alta voce.
- La versione resta candidata finche' tasti, microfono, dettatura e voce
  italiana non vengono provati su un PC Windows reale partendo dall'archivio.

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
- `install.bat` mostra chiaramente esito e codice di uscita, mentre `install.ps1` copia `INSTALLA_CON_AI.md` nella cartella locale per lasciare all'agente la missione completa.
- Alla persona restano soltanto conferme Windows e prova reale.

## Non rilasciato - 17/07/2026 (9) — voce italiana scelta, non imposta

- La prima installazione propone il **Profilo LeaderAI consigliato** in una sola domanda e distingue i requisiti tecnici dalle preferenze opzionali.
- Aggiunta `voce_nome` alla configurazione: `voce_hook.py --list-voices` elenca le voci italiane installate, `--test-voice "NOME"` le fa ascoltare e `--set-voice "NOME"` salva soltanto una voce realmente disponibile.
- App e hook usano la voce scelta; se manca, ripiegano sulla prima voce italiana installata senza inventare un nome non presente sul PC.
- La voce e i tasti restano da collaudare su un PC Windows reale prima del rilascio.

## Non rilasciato - 17/07/2026 — contratto sorgente unica

- La repo `voce` resta l'unica casa del prodotto. Il Mac usato da Sal punta direttamente alla cartella `mac/`; Windows resta una variante tecnica separata solo perche' il sistema operativo richiede codice diverso. Ogni cambiamento di comportamento Mac deve continuare a essere riflesso e collaudato qui prima della release.

## Non rilasciato - 17/07/2026 (8) — aggiornamento completo, non ripartenza da zero

- Preparata **v1.3**: `install.ps1` copia anche `voce_hook.py`, lo collega agli hook globali di Claude Code/Codex senza cancellare quelli esistenti e ne verifica la presenza.
- Installazione e aggiornamento fondono i nuovi default con il config gia' presente: restano glossario, sostituzioni, tasti, modello, voce scelta e calibrazione microfono; il prodotto aggiorna marchio e comportamento base.
- Aggiunta prova audio Windows durante l'installazione e missione agente estesa fino alla lettura reale di una risposta completa.
- Tutta la logica e' testata senza toccare le configurazioni vive; dettatura, tasti e qualita' della voce restano da collaudare su un PC Windows reale prima del rilascio.

## Non rilasciato - 09/07/2026 (7)

- **Airbag "audio fuori scala"** (gemello Mac): dettatura con rms > 1.0 = sample fuori da [-1, 1], impossibile per uno stream float32 sano → audio corrotto dal driver, si scarta invece di trascriverlo (su Mac Whisper allucinava e l'invio automatico spediva spazzatura agli agenti). Da collaudare su PC Windows reale insieme al resto.

## Non rilasciato - 05/07/2026 (6)

- **Pulizia saltata in conversazione** (gemello Mac): a voce ON la pulizia (1-3s extra) si salta, l'agente capisce il parlato grezzo. Nuova chiave `pulizia_in_conversazione` (default `false`).

## Non rilasciato - 05/07/2026 (5)

- **Pausa pre-Invio consapevole del contesto** (gemello Mac): a voce ON (conversazione con l'agente) la pausa scende a `invio_automatico_ritardo_conversazione_sec` (default 0.3s) invece di 2.5s.

## Non rilasciato - 05/07/2026 (4)

- **Rotazione log a 7 giorni** (gemello Mac): `debug_dettature: true` logga il grezzo in chiaro, ora limitato agli ultimi 7 giorni invece di accumularsi senza limiti.

## Non rilasciato - 05/07/2026 (3)

- **Pausa prima dell'Invio automatico** (gemello Mac): nuova chiave `invio_automatico_ritardo_sec` in `config.json` (default 2.5s), tempo per correggere il testo prima che parta l'Invio.

## Non rilasciato - 05/07/2026 (2)

- **Invio automatico sempre attivo** (gemello Mac): non dipende piu' dal toggle "voce agenti" (VOICE_ON), che resta solo per la lettura ad alta voce delle risposte.

## Non rilasciato - 05/07/2026

- **Fix testo incollato sulla finestra sbagliata** (gemello Mac): se una dettatura lunga (pulizia inclusa) richiedeva qualche secondo e nel frattempo cambiavi finestra, il testo finiva incollato dove si trovava il focus a fine elaborazione, non dove avevi parlato. Ora la finestra-bersaglio (`GetForegroundWindow`) viene memorizzata al momento dello stop e riportata avanti (`SetForegroundWindow`) prima di incollare, sempre.
- Il fix del blocco ricorrente per deadlock CoreAudio (Mac) NON è stato portato qui: è specifico dell'HAL di CoreAudio, nessuna prova che affligga anche Windows. Se capita un blocco analogo su Windows, verificarlo prima di copiare la stessa soluzione (stream sempre aperto).

## Non rilasciato - 03/07/2026

- **Fix eco glossario nel detta pulito** (gemello Mac): regola 5 del prompt riformulata (la vecchia "Scrivi correttamente questi nomi" faceva appendere il glossario al testo) + guardia `pulizia_sospetta`: scarta la pulizia se aggiunge ≥2 nomi mai dettati o collassa il testo sotto un terzo delle parole.

## Non rilasciato - 02/07/2026

- **Apprendimento automatico** (gemello Mac): log testi opzionale con `debug_dettature`, giro giornaliero che impara le `sostituzioni` dagli errori ricorrenti. Da collaudare su PC reale.

- Prompt di pulizia allineato al Mac (regole numerate su riga singola). La corsia Apple Intelligence resta solo-Mac (su Windows non esiste equivalente di serie): qui la catena è agente -> grezzo.

- **Glossario**: nuova chiave `glossario` in `config.json`, passata a faster-whisper come `initial_prompt` — nomi propri e brand scritti giusti. Più mappa `sostituzioni` ("sbagliato → giusto", parola intera, case-insensitive).
- **Detta pulito**: le dettature lunghe (≥ `pulizia_min_parole`, default 15) passano dall'agente già sul PC (`claude -p --model haiku`, riserva `codex exec`) che toglie ripetizioni, ripensamenti e intercalari e sistema la punteggiatura. Stato "Sistemo..." sulla pill. Fallback totale: se l'agente manca, sbaglia o supera `pulizia_timeout_sec` (20s), si incolla il testo grezzo.
- Pulizia più veloce: `claude -p` parte "spoglio" (`--tools "" --strict-mcp-config --setting-sources "" --no-session-persistence`): ~2-3s in meno a chiamata, misurato; timeout portato a 20s (la chiamata reale sta sui 9-15s).
- Specchio della versione Mac dello stesso giorno (regola gemelle). **Da collaudare su PC Windows reale.**

## Non rilasciato - 27/06/2026

- Istruzioni `INSTALLA_CON_AI.md` riscritte come missione autonoma: l'agente del cliente fa autodiagnosi, auto-riparazione e prova reale, con `/goal` come aiuto opzionale.
- README e messaggi dell'installer allineati a v1.2: Ctrl destro per dettare, tasto Menu per voce agenti, niente residui F8 nelle istruzioni correnti.

## v1.2 - 26/06/2026

- Tasti come sul Mac: **Ctrl destro** detta (tieni premuto, parla, rilascia), **tasto Menu** accende/spegne la voce agenti. Tolto F8 (sui portatili i tasti F fanno volume/luminosita').
- Voce in uscita (legge le risposte ad alta voce, voce italiana di Windows) inglobata nell'app.
- App in **un unico file** `voice_dettatura_windows.py` (dettatura + pannello + voce). Resta solo `voce_hook.py` come hook opzionale che Claude Code richiama.

## v1.1 - 26/06/2026

- Pannello brandizzato come la versione Mac: pill scura in basso al centro con il marchio `salchiarenza.ai` e barra di lineette verdi ad arco "a sorriso" che si muovono col volume (overlay Tkinter, nessuna dipendenza extra).
- L'overlay non ruba il focus: continui a scrivere nel programma dove sei (finestra click-through e non attivabile).
- Icona cliccabile vera "Voce Dettatura" su Scrivania e nel Menu Start: il cliente non apre mai il terminale.
- Modello di trascrizione di default piu' forte (`medium`) per una resa migliore; resta configurabile in `config.json`.

## v1.0.0-beta - 21/06/2026

- Prima versione beta pubblica per Windows.
- Dettatura locale con tasto `F8`.
- Installer PowerShell con launcher sulla Scrivania.
- Istruzioni semplificate per installazione guidata con Claude Code o Codex.
