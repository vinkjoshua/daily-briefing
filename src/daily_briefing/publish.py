"""Review and publish an existing private personal briefing with ordinary Git."""

from __future__ import annotations

import json
import re
from pathlib import Path, PurePosixPath

from daily_briefing import bootstrap
from daily_briefing.github import CommandError, git, run_gh
from daily_briefing.local import LocalError, _check_path, workflow_settings
from daily_briefing.sections import SectionError, load_sections


class PublishError(Exception):
    """Publication cannot safely proceed without the user's intervention."""


def _git(root: Path, *args: str, **kwargs):
    # Replacement refs must never hide outgoing credential-bearing history.
    return git(root, "--no-replace-objects", *args, **kwargs)


def _allowed(name: str) -> bool:
    path = PurePosixPath(name)
    return name in {
        "interests.md",
        ".github/workflows/briefing.yml",
        "briefing",
        "README.md",
        "AGENTS.md",
        "CLAUDE.md",
        ".gitignore",
    } or (len(path.parts) == 2 and path.parts[0] in {"sections", "state"} and path.suffix == ".md")


def _validate(root: Path) -> None:
    _check_path(root, root, directory=True)
    _check_path(root, root / "interests.md")
    _check_path(root, root / "state", directory=True)
    _check_path(root, root / "sections", directory=True)
    for path in (root / "sections").glob("*.md"):
        _check_path(root, path)
    if not (root / "interests.md").read_text(encoding="utf-8").strip():
        raise PublishError("interests.md is empty. Add your profile before publishing.")
    load_sections(root / "sections")
    workflow_settings(root)


def _repository(root: Path, gh: Path) -> tuple[str, str, dict]:
    origin = _git(root, "config", "--get", "remote.origin.url").stdout.strip()
    match = re.fullmatch(
        r"(?:https://github\.com/|git@github\.com:|ssh://git@github\.com/)"
        r"([A-Za-z0-9-]+/[A-Za-z0-9_.-]+?)(?:\.git)?/?",
        origin,
    )
    if not match:
        raise PublishError("Set origin to your personal GitHub repository (HTTPS or SSH).")
    name = match[1]
    account = json.loads(run_gh(gh, ["api", "user"]).stdout)
    repo = json.loads(
        run_gh(
            gh,
            [
                "repo",
                "view",
                name,
                "--json",
                "nameWithOwner,isPrivate,owner,defaultBranchRef",
            ],
        ).stdout
    )
    owner = name.split("/", 1)[0]
    if (
        account.get("login") != owner
        or repo.get("nameWithOwner") != name
        or repo.get("isPrivate") is not True
        or repo.get("owner", {}).get("login") != owner
    ):
        raise PublishError(
            "Origin must be a private repository owned by your authenticated account."
        )
    branch = (repo.get("defaultBranchRef") or {}).get("name", "")
    if not branch or _git(root, "check-ref-format", "--branch", branch, check=False).returncode:
        raise PublishError("The repository needs a valid default branch before publishing.")
    return name, branch, account


def _working(root: Path) -> tuple[list[str], list[str]]:
    if _git(root, "diff", "--cached", "--ita-visible-in-index", "--quiet", check=False).returncode:
        raise PublishError(
            "The index contains staged work. Commit or resolve it yourself, then rerun "
            "./briefing publish; publication leaves your staging unchanged."
        )
    changed = _git(root, "diff", "--name-only", "--no-renames", "-z", "HEAD").stdout
    new = _git(root, "ls-files", "--others", "--exclude-standard", "-z").stdout
    paths = sorted(set(filter(None, (changed + new).split("\0"))))
    for name in paths:
        if not _allowed(name):
            raise PublishError(
                f"Unrelated working path {name!r}; preserve it separately before publishing."
            )
        path = root / name
        if path.exists() or path.is_symlink():
            _check_path(root, path)
    return paths, list(filter(None, new.split("\0")))


