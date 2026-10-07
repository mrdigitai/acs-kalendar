# acs-kalendar — pravidla pro Claude Code

Česky, tykat.

## Git workflow

- Po každé funkční, malé změně udělej commit se srozumitelným popisem (česky, co a proč).
- Větší změny dělej ve vlastní větvi, ne přímo na `main`. Na `main` se jde až po Michalově schválení.
- Nikdy necommituj `.env` ani klíče (API klíče, tokeny, `.claude/settings.local.json`). Stageuj jen konkrétní soubory, žádné `git add -A`.
- Žádné automatické migrace databáze při deployi.
