# Tuning your daily briefing

Read `interests.md` and `sections/` before editing. Start with one concrete change,
then run `./briefing validate --dir .` and preview a briefing to check the result.
Keep iterating from the email: refine interests, adjust section instructions,
and remove sections that are not useful. Publish your accepted changes when ready.

Do not put SMTP credentials, ChatGPT login data, or BRIEFING_KEY in tracked files.
The schedule and its matching timezone input live in `.github/workflows/briefing.yml`.
