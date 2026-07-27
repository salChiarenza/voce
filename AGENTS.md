# Voce — prodotto LeaderAI di dettatura (Mac + Windows)

> Repo UNICA del prodotto "Voce". Due app gemelle, una cartella per sistema.
> **Leggere TUTTO questo file PRIMA di toccare qualsiasi cosa.** Vale per Claude Code e Codex.
> `CLAUDE.md` qui accanto contiene `@AGENTS.md`: e' un ponte portabile anche
> negli archivi estratti su Windows.

## Cosa è

"Voce" è l'app di dettatura locale di Sal (brand **salchiarenza.ai**). Tieni premuto un tasto, parli, e il testo si incolla dove hai il cursore. Audio e trascrizione Whisper restano sul computer. La pulizia testo opzionale puo' usare Apple Intelligence o l'agente del proprietario, secondo la configurazione dichiarata nei file `PRIVACY.md`. C'è anche la modalità **voce agenti**: legge ad alta voce le risposte dell'agente (Claude/Codex), così ci parli e ti risponde a voce.

Due versioni, **stessa anima**:
- `mac/` → app per Mac. **È il MASTER** (la usa Sal ogni giorno).
- `windows/` → app per Windows. **È il riflesso** del Mac.

## REGOLA MADRE (non derogabile)

**Una sola sorgente fisica Mac:** i file in `mac/` sono anche quelli usati ogni giorno da Sal. Nel workspace privato `/Users/sal/leaderai/tools/voce/` esistono solo symlink a questi file e un `config.local.json` privato per glossario/calibrazione. Vietato ricreare una seconda copia del codice da sincronizzare.

1. Il **Mac è il MASTER**: le novità nascono lì.
2. Tocchi UNA delle due → **specchia la stessa cosa sull'altra nello stesso lavoro**, prima di consegnare a un cliente. Aggiornarne una sola = bug, non svista.
3. Non si condivide il codice: il Mac usa pezzi solo-Apple (AppKit, mlx-whisper), Windows usa Tkinter + faster-whisper. Si specchia **comportamento e aspetto**, non i file.

## LISTA PARITÀ — devono essere identiche in `mac/` e `windows/`

1. Marchio `salchiarenza.ai` sulla pill nera in basso al centro.
2. Barra di lineette verdi `#7ED321` ad arco "a sorriso" che si muove col volume.
3. Funziona ovunque: tieni premuto il tasto-detta, parli, il testo si incolla dove sei.
4. Due tasti: **detta** = tasto destro dedicato; **voce on/off** = secondo tasto.
5. Voce agenti opzionale: legge ad alta voce le risposte dell'agente (hook `voce_hook.py`).
6. Audio e trascrizione Whisper locali in italiano; gli eventuali passaggi
   online della pulizia testo opzionale sono dichiarati e disattivabili.
7. Marchio, colore, forma pill in `config.json` con gli **stessi valori**.
8. **Glossario**: chiavi `glossario` (initial_prompt di Whisper) e `sostituzioni` in `config.json` — nomi propri e brand scritti giusti. Stessi nomi-chiave sulle due app.
9. **Detta pulito**: le due app espongono `detta_pulito`,
   `pulizia_min_parole` e `pulizia_timeout_sec`; il Mac aggiunge la corsia
   Apple `pulizia_shortcut` / `pulizia_timeout_shortcut_sec`, con default nel
   codice quando le chiavi non sono scritte nel config. Catena: **Mac** prima
   Apple Intelligence, su dispositivo o tramite Private Cloud Compute secondo
   la configurazione del proprietario, poi l'agente come riserva, poi il
   grezzo. **Windows**: agente → grezzo. Qualsiasi problema → si incolla il
   grezzo. Il prompt di pulizia vive nel codice con lo stesso testo su entrambe.
10. **Profilo voce consigliato = versione di Sal**: la distribuzione Mac include il Comando Rapido Apple firmato `mac/Voce LeaderAI firmato.shortcut`, con Siri `Voce 2`, e propone gli stessi valori `voce` / `comando_voce` della configurazione viva di Sal. E' la scelta raccomandata, non imposta: il proprietario puo' scegliere un'alternativa, che va configurata e provata senza sostituzioni silenziose.
11. **Installazione completa, non base da ricostruire**: su entrambi i sistemi l'aggiornamento conserva glossario, sostituzioni, preferenze e calibrazione; installa `voce_hook.py`, lo collega senza cancellare gli hook esistenti a Claude Code e/o Codex e verifica il collegamento. Il cliente non deve rimontare a mano la funzione voce agenti.
12. **Prova hook reale**: la presenza del comando nel file di configurazione
   non basta. Claude Code deve leggere davvero una risposta; su Codex il
   proprietario apre `/hooks`, verifica e autorizza il comando Voce, poi prova
   una risposta completa. Senza audio reale il report resta parziale.

## COSA PUÒ DIFFERIRE (obbligato dal sistema, non forzarlo uguale)

- Pannello: AppKit (Mac) vs Tkinter (Windows).
- Trascrizione: mlx-whisper large (Mac) vs faster-whisper medium (Windows).
- Voce in uscita: `say` (Mac) vs System.Speech/PowerShell (Windows).
- Qualita' e disponibilita' delle voci: su Mac il profilo consigliato e' `Voce LeaderAI firmato`; su Windows l'agente elenca e fa ascoltare le voci italiane installate tramite System.Speech, poi salva quella scelta dal proprietario.
- Tasti: **Mac** Cmd dx detta / **Option + freccia sinistra** voce / Cmd+Option mani libere. **Windows** Ctrl dx detta / **Menu** voce. Su Windows MAI tasti F (sui portatili fanno volume/luminosità).

