# Changelog Voce

Questo file registra le versioni dell'unico prodotto Voce. I dettagli tecnici
restano nei changelog [`mac/`](mac/CHANGELOG.md) e
[`windows/`](windows/CHANGELOG.md).

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
