# Tuning your daily briefing

Read `interests.md` and `sections/` before editing. Start with one concrete change,
then run `./briefing validate --dir .` and preview a briefing to check the result.
Keep iterating from the email: refine interests, adjust section instructions,
and remove sections that are not useful. Run `./briefing publish` to review every
outgoing commit and publish accepted changes. Use `./briefing publish --run` only
when a normal daily run is wanted; it respects the already-sent guard.

Preserve staged and unrelated work. Publication refuses those changes rather than
unstaging or stashing them. If a bot update conflicts, publication aborts its rebase
and retains your local commit; follow its recovery steps and review again. Inspect
the remote after a failed push and Actions after an uncertain dispatch before retrying.

If outgoing merges or forbidden history block publication, keep the original
checkout. Use the error's exact GitHub CLI `repo clone` command to create a separate
clean private clone, copy only accepted allowlisted personalization (no old `.git`,
history or credentials), then run `./briefing validate --dir .` and `./briefing publish`
there. Do not automatically rewrite the user's history.

Do not put SMTP credentials, ChatGPT login data, or BRIEFING_KEY in tracked files.
The schedule and its matching timezone input live in `.github/workflows/briefing.yml`.