def _outgoing(root: Path, remote: str) -> list[str]:
    if _git(root, "merge-base", remote, "HEAD", check=False).returncode:
        raise PublishError(
            "Local and remote histories are unrelated. Keep this checkout; clone your "
            "private repository separately and copy only your accepted personalization."
        )
    commits = _git(root, "rev-list", "--reverse", f"{remote}..HEAD").stdout.splitlines()
    for commit in commits:
        if len(_git(root, "rev-list", "--parents", "-n", "1", commit).stdout.split()) > 2:
            raise PublishError(
                "Outgoing merge history is unsupported. Review it manually before publishing."
            )
        names = _git(
            root,
            "diff-tree",
            "--root",
            "--no-commit-id",
            "--name-only",
            "--no-renames",
            "-r",
            "-z",
            commit,
        ).stdout.split("\0")
        for name in filter(None, names):
            if not _allowed(name):
                raise PublishError(
                    f"Outgoing commit {commit[:12]} touches forbidden path {name!r}, even if "
                    "later deleted. Keep your work and remove that commit "
                    "from publication manually."
                )
            tree = _git(root, "ls-tree", "-z", commit, "--", name).stdout
            if tree and tree.split(" ", 1)[0] not in {"100644", "100755"}:
                raise PublishError(
                    f"Outgoing commit {commit[:12]} contains a nonregular file: {name!r}."
                )
    return commits


def _review(root: Path, commits: list[str], paths: list[str], new: list[str]) -> str:
    parts = [_git(root, "rev-parse", "HEAD").stdout]
    for commit in commits:
        parts.append(
            _git(root, "show", "--no-ext-diff", "--no-textconv", "--format=fuller", commit).stdout
        )
    if paths:
        parts.append(
            _git(
                root, "diff", "--no-ext-diff", "--no-textconv", "--binary", "HEAD", "--", *paths
            ).stdout
        )
    for name in new:
        parts.append(f"New file: {name}\n" + (root / name).read_text(encoding="utf-8"))
    return "\n".join(parts)


def _confirm(review: str) -> bool:
    print("Review all outgoing commits and working changes:\n" + review)
    return input("Commit and publish these reviewed changes? [y/N] ").strip().lower() in {
        "y",
        "yes",
    }


def _protect_ignored(root: Path, remote: str) -> None:
    ignored = _git(root, "ls-files", "--others", "--ignored", "--exclude-standard", "-z")
    tracked = _git(root, "ls-tree", "-r", "--name-only", "-z", remote).stdout.split("\0")
    for name in filter(None, ignored.stdout.split("\0")):
        if any(
            path == name or path.startswith(name + "/") or name.startswith(path + "/")
            for path in filter(None, tracked)
        ):
            raise PublishError(
                f"Remote files overlap ignored local work {name!r}. Preserve that work "
                "outside the checkout before publishing; no files were removed."
            )


