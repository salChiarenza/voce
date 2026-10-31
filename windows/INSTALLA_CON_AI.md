# Installa Voce LeaderAI su Windows

Voce arriva dall'unico pacchetto Mac + Windows pubblicato su GitHub, sempre
all'ultima versione: https://github.com/salChiarenza/voce/releases/latest/download/Voce.zip
Vale per chi la installa per la prima volta e per chi l'ha
gia' installata e ha un problema. Il percorso ha tre momenti, tutti dell'agente:

1. Fase 0: diagnosi in sola lettura, prima di installare qualsiasi cosa;
2. l'agente sceglie `windows/` ed esegue l'installer (nuova installazione o aggiornamento);
3. lo stesso agente lavora sulla cartella installata, completa la diagnosi, prova e chiude.

Al proprietario restano le conferme di Windows e la prova con il microfono. L'installazione avviene nel profilo Windows dell'utente tramite `install.bat`.

## Fase 0: diagnosi, prima di installare

Prima di scaricare dipendenze o modello, in PowerShell e in sola lettura:

```powershell
$env:PROCESSOR_ARCHITECTURE                                   # deve essere AMD64
(Get-CimInstance Win32_OperatingSystem).Caption               # Windows 10 o 11
[math]::Floor((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB)   # memoria, GB
[math]::Floor((Get-PSDrive ($env:SystemDrive.TrimEnd(':'))).Free / 1GB)          # spazio libero, GB
py -3 --version; python --version                             # Python 3.11 o successivo
Test-NetConnection pypi.org -Port 443 -InformationLevel Quiet
Test-NetConnection huggingface.co -Port 443 -InformationLevel Quiet
Test-Path "$HOME\VoiceDettaturaWindows\VERSION"               # Voce gia' installata?
Get-Process | Where-Object { $_.ProcessName -match 'dragon|whisper|wispr|dettat|dictat' }   # altre app per dettare
```

Requisiti (fonti nel CHANGELOG, versione 1.3.0-rc.32): Windows 10 o 11 a 64 bit su
processore Intel o AMD (il motore di trascrizione non esiste per Windows su ARM),
16 GB di memoria, 10 GB liberi sul disco (2 GB per un aggiornamento), Python 3.11
o successivo, internet la prima volta.

- Tutto a posto: di' «la Voce va bene per questo computer» e prosegui.
- Manca un requisito del computer (processore, Windows, memoria, spazio): non
  installare niente. Di' al proprietario, in una riga:
  «la Voce non va per questo computer, perche' X: la Voce trascrive sul computer, senza mandare l'audio in
  rete, con un modello che resta in memoria accanto alla tua AI; servirebbe Y».
- Manca software (Python, internet): sistemalo tu, Python dal programma ufficiale
  di python.org, e rifai la diagnosi.
- Voce gia' installata: leggi `voice.log` nella sua cartella e, se scrive da sola o
  e' lenta, applica prima «Se la Voce scrive da sola» qui in fondo, poi aggiorna.

## Missione unica dell'agente

1. Scarica tu il pacchetto Voce da https://github.com/salChiarenza/voce/releases/latest/download/Voce.zip
   in una cartella temporanea; il proprietario non fa da tramite.
2. Verifica che il pacchetto contenga `VERSION`, `mac/` e `windows/`: le due
   versioni devono restare insieme anche se su questo computer ne installi una.
3. Estrai il pacchetto, entra in `windows` e verifica la versione dichiarata.
4. Esegui `install.bat` e resta sulla finestra fino al messaggio `Installazione completata`.
5. Chiedi al proprietario di confermare gli avvisi di Windows e dell'antivirus, indicando con precisione cosa deve autorizzare.
6. Se l'installazione si interrompe, leggi il messaggio nella finestra, correggi la causa ed esegui di nuovo `install.bat`.

Aggiornamento: se Voce e' gia' installata, riscarica l'ultima versione dallo stesso
link, estraila e rilancia l'installazione. L'installer conserva la configurazione
personale.

L'installer crea o aggiorna:

```text
%USERPROFILE%\VoiceDettaturaWindows
```

e aggiunge l'icona **Voce Dettatura** sulla Scrivania e nel Menu Start.

## Continuazione automatica dopo l'installazione

Dopo il messaggio `Installazione completata`, prosegui nella stessa sessione:
entra nella cartella locale qui sotto e completa subito la missione di diagnosi
e prova. Il percorso usa un solo messaggio iniziale. Al proprietario chiedi
soltanto i gesti fisici e le conferme di Windows nel momento in cui servono.

## Missione locale di diagnosi e collaudo

L'agente lavora sulla cartella locale gia' installata:

```text
%USERPROFILE%\VoiceDettaturaWindows
```

Obiettivo: portare Voce fino a una prova reale, conservando la configurazione personale esistente.

