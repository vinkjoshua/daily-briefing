# Daily briefing — Wednesday 7 October

**Action today:** Register for the Rotterdam Agents Meetup (approval required, 40 seats) and check that presale access for the Northern Lights Festival opens Friday.

## Research

- **Sparse routing for small tool-calling models** — Lakeside Labs, 3 Oct 2026 ([paper](https://example.org/papers/sparse-routing), [code](https://example.org/code/sparse-routing)). Preprint. The authors route each tool call to a small specialist model and fall back to a large one when confidence is low. On a public tool-use benchmark they report 38% lower cost at equal accuracy. Limitations: one benchmark, no ablation of the confidence threshold.
  **Try:** Log the confidence of your agent's tool calls for a week and see how many a model one size smaller would have handled.
- **Postmortem: eval drift in a long-running support agent** — Harbor Systems engineering blog, 1 Oct 2026 ([link](https://example.org/blog/eval-drift)). Production report. Pass rates fell 9 points over six months with no code change, because the underlying tickets changed. They fixed it with a monthly refreshed eval set. Limitations: one product, no numbers on the refresh cost.
  **Try:** Add a dated sample of last month's real inputs to your eval set and compare it with your frozen set.

## Open-source radar

- **[tracewise](https://example.org/tracewise)** — Local trace viewer for agent runs. MIT licence, 2 weeks old, 3.1k stars, weekly commits. Useful because it works offline with any OpenAI-compatible client. Try: `pip install tracewise && tracewise serve`.
- **[patchbay](https://example.org/patchbay)** — A small library that turns a folder of Markdown prompts into versioned, testable functions. Apache-2.0, v0.4 released 4 Oct, 900 stars. Try: `npx patchbay init`.

## AI events & talks

- **Canal AI Guild** — Building agents with open models: a hands-on evening. Thursday 15 Oct, 18:30, Amsterdam, Canal Hall. Registration: approval required. [Link](https://example.org/events/open-model-agents)
- Rotterdam Agents Meetup — Three lightning talks on evals. Tuesday 20 Oct, 19:00, Rotterdam, Harbour Café. Registration: open, 40 seats. [Link](https://example.org/events/rotterdam-agents)

## This week

- Open studio weekend at the Riverside Gallery — Sat 10 and Sun 11 Oct, 11:00–17:00, free, no ticket needed. [Link](https://example.org/whatson/open-studio)
- Jazz at the Old Dock — Thursday 8 Oct, 20:30, €18, selling fast. [Link](https://example.org/whatson/jazz-old-dock)
- Autumn market on Cathedral Square — Friday 9 Oct, 09:00–15:00, free. [Link](https://example.org/whatson/autumn-market)

## Book ahead

**ACTION**
- Northern Lights Festival, 12–14 Feb 2027 — presale opens Friday 9 Oct at 10:00; register for the presale list beforehand. [Link](https://example.org/festival/presale)
- Modern Light exhibition, until 14 Mar 2027 — timed tickets for weekends are selling; book a slot before the end of the month. [Link](https://example.org/exhibitions/modern-light)

**On the radar**
- Delta Systems Conference, 18 Mar 2027 — early-bird registration opens in November. [Link](https://example.org/conf/delta)

Sources: arXiv, Harbor Systems blog, GitHub Trending, Luma, Riverside Gallery agenda, festival and gallery sites.
