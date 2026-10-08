"""Guided setup with fake network boundaries and real local Git repositories."""

import json
import os
import subprocess
from pathlib import Path

import pytest
import yaml

from daily_briefing import cli


class FakeGitHub:
    def __init__(self):
        self.repo = None
        self.secrets = {}
        self.events = []
        self.remote_sha = None
        self.fail_create = False
        self.fail_dispatch = False
        self.fail_push = False
        self.dispatched = False
        self.runs = [
            {
                "databaseId": 42,
                "url": "https://github.com/alice/daily/actions/runs/42",
                "status": "queued",
                "conclusion": "",
            }
        ]

    def run(self, binary, args, *, input_text=None, capture=True, check=True):
        from daily_briefing.github import CommandError

        self.events.append(tuple(args))
        code, output = 0, ""
        if args[:2] == ["auth", "status"]:
            pass
        elif args[:2] == ["api", "user"]:
            output = json.dumps({"login": "alice", "id": 123, "type": "User"})
        elif args[0] == "api" and args[1].startswith("repos/"):
            assert self.repo is None
            code, output = 1, "HTTP/2.0 404 Not Found\n"
        elif args[:2] == ["repo", "view"]:
            if self.repo:
                output = json.dumps(self.repo)
            else:
                code = 1
        elif args[:2] == ["repo", "create"]:
            assert self.repo is None
            assert "--private" in args
            self.repo = {
                "nameWithOwner": "alice/daily",
                "id": "R_123",
                "isPrivate": True,
                "owner": {"login": "alice", "id": "123"},
                "isEmpty": True,
            }
            if self.fail_create:
                raise CommandError("uncertain creation")
        elif args[:2] == ["secret", "list"]:
            output = json.dumps([{"name": name} for name in self.secrets])
        elif args[:2] == ["secret", "set"]:
            assert input_text is not None and input_text not in args
            self.secrets[args[2]] = input_text
        elif args[:2] == ["workflow", "run"]:
            self.dispatched = True
            if self.fail_dispatch:
                raise CommandError("uncertain dispatch")
        elif args[:2] == ["run", "list"]:
            output = json.dumps(self.runs if self.dispatched else [])
        else:
            raise AssertionError(args)
        result = subprocess.CompletedProcess(args, code, output, "")
        if code and check:
            raise CommandError("not found")
        return result


@pytest.fixture
def setup_env(tmp_path, monkeypatch):
    from daily_briefing import setup
    from daily_briefing.github import git as real_git
    from test_mailer import FakeSMTP

    fake = FakeGitHub()
    monkeypatch.setattr(setup, "ensure_tool", lambda name: Path("/fake/gh"))
    monkeypatch.setattr(setup, "run_gh", fake.run)
    monkeypatch.setattr(setup.shutil, "which", lambda name: "/usr/bin/" + name)
    monkeypatch.setattr(setup, "_default_timezone", lambda: "UTC")
    monkeypatch.setattr(setup.mailer.smtplib, "SMTP_SSL", FakeSMTP)
    monkeypatch.setattr(setup.mailer.smtplib, "SMTP", FakeSMTP)
    FakeSMTP.instances.clear()

    def git(root, *args, gh_bin=None, check=True):
        if args[0] == "push":
            assert set(fake.secrets) == {"SMTP_USER", "SMTP_PASSWORD", "BRIEFING_KEY"}
            fake.events.append(("push",))
            fake.remote_sha = real_git(root, "rev-parse", "HEAD").stdout.strip()
            fake.repo["isEmpty"] = False
            if fake.fail_push:
                from daily_briefing.github import CommandError

                raise CommandError("uncertain push")
            return subprocess.CompletedProcess(args, 0, "", "")
        if args[0] == "ls-remote":
            output = f"{fake.remote_sha}\trefs/heads/main\n" if fake.remote_sha else ""
            return subprocess.CompletedProcess(args, 0, output, "")
        return real_git(root, *args, check=check)

    monkeypatch.setattr(setup, "git", git)
    return setup, fake, tmp_path / "my briefing", FakeSMTP


def answers(monkeypatch, values, password="abcd efgh"):
    from daily_briefing import setup

    values = iter(values)
    monkeypatch.setattr("builtins.input", lambda prompt: next(values))
    monkeypatch.setattr(setup.getpass, "getpass", lambda prompt: password)