def publish(root: Path, *, run: bool = False) -> int:
    """Publish reviewed instance changes, optionally dispatching an ordinary daily run.

    Args:
        root: Existing personal briefing checkout.
        run: Dispatch only after successful or no-op publication, without forcing email.

    Returns:
        Zero on success, 130 on cancellation, or one with safe recovery guidance.
    """
    try:
        root = root.absolute()
        _validate(root)
        if (
            Path(_git(root, "rev-parse", "--show-toplevel").stdout.strip()).resolve()
            != root.resolve()
        ):
            raise PublishError(
                "Run publication from the briefing repository root, not an ancestor checkout."
            )
        paths, new = _working(root)
        gh = bootstrap.ensure_tool("gh")
        name, branch, account = _repository(root, gh)
        local_branch = _git(root, "symbolic-ref", "--quiet", "--short", "HEAD", check=False)
        if local_branch.returncode or local_branch.stdout.strip() != branch:
            raise PublishError(
                f"Use the repository's default branch {branch!r}. Keep your work and switch "
                "branches manually; detached and custom branches are not published."
            )
        for marker in (
            "MERGE_HEAD",
            "CHERRY_PICK_HEAD",
            "REVERT_HEAD",
            "rebase-merge",
            "rebase-apply",
        ):
            marker_path = Path(_git(root, "rev-parse", "--git-path", marker).stdout.strip())
            if not marker_path.is_absolute():
                marker_path = root / marker_path
            if marker_path.exists():
                raise PublishError(
                    "Finish or abort your existing Git operation manually before publishing."
                )
        url = f"https://github.com/{name}.git"
        _git(root, "fetch", "--no-tags", url, f"refs/heads/{branch}", gh_bin=gh)
        remote = _git(root, "rev-parse", "FETCH_HEAD").stdout.strip()
        commits = _outgoing(root, remote)
        _protect_ignored(root, remote)
        if commits or paths:
            review = _review(root, commits, paths, new)
            if not _confirm(review):
                print("Publication cancelled; your files, commits and staging are preserved.")
                return 130
            _validate(root)
            check_paths, check_new = _working(root)
            if _review(root, _outgoing(root, remote), check_paths, check_new) != review:
                raise PublishError(
                    "Work changed during review. Rerun ./briefing publish to review it again."
                )
            for key, value in (
                ("user.name", account["login"]),
                ("user.email", f"{account['id']}+{account['login']}@users.noreply.github.com"),
            ):
                if not _git(root, "config", "--get", key, check=False).stdout.strip():
                    _git(root, "config", "--local", key, value)
            if paths:
                _git(root, "add", "--", *paths)
                _git(root, "commit", "-m", "chore: tune daily briefing")
        if _working(root)[0]:
            raise PublishError(
                "Working changes remain. Keep them and rerun ./briefing publish after reviewing."
            )
        old_head = _git(root, "rev-parse", "HEAD").stdout.strip()
        if _git(root, "merge-base", "--is-ancestor", remote, "HEAD", check=False).returncode:
            _protect_ignored(root, remote)
            rebased = _git(root, "rebase", remote, check=False)
            if rebased.returncode:
                _git(root, "rebase", "--abort")
                raise PublishError(
                    f"Rebase conflict: your local commit and work are retained. Fetch {url} "
                    f"refs/heads/{branch}, run git rebase FETCH_HEAD, resolve conflicts and use "
                    "git rebase --continue (or --abort), then rerun ./briefing publish."
                )
            _validate(root)
            commits = _outgoing(root, remote)
            if commits and _git(root, "rev-parse", "HEAD").stdout.strip() != old_head:
                review = _review(root, commits, [], [])
                if not _confirm(review):
                    print("Publication cancelled after rebase; your reviewed local commits remain.")
                    return 130
                if _review(root, _outgoing(root, remote), *_working(root)) != review:
                    raise PublishError(
                        "Work changed during review. Rerun ./briefing publish to review it again."
                    )
        _validate(root)
        paths, _ = _working(root)
        commits = _outgoing(root, remote)
        if paths:
            raise PublishError(
                "Work changed after review. Rerun ./briefing publish to review it again."
            )
        if commits:
            try:
                _git(root, "push", url, f"HEAD:refs/heads/{branch}", gh_bin=gh)
            except CommandError:
                raise PublishError(
                    "Push failed or its outcome is uncertain; your local commit is retained. "
                    "Inspect the remote branch and GitHub access, then rerun ./briefing publish "
                    "to fetch and review again. Never force-push."
                ) from None
            print("Reviewed changes published.")
        else:
            print("No changes to publish; checkout is up to date.")
        if run:
            try:
                run_gh(gh, ["workflow", "run", "briefing.yml", "--repo", name, "--ref", branch])
            except CommandError:
                raise PublishError(
                    f"Dispatch outcome is uncertain. Inspect https://github.com/{name}/actions "
                    "before using Run workflow; do not blindly retry --run."
                ) from None
            print(f"Daily run requested (daily guard respected): https://github.com/{name}/actions")
        return 0
    except (
        PublishError,
        LocalError,
        SectionError,
        bootstrap.BootstrapError,
        CommandError,
        OSError,
        ValueError,
        KeyError,
        TypeError,
    ) as exc:
        print(f"Problem: {exc}")
        return 1
    except (EOFError, KeyboardInterrupt):
        print("Publication cancelled; your local work is retained.")
        return 130
