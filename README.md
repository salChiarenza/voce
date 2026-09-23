# Voce — dettatura locale LeaderAI

App di dettatura locale di **salchiarenza.ai**: tieni premuto un tasto, parli, il testo si scrive dove hai il cursore. Audio e trascrizione Whisper restano sul computer. Nelle chat AI arriva subito il testo grezzo; sul Mac, negli altri programmi, una pulizia Apple opzionale ha un tetto di 2 secondi e non usa l'agente come riserva. In più, modalità **Voce AI**: legge ad alta voce le risposte del tuo assistente con l'audio sintetico del sistema e lo dichiara quando viene accesa.

Mentre parli compare in basso al centro una pill con il logo **LeaderAI.** (il punto verde cresce con la voce e pulsa mentre trascrive) e una barra di lineette verdi ad arco "a sorriso" che si muove col volume.

Nella copia di lavoro del 05/09/2026 la voce legge meglio elenchi e tabelle,
permette di rileggere l’ultima risposta e di scegliere una conversazione dal
menu **Voce** (Mac) o dalla finestra **Voce AI** (Windows). Le istruzioni e i
limiti di conservazione locale sono nei README e nella privacy del sistema.
Ogni risposta parte solo con **ChatGPT** per Codex oppure **Claude** per
Claude Code, senza pronunciare il progetto o `LeaderAI` come parte del nome.
Il turno di chi parla ha precedenza fino all'Invio: una risposta precedente
arrivata mentre si sta ancora dettando viene scartata e non parla sopra la
nuova domanda.
Queste novita’ locali entreranno nel pacchetto Drive con il prossimo rilascio.

## Due versioni

| Sistema | Cartella | Dettatura | Voce on/off |
|---|---|---|---|
| **Mac** | [`mac/`](mac/) | Cmd destro | Option + freccia sinistra |
| **Windows** | [`windows/`](windows/) | Ctrl destro | tasto Menu |

Mac e Windows sono disponibili insieme nello stesso pacchetto Voce. Dal modulo
**App** di LeaderAI Ecosystem apri il collegamento Google Drive e affidalo al
tuo Claude Code o Codex: sceglie la cartella del tuo sistema, segue
`INSTALLA_CON_AI.md`, installa, ripara e completa il collaudo. A te restano
permessi e prova fisica. Google Drive contiene la distribuzione corrente; questa
cartella locale e' la copia di lavoro e GitHub riceve soltanto il backup dopo
la prova Drive.

Per consegnare Voce a un cliente, usa il modello versionato [`EMAIL_CONSEGNA.md`](EMAIL_CONSEGNA.md). L'email, il launcher e le istruzioni locali vengono aggiornati insieme.

## Versione e stato

La versione unica è in [`VERSION`](VERSION); la storia generale è in
[`CHANGELOG.md`](CHANGELOG.md). Mac è la sorgente usata ogni giorno da Sal.
La versione Windows resta candidata finché dettatura, tasti e voce non vengono
provati su un PC Windows reale, ma e' gia' disponibile nello stesso pacchetto
della versione Mac. Ogni correzione nata dagli utilizzi aggiorna questa stessa
fonte e il pacchetto unico, senza creare copie.

Il collaudo della voce agenti include una risposta realmente ascoltata. Su
Codex il proprietario verifica e autorizza il comando da `/hooks`: trovare il
comando nel file di configurazione non prova che sia già fidato ed eseguito.

Su Mac il prodotto consegnato è la **fotocopia funzionale** della versione
usata da Sal: stessa voce Apple, stessi tasti, stessi tempi, stessi toggle e
stesso comportamento. Glossario, sostituzioni apprese e log restano personali.
Il collaudo si chiude solo con `FOTOCOPIA_SAL_OK` e prova audio reale.

## Per chi sviluppa

Le due app sono **gemelle**: il Mac è il master, Windows è il riflesso. Regole, lista parità e divieti in [`AGENTS.md`](AGENTS.md). Leggerlo prima di toccare qualsiasi cosa.

Le prove del prodotto vivono nella repo:

```text
python -m pip install -r requirements-test.txt
python -m pytest tests -q
```

## Privacy e licenza

La dettatura gira in locale: niente audio o testi inviati a server di questo progetto. La lettura delle risposte viene riprodotta al momento e non crea un file audio. Dettagli nei `PRIVACY.md` di ogni cartella. Licenza MIT (`LICENSE`).