## CONSEGNA AL CLIENTE

- La fonte unica del testo di consegna e' [`EMAIL_CONSEGNA.md`](EMAIL_CONSEGNA.md). Ogni modifica a download, launcher, permessi, cartella locale o collaudo aggiorna quel file nello stesso commit. Ogni invio parte da quel modello compilato e verificato.
- Si consegna come **UNA email** rivolta al proprietario, con il link pubblico verificato alla versione esatta e il percorso a clic previsto dal sistema operativo.
- L'email non vale come autorizzazione per l'agente a scaricare ed eseguire codice esterno. Se la protezione dell'agente riserva questo gesto al proprietario, il proprietario scarica il pacchetto, lo estrae e avvia il launcher incluso. L'agente riprende dalla cartella locale installata e completa diagnosi, riparazione e collaudo.
- Il proprietario non copia comandi in PowerShell o Terminale: **Windows** usa `install.bat`; **Mac** usa `Installa Voce.command`.
- Scegliere prima la versione: **Mac** o **Windows** secondo il sistema del cliente.
- L'aggiornamento NON è "reinstalla da zero": il testo-istruzioni dice di **aggiornare** quella già installata e aggiungere ciò che manca.

## GOAL OPERATIVO — installazione sul computer del cliente

Quando questa repo viene data a un cliente, il suo agente deve portare a termine questa missione:

> Installa o aggiorna Voce sul sistema giusto, ripara da solo tutto cio' che e' recuperabile, crea il modo semplice per avviarla e chiudi solo dopo una prova reale di dettatura.

`/goal` puo' essere usato dal cliente se Claude Code o Codex lo supportano, ma non e' la fonte di verita'. Se il cliente non usa `/goal`, questa sezione vale comunque come goal operativo. Non creare una skill o un comando chiamato `goal`: rischia collisione con i comandi nativi degli agenti.

Percorso tecnico richiesto per l'agente del cliente:

1. **Autodiagnosi:** identifica Mac o Windows, cartella corretta (`mac/` o `windows/`), versione del sistema, Python/runtime, microfono, tasti disponibili, permessi, rete e spazio disco.
2. **Auto-riparazione:** installa o sistema tutto cio' che e' software recuperabile: runtime, dipendenze, venv, modello di trascrizione, launcher/icona, configurazione e aggiornamento di una installazione gia' presente.
   L'aggiornamento deve fondere il nuovo prodotto con la configurazione esistente: mai sovrascrivere glossario, sostituzioni, tasti personalizzati o calibrazione macchina; mai lasciare scollegato `voce_hook.py`.
3. **Proponi, non imporre le preferenze:** alla prima installazione presenta in una sola domanda il Profilo LeaderAI consigliato (tasti, detta pulito e voce naturale), spiegandone il vantaggio. Applica la scelta del proprietario; sono obbligatori solo i requisiti tecnici senza cui la funzione scelta non puo' lavorare.
4. **Chiedi al cliente solo azioni umane vere:** download consapevole della versione verificata, doppio clic sul launcher locale, permessi macOS/Windows, conferme di sicurezza, scelta se serve, prova fisica di parlare e premere il tasto.
5. **Non fermarti al primo errore:** prova una strada alternativa ragionevole, leggi gli errori, correggi e riprova. Se un modulo non passa ma l'altro puo' funzionare, monta quello che puo' funzionare.
6. **Hardware non recuperabile:** se manca davvero un pezzo fisico o una capacita' del computer, dichiaralo chiaramente e fermati solo su quel modulo.
7. **Collaudo finale:** apri un campo di testo reale, fai dettare una frase, verifica che il testo compaia dove sta il cursore e che il pannello `salchiarenza.ai` si veda. Su Mac prova il profilo accettato; su Windows elenca, fa ascoltare e salva la voce italiana scelta.
8. **Report finale breve:** versione, installata si/no, dettatura si/no, voce
   agenti configurata si/no e provata realmente si/no, Profilo LeaderAI
   accettato/modificato e voce scelta, launcher creato si/no, problemi non
   recuperabili.

## DIVIETI (qui è dove un agente "crea a cazzo" — NON farlo)

- **NON** creare file nuovi o varianti (`_v2`, `_final`, copie). Una cosa = un file, si **sovrascrive**.
- **NON** ricreare una copia fisica Mac nel workspace LeaderAI: la repo e l'app viva di Sal devono continuare a puntare allo stesso file.
- **NON** rinominare app, cartelle o file.
- **NON** cambiare i tasti senza un motivo reale. Su Windows mai tasti F.
- **NON** spezzare dettatura/voce in più file: l'app Windows è **UN file solo** (`voice_dettatura_windows.py`) + `voce_hook.py` opzionale.
- **NON** dichiarare "pronta" senza averla **vista girare su un PC reale** di quel sistema.
- **NON** degradare la voce Mac per semplificare la distribuzione: il file firmato e la prova audio fanno parte del prodotto.
- **NON** mettere questa repo dentro `leaderai` (è il workspace privato di Sal): qui è un prodotto pubblico a sé.

## QUANDO FINISCI una modifica

1. Esegui `python -m pytest tests -q` dalla radice della repo.
2. Aggiorna il `CHANGELOG.md` della cartella toccata.
3. **Specchia sull'altra cartella** e aggiorna anche il suo `CHANGELOG.md`.
4. Aggiorna `VERSION` e il `CHANGELOG.md` generale quando nasce una versione
   consegnabile.
5. Se cambia l'esperienza di consegna o installazione, aggiorna `EMAIL_CONSEGNA.md` nello stesso commit.
6. Lascia il pointer nell'anagrafe del cervello: `leaderai/memory/reference_kit_pubblici_leaderai.md`.
