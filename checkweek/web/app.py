"""Flask web application for CheckWeek dashboard."""

from __future__ import annotations

import traceback

from flask import Flask, redirect, render_template, request, url_for

from checkweek.config import AppConfig
from checkweek.models import (
    RoutineDefinition,
    Task,
    TaskStatus,
    TaskStore,
    TaskTag,
    TaskType,
)

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
    """Main dashboard - weekly checklist view."""
    week = store.get_current_week()
    summary = week.get_summary()

    # 섹션별 분류
    once_pending = [
        t for t in week.tasks
        if t.task_type == TaskType.ONCE and t.status != TaskStatus.DONE
    ]
    routine_pending = [
        t for t in week.tasks
        if t.task_type == TaskType.ROUTINE and t.status != TaskStatus.DONE
    ]
    completed = [t for t in week.tasks if t.status == TaskStatus.DONE]

    routines = store.load_routines()

    return render_template(
        "index.html",
        week=week,
        summary=summary,
        once_pending=once_pending,
        routine_pending=routine_pending,
        completed=completed,
        tags=[t.value for t in TaskTag],
        routines=routines,
    )


@app.route("/add", methods=["POST"])
def add_task():
    """Add a one-time task."""
    title = request.form.get("title", "").strip()
    tag = request.form.get("tag", "other")

    if title:
        week = store.get_current_week()
        task = Task(title=title, tag=TaskTag(tag))
        week.add_task(task)
        store.save_week(week)

    return redirect(url_for("index"))


@app.route("/check/<task_id>", methods=["POST"])
def check_task(task_id: str):
    """Check a task (once: done, routine: count+1)."""
    week = store.get_current_week()
    week.check_task(task_id)
    store.save_week(week)
    return redirect(url_for("index"))


@app.route("/uncheck/<task_id>", methods=["POST"])
def uncheck_task(task_id: str):
    """Uncheck a task (once: undo, routine: count-1)."""
    week = store.get_current_week()
    week.uncheck_task(task_id)
    store.save_week(week)
    return redirect(url_for("index"))


@app.route("/delete/<task_id>", methods=["POST"])
def delete_task(task_id: str):
    """Delete a task."""
    week = store.get_current_week()
    week.remove_task(task_id)
    store.save_week(week)
    return redirect(url_for("index"))


@app.route("/routine/add", methods=["POST"])
def add_routine():
    """Add a routine definition + create task for current week."""
    title = request.form.get("title", "").strip()
    tag = request.form.get("tag", "other")
    target_count = int(request.form.get("target_count", 1))

    if title and target_count > 0:
        routine = RoutineDefinition(
            title=title,
            tag=TaskTag(tag),
            target_count=target_count,
        )
        store.add_routine(routine)

        # 현재 주에 즉시 Task 생성
        week = store.get_current_week()
        if not week.has_routine(routine.id):
            week.add_task(routine.create_task())
            store.save_week(week)

    return redirect(url_for("index"))


@app.route("/routine/delete/<routine_id>", methods=["POST"])
def delete_routine(routine_id: str):
    """Delete a routine definition."""
    store.remove_routine(routine_id)
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