def initial(
    root,
    *,
    provider="gmail",
    host=None,
    city="Utrecht",
    timezone="Europe/Amsterdam",
    start="07:00",
    launch="n",
):
    values = ["y", "daily", str(root), provider]
    if host:
        values += [host, "465"]
    return values + [
        "a@example.com",
        "",
        city,
        "Databases $(touch /tmp/nope)",
        "Music: jazz # safely raw",
        "1,4",
        timezone,
        start,
        "y",
        launch,
    ]


def read_state(root):
    return json.loads((root / ".git/daily-briefing-init.json").read_text())


@pytest.mark.parametrize("timezone", ["", "UTC", "Etc/UTC"])
def test_utc_setup_emits_timezone_accepted_by_workflow_linter(setup_env, monkeypatch, timezone):
    setup, _, root, _ = setup_env
    answers(monkeypatch, [*initial(root, timezone=timezone)[:-2], "n"])
    assert setup.initialize(root) == 0
    workflow = yaml.safe_load((root / ".github/workflows/briefing.yml").read_text())
    assert workflow[True]["schedule"] == [{"cron": "0 7,8,9 * * *", "timezone": "Etc/UTC"}]
    assert workflow["jobs"]["briefing"]["steps"][1]["with"]["timezone"] == "Etc/UTC"


@pytest.mark.parametrize("resume", [False, True])
@pytest.mark.parametrize("recipient", ["", "reader@example.com"])
def test_publication_review_shows_accepted_recipient_and_sections(
    setup_env, monkeypatch, capsys, resume, recipient
):
    setup, fake, root, _ = setup_env
    values = initial(root)[:-2]
    values[5] = recipient
    if resume:
        answers(monkeypatch, [*values, "n"])
        assert setup.initialize(root) == 0
        capsys.readouterr()
        section = root / "sections/10-research.md"
        section.write_text(
            section.read_text().replace("title: Research", "title: Accepted research")
        )
        values = ["a@example.com", recipient]
    iterator = iter(values)

    def answer(prompt):
        if prompt.startswith("Publish these accepted files"):
            summary = capsys.readouterr().out.split(f"Publish {root}", 1)[1]
            assert "alice/daily" in summary
            assert f"Recipient: {recipient or 'a@example.com'}" in summary
            assert ("Accepted research" if resume else "Research") in summary
            assert "10-research.md" in summary
            assert "This week" in summary and "40-this-week.md" in summary
            assert "20-open-source.md" not in summary
            assert "abcd efgh" not in summary and "abcdefgh" not in summary
            return "n"
        return next(iterator)

    monkeypatch.setattr("builtins.input", answer)
    monkeypatch.setattr(setup.getpass, "getpass", lambda prompt: "abcd efgh")
    assert setup.initialize(root) == 0
    assert fake.repo is None and not fake.secrets
    assert "abcdefgh" not in (root / ".git/daily-briefing-init.json").read_text()


def test_cli_registers_init_with_default(monkeypatch):
    assert "init" in cli.COMMANDS


def test_full_setup_personalizes_and_secrets_precede_push(setup_env, monkeypatch):
    setup, fake, root, smtp = setup_env
    answers(monkeypatch, initial(root))
    assert setup.initialize(root) == 0
    assert sorted(path.name for path in (root / "sections").iterdir()) == [
        "10-research.md",
        "40-this-week.md",
    ]
    interests = (root / "interests.md").read_text()
    assert "Utrecht" in interests and "Databases $(touch /tmp/nope)" in interests
    assert "Music: jazz # safely raw" in interests
    assert "Anthropic" not in interests
    workflow = yaml.safe_load((root / ".github/workflows/briefing.yml").read_text())
    assert workflow[True]["schedule"] == [{"cron": "0 7,8,9 * * *", "timezone": "Europe/Amsterdam"}]
    action = workflow["jobs"]["briefing"]["steps"][1]["with"]
    assert action["timezone"] == "Europe/Amsterdam"
    assert action["smtp-host"] == "smtp.gmail.com" and action["smtp-port"] == "465"
    assert workflow["permissions"] == {"contents": "write"}
    assert workflow["concurrency"] == {"group": "daily-briefing", "cancel-in-progress": False}
    assert fake.secrets["SMTP_PASSWORD"] == "abcdefgh"
    assert len(fake.secrets["BRIEFING_KEY"]) >= 32
    assert smtp.instances[0].calls[0] == ("login", "a@example.com", "abcdefgh")
    assert read_state(root)["published"] is True
    tracked = subprocess.run(
        ["git", "-C", str(root), "ls-files"], text=True, capture_output=True, check=True
    ).stdout
    assert ".git/" not in tracked and "AGENTS.md" in tracked and "CLAUDE.md" in tracked
    for path in root.rglob("*"):
        if path.is_file() and ".git" not in path.parts:
            assert "abcdefgh" not in path.read_text()


