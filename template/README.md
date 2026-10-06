# My daily briefing

Every morning Codex researches what you care about and emails you a short, sourced briefing. It runs on **your own ChatGPT plan**, on GitHub Actions' free minutes. Your laptop can stay closed.

Powered by [vinkjoshua/daily-briefing](https://github.com/vinkjoshua/daily-briefing).

## Guided setup

Install Git and [uv](https://docs.astral.sh/uv/getting-started/installation/), then run:

```sh
uv tool run --from daily-briefing==1.1.0 daily-briefing init my-briefing
```

Use macOS, Linux or WSL on x86-64 or ARM64. Setup downloads the pinned GitHub CLI
if needed, confirms your personal GitHub account, tests your email settings,
collects your interests and selected sections, then prepares the local files.
Review the publication summary before it creates your empty Private repository,
uploads the three secrets and pushes the runnable workflow.

Gmail requires an App Password; iCloud requires an app-specific password and
Fastmail requires an app password with mail access. Custom providers use the
host and port you enter. Password spaces are removed only for Gmail.
The test email is sent before repository creation. SMTP passwords and the
generated encryption key are never saved in local setup files.

If you cancel, rerun `daily-briefing init` with the same directory. Accepted
personalization is preserved, and identity/progress are stored only under `.git`.
If a creation, push or launch outcome is uncertain, inspect the linked GitHub
repository or Actions page first. Setup never blindly retries those operations,
and an uncertain creation requires your explicit ownership confirmation.
Preview before publishing:

```bash
./briefing try --open
./briefing try --section 10-research
```

Use the exact section filename stem for `--section`. The command reuses your
local Codex browser login (`CODEX_HOME` or `~/.codex`) and the literal timezone,
model and reasoning effort in your workflow. Run the displayed Codex login command locally if asked.
It writes `preview.html` atomically; your interests, sections, state, archives and
Git repository are unchanged. Your local login may refresh normally. Generation
ignores user config, rules and agent instructions. Symlinked inputs/output and
workflow expressions for preview settings are refused.

If an existing GitHub login cannot push workflow files, grant the workflow scope
with `gh auth refresh --hostname github.com --scopes workflow`, then inspect the
remote before pushing accepted files manually and resuming setup.
Completed setup never changes secrets or dispatches another cloud run.
Declining the first launch leaves **Run workflow** available whenever you are ready.

## Set up (about 10 minutes, browser only)

1. **Create your copy:** click **Use this template → Create a new repository** and choose **Private**. Private is required, because your encrypted ChatGPT login is stored in the repository.
2. **Allow device-code login in ChatGPT:** ChatGPT → Settings → Security → enable device code login for Codex.
3. **Create an email password.** For Gmail: turn on 2-Step Verification, then create an App Password at https://myaccount.google.com/apppasswords. For other providers, see "Other email providers" below.
4. **Add three secrets:** your repo → Settings → Secrets and variables → Actions → New repository secret:
   - `SMTP_USER`: your email address
   - `SMTP_PASSWORD`: the App Password
   - `BRIEFING_KEY`: a random string of 32+ characters (use a password generator; you never need to type it again)
5. **Connect ChatGPT:** Actions tab → **Daily briefing** → **Run workflow**. Within a few minutes you get an email with a code (also shown in the run log). Open https://auth.openai.com/codex/device, sign in and enter it within 15 minutes. Your first briefing follows.

From then on the browser starter runs at 07:00, 08:00 and 09:00 UTC. Guided setup uses your chosen local start time and up to two same-day hourly retries. The first success sends. In `.github/workflows/briefing.yml`, keep the schedule's IANA `timezone:` and the action's `timezone:` input identical when changing your schedule.

## Make it yours
- `interests.md`: what you care about, your city, sources.
- `sections/`: one file per email section (title and icon at the top, instructions below). Add, delete or reorder freely; the file name sets the order.
- `state/watchlist.md`: mark a row `booked` or `skip` to stop reminders.
- `timezone:` in `.github/workflows/briefing.yml`: your IANA timezone.

## Tune with a coding assistant

`AGENTS.md` and `CLAUDE.md` describe the tuning loop. Edit one interest or section
at a time, run `./briefing validate --dir .`, preview a briefing, then publish your
accepted changes. The `briefing` launcher works from any directory, including
paths with spaces, and runs the pinned daily-briefing 1.1.0 package.

Use `./briefing publish` to review and publish accepted changes, or
`./briefing publish --run` to request an ordinary daily run afterward. The daily
guard still prevents a second email for a day already sent. Publication verifies
the private repository and authenticated owner, validates the local inputs, and
shows every outgoing commit plus accepted file diffs before asking for confirmation.
Staged work and unrelated dirty files require manual attention; cancellation
preserves your edits. Previews, archives and credentials are excluded, including
forbidden files added and deleted in outgoing history. Keep credentials out of
allowed files too.

Bot updates are fetched and rebased. A conflict aborts the rebase and retains your
local commit with recovery instructions. If a push fails, inspect the remote and
retry `./briefing publish`; never force-push. If dispatch is uncertain, inspect
Actions before requesting another run.

For rejected outgoing merges or forbidden history, keep this checkout and use
the exact GitHub CLI `repo clone` command displayed in the error to make a separate
clean clone of your private repository. Its CLI path works even without `gh` on
PATH. Copy only accepted allowlisted personalization; never copy the old `.git`,
history or credentials. In the clean clone, run `./briefing validate --dir .` and
`./briefing publish`. Publication never rewrites the original history automatically.

## If it needs you
- **"Reconnect needed" email:** whenever convenient, press **Run workflow** and enter the emailed code. Nothing expires until you press the button.
- **"Run failed" email:** it retries at the next scheduled attempt. The email links to the log.

## Other email providers
Add `smtp-host:` and `smtp-port:` under `with:` in the workflow, e.g. `smtp.office365.com` / `587` or `smtp.fastmail.com` / `465`.

## Costs
- GitHub Free includes 2,000 Actions minutes a month for private repos; this uses roughly 450.
- Codex usage counts against your ChatGPT plan.
