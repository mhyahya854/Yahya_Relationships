# UI smoke test (headless Edge)

The full acceptance flow is exercised against the running dev stack:

1. Start the backend and frontend: `npm run dev`
2. In a second terminal, install the harness and run it:

```powershell
npm install   # inside tests/ui
node smoke.mjs
```

The script launches the installed Microsoft Edge in headless mode and walks
through the diagram-first acceptance flow: default perspective, multi-path
relationship panel, **Show why** on the primary and additional paths (with
different highlighted paths), exit path mode, expand/collapse of branches,
perspective switching by double-click, keyboard return to the owner, a
general close-friend edge, journal/backup tool health, and the Family Mermaid
regression. Screenshots land in `tests/ui/shots/` (copy the required ones to
`docs/ui-screenshots/` after a verified run). It exits non-zero on any
console error.

The test creates one temporary person named "Sami Friend", a close-friend
relationship, one journal entry and one backup. Clean them afterwards:

```powershell
python tests/ui/clean_smoke_data.py
```
