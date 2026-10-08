Today is $today. Produce my personal daily briefing. It will be emailed to me as-is. Work in the current directory.

## Before you start
Read `interests.md` (what I care about) and `state/seen.md` (items already sent), plus any other `state/` files a section mentions.
Do not repeat anything in `state/seen.md` unless it has a material update; if you resurface it, say what changed. A section may define its own exceptions.

## Rules
- Use live web search. Prefer primary sources (paper, repo, official event page) over aggregators.
- Your shell has no network access; do not try curl, Python or APIs. Use web search for everything online.
- Never invent dates, prices, results, star counts or implementation details. If unverified, say so.
- Distinguish author or organiser claims from your own assessment.
- Write in a concise, natural editorial voice: concrete details, plain language, no hype or repetitive "Why it matters" labels.
- Add one short introductory sentence immediately below each populated `##` heading, previewing today's actual selections. Avoid boilerplate category descriptions or a fabricated common theme.
- Within each item's summary paragraph, weave in a specific reason it is useful, interesting or worth considering, grounded in verified detail and `interests.md`. This includes professional, leisure and book-ahead events; explain the relevant topic, format or practical opportunity rather than merely listing logistics. Do not invent preferences, promise enjoyment or imply unsupported event ambiance.
- Any section may be empty: write "Nothing worth your time today." without an introduction rather than padding. Keep repeated ACTION reminders to one concise line with the relevant reason and deadline.
- Whole email under 1,200 words. Put important source-access failures in one final line starting with "Sources:".
- Only change files under `state/`. Never edit any other file.

## Sections
$sections

## After writing
Append every item included today to `state/seen.md` as `YYYY-MM-DD | section | key (ID, repo or URL) | title`, and save any other `state/` files a section asked you to maintain.

## Output
Your final message is the email body in Markdown and nothing else:

# Daily briefing — <weekday d month>
**Action today:** <one line, only if a section flags something to act on today; otherwise omit this line>
$skeleton
