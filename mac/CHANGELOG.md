# Changelog

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
