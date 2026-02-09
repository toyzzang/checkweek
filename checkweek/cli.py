"""CLI interface for CheckWeek - weekly task management."""

from __future__ import annotations

import sys

import click
from rich.console import Console
from rich.table import Table

from checkweek.config import AppConfig
from checkweek.models import Task, TaskStatus, TaskStore, TaskTag

console = Console()

VALID_TAGS = [t.value for t in TaskTag]
VALID_STATUSES = [s.value for s in TaskStatus]


@click.group()
@click.version_option(package_name="checkweek")
def main():
    """CheckWeek - Weekly task management with Notion sync."""
    pass


# --- Task commands ---


@main.command()
@click.argument("title")
@click.option(
    "--tag",
    "-t",
    type=click.Choice(VALID_TAGS),
    default="other",
    help="Task tag/category",
)
@click.option("--due", "-d", default=None, help="Due date (YYYY-MM-DD)")
def add(title: str, tag: str, due: str | None):
    """Add a new task to the current week."""
    store = TaskStore()
    week = store.get_current_week()

    task = Task(title=title, tag=TaskTag(tag), due_date=due)
    week.add_task(task)
    store.save_week(week)

    console.print(f"[green]Added:[/green] {task.title} [dim](#{task.id})[/dim]")


@main.command(name="list")
@click.option(
    "--status",
    "-s",
    type=click.Choice(VALID_STATUSES),
    default=None,
    help="Filter by status",
)
@click.option("--all-weeks", "-a", is_flag=True, help="Show all weeks")
def list_tasks(status: str | None, all_weeks: bool):
    """List tasks for the current week."""
    store = TaskStore()

    if all_weeks:
        weeks = store.load_all_weeks()
    else:
        weeks = [store.get_current_week()]

    if not weeks:
        console.print("[yellow]No tasks found.[/yellow]")
        return

    for week in weeks:
        table = Table(
            title=f"Week: {week.week_start} ~ {week.week_end}",
            show_header=True,
            header_style="bold cyan",
        )
        table.add_column("ID", style="dim", width=8)
        table.add_column("Task", min_width=30)
        table.add_column("Status", width=12)
        table.add_column("Tag", width=10)
        table.add_column("Due", width=12)

        status_styles = {
            TaskStatus.TODO: "[white]TODO[/white]",
            TaskStatus.IN_PROGRESS: "[blue]IN PROGRESS[/blue]",
            TaskStatus.DONE: "[green]DONE[/green]",
        }

        tasks = week.tasks
        if status:
            filter_status = TaskStatus(status)
            tasks = [t for t in tasks if t.status == filter_status]

        for task in tasks:
            table.add_row(
                task.id,
                task.title,
                status_styles.get(task.status, str(task.status)),
                task.tag.value,
                task.due_date or "-",
            )

        console.print(table)

        summary = week.get_summary()
        synced = "[green]Yes[/green]" if week.synced_to_notion else "[yellow]No[/yellow]"
        console.print(
            f"  Total: {summary['total']} | "
            f"Done: {summary['done']} | "
            f"In Progress: {summary['in_progress']} | "
            f"Todo: {summary['todo']} | "
            f"Completion: {summary['completion_rate']} | "
            f"Notion Synced: {synced}"
        )
        console.print()


@main.command()
@click.argument("task_id")
@click.argument(
    "status", type=click.Choice(VALID_STATUSES)
)
def done(task_id: str, status: str):
    """Update a task's status. Usage: checkweek done <task_id> <status>"""
    store = TaskStore()
    week = store.get_current_week()

    new_status = TaskStatus(status)
    if week.update_task_status(task_id, new_status):
        store.save_week(week)
        console.print(
            f"[green]Updated:[/green] #{task_id} -> {new_status.value}"
        )
    else:
        console.print(f"[red]Task not found:[/red] #{task_id}")


@main.command()
@click.argument("task_id")
def remove(task_id: str):
    """Remove a task from the current week."""
    store = TaskStore()
    week = store.get_current_week()

    if week.remove_task(task_id):
        store.save_week(week)
        console.print(f"[green]Removed:[/green] #{task_id}")
    else:
        console.print(f"[red]Task not found:[/red] #{task_id}")


# --- Notion commands ---


