"""GitHub auto-commit module - detects changes and commits with summary messages."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from git import InvalidGitRepositoryError, Repo

from checkweek.config import AppConfig

logger = logging.getLogger(__name__)


def get_repo(repo_path: str) -> Repo:
    """Get a git.Repo object for the given path."""
    try:
        return Repo(repo_path)
    except InvalidGitRepositoryError:
        raise ValueError(f"Not a valid git repository: {repo_path}")


def detect_changes(repo: Repo) -> dict:
    """Detect all changes in the repository.

    Returns a dict with 'modified', 'added', 'deleted', 'untracked' lists.
    """
    changes = {
        "modified": [],
        "added": [],
        "deleted": [],
        "untracked": list(repo.untracked_files),
    }

    if repo.head.is_valid():
        diff = repo.index.diff(repo.head.commit)
        for d in diff:
            if d.change_type == "M":
                changes["modified"].append(d.a_path)
            elif d.change_type == "A":
                changes["added"].append(d.a_path)
            elif d.change_type == "D":
                changes["deleted"].append(d.a_path)

    # Also check unstaged changes
    diff_unstaged = repo.index.diff(None)
    for d in diff_unstaged:
        if d.change_type == "M" and d.a_path not in changes["modified"]:
            changes["modified"].append(d.a_path)

    return changes


def generate_commit_message(changes: dict) -> str:
    """Generate a descriptive commit message based on detected changes."""
    parts = []
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    if changes["added"] or changes["untracked"]:
        new_files = changes["added"] + changes["untracked"]
        parts.append(f"Add {len(new_files)} new file(s)")

    if changes["modified"]:
        parts.append(f"Update {len(changes['modified'])} file(s)")

    if changes["deleted"]:
        parts.append(f"Remove {len(changes['deleted'])} file(s)")

    if not parts:
        return f"chore: weekly sync checkpoint ({timestamp})"

    summary = ", ".join(parts).lower()
    # Capitalize first letter
    summary = summary[0].upper() + summary[1:]

    detail_lines = []
    for category, files in changes.items():
        if files:
            for f in files[:5]:  # Limit to 5 files per category
                prefix = {"modified": "M", "added": "A", "deleted": "D", "untracked": "?"}
                detail_lines.append(f"  {prefix[category]} {f}")
            if len(files) > 5:
                detail_lines.append(f"  ... and {len(files) - 5} more")

    message = f"{summary}\n\n{chr(10).join(detail_lines)}\n\nAuto-committed at {timestamp}"
    return message


def auto_commit_changes(config: AppConfig | None = None) -> str | None:
    """Detect changes, stage, commit, and optionally push.

    Returns the commit message if a commit was made, None otherwise.
    """
    config = config or AppConfig.load()
    repo_path = config.github.repo_path

    if not repo_path:
        logger.warning("No repository path configured for auto-commit")
        return None

    repo = get_repo(repo_path)
    changes = detect_changes(repo)

    has_changes = any(
        changes[k] for k in ("modified", "added", "deleted", "untracked")
    )

    if not has_changes:
        logger.info("No changes detected, skipping commit")
        return None

    # Stage all changes
    if changes["untracked"]:
        repo.index.add(changes["untracked"])
    if changes["modified"]:
        repo.index.add(changes["modified"])
    if changes["deleted"]:
        repo.index.remove(changes["deleted"])

    # Also stage any remaining unstaged changes
    repo.git.add(A=True)

    # Generate and create commit
    message = generate_commit_message(changes)
    repo.index.commit(message)
    logger.info("Created commit: %s", message.split("\n")[0])

    # Push if branch is configured
    branch = config.github.branch
    if branch:
        try:
            origin = repo.remote("origin")
            origin.push(branch)
            logger.info("Pushed to origin/%s", branch)
        except Exception as e:
            logger.error("Failed to push: %s", e)

    return message
