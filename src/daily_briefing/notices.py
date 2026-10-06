"""Markdown bodies for the reconnect, login-code and failure emails."""

from __future__ import annotations

DEVICE_URL = "https://auth.openai.com/codex/device"
NOTICE_ICONS: dict[str, str] = {"Reconnect": "🔑", "Login code": "🔑", "What happened": "⚠️"}


def reconnect_notice(workflow_url: str) -> str:
    """Email asking the user to press Run workflow whenever convenient.

    Args:
        workflow_url: Page with the Run workflow button.

    Returns:
        Briefing-style Markdown.
    """
    return (
        "# Daily briefing — reconnect needed\n"
        "**Action today:** Reconnect your ChatGPT login whenever convenient; "
        "it takes a minute.\n\n"
        "## Reconnect\n"
        "Your briefing could not log in to Codex, so today's briefing was "
        "skipped.\n\n"
        f"1. Open [the workflow page]({workflow_url}) and press **Run workflow**. "
        "Any time works; there is no deadline yet.\n"
        "2. Within a few minutes you get an email with a one-time code (it is also "
        "shown in the run log).\n"
        f"3. Open {DEVICE_URL}, sign in to ChatGPT and enter the code within "
        "15 minutes.\n\n"
        "The run then saves the new login and sends today's briefing.\n"
    )


def device_code_notice(url: str, code: str) -> str:
    """Email carrying the one-time device code.

    Args:
        url: Device login page.
        code: One-time code, e.g. "ABCD-12345".

    Returns:
        Briefing-style Markdown.
    """
    return f"""# Daily briefing — your login code
**Action today:** Enter code **{code}** at {url} within 15 minutes.

## Login code
1. Open {url} and sign in to ChatGPT.
2. Enter **{code}**.

Only do this if you just pressed Run workflow. If you did not, ignore this email.
"""


def failure_notice(reason: str, run_url: str) -> str:
    """Email reporting a failed run.

    Args:
        reason: Error text; only the last 40 lines are kept.
        run_url: Link to the run log, or "".

    Returns:
        Briefing-style Markdown.
    """
    tail = "\n".join(reason.splitlines()[-40:]).replace("```", "'''")
    link = f" See the [run log]({run_url})." if run_url else ""
    return (
        "# Daily briefing — run failed\n\n"
        "## What happened\n"
        f"Today's run failed.{link} It retries at the next scheduled attempt; "
        "to retry now, press **Run workflow**.\n\n"
        "```\n"
        f"{tail}\n"
        "```\n"
    )
