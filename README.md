# Voce Dettatura

Tieni premuto un tasto, parli, e il testo compare dove hai il cursore. Tutto resta in locale sul tuo computer. Per Mac; su Windows è ancora in prova.

## Per te, una riga

Incolla questa frase nella tua AI (Claude Code o Codex):

> Installa Voce Dettatura sul mio computer: scarica https://github.com/salChiarenza/voce/releases/latest/download/Voce.zip, poi apri il file mac/INSTALLA_CON_AI.md se sono su Mac o windows/INSTALLA_CON_AI.md se sono su Windows, e segui quelle istruzioni.

Su Mac detti con Cmd destro. Su Windows con Ctrl destro.

## Istruzioni per la tua AI

**Missione:** installare Voce Dettatura sul computer della persona, così che possa dettare in qualsiasi campo di testo. Tutto resta in locale.

**Passi:**

1. Scarica https://github.com/salChiarenza/voce/releases/latest/download/Voce.zip ed estrai il pacchetto.
2. Controlla il sistema: Mac o Windows.
3. Apri il file di istruzioni giusto, `mac/INSTALLA_CON_AI.md` su Mac, `windows/INSTALLA_CON_AI.md` su Windows, e seguilo.
4. Guida la persona nei permessi che il sistema chiede. I gesti di sicurezza (conferme, password) li fa lei.

**Prove:**

1. Chiedi alla persona di aprire un campo di testo e tenere premuto Cmd destro (Mac) o Ctrl destro (Windows).
2. Fai dire una frase corta.
3. Controlla che il testo compaia nel campo.

**Alla fine:** di' alla persona che ora detta con Cmd destro su Mac o Ctrl destro su Windows, e che se qualcosa non risponde ti basta descriverlo. Se vuoi, proponi un secondo giro di prova.

**Aggiornare:** riscarica lo stesso link, estrai, e rilancia l'installazione: conserva le scelte della persona.

## Requisiti

- **Mac:** chip Apple Silicon (M1 o successivo), macOS 14 o successivo, 16 GB di memoria, 10 GB liberi sul disco, Python 3.11 o successivo.
- **Windows:** Windows 10 o 11 a 64 bit, 16 GB di memoria, 10 GB liberi sul disco, Python 3.11 o successivo. La versione Windows non è ancora provata su un PC vero.
- Internet la prima volta, per scaricare il modello di trascrizione.

Il dettaglio, con la diagnosi prima dell'installazione, è in [`mac/INSTALLA_CON_AI.md`](mac/INSTALLA_CON_AI.md) e [`windows/INSTALLA_CON_AI.md`](windows/INSTALLA_CON_AI.md). Scheda tecnica di ogni sistema: [`mac/README.md`](mac/README.md), [`windows/README.md`](windows/README.md).

## Privacy

Audio e trascrizione restano sul tuo computer: niente viene inviato a server di questo progetto. Dettagli in `mac/PRIVACY.md` e `windows/PRIVACY.md`.

## Licenza

MIT, vedi [`LICENSE`](LICENSE).

## Chi l'ha fatta

Sal Chiarenza, [LeaderAI](https://www.salchiarenza.ai/claude).