def test_custom_password_and_yaml_literals_are_preserved(setup_env, monkeypatch):
    setup, fake, root, smtp = setup_env
    answers(
        monkeypatch,
        initial(root, provider="custom", host="smtp.example.com", start="23:30"),
        password=" leading middle trailing ",
    )
    assert setup.initialize(root) == 0
    assert fake.secrets["SMTP_PASSWORD"] == " leading middle trailing "
    assert smtp.instances[0].calls[0][-1] == " leading middle trailing "
    workflow = yaml.safe_load((root / ".github/workflows/briefing.yml").read_text())
    assert workflow[True]["schedule"] == [{"cron": "30 23 * * *", "timezone": "Europe/Amsterdam"}]


def test_nonempty_directory_is_rejected_without_mutation(setup_env, monkeypatch):
    setup, fake, root, _ = setup_env
    root.mkdir()
    (root / "keep.txt").write_text("mine")
    answers(monkeypatch, ["y", "daily", str(root)])
    assert setup.initialize(root) == 1
    assert sorted(p.name for p in root.iterdir()) == ["keep.txt"]
    assert not fake.secrets and fake.repo is None


def test_existing_repo_collision_is_never_adopted(setup_env, monkeypatch):
    setup, fake, root, _ = setup_env
    fake.repo = {
        "nameWithOwner": "alice/daily",
        "id": "R_999",
        "isPrivate": True,
        "owner": {"login": "alice"},
        "isEmpty": True,
    }
    answers(monkeypatch, initial(root))
    assert setup.initialize(root) == 1
    assert fake.secrets == {} and not read_state(root).get("create_intent")


def test_cancel_after_preparation_preserves_files_and_resume(setup_env, monkeypatch):
    setup, fake, root, _ = setup_env
    vals = initial(root)[:-2]
    iterator = iter(vals)
    monkeypatch.setattr(
        "builtins.input",
        lambda prompt: (
            next(iterator)
            if "Publish" not in prompt
            else (_ for _ in ()).throw(KeyboardInterrupt())
        ),
    )
    monkeypatch.setattr(setup.getpass, "getpass", lambda prompt: "abcd efgh")
    assert cli.main(["init", str(root)]) == 130
    before = (root / "interests.md").read_text()
    assert fake.repo is None
    (root / "interests.md").write_text(before + "\nAccepted local edit\n")
    answers(monkeypatch, ["a@example.com", "", "y", "n"])
    assert setup.initialize(root) == 0
    assert (root / "interests.md").read_text().endswith("Accepted local edit\n")


def test_completed_rerun_preserves_secrets_and_does_not_dispatch(setup_env, monkeypatch):
    setup, fake, root, _ = setup_env
    answers(monkeypatch, initial(root, launch="y"))
    assert setup.initialize(root) == 0
    secrets = fake.secrets.copy()
    fake.events.clear()
    answers(monkeypatch, [])
    assert setup.initialize(root) == 0
    assert fake.secrets == secrets
    assert not any(event[:2] in [("secret", "set"), ("workflow", "run")] for event in fake.events)


def test_ambiguous_create_requires_ownership_confirmation(setup_env, monkeypatch):
    setup, fake, root, _ = setup_env
    fake.fail_create = True
    answers(monkeypatch, initial(root))
    assert setup.initialize(root) == 1
    assert read_state(root)["create_intent"] is True and fake.secrets == {}
    answers(monkeypatch, ["n"])
    assert setup.initialize(root) == 1
    assert fake.secrets == {}
    answers(monkeypatch, ["y", "a@example.com", "", "y", "n"])
    assert setup.initialize(root) == 0
    assert sum(e[:2] == ("repo", "create") for e in fake.events) == 1


def test_ambiguous_push_inspects_remote_without_retry(setup_env, monkeypatch):
    setup, fake, root, _ = setup_env
    fake.fail_push = True
    answers(monkeypatch, initial(root))
    assert setup.initialize(root) == 1
    assert read_state(root)["push_intent"] is True
    answers(monkeypatch, ["n"])
    assert setup.initialize(root) == 0
    assert fake.events.count(("push",)) == 1


