"""Tests for the Flask web application."""

import json
import tempfile
from pathlib import Path

import pytest

from checkweek.models import Task, TaskStatus, TaskStore, TaskTag
from checkweek.web.app import app, store as default_store


@pytest.fixture
def tmp_store(tmp_path):
    """Create a TaskStore with a temporary file."""
    return TaskStore(file_path=tmp_path / "tasks.json")


@pytest.fixture
def client(tmp_store, monkeypatch):
    """Create a Flask test client with isolated storage."""
    import checkweek.web.app as web_module
    monkeypatch.setattr(web_module, "store", tmp_store)
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


class TestWebRoutes:
    def test_index_empty(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert b"CheckWeek" in resp.data

    def test_add_task(self, client, tmp_store):
        resp = client.post("/add", data={
            "title": "Test web task",
            "tag": "work",
            "due_date": "2026-02-15",
        }, follow_redirects=True)
        assert resp.status_code == 200
        assert b"Test web task" in resp.data

        week = tmp_store.get_current_week()
        assert len(week.tasks) == 1
        assert week.tasks[0].title == "Test web task"

    def test_add_empty_title_ignored(self, client, tmp_store):
        resp = client.post("/add", data={
            "title": "   ",
            "tag": "other",
        }, follow_redirects=True)
        assert resp.status_code == 200
        week = tmp_store.get_current_week()
        assert len(week.tasks) == 0

    def test_update_status(self, client, tmp_store):
        week = tmp_store.get_current_week()
        task = Task(title="Move me", status=TaskStatus.TODO)
        week.add_task(task)
        tmp_store.save_week(week)

        resp = client.post(f"/status/{task.id}/in_progress", follow_redirects=True)
        assert resp.status_code == 200

        updated = tmp_store.get_current_week()
        assert updated.tasks[0].status == TaskStatus.IN_PROGRESS

    def test_delete_task(self, client, tmp_store):
        week = tmp_store.get_current_week()
        task = Task(title="Delete me")
        week.add_task(task)
        tmp_store.save_week(week)

        resp = client.post(f"/delete/{task.id}", follow_redirects=True)
        assert resp.status_code == 200

        updated = tmp_store.get_current_week()
        assert len(updated.tasks) == 0

    def test_history_page(self, client):
        resp = client.get("/history")
        assert resp.status_code == 200
        assert b"Week History" in resp.data

    def test_kanban_groups(self, client, tmp_store):
        week = tmp_store.get_current_week()
        week.add_task(Task(title="Todo task", status=TaskStatus.TODO))
        week.add_task(Task(title="WIP task", status=TaskStatus.IN_PROGRESS))
        week.add_task(Task(title="Done task", status=TaskStatus.DONE))
        tmp_store.save_week(week)

        resp = client.get("/")
        assert resp.status_code == 200
        assert b"Todo task" in resp.data
        assert b"WIP task" in resp.data
        assert b"Done task" in resp.data
