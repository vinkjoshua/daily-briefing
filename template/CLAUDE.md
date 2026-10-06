# Daily briefing tuning

Follow the tuning loop in `AGENTS.md`: read interests and sections, make one
concrete improvement, validate and preview it, then publish accepted changes.
Use `./briefing publish` to review and publish outgoing commits and accepted edits.
`./briefing publish --run` requests an ordinary run and respects the daily guard.
Preserve staged and unrelated work; follow the displayed recovery instructions
after a bot conflict, and inspect the remote or Actions after uncertain outcomes.
For unsupported outgoing history, preserve the original checkout and use the
displayed GitHub CLI `repo clone` command for a separate clean private clone.
Copy only accepted allowlisted personalization, excluding old `.git`, history and
credentials; validate and publish from the clean clone. Never rewrite history automatically.
Never write credentials or login data into tracked files.