def test_ambiguous_dispatch_is_not_retried(setup_env, monkeypatch, capsys):
    setup, fake, root, _ = setup_env
    fake.fail_dispatch = True
    answers(monkeypatch, initial(root, launch="y"))
    assert setup.initialize(root) == 1
    assert "Actions" in capsys.readouterr().out
    assert read_state(root)["dispatch_intent"] is True
    answers(monkeypatch, [])
    assert setup.initialize(root) == 0
    assert sum(e[:2] == ("workflow", "run") for e in fake.events) == 1


def test_launch_shows_actual_queued_run_not_completion(setup_env, monkeypatch, capsys):
    setup, fake, root, _ = setup_env
    answers(monkeypatch, initial(root, launch="y"))
    assert setup.initialize(root) == 0
    output = capsys.readouterr().out
    assert "https://github.com/alice/daily/actions/runs/42" in output and "queued" in output
    assert "briefing sent" not in output.lower()


def test_invalid_inputs_reprompt(setup_env, monkeypatch):
    setup, _, root, _ = setup_env
    values = [
        "y",
        "bad/name",
        "daily",
        str(root),
        "invalid",
        "gmail",
        "no-at",
        "a@example.com",
        "",
        "Utrecht",
        "Databases",
        "Music",
        "",
        "9",
        "1,4",
        "No/Zone",
        "Europe/Amsterdam",
        "7am",
        "07:00",
        "y",
        "n",
    ]
    answers(monkeypatch, values)
    assert setup.initialize(root) == 0


def test_generated_launcher_uses_own_directory_from_any_cwd(setup_env, monkeypatch, tmp_path):
    setup, _, root, _ = setup_env
    answers(monkeypatch, initial(root))
    assert setup.initialize(root) == 0
    bindir = tmp_path / "bin"
    bindir.mkdir()
    uv = bindir / "uv"
    uv.write_text('#!/bin/sh\nprintf \'%s\\n\' "$PWD" "$@"\n')
    uv.chmod(0o755)
    monkeypatch.setenv("PATH", str(bindir) + ":/usr/bin:/bin")
    result = subprocess.run(
        [str(root / "briefing"), "validate"],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=True,
    )
    assert result.stdout.splitlines() == [
        str(root),
        "tool",
        "run",
        "--from",
        "git+https://github.com/vinkjoshua/daily-briefing@v1.1.0",
        "daily-briefing",
        "validate",
    ]


def test_raw_personalization_keeps_user_whitespace(setup_env, monkeypatch):
    setup, _, root, _ = setup_env
    values = initial(root)
    values[6:9] = ["  Utrecht  ", "  Databases  ", "  Jazz  "]
    answers(monkeypatch, values)
    assert setup.initialize(root) == 0
    interests = (root / "interests.md").read_text()
    assert "Home city:   Utrecht  \n" in interests
    assert "\n  Databases  \n" in interests and "\n  Jazz  \n" in interests


def test_cancel_mid_personalization_keeps_city_and_resumes(setup_env, monkeypatch):
    setup, fake, root, _ = setup_env
    values = iter(initial(root)[:7])

    def input_until_city(prompt):
        if "Professional and research" in prompt:
            raise EOFError
        return next(values)

    monkeypatch.setattr("builtins.input", input_until_city)
    monkeypatch.setattr(setup.getpass, "getpass", lambda prompt: "abcd efgh")
    assert cli.main(["init", str(root)]) == 130
    assert "Home city: Utrecht" in (root / "interests.md").read_text()
    assert fake.repo is None
    answers(monkeypatch, ["a@example.com", "", "Databases", "Jazz", "1", "UTC", "07:00", "y", "n"])
    assert setup.initialize(root) == 0
    assert (root / "interests.md").read_text().count("Home city:") == 1


def test_nonempty_created_remote_is_rejected_before_secret_upload(setup_env, monkeypatch):
    setup, fake, root, _ = setup_env
    fake.fail_create = True
    answers(monkeypatch, initial(root))
    assert setup.initialize(root) == 1
    state = read_state(root)
    state["repo_id"] = fake.repo["id"]
    (root / ".git/daily-briefing-init.json").write_text(json.dumps(state))
    fake.repo["isEmpty"] = False
    answers(monkeypatch, ["a@example.com", "", "y", "n"])
    assert setup.initialize(root) == 1
    assert not fake.secrets


