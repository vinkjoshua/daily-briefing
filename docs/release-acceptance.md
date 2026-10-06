# v1.1 release acceptance

Run this checklist before releasing `v1.1.0`, updating the action's `v1` tag, or
copying `template/` into the public starter repository. These are later release
owner actions; implementation has not published refs, repositories, emails or
releases. `template/` is the canonical set of prepared public-template updates.

Record the candidate commit, platform/architecture, Python/uv/Git versions, CI
links and each result. Leave unexecuted items marked **not run**. Never record
passwords, encryption keys or authentication tokens in the evidence.

## Pin the candidate

Use a full 40-character engine commit SHA already accessible on GitHub after an
approved candidate publication. An unpublished local SHA cannot resolve through
`uv` or Actions. Use the same SHA for both the CLI and action throughout these
checks; neither `@v1` nor the pending `@v1.1.0` tag proves candidate behavior.

```sh
daily_briefing_candidate_sha='<published full 40-character commit SHA>'
daily_briefing_candidate_source="git+https://github.com/vinkjoshua/daily-briefing@${daily_briefing_candidate_sha}"
uv tool run --from "$daily_briefing_candidate_source" daily-briefing --help
uv tool run --from "$daily_briefing_candidate_source" daily-briefing init candidate-briefing
```

For a disposable repository, decline **Publish these accepted files** at the
first review. In the prepared instance, edit:

- `.github/workflows/briefing.yml`: replace `vinkjoshua/daily-briefing@v1` with
  `vinkjoshua/daily-briefing@<the same full SHA>`.
- `briefing`: replace the `--from` URL's `@v1.1.0` with `@<the same full SHA>`.

Resume with the same candidate-pinned `uv tool run … init candidate-briefing`
command. Setup preserves these accepted files. Keep these overrides until all
acceptance checks finish. For source-only offline work use `uv run daily-briefing`;
that is useful development evidence, not a released-install or live-cloud check.

## CI and artifacts

- [ ] CI passes on `ubuntu-24.04` and `macos-15` with Python 3.11, 3.12, 3.13 and
  3.14; record all eight job results plus Ruff, pytest and actionlint v1.7.12.
- [ ] Each matrix job builds the wheel and sdist, rebuilds a wheel from the
  sdist, installs it outside the checkout, runs CLI help and validates the
  installed starter. No skipped Hatchling test substitutes for this smoke.
- [ ] The canonical source `template/` validates and its launcher works when
  called by absolute path from another directory containing spaces.

## WSL

- [ ] In a fresh WSL2 Ubuntu environment on the intended architecture, install
  Git/uv and use Python 3.11 or newer. Work under the Linux home filesystem.
  Confirm the candidate-pinned CLI help; this is not a native Windows test.
- [ ] Complete the private-repository flow below in WSL, including GitHub browser
  authentication and real SMTP. Confirm the chosen timezone and fallback/default
  prompts, then cancel after accepted personalization and resume it unchanged.
- [ ] Sign in to local Codex using the displayed login command; generate
  `./briefing try --section 10-research --open`. Confirm the preview opens (or
  document WSL browser integration limits and open `preview.html` manually).
- [ ] Call the launcher from a different directory with spaces, validate the
  instance, and publish accepted changes. Record architecture and outcomes;
  repeat on the other architecture if support evidence is required there.

## Throwaway private repository and real scheduled run

Use a unique repository owned by a personal test account, real SMTP app
credentials and a disposable profile. Allow actual email and Codex usage for
this check. Never repurpose an existing briefing repository.

- [ ] Guided setup sends the SMTP test email before repository creation. Confirm
  the message arrives, the recipient is right and the repo is **Private**.
- [ ] Confirm all three secret names (`SMTP_USER`, `SMTP_PASSWORD`, `BRIEFING_KEY`)
  are present before the first runnable workflow push. Inspect the committed
  files and local progress file: secrets are absent and progress is under `.git`.
- [ ] Confirm the workflow and launcher retain the full candidate SHA overrides,
  `main` is the default branch, the IANA schedule/action timezones agree, and the
  launcher is executable. Decline or accept the first launch deliberately.
- [ ] Accept the optional first launch, confirm its linked queued/in-progress
  status and complete the emailed cloud device-code login while the run waits.
  Receive a briefing and confirm encrypted login, archive and dedup state commit
  back. Local Codex login must remain separate from cloud login.
- [ ] Rerun candidate setup: accepted edits stay intact, secret names are retained
  and it does not launch a second first run. Test declined-launch setup in a
  second disposable instance if necessary; Actions must remain usable manually.
- [ ] After a cloud bot state update, edit an interest/section, generate a local
  preview and run `./briefing publish`. Review both outgoing changes and the
  second review after rebase; confirm bot state and accepted edits both survive,
  the origin is unchanged and preview/credentials remain unpublished.
- [ ] Run `./briefing publish --run` after a briefing has already been sent that
  day: confirm an ordinary dispatch and daily-guard skip rather than another
  email. Inspect Actions before retrying any uncertain dispatch or push.
- [ ] Exercise a conflicting bot/local edit in the disposable repo; confirm the
  rebase aborts and the reviewed local commit survives. Follow the printed
  recovery steps, preserving the original checkout. Never force-push.
- [ ] Exercise staged work and a forbidden outgoing path (even when later
  deleted); publication must refuse. Use the displayed separate-clean-clone
  recovery for history rejection, copying only allowed personalization.
- [ ] Arrange a future local-time schedule on the default branch for a day with
  no sent marker, retaining the same IANA timezone in both places. Publish the
  accepted workflow edit, then wait for **one real `schedule` event**. Record the
  scheduled and actual start times, successful email, archive/state commit, and
  a later retry's daily-guard skip. A manual dispatch is not scheduled evidence;
  account for approximate timing and GitHub delays.
- [ ] Confirm browser-only setup still works from the prepared source template
  with the candidate action override, manual secrets and **Run workflow**.

## Release owner follow-up

After acceptance and explicit release authorization, publish the immutable
`v1.1.0` engine tag, update `v1` to the reviewed engine commit, and copy the
canonical `template/` source files (including launcher, guidance and workflow)
to the public template through the normal reviewed process. Verify the released
`uv tool install 'git+https://github.com/vinkjoshua/daily-briefing@v1.1.0'`
command and source launcher resolve that tag. No PyPI publishing
pipeline or verified package namespace is assumed.

## Implementation-time evidence (2026-10-06)

Local automated checks use macOS and Python 3.13 with compatible cached
dependencies because shell DNS is unavailable. Python 3.11/3.12, Linux, WSL,
actionlint/Go/shellcheck, the Hatchling artifact build/install, real SMTP,
interactive GitHub/Codex authentication, remote publication and a scheduled cloud
run are **not run** here. CI and all live checklist boxes remain pending until
executed in the appropriate environment. Fake SMTP/GitHub/Codex plus a real local
bare Git remote verify integration, not provider behavior or live login.
