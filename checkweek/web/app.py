"""Flask web application for CheckWeek dashboard."""

from __future__ import annotations

import traceback

from flask import Flask, redirect, render_template, request, url_for

from checkweek.config import AppConfig
from checkweek.models import Task, TaskStatus, TaskStore, TaskTag

app = Flask(__name__)
store = TaskStore()


@app.errorhandler(Exception)
def handle_error(e):
    """Show error details instead of generic 500 page."""
    tb = traceback.format_exc()
    return (
        f"<h1>Error</h1><pre>{tb}</pre>"
        f"<p><a href='/'>Back to dashboard</a></p>"
    ), 500


@app.route("/")
def index():
    """Main dashboard - show current week's tasks."""
    week = store.get_current_week()
    summary = week.get_summary()

    # Group tasks by status for kanban-style view
    groups = {
        "todo": [t for t in week.tasks if t.status == TaskStatus.TODO],
        "in_progress": [t for t in week.tasks if t.status == TaskStatus.IN_PROGRESS],
        "done": [t for t in week.tasks if t.status == TaskStatus.DONE],
    }

    return render_template(
        "index.html",
        week=week,
        summary=summary,
        groups=groups,
        tags=[t.value for t in TaskTag],
        statuses=[s.value for s in TaskStatus],
    )


@app.route("/add", methods=["POST"])
def add_task():
    """Add a new task."""
    title = request.form.get("title", "").strip()
    tag = request.form.get("tag", "other")
    due_date = request.form.get("due_date", "").strip() or None

    if title:
        week = store.get_current_week()
        task = Task(title=title, tag=TaskTag(tag), due_date=due_date)
        week.add_task(task)
        store.save_week(week)

    return redirect(url_for("index"))


@app.route("/status/<task_id>/<new_status>", methods=["POST"])
def update_status(task_id: str, new_status: str):
    """Update a task's status."""
    week = store.get_current_week()
    week.update_task_status(task_id, TaskStatus(new_status))
    store.save_week(week)
    return redirect(url_for("index"))


@app.route("/delete/<task_id>", methods=["POST"])
def delete_task(task_id: str):
    """Delete a task."""
    week = store.get_current_week()
    week.remove_task(task_id)
    store.save_week(week)
    return redirect(url_for("index"))


@app.route("/sync", methods=["POST"])
def sync_notion():
    """Sync current week to Notion."""
    config = AppConfig.load()
    if not config.notion.api_key or not config.notion.database_id:
        return redirect(url_for("index"))

    try:
        from checkweek.notion.client import NotionClient

        week = store.get_current_week()
        client = NotionClient(config)
        updated = client.sync_week_to_notion(week)
        store.save_week(updated)
    except Exception:
        pass

    return redirect(url_for("index"))


@app.route("/history")
def history():
    """Show all weeks."""
    weeks = store.load_all_weeks()
    weeks_with_summary = []
    for w in reversed(weeks):
        weeks_with_summary.append({"week": w, "summary": w.get_summary()})
    return render_template("history.html", weeks=weeks_with_summary)


def run_web(host: str = "0.0.0.0", port: int = 5000, debug: bool = False):
    """Start the Flask web server."""
    app.run(host=host, port=port, debug=debug)
