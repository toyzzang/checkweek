"""Weekly task scheduler - handles automatic end-of-week sync and rollover."""

from __future__ import annotations

import logging
from datetime import date, timedelta

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from checkweek.config import AppConfig
from checkweek.models import Task, TaskStatus, TaskStore, WeeklyTaskList

logger = logging.getLogger(__name__)

DAY_MAP = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}


def weekly_sync_job(config: AppConfig | None = None) -> dict:
    """Execute the weekly sync: push to Notion and roll over incomplete tasks.

    Returns a summary dict of what was done.
    """
    config = config or AppConfig.load()
    store = TaskStore()
    current_week = store.get_current_week()
    summary = current_week.get_summary()

    result = {
        "week": f"{current_week.week_start} ~ {current_week.week_end}",
        "summary": summary,
        "synced_to_notion": False,
        "rolled_over": 0,
    }

    # 1. Sync to Notion if configured
    if config.notion.api_key and config.notion.database_id:
        try:
            from checkweek.notion.client import NotionClient

            notion = NotionClient(config)
            notion.sync_week_to_notion(current_week)
            store.save_week(current_week)
            result["synced_to_notion"] = True
            logger.info("Successfully synced week to Notion")
        except Exception as e:
            logger.error("Failed to sync to Notion: %s", e)
            result["notion_error"] = str(e)

    # 2. Roll over incomplete tasks to next week
    incomplete = current_week.get_incomplete_tasks()
    if incomplete:
        today = date.today()
        next_monday = today + timedelta(days=(7 - today.weekday()))
        next_sunday = next_monday + timedelta(days=6)

        next_week = WeeklyTaskList(
            week_start=next_monday.isoformat(),
            week_end=next_sunday.isoformat(),
        )

        # Check if next week already exists
        all_weeks = store.load_all_weeks()
        existing = None
        for w in all_weeks:
            if w.week_start == next_week.week_start:
                existing = w
                break

        target_week = existing or next_week

        for task in incomplete:
            rolled_task = Task(
                title=task.title,
                status=TaskStatus.TODO,
                tag=task.tag,
                due_date=None,  # Reset due date for new week
            )
            target_week.add_task(rolled_task)

        store.save_week(target_week)
        result["rolled_over"] = len(incomplete)
        logger.info("Rolled over %d incomplete tasks", len(incomplete))

    # 3. Auto-commit to GitHub if configured
    if config.github.auto_commit and config.github.repo_path:
        try:
            from checkweek.github.auto_commit import auto_commit_changes

            auto_commit_changes(config)
            result["git_committed"] = True
            logger.info("Auto-committed changes to GitHub")
        except Exception as e:
            logger.error("Failed to auto-commit: %s", e)
            result["git_error"] = str(e)

    return result


def start_scheduler(config: AppConfig | None = None) -> None:
    """Start the blocking scheduler for weekly sync."""
    config = config or AppConfig.load()
    scheduler = BlockingScheduler()

    day = config.scheduler.weekly_sync_day
    hour = config.scheduler.weekly_sync_hour
    minute = config.scheduler.weekly_sync_minute

    trigger = CronTrigger(
        day_of_week=DAY_MAP.get(day, 6),  # default Sunday
        hour=hour,
        minute=minute,
    )

    scheduler.add_job(
        weekly_sync_job,
        trigger=trigger,
        args=[config],
        id="weekly_sync",
        name="Weekly task sync to Notion",
    )

    logger.info(
        "Scheduler started. Weekly sync scheduled for %s at %02d:%02d",
        day,
        hour,
        minute,
    )

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped.")
