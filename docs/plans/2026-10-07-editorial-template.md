# Ivory and slate-blue briefing

Approved design: one warm editorial email, replacing the green cards and coloured pills.

## Global constraints

- Background ivory `#F7F4ED`; main text charcoal `#272A2C`; links and accents slate blue `#526B7A`; secondary text grey `#686D70`; dividers pale grey `#D9DDD9`.
- Continuous reading column capped at 640px, 34px Georgia masthead, 22px Georgia section headings, 16px sans-serif body text with generous line spacing.
- Table-based email layout, inline styles, system fonts, no new dependencies or theme settings.
- Preserve Markdown parsing, renderer signatures, section order/content, safe escaping, image blocking, optional content, footer information and plaintext delivery. Continue accepting icon metadata without displaying decorative icons.
- Preview and sent email use the same renderer.

### Task 1: Redesign and verify the shared email renderer

Read the existing renderer, template, tests, CLI callers, and sample before editing. Use Ponytail and TDD. Change the renderer and template together as one small unit.

1. Update `tests/test_render.py` first. Replace pill/badge/green-label expectations with checks preserving ordinary bold emphasis, punctuation (including the em dash after a bold list lead-in), links, and list structure without decorative wrappers. Add meaningful coverage for the heading structure, icons being accepted but absent from rendered headings, optional blocks, long text, tables and code. Keep existing parsing/escaping/image-blocking tests. Run focused tests and record expected failures before implementing.
2. Update `src/daily_briefing/template.html` and the style constants in `src/daily_briefing/render.py`. Delete automatic pill, badge, and green-label transformations; use regular Markdown plus inline styles. Use semantic h1/h2 headings with explicit inline margins/fonts. Put the kicker (normally Daily briefing) in the masthead, followed by headline/date, section count, and reading time in plain smaller text. Show Action today as an opening note with small blue heading and no card. Sections use whitespace and thin dividers, with no rounded card backgrounds, thick borders, or emoji. Preserve authored Markdown emphasis and punctuation rather than imposing uppercase labels. Links use true underlines; strong text inherits its surrounding colour: ordinary emphasis remains charcoal and linked emphasis remains slate blue. Footer stays quiet and readable. Code/quotes/tables should share the restrained palette and wrap safely on mobile. Use fluid width with modest padding that fits 375px and long headings; avoid fixed-width content except the email max-width. Keep layout fonts explicit on content cells for reliable email rendering.
3. Update README wording and any touched docstrings that inaccurately promise green cards or displayed icons. Keep existing frontmatter compatible. The controller will generate `docs/screenshot.png` from the actual rendered sample and inspect desktop/mobile previews; coordinate before committing that file. No redesign of the generation prompt or starter setup.
4. Run focused tests, then the full pytest suite and Ruff. Report exact commands, red/green evidence, skips/limitations and self-review findings. Commit the task's source/tests/docs after checks; no push or merge.

## Visual acceptance (controller)

- Render existing sample plus a stress fixture with long headings/links, tables, code and absent optional blocks.
- Inspect desktop and 375px mobile output for hierarchy, wrapping, margins, contrast and horizontal overflow. Use 640px maximum email width and measured 5.1:1 slate-blue contrast on ivory.
- Refresh README screenshot from actual rendered output. Keep a local preview for the user.
- Browser rendering is not inbox testing: report actual email-client checks separately and do not send mail without authorization.

## References

- https://thebrowser.com/sample/ — headline, source, summary and separator rhythm.
- https://mailchimp.com/help/limitations-of-html-email/ — basic table layout, inline styles and system fonts.
