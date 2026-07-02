# Voce — prodotto LeaderAI di dettatura (Mac + Windows)

> Repo UNICA del prodotto "Voce". Due app gemelle, una cartella per sistema.
> **Leggere TUTTO questo file PRIMA di toccare qualsiasi cosa.** Vale per Claude Code e Codex.
> `CLAUDE.md` qui accanto è un symlink di questo file.

## Cosa è

"Voce" è l'app di dettatura locale di Sal (brand **salchiarenza.ai**). Tieni premuto un tasto, parli, e il testo si incolla dove hai il cursore. Tutto in **locale**, niente cloud. C'è anche la modalità **voce agenti**: legge ad alta voce le risposte dell'agente (Claude/Codex), così ci parli e ti risponde a voce.

Due versioni, **stessa anima**:
- `mac/` → app per Mac. **È il MASTER** (la usa Sal ogni giorno).
- `windows/` → app per Windows. **È il riflesso** del Mac.

## REGOLA MADRE (non derogabile)

1. Il **Mac è il MASTER**: le novità nascono lì.
2. Tocchi UNA delle due → **specchia la stessa cosa sull'altra nello stesso lavoro**, prima di consegnare a un cliente. Aggiornarne una sola = bug, non svista.
3. Non si condivide il codice: il Mac usa pezzi solo-Apple (AppKit, mlx-whisper), Windows usa Tkinter + faster-whisper. Si specchia **comportamento e aspetto**, non i file.

## LISTA PARITÀ — devono essere identiche in `mac/` e `windows/`

1. Marchio `salchiarenza.ai` sulla pill nera in basso al centro.
2. Barra di lineette verdi `#7ED321` ad arco "a sorriso" che si muove col volume.
3. Funziona ovunque: tieni premuto il tasto-detta, parli, il testo si incolla dove sei.
4. Due tasti: **detta** = tasto destro dedicato; **voce on/off** = secondo tasto.
5. Voce agenti opzionale: legge ad alta voce le risposte dell'agente (hook `voce_hook.py`).
6. Trascrizione locale in italiano, niente cloud.
7. Marchio, colore, forma pill in `config.json` con gli **stessi valori**.
8. **Glossario**: chiavi `glossario` (initial_prompt di Whisper) e `sostituzioni` in `config.json` — nomi propri e brand scritti giusti. Stessi nomi-chiave sulle due app.
9. **Detta pulito**: chiavi `detta_pulito`, `pulizia_min_parole`, `pulizia_timeout_sec`, `pulizia_shortcut`, `pulizia_timeout_shortcut_sec`. Le dettature lunghe si ripuliscono (via ripetizioni/ripensamenti, punteggiatura sistemata); la pill mostra "Sistemo…". Catena: **Mac** prima il modello Apple on-device via Comando Rapido "Voce Pulita" (~1s, zero cloud; differenza obbligata: su Windows non esiste) → agente locale (`claude -p` spoglio, riserva `codex exec`) → grezzo. **Windows**: solo agente → grezzo. Qualsiasi problema → si incolla il grezzo: la dettatura non si perde MAI. Il prompt di pulizia è UNO (`prompt_pulizia`, regole numerate su riga singola): stesso testo su entrambe.

## COSA PUÒ DIFFERIRE (obbligato dal sistema, non forzarlo uguale)

- Pannello: AppKit (Mac) vs Tkinter (Windows).
- Trascrizione: mlx-whisper large (Mac) vs faster-whisper medium (Windows).
- Voce in uscita: `say` (Mac) vs System.Speech/PowerShell (Windows).
- Tasti: **Mac** Cmd dx detta / Alt dx voce. **Windows** Ctrl dx detta / **Menu** voce. Su Windows MAI tasti F (sui portatili fanno volume/luminosità).

## CONSEGNA AL CLIENTE

- Si consegna come **UNA email** il cui corpo è il **testo-istruzioni** per il Claude/Codex del cliente. Niente allegati, niente istruzioni tecniche a mano.
- Scegliere prima la versione: **Mac** o **Windows** secondo il sistema del cliente.
- L'aggiornamento NON è "reinstalla da zero": il testo-istruzioni dice di **aggiornare** quella già installata e aggiungere ciò che manca.

## GOAL OPERATIVO — installazione sul computer del cliente

Quando questa repo viene data a un cliente, il suo agente deve portare a termine questa missione:

> Installa o aggiorna Voce sul sistema giusto, ripara da solo tutto cio' che e' recuperabile, crea il modo semplice per avviarla e chiudi solo dopo una prova reale di dettatura.

`/goal` puo' essere usato dal cliente se Claude Code o Codex lo supportano, ma non e' la fonte di verita'. Se il cliente non usa `/goal`, questa sezione vale comunque come goal operativo. Non creare una skill o un comando chiamato `goal`: rischia collisione con i comandi nativi degli agenti.

Ordine obbligatorio per l'agente del cliente:

1. **Autodiagnosi:** identifica Mac o Windows, cartella corretta (`mac/` o `windows/`), versione del sistema, Python/runtime, microfono, tasti disponibili, permessi, rete e spazio disco.
2. **Auto-riparazione:** installa o sistema tutto cio' che e' software recuperabile: runtime, dipendenze, venv, modello di trascrizione, launcher/icona, configurazione e aggiornamento di una installazione gia' presente.
3. **Chiedi al cliente solo azioni umane vere:** clic su permessi macOS/Windows, conferme SmartScreen/admin, scelta se serve, prova fisica di parlare e premere il tasto.
4. **Non fermarti al primo errore:** prova una strada alternativa ragionevole, leggi gli errori, correggi e riprova. Se un modulo non passa ma l'altro puo' funzionare, monta quello che puo' funzionare.
5. **Hardware non recuperabile:** se manca davvero un pezzo fisico o una capacita' del computer, dichiaralo chiaramente e fermati solo su quel modulo.
6. **Collaudo finale:** apri un campo di testo reale, fai dettare una frase, verifica che il testo compaia dove sta il cursore e che il pannello `salchiarenza.ai` si veda. Se la voce agenti e' configurata, verifica anche l'accensione/spegnimento.
7. **Report finale breve:** installata si/no, dettatura si/no, voce agenti si/no, launcher creato si/no, problemi non recuperabili.

## DIVIETI (qui è dove un agente "crea a cazzo" — NON farlo)

- **NON** creare file nuovi o varianti (`_v2`, `_final`, copie). Una cosa = un file, si **sovrascrive**.
- **NON** rinominare app, cartelle o file.
- **NON** cambiare i tasti senza un motivo reale. Su Windows mai tasti F.
- **NON** spezzare dettatura/voce in più file: l'app Windows è **UN file solo** (`voice_dettatura_windows.py`) + `voce_hook.py` opzionale.
- **NON** dichiarare "pronta" senza averla **vista girare su un PC reale** di quel sistema.
- **NON** mettere questa repo dentro `leaderai` (è il workspace privato di Sal): qui è un prodotto pubblico a sé.

## QUANDO FINISCI una modifica

1. Aggiorna il `CHANGELOG.md` della cartella toccata.
2. **Specchia sull'altra cartella** e aggiorna anche il suo `CHANGELOG.md`.
3. Lascia il pointer nell'anagrafe del cervello: `leaderai/memory/reference_kit_pubblici_leaderai.md`.