def test_retry_after_local_commit_interruption_reuses_origin_and_commit(setup_env, monkeypatch):
    setup, fake, root, _ = setup_env
    git = setup.git

    def interrupt_after_commit(path, *args, **kwargs):
        result = git(path, *args, **kwargs)
        if "commit" in args:
            raise KeyboardInterrupt
        return result

    monkeypatch.setattr(setup, "git", interrupt_after_commit)
    answers(monkeypatch, initial(root))
    assert cli.main(["init", str(root)]) == 130
    assert fake.secrets and (root / "interests.md").is_file()
    monkeypatch.setattr(setup, "git", git)
    answers(monkeypatch, ["y", "n"])
    assert setup.initialize(root) == 0
    assert fake.events.count(("push",)) == 1


def test_published_missing_key_is_not_regenerated(setup_env, monkeypatch):
    setup, fake, root, _ = setup_env
    answers(monkeypatch, initial(root))
    assert setup.initialize(root) == 0
    del fake.secrets["BRIEFING_KEY"]
    fake.events.clear()
    answers(monkeypatch, [])
    assert setup.initialize(root) == 1
    assert not any(event[:2] == ("secret", "set") for event in fake.events)


def test_unconfirmed_repository_id_change_stops_resume(setup_env, monkeypatch):
    setup, fake, root, _ = setup_env
    answers(monkeypatch, initial(root))
    assert setup.initialize(root) == 0
    fake.repo["id"] = "R_other"
    fake.events.clear()
    answers(monkeypatch, [])
    assert setup.initialize(root) == 1
    assert not any(event[:2] == ("secret", "set") for event in fake.events)


def test_uncertain_push_to_empty_remote_does_not_retry(setup_env, monkeypatch):
    setup, fake, root, _ = setup_env
    fake.fail_push = True
    answers(monkeypatch, initial(root))
    assert setup.initialize(root) == 1
    fake.remote_sha = None
    fake.repo["isEmpty"] = True
    answers(monkeypatch, [])
    assert setup.initialize(root) == 1
    assert fake.events.count(("push",)) == 1


def test_symlink_directory_is_rejected(setup_env, monkeypatch, tmp_path):
    setup, fake, root, _ = setup_env
    target = tmp_path / "target"
    target.mkdir()
    root.symlink_to(target, target_is_directory=True)
    answers(monkeypatch, [])
    assert setup.initialize(root) == 1
    assert not list(target.iterdir()) and not fake.events


@pytest.mark.parametrize(
    "provider,host,port",
    [("icloud", "smtp.mail.me.com", 587), ("fastmail", "smtp.fastmail.com", 465)],
)
def test_named_providers_preserve_password_spaces(setup_env, monkeypatch, provider, host, port):
    setup, fake, root, smtp = setup_env
    answers(monkeypatch, initial(root, provider=provider), password=" a b ")
    assert setup.initialize(root) == 0
    assert fake.secrets["SMTP_PASSWORD"] == " a b "
    assert (smtp.instances[0].host, smtp.instances[0].port) == (host, port)
    assert ("login", "a@example.com", " a b ") in smtp.instances[0].calls


def test_missing_key_before_publication_can_be_regenerated(setup_env, monkeypatch):
    setup, fake, root, _ = setup_env
    git = setup.git

    def interrupt_before_commit(path, *args, **kwargs):
        if "commit" in args:
            raise KeyboardInterrupt
        return git(path, *args, **kwargs)

    monkeypatch.setattr(setup, "git", interrupt_before_commit)
    answers(monkeypatch, initial(root))
    assert cli.main(["init", str(root)]) == 130
    previous = fake.secrets.pop("BRIEFING_KEY")
    smtp = fake.secrets.copy()
    monkeypatch.setattr(setup, "git", git)
    answers(monkeypatch, ["y", "n"])
    assert setup.initialize(root) == 0
    assert fake.secrets["BRIEFING_KEY"] != previous
    assert {name: fake.secrets[name] for name in smtp} == smtp


def test_smtp_failure_reprompts_before_remote_creation(setup_env, monkeypatch):
    import smtplib

    setup, fake, root, _ = setup_env
    send = setup.mailer.send
    count = 0

    def fail_first(message, settings):
        nonlocal count
        count += 1
        assert fake.repo is None
        if count == 1:
            raise smtplib.SMTPAuthenticationError(535, b"bad credentials")
        return send(message, settings)

    monkeypatch.setattr(setup.mailer, "send", fail_first)
    values = initial(root)
    values[6:6] = ["a@example.com", ""]
    answers(monkeypatch, values)
    assert setup.initialize(root) == 0
    assert count == 2


