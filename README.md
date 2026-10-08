# daily-briefing

A GitHub Action that has Codex research your interests every morning and email you a short, sourced briefing. It uses your own ChatGPT account and GitHub Actions allowance.

![Example email](docs/screenshot.png)

The [sample briefing](examples/sample-briefing.md) is illustrative: its organisations,
projects, events and program details are fictional, with example.org links.

## How it works

1. **Schedule.** The workflow runs at your chosen local time, with up to two same-day hourly retries. The browser starter defaults to 07:00, 08:00 and 09:00 UTC.
2. **Guard.** If today's briefing was already sent, the run stops. The first attempt that succeeds sends; the others skip.
3. **Codex with live web search.** Codex reads your `interests.md` and one file per section, searches the web and writes the briefing as Markdown.
4. **Burgundy and ivory HTML email.** The engine renders the Markdown as an HTML email and sends it over SMTP.
5. **State and login committed back.** Dedup state, the briefing archive and your encrypted Codex login are committed to your repository.

## Quick start

Use macOS, Linux or WSL on x86-64 or ARM64. Install [Git](https://git-scm.com/downloads)
and [uv](https://docs.astral.sh/uv/getting-started/installation/), with Python 3.11
or newer available (uv can install Python). Internet access, a personal GitHub
account, a Codex-enabled ChatGPT account and SMTP access are required. Setup
downloads GitHub CLI 2.102.0 when needed; local previews download Codex 0.160.0.
Native Windows shells are not supported; use WSL.

Install the released CLI from the engine's Git tag, then start guided setup:

```sh
uv tool install 'git+https://github.com/vinkjoshua/daily-briefing@v1.1.0'
daily-briefing init my-briefing
```

Setup confirms your personal GitHub account, tests email before creating a private
repository, collects interests and sections, and installs secrets before publishing
the workflow. Review its summary, then optionally launch your first cloud run.
If the installed command is not on PATH, run `uv tool update-shell` and reopen your
shell. The instance's `./briefing` launcher uses the same `v1.1.0` Git source;
the cloud action remains `vinkjoshua/daily-briefing@v1`.
Rerun `daily-briefing init my-briefing` after cancelling to preserve accepted files.

Guided setup defaults to `my-briefing`, Gmail SMTP on port 465, the sender as
recipient, a detected IANA timezone (UTC if unavailable), and a 07:00 start.
Choose one or more of the five starter sections. The model defaults to Codex's
default and reasoning effort to `high`. Retries run hourly up to twice, ending
before local midnight. GitHub schedules run approximately at the requested time,
can be delayed or skipped under load, and only run on the default branch; keep
the schedule and action timezone values identical.
[GitHub schedule reference](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).

For email, use a provider app password rather than your normal account password:
[Gmail app passwords](https://support.google.com/accounts/answer/185833) require
2-Step Verification and may be unavailable for some accounts;
[Apple app-specific passwords](https://support.apple.com/en-gb/102654) require
two-factor authentication. Fastmail needs an app password with mail access and a
plan supporting SMTP; see [Fastmail setup](https://www.fastmail.help/hc/en-us/articles/360058752834-Set-up-Fastmail-on-your-device)
and [server settings](https://www.fastmail.help/hc/en-us/articles/1500000278342-Server-names-and-ports).
Custom SMTP providers must support implicit TLS on 465 or STARTTLS on another
port (usually 587). Setup sends a test email before creating the repository;
passwords and the generated encryption key stay out of local progress files.

From your instance directory, generate a local preview:

```bash
./briefing try --open
./briefing try --section 10-research
```

`try` uses the timezone, model and reasoning effort written literally in
`.github/workflows/briefing.yml`. It reuses your local Codex browser login
(`CODEX_HOME`, or `~/.codex`) and its file, keyring or auto credential store.
If login is needed, run the displayed Codex login command locally and try again. No cloud login or
SMTP secrets are needed for a preview. This local login is separate from the
encrypted cloud login: connecting locally does not connect Actions, and connecting
Actions does not sign in your laptop. The first cloud run may email a device code;
complete that login while the run is waiting.

Generation happens in a temporary directory containing your interests, selected
sections and state. Only `preview.html` is written back; dedup state, archives and
Git files remain intact. Existing Codex credentials may refresh normally. User
config, rules and agent instructions are ignored during generation. Workflow
expressions for preview settings and symlinked inputs/output are refused.
The existing `daily-briefing preview MARKDOWN` command still renders a saved draft.
The generated repository's `AGENTS.md` and `CLAUDE.md` explain the tuning loop.

Publish accepted edits from your instance directory:

```sh
./briefing publish
./briefing publish --run
```

Publication checks your private GitHub repository and account, validates the
profile, sections and literal workflow settings, and shows every outgoing commit
plus allowed working changes for confirmation. It publishes interests, section
and state Markdown, the workflow, launcher, guidance and ignore files. Previews,
archives, encrypted login files and credentials are excluded, including forbidden
paths added in an earlier outgoing commit and later deleted. Never put credentials
inside otherwise allowed files. Staged work and unrelated dirty files stop
publication with guidance; cancellation preserves your accepted edits.

Bot updates are fetched and rebased using ordinary Git. If conflicts occur, the
rebase is aborted and your local commit is retained; follow the displayed recovery
steps and review again. A failed push retains your commit: inspect the remote,
then retry `./briefing publish`. The command never force-pushes. `--run` requests
an ordinary daily run after publication succeeds; it respects the already-sent
guard. If dispatch is uncertain, inspect Actions before requesting another run.

If outgoing merges or forbidden files in history block publication, keep the
original checkout. Use the exact GitHub CLI `repo clone` command shown by the
error to create a separate clean clone of your private repository; the displayed
CLI path also works when `gh` is not on PATH. Copy only accepted allowlisted
personalization into that clone, never the old `.git`, history or credentials.
From the clean clone, run `./briefing validate --dir .` and `./briefing publish`.
Publication does not rewrite the original history automatically.

For browser-only setup:

Use the starter template: [vinkjoshua/daily-briefing-template](https://github.com/vinkjoshua/daily-briefing-template).

1. Click **Use this template** and create the repository as **Private**.
2. Add three secrets: `SMTP_USER`, `SMTP_PASSWORD` and `BRIEFING_KEY`.
3. Open the Actions tab and press **Run workflow**. You get an email with a login code.

The template README has the full walkthrough. The template's workflow calls this action as `vinkjoshua/daily-briefing@v1`:

```yaml
- uses: vinkjoshua/daily-briefing@v1
  with:
    smtp-user: ${{ secrets.SMTP_USER }}
    smtp-password: ${{ secrets.SMTP_PASSWORD }}
    auth-key: ${{ secrets.BRIEFING_KEY }}
```

## Self-repairing login

Codex needs a ChatGPT login, and logins expire. When the saved login stops working:

1. The scheduled run emails "reconnect needed". It does not fail the schedule.
2. Press **Run workflow** whenever it suits you. There is no deadline until you do.
3. The run emails a device code and prints it in the log. The code is valid for 15 minutes.
4. Enter the code at the OpenAI device page. The run saves the new login, encrypted, and sends your briefing.

## Inputs

| Input | Default | Description |
| --- | --- | --- |
| `smtp-user` | required | SMTP login, sender and default recipient. |
| `smtp-password` | required | SMTP password. For Gmail, an App Password. |
| `auth-key` | required | Random string of 32+ characters that encrypts the saved Codex login. |
| `timezone` | `Europe/Amsterdam` | IANA timezone that defines "today". |
| `smtp-host` | `smtp.gmail.com` | SMTP host. |
| `smtp-port` | `465` | `465` for implicit TLS, `587` for STARTTLS. |
| `mail-to` | empty (uses `smtp-user`) | Recipient. |
| `model` | empty (Codex default) | Optional Codex model override. |
| `reasoning-effort` | `high` | Codex reasoning effort. |
| `codex-version` | `0.160.0` | Codex CLI version to install. |
| `force` | `false` | Send even if today's briefing was already sent. |
| `github-token` | `${{ github.token }}` | Token used to commit state back to the repository. |

The template workflow uses `actions/checkout@v7`; the action itself uses `actions/setup-node@v7` and `astral-sh/setup-uv@v10.2.0`. Codex CLI 0.160.0 is pinned.

## Sections

Each section is one Markdown file in `sections/`. The file name sets the order. Front matter holds the title and optional icon metadata; icons are accepted for compatibility and omitted from the email. The body is the instruction Codex follows for that section.

```markdown
---
title: Research
icon: 🧠
---
Max 3 items. Papers from the last 7 days in the research areas in `interests.md`.
Per item: title, link, how the method works, limitations, one experiment I could try.
```

The starter template ships five sections: Research, Open-source radar, Professional events & talks, This week and Book ahead. Add, remove or reorder files to change the email.

## Security model

- **Private repositories only.** The engine refuses to run when the event says the repository is public. Your encrypted login lives in the repository.
- **Encrypted login.** The Codex login is encrypted with `BRIEFING_KEY` before it is committed. Without the key it is unreadable.
- **Codex gets no secrets.** Its environment is an allowlist (`PATH`, `HOME`, `LANG`, `LC_ALL`, `TZ`, `TMPDIR`, `USER`, plus `CODEX_HOME`). Its shell has no network.
- **Narrow commits.** The engine commits only `state/`, `briefings/` and `.briefing/`.

## Costs

Codex generation and previews count against your account's usage limits. GitHub
Actions runs consume your account's allowance; runtime, retries, runner platform
and plan affect the total. SMTP access may require a paid email plan. Check your
providers' current plans and usage pages; this project does not promise a fixed
monthly cost or free service.

## Available commands

`init`, `try`, `publish`, `validate` and saved-Markdown `preview` are available.
`guard`, `run` and `persist` remain the cloud engine commands. There is no local
`status`, `doctor`, `reset`, `upgrade`, `force` or cloud credential migration
command in this release. Use Actions and the documented manual recovery steps;
the browser workflow's explicit `force` input is still available.

## Development

```bash
uv sync
uv run pytest
uv run ruff check
uv run ruff format --check
uv build
uv run daily-briefing preview examples/sample-briefing.md --sections template/sections
```

CI runs pytest and Ruff on Linux/macOS with Python 3.11–3.14, builds wheel and
sdist, rebuilds the sdist, and checks an isolated installed CLI and starter.
For candidate Git refs, WSL and real private-repository acceptance (including a
scheduled run), follow [the release checklist](docs/release-acceptance.md).

## Licence

MIT.
