"""Tests for data models and task store."""

import json
import tempfile
from datetime import date, timedelta
from pathlib import Path

import pytest

from checkweek.models import Task, TaskStatus, TaskStore, TaskTag, WeeklyTaskList


class TestTask:
    def test_create_task_defaults(self):
        task = Task(title="Test task")
        assert task.title == "Test task"
        assert task.status == TaskStatus.TODO
        assert task.tag == TaskTag.OTHER
        assert task.due_date is None
        assert task.id is not None
        assert len(task.id) == 8

    def test_task_to_dict(self):
        task = Task(title="Test", tag=TaskTag.WORK, status=TaskStatus.IN_PROGRESS)
        d = task.to_dict()
        assert d["title"] == "Test"
        assert d["status"] == "in_progress"
        assert d["tag"] == "work"

    def test_task_from_dict(self):
        data = {
            "id": "abc12345",
            "title": "From dict",
            "status": "done",
            "tag": "study",
            "due_date": "2026-02-15",
        }
        task = Task.from_dict(data)
        assert task.id == "abc12345"
        assert task.title == "From dict"
        assert task.status == TaskStatus.DONE
        assert task.tag == TaskTag.STUDY
        assert task.due_date == "2026-02-15"

    def test_task_roundtrip(self):
        original = Task(
            title="Roundtrip",
            status=TaskStatus.IN_PROGRESS,
            tag=TaskTag.MEETING,
            due_date="2026-03-01",
        )
        restored = Task.from_dict(original.to_dict())
        assert restored.title == original.title
        assert restored.status == original.status
        assert restored.tag == original.tag
        assert restored.due_date == original.due_date


class TestWeeklyTaskList:
    def test_create_weekly_list(self):
        week = WeeklyTaskList(week_start="2026-02-09", week_end="2026-02-15")
        assert week.week_start == "2026-02-09"
        assert week.tasks == []
        assert week.synced_to_notion is False

    def test_add_and_remove_task(self):
        week = WeeklyTaskList(week_start="2026-02-09", week_end="2026-02-15")
        task = Task(title="Test task")
        week.add_task(task)
        assert len(week.tasks) == 1

        result = week.remove_task(task.id)
        assert result is True
        assert len(week.tasks) == 0

    def test_remove_nonexistent_task(self):
        week = WeeklyTaskList(week_start="2026-02-09", week_end="2026-02-15")
        assert week.remove_task("nonexistent") is False

    def test_update_task_status(self):
        week = WeeklyTaskList(week_start="2026-02-09", week_end="2026-02-15")
        task = Task(title="Test")
        week.add_task(task)

        result = week.update_task_status(task.id, TaskStatus.DONE)
        assert result is True
        assert week.tasks[0].status == TaskStatus.DONE

    def test_get_incomplete_tasks(self):
        week = WeeklyTaskList(week_start="2026-02-09", week_end="2026-02-15")
        week.add_task(Task(title="Done task", status=TaskStatus.DONE))
        week.add_task(Task(title="Todo task", status=TaskStatus.TODO))
        week.add_task(Task(title="WIP task", status=TaskStatus.IN_PROGRESS))

        incomplete = week.get_incomplete_tasks()
        assert len(incomplete) == 2
        assert all(t.status != TaskStatus.DONE for t in incomplete)

    def test_get_summary(self):
        week = WeeklyTaskList(week_start="2026-02-09", week_end="2026-02-15")
        week.add_task(Task(title="A", status=TaskStatus.DONE))
        week.add_task(Task(title="B", status=TaskStatus.TODO))
        week.add_task(Task(title="C", status=TaskStatus.IN_PROGRESS))
        week.add_task(Task(title="D", status=TaskStatus.DONE))

        summary = week.get_summary()
        assert summary["total"] == 4
        assert summary["done"] == 2
        assert summary["in_progress"] == 1
        assert summary["todo"] == 1
        assert summary["completion_rate"] == "50.0%"

    def test_empty_summary(self):
        week = WeeklyTaskList(week_start="2026-02-09", week_end="2026-02-15")
        summary = week.get_summary()
        assert summary["total"] == 0
        assert summary["completion_rate"] == "0%"


class TestTaskStore:
    def test_store_save_and_load(self, tmp_path):
        store = TaskStore(file_path=tmp_path / "tasks.json")
        week = WeeklyTaskList(week_start="2026-02-09", week_end="2026-02-15")
        week.add_task(Task(title="Persistent task"))

        store.save_week(week)
        loaded_weeks = store.load_all_weeks()

        assert len(loaded_weeks) == 1
        assert loaded_weeks[0].tasks[0].title == "Persistent task"

    def test_get_current_week(self, tmp_path):
        store = TaskStore(file_path=tmp_path / "tasks.json")
        week = store.get_current_week()

        today = date.today()
        monday = today - timedelta(days=today.weekday())
        assert week.week_start == monday.isoformat()

    def test_save_week_updates_existing(self, tmp_path):
        store = TaskStore(file_path=tmp_path / "tasks.json")
        week = store.get_current_week()
        week.add_task(Task(title="First"))
        store.save_week(week)

        week.add_task(Task(title="Second"))
        store.save_week(week)

        loaded = store.load_all_weeks()
        assert len(loaded) == 1
        assert len(loaded[0].tasks) == 2