@main.command(name="setup-notion")
@click.option("--api-key", prompt="Notion API Key", help="Notion integration API key")
@click.option(
    "--parent-page-id",
    prompt="Notion Parent Page ID",
    help="Page ID to create database under",
)
def setup_notion(api_key: str, parent_page_id: str):
    """Set up Notion integration and create the weekly database."""
    config = AppConfig.load()
    config.notion.api_key = api_key
    config.notion.parent_page_id = parent_page_id
    config.save()

    try:
        from checkweek.notion.client import NotionClient

        client = NotionClient(config)
        db_id = client.create_weekly_database()
        console.print(
            f"[green]Notion database created![/green]\n"
            f"  Database ID: {db_id}"
        )
    except Exception as e:
        console.print(f"[red]Failed to create database:[/red] {e}")


@main.command(name="sync")
def sync_notion():
    """Sync current week's tasks to Notion."""
    config = AppConfig.load()

    if not config.notion.api_key or not config.notion.database_id:
        console.print(
            "[red]Notion not configured.[/red] Run 'checkweek setup-notion' first."
        )
        return

    store = TaskStore()
    week = store.get_current_week()

    try:
        from checkweek.notion.client import NotionClient

        client = NotionClient(config)
        updated_week = client.sync_week_to_notion(week)
        store.save_week(updated_week)

        summary = updated_week.get_summary()
        console.print(
            f"[green]Synced to Notion![/green]\n"
            f"  Tasks synced: {summary['total']}\n"
            f"  Completion: {summary['completion_rate']}"
        )
    except Exception as e:
        console.print(f"[red]Sync failed:[/red] {e}")


# --- Scheduler commands ---


@main.command(name="run-scheduler")
def run_scheduler():
    """Start the background scheduler for weekly auto-sync."""
    import logging

    logging.basicConfig(level=logging.INFO)
    console.print("[cyan]Starting weekly scheduler...[/cyan]")
    console.print("Press Ctrl+C to stop.\n")

    from checkweek.scheduler.weekly import start_scheduler

    config = AppConfig.load()
    start_scheduler(config)


@main.command(name="run-sync")
def run_sync_now():
    """Manually trigger the weekly sync job (Notion sync + task rollover)."""
    from checkweek.scheduler.weekly import weekly_sync_job

    console.print("[cyan]Running weekly sync...[/cyan]")
    result = weekly_sync_job()

    console.print(f"\n[bold]Sync Result:[/bold]")
    console.print(f"  Week: {result['week']}")
    console.print(f"  Summary: {result['summary']}")
    console.print(f"  Synced to Notion: {result['synced_to_notion']}")
    console.print(f"  Tasks rolled over: {result['rolled_over']}")

    if "notion_error" in result:
        console.print(f"  [red]Notion error: {result['notion_error']}[/red]")
    if "git_error" in result:
        console.print(f"  [red]Git error: {result['git_error']}[/red]")


# --- Config commands ---


@main.command(name="config")
@click.option("--show", is_flag=True, help="Show current configuration")
def config_cmd(show: bool):
    """View or edit configuration."""
    config = AppConfig.load()

    if show:
        console.print("[bold]Current Configuration:[/bold]")
        console.print(f"\n  [cyan]Notion:[/cyan]")
        console.print(f"    API Key: {'****' + config.notion.api_key[-4:] if config.notion.api_key else '[red]Not set[/red]'}")
        console.print(f"    Database ID: {config.notion.database_id or '[red]Not set[/red]'}")
        console.print(f"    Parent Page ID: {config.notion.parent_page_id or '[red]Not set[/red]'}")
        console.print(f"\n  [cyan]GitHub:[/cyan]")
        console.print(f"    Repo Path: {config.github.repo_path or '[red]Not set[/red]'}")
        console.print(f"    Auto Commit: {config.github.auto_commit}")
        console.print(f"    Branch: {config.github.branch}")
        console.print(f"\n  [cyan]Scheduler:[/cyan]")
        console.print(f"    Sync Day: {config.scheduler.weekly_sync_day}")
        console.print(f"    Sync Time: {config.scheduler.weekly_sync_hour:02d}:{config.scheduler.weekly_sync_minute:02d}")
    else:
        console.print("Use 'checkweek config --show' to view config.")
        console.print("Use environment variables or edit ~/.checkweek/config.json directly.")


if __name__ == "__main__":
    main()