def test_network_failure_is_not_treated_as_available_repo(setup_env, monkeypatch):
    setup, fake, root, _ = setup_env
    run_gh = setup.run_gh

    def unavailable(binary, args, **kwargs):
        if args[0] == "api" and args[1].startswith("repos/"):
            return subprocess.CompletedProcess(args, 1, "HTTP/2.0 503 Service Unavailable", "")
        return run_gh(binary, args, **kwargs)

    monkeypatch.setattr(setup, "run_gh", unavailable)
    answers(monkeypatch, initial(root))
    assert setup.initialize(root) == 1
    assert fake.repo is None and not read_state(root).get("create_intent")


def test_missing_git_or_uv_stops_before_github(setup_env, monkeypatch):
    setup, fake, root, _ = setup_env
    monkeypatch.setattr(setup.shutil, "which", lambda name: None)
    answers(monkeypatch, [])
    assert setup.initialize(root) == 1
    assert fake.events == [] and not root.exists()


def test_cli_init_defaults_to_my_briefing(monkeypatch):
    from daily_briefing import setup

    paths = []
    monkeypatch.setattr(setup, "initialize", lambda directory: paths.append(directory) or 0)
    assert cli.main(["init"]) == 0
    assert paths == [Path("my-briefing")]


def test_partial_smtp_upload_resumes_with_consistent_tested_pair(setup_env, monkeypatch):
    from daily_briefing.github import CommandError

    setup, fake, root, _ = setup_env
    run_gh = setup.run_gh

    def fail_user_upload(binary, args, **kwargs):
        if args[:3] == ["secret", "set", "SMTP_USER"]:
            raise CommandError("uncertain secret upload")
        return run_gh(binary, args, **kwargs)

    monkeypatch.setattr(setup, "run_gh", fail_user_upload)
    answers(monkeypatch, initial(root), password="first password")
    assert setup.initialize(root) == 1
    assert fake.secrets["SMTP_PASSWORD"] == "firstpassword"
    key = fake.secrets["BRIEFING_KEY"]
    monkeypatch.setattr(setup, "run_gh", run_gh)
    answers(monkeypatch, ["a@example.com", "", "y", "n"], password="second password")
    assert setup.initialize(root) == 0
    assert fake.secrets["SMTP_PASSWORD"] == "secondpassword"
    assert fake.secrets["BRIEFING_KEY"] == key


def test_uncertain_push_checks_expected_repo_even_if_origin_changed(setup_env, monkeypatch):
    setup, fake, root, _ = setup_env
    fake.fail_push = True
    answers(monkeypatch, initial(root))
    assert setup.initialize(root) == 1
    git = setup.git
    git(root, "remote", "set-url", "origin", "https://github.com/alice/unrelated.git")

    def different_origin(path, *args, **kwargs):
        if args[:2] == ("ls-remote", "origin"):
            return subprocess.CompletedProcess(args, 0, "other-sha\trefs/heads/main\n", "")
        return git(path, *args, **kwargs)

    monkeypatch.setattr(setup, "git", different_origin)
    answers(monkeypatch, ["n"])
    assert setup.initialize(root) == 0
    assert fake.events.count(("push",)) == 1


def test_fresh_auth_requests_workflow_scope_for_initial_workflow_push(setup_env, monkeypatch):
    setup, fake, root, _ = setup_env
    run_gh = setup.run_gh
    logins = []

    def unauthenticated(binary, args, **kwargs):
        if args[:2] == ["auth", "status"]:
            return subprocess.CompletedProcess(args, 1, "", "")
        if args[:2] == ["auth", "login"]:
            logins.append(args)
            return subprocess.CompletedProcess(args, 0, "", "")
        return run_gh(binary, args, **kwargs)

    monkeypatch.setattr(setup, "run_gh", unauthenticated)
    answers(monkeypatch, initial(root))
    assert setup.initialize(root) == 0
    assert "--scopes" in logins[0] and logins[0][logins[0].index("--scopes") + 1] == "workflow"
    assert "--web" in logins[0] and "https" in logins[0]


def prepare_without_publication(setup, root, monkeypatch):
    answers(monkeypatch, initial(root)[:-2] + ["n"])
    assert setup.initialize(root) == 0


