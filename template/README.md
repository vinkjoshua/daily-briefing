# My daily briefing

Every morning Codex researches what you care about and emails you a short, sourced briefing. It runs on **your own ChatGPT plan**, on GitHub Actions' free minutes. Your laptop can stay closed.

Powered by [vinkjoshua/daily-briefing](https://github.com/vinkjoshua/daily-briefing).

## Set up (about 10 minutes, browser only)

1. **Create your copy:** click **Use this template → Create a new repository** and choose **Private**. Private is required, because your encrypted ChatGPT login is stored in the repository.
2. **Allow device-code login in ChatGPT:** ChatGPT → Settings → Security → enable device code login for Codex.
3. **Create an email password.** For Gmail: turn on 2-Step Verification, then create an App Password at https://myaccount.google.com/apppasswords. For other providers, see "Other email providers" below.
4. **Add three secrets:** your repo → Settings → Secrets and variables → Actions → New repository secret:
   - `SMTP_USER`: your email address
   - `SMTP_PASSWORD`: the App Password
   - `BRIEFING_KEY`: a random string of 32+ characters (use a password generator; you never need to type it again)
5. **Connect ChatGPT:** Actions tab → **Daily briefing** → **Run workflow**. Within a few minutes you get an email with a code (also shown in the run log). Open https://auth.openai.com/codex/device, sign in and enter it within 15 minutes. Your first briefing follows.

From then on it runs every morning, three attempts at 41 past 4, 5 and 6 UTC. The first one that succeeds sends. The cron hours are UTC: 41 past 4, 5 and 6 UTC is about 06:40-08:40 in Amsterdam in summer. If you live elsewhere, change the hours in `.github/workflows/briefing.yml` to your own morning in UTC. The `timezone:` input only decides the briefing date.

## Make it yours
- `interests.md`: what you care about, your city, sources.
- `sections/`: one file per email section (title and icon at the top, instructions below). Add, delete or reorder freely; the file name sets the order.
- `state/watchlist.md`: mark a row `booked` or `skip` to stop reminders.
- `timezone:` in `.github/workflows/briefing.yml`: your IANA timezone.

## If it needs you
- **"Reconnect needed" email:** whenever convenient, press **Run workflow** and enter the emailed code. Nothing expires until you press the button.
- **"Run failed" email:** it retries at the next scheduled attempt. The email links to the log.

## Other email providers
Add `smtp-host:` and `smtp-port:` under `with:` in the workflow, e.g. `smtp.office365.com` / `587` or `smtp.fastmail.com` / `465`.

## Costs
- GitHub Free includes 2,000 Actions minutes a month for private repos; this uses roughly 450.
- Codex usage counts against your ChatGPT plan.
