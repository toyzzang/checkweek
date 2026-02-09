"""Tests for the weekly scheduler logic."""

import json
import tempfile
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from checkweek.config import AppConfig
from checkweek.models import Task, TaskStatus, TaskStore, TaskTag, WeeklyTaskList
from checkweek.scheduler.weekly import weekly_sync_job


class TestWeeklySyncJob:
    def test_sync_with_no_notion_config(self, tmp_path):
        """Sync job should work without Notion configured (just rollover)."""
        config = AppConfig()
        store = TaskStore(file_path=tmp_path / "tasks.json")

        # Create current week with tasks
        week = store.get_current_week()
        week.add_task(Task(title="Done task", status=TaskStatus.DONE))
        week.add_task(Task(title="Incomplete task", status=TaskStatus.TODO))
        store.save_week(week)

        with patch("checkweek.scheduler.weekly.TaskStore") as mock_store_cls:
            mock_store_cls.return_value = store
            result = weekly_sync_job(config)

        assert result["synced_to_notion"] is False
        assert result["rolled_over"] == 1

    def test_sync_rolls_over_incomplete_tasks(self, tmp_path):
        """Incomplete tasks should be rolled over to the next week."""
        config = AppConfig()
        store = TaskStore(file_path=tmp_path / "tasks.json")

        week = store.get_current_week()
        week.add_task(Task(title="Task A", status=TaskStatus.TODO, tag=TaskTag.WORK))
        week.add_task(Task(title="Task B", status=TaskStatus.IN_PROGRESS, tag=TaskTag.STUDY))
        week.add_task(Task(title="Task C", status=TaskStatus.DONE))
        store.save_week(week)

        with patch("checkweek.scheduler.weekly.TaskStore") as mock_store_cls:
            mock_store_cls.return_value = store
            result = weekly_sync_job(config)

        assert result["rolled_over"] == 2

        # Verify next week was created with rolled-over tasks
        all_weeks = store.load_all_weeks()
        assert len(all_weeks) == 2

        next_week = [w for w in all_weeks if w.week_start != week.week_start][0]
        assert len(next_week.tasks) == 2
        titles = {t.title for t in next_week.tasks}
        assert "Task A" in titles
        assert "Task B" in titles

    def test_sync_no_rollover_when_all_done(self, tmp_path):
        """No rollover should happen when all tasks are done."""
        config = AppConfig()
        store = TaskStore(file_path=tmp_path / "tasks.json")

        week = store.get_current_week()
        week.add_task(Task(title="Done A", status=TaskStatus.DONE))
        week.add_task(Task(title="Done B", status=TaskStatus.DONE))
        store.save_week(week)

        with patch("checkweek.scheduler.weekly.TaskStore") as mock_store_cls:
            mock_store_cls.return_value = store
            result = weekly_sync_job(config)

        assert result["rolled_over"] == 0