1. Verifica la presenza di `VERSION`, `voice_dettatura_windows.py`, `voce_hook.py`, `config.json`, `.venv` e `Voce Dettatura.bat`.
2. Verifica Python, PowerShell, microfono, tasto Ctrl destro, tasto Menu, memoria, rete e spazio disponibile.
3. Controlla che l'aggiornamento abbia conservato glossario, sostituzioni, tasti, modello, voce scelta e calibrazione gia' presenti.
4. Esegui la verifica sintattica dei file Python con l'interprete della cartella `.venv`.
5. Esegui `voce_hook.py --check-hooks` con l'interprete della cartella `.venv`. Il
   controllo AVVIA il comando scritto nella configurazione (`--ping`): vale solo
   `configurato e funzionante`; `NON FUNZIONA` dice perche'. Claude Code su
   Windows si collega senza shell (`command` + `args`, da Claude Code 2.1.139:
   se e' piu' vecchia il controllo dice di aggiornarla): Git Bash toglie le barre
   rovesciate dei percorsi e il gancio non parte. Ripara con `--install-hooks` e
   ripeti la verifica.
6. Avvia Voce dall'icona sulla Scrivania.
7. Guida il proprietario nella prova in Blocco note: Ctrl destro tenuto, frase dettata, rilascio, testo inserito e pannello `LeaderAI.` visibile con il sorriso verde.
8. Elenca le voci italiane disponibili con `voce_hook.py --list-voices`.
9. Falle ascoltare una alla volta con `voce_hook.py --test-voice "NOME"` e salva quella scelta con `voce_hook.py --set-voice "NOME"`.
10. Per Codex fai aprire `/hooks` al proprietario, verifica il comando
    `voce_hook.py` e chiedi la fiducia esplicita se richiesta.
11. Prova il tasto Menu, tenuto premuto un secondo (un tocco non deve fare
    niente): l'accensione deve dire `Voce AI` e `audio sintetico`.
    Prova poi una risposta completa dell'agente e verifica che venga letta
    davvero con la voce scelta. `--check-hooks` avvia il comando di collegamento ma
    non prova la fiducia di Codex ne' l'ascolto: la prova vera e' la risposta
    letta. Se all'accensione la voce dice `Attenzione: il collegamento non
    funziona`, riesegui `--install-hooks` e `--check-hooks`.
12. Quando Windows richiede microfono o altre conferme, indica al proprietario il gesto preciso e riprendi il collaudo subito dopo.
13. Se lo scaricamento del modello della voce fallisce, tratta l'antivirus come
    prima causa: gli scudi web e posta intercettano il traffico e lo firmano con
    una radice propria. Misura la catena host per host su `github.com`,
    `raw.githubusercontent.com` e `huggingface.co`, distingui la radice fidata
    da quella non fidata e riprova con un canale che usa l'archivio certificati
    di Windows. Quando resta necessaria una scelta del proprietario, indica il
    percorso esatto dentro il suo antivirus e l'esclusione da aggiungere.
    Origine: consegna Windows del 28/07/2026 fermata da Avast su questo punto.
14. Ripara gli errori software locali recuperabili, ripeti la prova interessata e chiudi quando gli esiti sono verificati.
15. Prova di chiusura, sempre: una dettatura con Ctrl destro arriva in Blocco note in
    pochi secondi; poi, per due minuti in cui il proprietario non detta, `voice.log`
    non scrive testi da solo: dopo i due minuti, nelle righe successive all'ora segnata,
    nessuna `incollato (programma bersaglio` e nessuna `invio automatico premuto`.

## Profilo LeaderAI consigliato

Alla prima installazione proponi in una sola domanda:

- Ctrl destro per dettare;
- tasto Menu, tenuto un secondo, per la voce;
- testo grezzo immediato con glossario e sostituzioni locali;
- voce agenti inizialmente spenta;
- scelta guidata della voce italiana percepita come piu' naturale.

Applica la scelta del proprietario, salvala nella configurazione locale e
mostrala nella conferma finale.

## Conferma finale

Mostra al proprietario:

- versione e cartella installata;
- icona creata;
- dettatura con Ctrl destro;
- pannello `LeaderAI.`;
- tasto Menu e voce agenti;
- prova dei due minuti senza testi scritti da soli;
- avviso `Voce AI` e `audio sintetico` verificato all'accensione;
- collegamento configurato a Claude Code o Codex e prova audio reale;
- voce italiana scelta;
- configurazione precedente conservata;
- gesti umani richiesti e completati durante la prova.

Apri con `Perfetto, l'ho fatto. Tutto completato e funzionante.` soltanto dopo
che tutte le prove sono passate. Poi chiudi il
lavoro sul computer del proprietario.

## Uso quotidiano

1. Clicca l'icona **Voce Dettatura**.
2. Tieni premuto **Ctrl destro**, parla e rilascia.
3. Usa il tasto **Menu** per accendere o spegnere la voce agenti.
4. Chiudi la finestra di Voce per terminare l'app.

## Se la Voce scrive da sola

Su Windows non ci sono le mani libere: la Voce scrive soltanto mentre Ctrl destro
e' tenuto premuto. Se compaiono testi da soli, l'AI del proprietario:

1. legge le ultime righe di `voice.log` con `incollato (programma bersaglio`
   (testo scritto) e `invio automatico premuto` (testo inviato): ogni testo vero
   ha davanti la sua registrazione;
2. controlla che giri una sola Voce (`Get-Process python*` e la riga di comando con
   `voice_dettatura_windows.py`) e che non ci sia un'altra app per dettare attiva;
3. chiede al proprietario se il Ctrl destro resta incastrato;
4. chiude le copie in piu', riavvia Voce dall'icona e rifa' la prova di chiusura (punto 15).
