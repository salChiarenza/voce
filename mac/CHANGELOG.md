# Changelog

## Non rilasciato - 02/07/2026

- **Corsia veloce detta pulito (Mac)**: se esiste il Comando Rapido "Voce Pulita" (modello Apple Intelligence on-device, ponte puro creato dal kit al Passo 3-bis), la pulizia corre in ~1s a zero cloud; l'agente resta come riserva. Prompt di pulizia riscritto (regole numerate su riga singola): ora risolve bene i ripensamenti anche col modello on-device.

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
