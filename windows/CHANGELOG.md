# Changelog

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
