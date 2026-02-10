"""Configuration management for CheckWeek."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

CONFIG_DIR = Path.home() / ".checkweek"
CONFIG_FILE = CONFIG_DIR / "config.json"
TASKS_FILE = CONFIG_DIR / "tasks.json"
ROUTINES_FILE = CONFIG_DIR / "routines.json"


@dataclass
class NotionConfig:
    api_key: str = ""
    database_id: str = ""
    parent_page_id: str = ""


@dataclass
class GitHubConfig:
    repo_path: str = ""
    auto_commit: bool = False
    branch: str = "main"


@dataclass
class SchedulerConfig:
    weekly_sync_day: str = "sunday"  # day of week to run sync
    weekly_sync_hour: int = 23
    weekly_sync_minute: int = 59


@dataclass
class AppConfig:
    notion: NotionConfig = field(default_factory=NotionConfig)
    github: GitHubConfig = field(default_factory=GitHubConfig)
    scheduler: SchedulerConfig = field(default_factory=SchedulerConfig)

    @classmethod
    def load(cls) -> AppConfig:
        """Load configuration from environment variables and config file."""
        config = cls()

        # Load from environment variables first
        config.notion.api_key = os.getenv("NOTION_API_KEY", "")
        config.notion.database_id = os.getenv("NOTION_DATABASE_ID", "")
        config.notion.parent_page_id = os.getenv("NOTION_PARENT_PAGE_ID", "")
        config.github.repo_path = os.getenv("GITHUB_REPO_PATH", "")

        # Override with config file if it exists
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE) as f:
                data = json.load(f)

            if "notion" in data:
                for key, value in data["notion"].items():
                    if hasattr(config.notion, key) and value:
                        setattr(config.notion, key, value)

            if "github" in data:
                for key, value in data["github"].items():
                    if hasattr(config.github, key):
                        setattr(config.github, key, value)

            if "scheduler" in data:
                for key, value in data["scheduler"].items():
                    if hasattr(config.scheduler, key):
                        setattr(config.scheduler, key, value)

        return config

    def save(self) -> None:
        """Save current configuration to config file."""
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)

        data = {
            "notion": {
                "api_key": self.notion.api_key,
                "database_id": self.notion.database_id,
                "parent_page_id": self.notion.parent_page_id,
            },
            "github": {
                "repo_path": self.github.repo_path,
                "auto_commit": self.github.auto_commit,
                "branch": self.github.branch,
            },
            "scheduler": {
                "weekly_sync_day": self.scheduler.weekly_sync_day,
                "weekly_sync_hour": self.scheduler.weekly_sync_hour,
                "weekly_sync_minute": self.scheduler.weekly_sync_minute,
            },
        }

        with open(CONFIG_FILE, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