def test_resumed_init_rejects_selected_fifo_before_summary_read(setup_env, monkeypatch, capsys):
    setup, fake, root, _ = setup_env
    prepare_without_publication(setup, root, monkeypatch)
    selected = root / "sections/10-research.md"
    selected.unlink()
    os.mkfifo(selected)
    accepted = (root / "interests.md").read_bytes()
    read_text = Path.read_text

    def reject_fifo_read(path, *args, **kwargs):
        if path == selected:
            pytest.fail("Opened nonregular selected section before validation")
        return read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", reject_fifo_read)
    answers(monkeypatch, ["a@example.com", "", "n"])
    assert setup.initialize(root) == 1
    assert "regular files" in capsys.readouterr().out
    assert (root / "interests.md").read_bytes() == accepted
    assert not selected.is_file() and selected.exists()
    assert fake.repo is None and not fake.secrets and ("push",) not in fake.events


def commit_fixture(setup, root, message):
    setup.git(
        root,
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=fixture@example.com",
        "commit",
        "-m",
        message,
    )


def test_resumed_init_rejects_staged_extra_without_changing_index(setup_env, monkeypatch):
    setup, fake, root, _ = setup_env
    prepare_without_publication(setup, root, monkeypatch)
    private = root / "auth.json"
    private.write_text('{"refresh_token": "private-fixture"}\n')
    setup.git(root, "add", "--", "auth.json")
    index = (root / ".git/index").read_bytes()
    answers(monkeypatch, ["a@example.com", "", "y", "n"])
    assert setup.initialize(root) == 1
    assert (root / ".git/index").read_bytes() == index
    assert private.read_text() == '{"refresh_token": "private-fixture"}\n'
    assert fake.repo is None and not fake.secrets and ("push",) not in fake.events


def test_resumed_init_rejects_secret_bearing_deleted_ancestor(setup_env, monkeypatch):
    setup, fake, root, _ = setup_env
    prepare_without_publication(setup, root, monkeypatch)
    private = root / "auth.json"
    private.write_text('{"refresh_token": "private-fixture"}\n')
    setup.git(root, "add", "--", "auth.json")
    commit_fixture(setup, root, "Private local scratch")
    setup.git(root, "rm", "--", "auth.json")
    commit_fixture(setup, root, "Remove local scratch")
    index = (root / ".git/index").read_bytes()
    head = setup.git(root, "rev-parse", "HEAD").stdout
    answers(monkeypatch, ["a@example.com", "", "y", "n"])
    assert setup.initialize(root) == 1
    assert (root / ".git/index").read_bytes() == index
    assert setup.git(root, "rev-parse", "HEAD").stdout == head
    assert fake.repo is None and not fake.secrets and ("push",) not in fake.events


def test_resumed_init_rejects_symlink_in_deleted_ancestor(setup_env, monkeypatch):
    setup, fake, root, _ = setup_env
    prepare_without_publication(setup, root, monkeypatch)
    interests = root / "interests.md"
    accepted = interests.read_text()
    interests.unlink()
    interests.symlink_to("../outside-private-data")
    setup.git(root, "add", "--", "interests.md")
    commit_fixture(setup, root, "Local symlink")
    interests.unlink()
    interests.write_text(accepted)
    setup.git(root, "add", "--", "interests.md")
    commit_fixture(setup, root, "Restore regular interests")
    index = (root / ".git/index").read_bytes()
    answers(monkeypatch, ["a@example.com", "", "y", "n"])
    assert setup.initialize(root) == 1
    assert interests.read_text() == accepted
    assert (root / ".git/index").read_bytes() == index
    assert fake.repo is None and ("push",) not in fake.events


@pytest.mark.parametrize("relative", ["state/auth.json", "sections/credentials.md"])
def test_initial_staging_leaves_unrelated_nested_files_untracked(setup_env, monkeypatch, relative):
    setup, fake, root, _ = setup_env
    prepare_without_publication(setup, root, monkeypatch)
    private = root / relative
    private.write_text("private local data\n")
    answers(monkeypatch, ["a@example.com", "", "y", "n"])
    assert setup.initialize(root) == 0
    files = setup.git(root, "ls-tree", "-r", "--name-only", "HEAD").stdout.splitlines()
    assert relative not in files
    assert private.read_text() == "private local data\n"
    assert fake.events.count(("push",)) == 1
