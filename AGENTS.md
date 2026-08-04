# Voce — prodotto LeaderAI di dettatura (Mac + Windows)

> Repo UNICA del prodotto "Voce". Due app gemelle, una cartella per sistema.
> **Leggere TUTTO questo file PRIMA di toccare qualsiasi cosa.** Vale per Claude Code e Codex.
> `CLAUDE.md` qui accanto contiene `@AGENTS.md`: e' un ponte portabile anche
> nelle copie locali su Windows.

## Cosa è

"Voce" è l'app di dettatura locale di Sal (brand **salchiarenza.ai**). Tieni premuto un tasto, parli, e il testo si incolla dove hai il cursore. Audio e trascrizione Whisper restano sul computer. Nelle chat AI arriva sempre il grezzo immediato; sul Mac, fuori da quelle chat, la pulizia opzionale usa soltanto Apple Intelligence con un tetto breve. C'è anche la modalità **voce agenti**: legge ad alta voce le risposte dell'agente (Claude/Codex), così ci parli e ti risponde a voce.

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
9. **Testo immediato e pulizia sicura**: ChatGPT, Claude e Codex ricevono
   sempre il grezzo, anche a voce e mani libere spente. Nessun agente viene
   avviato nel percorso interattivo. Fuori dalle chat AI il **Mac** puo' usare
   Apple Intelligence, su dispositivo o tramite Private Cloud Compute secondo
   la configurazione del proprietario, con tetto `2s`; fallimento o guardia
   negativa → grezzo immediato. **Windows**, privo di una corsia locale
   equivalente, usa il grezzo con glossario e sostituzioni. La guardia gemella
   blocca variazioni oltre il 25% e nomi del glossario inventati.
10. **Mac = fotocopia funzionale della versione di Sal**: la distribuzione
    include il Comando Rapido Apple firmato
    `mac/Voce LeaderAI firmato.shortcut`, con Siri `Voce 2`, stessa voce
    interna, velocita', tono, tasti, tempi, toggle e soglie della
    configurazione viva di Sal. L'installer riallinea questi valori anche
    durante un aggiornamento e conserva soltanto glossario, sostituzioni
    apprese e preferenza di log. Il gate `FOTOCOPIA_SAL_OK` e la prova audio
    reale sono obbligatori.
11. **Installazione completa, non base da ricostruire**: su entrambi i sistemi l'aggiornamento conserva glossario, sostituzioni, preferenze e calibrazione; installa `voce_hook.py`, lo collega senza cancellare gli hook esistenti a Claude Code e/o Codex e verifica il collegamento. Il cliente non deve rimontare a mano la funzione voce agenti.
12. **Prova hook reale**: la presenza del comando nel file di configurazione
   non basta. Claude Code deve leggere davvero una risposta; su Codex il
   proprietario apre `/hooks`, verifica e autorizza il comando Voce, poi prova
   una risposta completa. Senza audio reale il report resta parziale.

## COSA PUÒ DIFFERIRE (obbligato dal sistema, non forzarlo uguale)

- Pannello: AppKit (Mac) vs Tkinter (Windows).
- Trascrizione: mlx-whisper large (Mac) vs faster-whisper medium (Windows).
- Voce in uscita: `say` (Mac) vs System.Speech/PowerShell (Windows).
- Qualita' e disponibilita' delle voci: su Mac lo standard e'
  `Voce LeaderAI firmato` e deve superare `FOTOCOPIA_SAL_OK`; su Windows
  l'agente elenca e fa ascoltare le voci italiane installate tramite
  System.Speech, poi salva quella scelta dal proprietario.
- Tasti: **Mac** Cmd dx detta / **Option + freccia sinistra** voce / Cmd+Option mani libere. **Windows** Ctrl dx detta / **Menu** voce. Su Windows MAI tasti F (sui portatili fanno volume/luminosità).

## CONSEGNA AL CLIENTE

- La fonte unica del testo di consegna e' [`EMAIL_CONSEGNA.md`](EMAIL_CONSEGNA.md). Ogni modifica al percorso di installazione, launcher, permessi, cartella locale o collaudo aggiorna quel file nello stesso commit. Ogni invio parte da quel modello compilato e verificato.
- Si consegna come **UNA email** rivolta al proprietario: il suo Claude Code o Codex prende la versione verificata dalla repo pubblica, installa e collauda.
- Il proprietario non preleva, non estrae e non avvia pacchetti. Interviene solo per permessi, conferme di sicurezza, scelte reali e prova fisica.
- Se l'agente non puo' eseguire direttamente l'installer, legge i sorgenti e ne riproduce localmente i passaggi. Il blocco non viene spostato sul proprietario.
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
3. **Applica lo standard corretto:** su Mac installa la fotocopia funzionale
   di Sal e conserva i soli dati personali. Su Windows applica i comportamenti
   compatibili e fa scegliere una voce italiana realmente disponibile, perche'
   la voce Apple non esiste su quel sistema.
4. **Chiedi al cliente solo azioni umane vere:** permessi macOS/Windows, login, conferme di sicurezza, scelta se serve, prova fisica di parlare e premere il tasto.
5. **Non fermarti al primo errore:** prova una strada alternativa ragionevole, leggi gli errori, correggi e riprova. Se un modulo non passa ma l'altro puo' funzionare, monta quello che puo' funzionare.
6. **Hardware non recuperabile:** se manca davvero un pezzo fisico o una capacita' del computer, dichiaralo chiaramente e fermati solo su quel modulo.
7. **Collaudo finale:** apri un campo di testo reale, fai dettare una frase,
   verifica che il testo compaia dove sta il cursore e che il pannello
   `salchiarenza.ai` si veda. Su Mac ottieni `FOTOCOPIA_SAL_OK` e prova
   l'audio; su Windows elenca, fa ascoltare e salva la voce italiana scelta.
8. **Report finale breve:** versione, installata si/no, dettatura si/no, voce
   agenti configurata si/no e provata realmente si/no, gate
   `FOTOCOPIA_SAL_OK` su Mac o voce scelta su Windows, launcher creato si/no,
   problemi non recuperabili.

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
