# Daily briefing — Wednesday 7 October

**Action today:** Request Canal AI Guild approval, register for Rotterdam Agents Meetup (40 seats), and join the festival presale list before Friday.

## Research

A cheaper tool-routing method and an eval-drift postmortem offer two concrete checks for agent systems.

- **Sparse routing for small tool-calling models** — Lakeside Labs, 3 Oct 2026 ([paper](https://example.org/papers/sparse-routing), [code](https://example.org/code/sparse-routing)). Preprint. The authors route each tool call to a small specialist model and fall back to a large one when confidence is low. For tool-heavy agents, the useful question is how often cheaper specialists can handle the work. On a public tool-use benchmark they report 38% lower cost at equal accuracy. Limitations: one benchmark, no ablation of the confidence threshold.
  **Try:** Log the confidence of your agent's tool calls for a week and see how many a model one size smaller would have handled.
- **Postmortem: eval drift in a long-running support agent** — Harbor Systems engineering blog, 1 Oct 2026 ([link](https://example.org/blog/eval-drift)). Production report. Pass rates fell 9 points over six months with no code change, because the underlying tickets changed. They fixed it with a monthly refreshed eval set, a useful reminder that a frozen test set can miss changes in real support traffic. Limitations: one product, no numbers on the refresh cost.
  **Try:** Add a dated sample of last month's real inputs to your eval set and compare it with your frozen set.

## Open-source radar

An offline trace viewer and versioned Markdown prompts offer practical ways to inspect and test agent work.

- **[tracewise](https://example.org/tracewise)** — Local trace viewer for agent runs. MIT licence, 2 weeks old, 3.1k stars, weekly commits. Useful because it works offline with any OpenAI-compatible client. Try: `pip install tracewise && tracewise serve`.
- **[patchbay](https://example.org/patchbay)** — A small library that turns a folder of Markdown prompts into versioned, testable functions, making prompt changes easier to check before using them in an agent. Apache-2.0, v0.4 released 4 Oct, 900 stars. Try: `npx patchbay init`.

## AI events & talks

An open-model workshop and three eval talks put agent implementation on the local agenda.

- **Canal AI Guild** — Building agents with open models: a hands-on evening, offering a chance to work through implementation rather than only hear a talk. Thursday 15 Oct, 18:30, Amsterdam, Canal Hall. Registration: approval required. [Link](https://example.org/events/open-model-agents)
- Rotterdam Agents Meetup — Three lightning talks on evals, a compact way to compare approaches to checking agent behavior. Tuesday 20 Oct, 19:00, Rotterdam, Harbour Café. Registration: open, 40 seats. [Link](https://example.org/events/rotterdam-agents)

## This week

Printmaking demonstrations, improvised jazz and an autumn produce market offer three different outings this week.

- Open studio weekend at the Riverside Gallery — Sat 10 and Sun 11 Oct, 11:00–17:00, free, no ticket needed. Artists will demonstrate printmaking, a chance to see how a finished image takes shape at the press. [Link](https://example.org/whatson/open-studio)
- Jazz at the Old Dock — Thursday 8 Oct, 20:30, €18, selling fast. A piano trio builds its set around improvisation, so familiar standards become a starting point for something new. [Link](https://example.org/whatson/jazz-old-dock)
- Autumn market on Cathedral Square — Friday 9 Oct, 09:00–15:00, free. Growers are bringing autumn produce, a chance to find seasonal ingredients and ask what to cook with them. [Link](https://example.org/whatson/autumn-market)

## Book ahead

Electronic music, interactive light works and practical systems workshops are the longer-range picks to plan for.

**ACTION**
- Northern Lights Festival, 12–14 Feb 2027 — three days of electronic sets and artist-led sound workshops; join the presale list before sales open Friday 9 Oct at 10:00. [Link](https://example.org/festival/presale)
- Modern Light exhibition, until 14 Mar 2027 — interactive installations change as visitors move through them, letting you explore light as a material; weekend slots are selling, so book before month-end. [Link](https://example.org/exhibitions/modern-light)

**On the radar**
- Delta Systems Conference, 18 Mar 2027 — workshops on observability and failure recovery offer implementation ideas to bring back to a project; early-bird registration opens in November. [Link](https://example.org/conf/delta)

Sources: arXiv, Harbor Systems blog, GitHub Trending, Luma, Riverside Gallery agenda, festival and gallery sites.
