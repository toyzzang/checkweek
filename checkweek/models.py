"""Data models for weekly task management."""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Optional

from checkweek.config import TASKS_FILE


class TaskStatus(str, Enum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"


class TaskTag(str, Enum):
    WORK = "work"
    PERSONAL = "personal"
    STUDY = "study"
    HEALTH = "health"
    MEETING = "meeting"
    OTHER = "other"


@dataclass
class Task:
    title: str
    status: TaskStatus = TaskStatus.TODO
    tag: TaskTag = TaskTag.OTHER
    due_date: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    notion_page_id: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "status": self.status.value,
            "tag": self.tag.value,
            "due_date": self.due_date,
            "created_at": self.created_at,
            "notion_page_id": self.notion_page_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Task:
        return cls(
            id=data["id"],
            title=data["title"],
            status=TaskStatus(data["status"]),
            tag=TaskTag(data["tag"]),
            due_date=data.get("due_date"),
            created_at=data.get("created_at", datetime.now().isoformat()),
            notion_page_id=data.get("notion_page_id"),
        )


@dataclass
class WeeklyTaskList:
    week_start: str  # ISO date string (Monday)
    week_end: str  # ISO date string (Sunday)
    tasks: list[Task] = field(default_factory=list)
    synced_to_notion: bool = False

    def to_dict(self) -> dict:
        return {
            "week_start": self.week_start,
            "week_end": self.week_end,
            "tasks": [t.to_dict() for t in self.tasks],
            "synced_to_notion": self.synced_to_notion,
        }

    @classmethod
    def from_dict(cls, data: dict) -> WeeklyTaskList:
        return cls(
            week_start=data["week_start"],
            week_end=data["week_end"],
            tasks=[Task.from_dict(t) for t in data.get("tasks", [])],
            synced_to_notion=data.get("synced_to_notion", False),
        )

    def add_task(self, task: Task) -> None:
        self.tasks.append(task)

    def remove_task(self, task_id: str) -> bool:
        for i, task in enumerate(self.tasks):
            if task.id == task_id:
                self.tasks.pop(i)
                return True
        return False

    def update_task_status(self, task_id: str, status: TaskStatus) -> bool:
        for task in self.tasks:
            if task.id == task_id:
                task.status = status
                return True
        return False

    def get_incomplete_tasks(self) -> list[Task]:
        return [t for t in self.tasks if t.status != TaskStatus.DONE]

    def get_summary(self) -> dict:
        total = len(self.tasks)
        done = sum(1 for t in self.tasks if t.status == TaskStatus.DONE)
        in_progress = sum(1 for t in self.tasks if t.status == TaskStatus.IN_PROGRESS)
        todo = sum(1 for t in self.tasks if t.status == TaskStatus.TODO)
        return {
            "total": total,
            "done": done,
            "in_progress": in_progress,
            "todo": todo,
            "completion_rate": f"{done / total * 100:.1f}%" if total > 0 else "0%",
        }


class TaskStore:
    """Persistent storage for weekly task lists."""

    def __init__(self, file_path: Path | None = None):
        self.file_path = file_path or TASKS_FILE

    def _ensure_file(self) -> None:
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.file_path.exists():
            with open(self.file_path, "w") as f:
                json.dump({"weeks": []}, f)

    def load_all_weeks(self) -> list[WeeklyTaskList]:
        self._ensure_file()
        with open(self.file_path) as f:
            data = json.load(f)
        return [WeeklyTaskList.from_dict(w) for w in data.get("weeks", [])]

    def save_all_weeks(self, weeks: list[WeeklyTaskList]) -> None:
        self._ensure_file()
        data = {"weeks": [w.to_dict() for w in weeks]}
        with open(self.file_path, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def get_current_week(self) -> WeeklyTaskList:
        today = date.today()
        monday = today - __import__("datetime").timedelta(days=today.weekday())
        sunday = monday + __import__("datetime").timedelta(days=6)
        week_start = monday.isoformat()
        week_end = sunday.isoformat()

        weeks = self.load_all_weeks()
        for week in weeks:
            if week.week_start == week_start:
                return week

        new_week = WeeklyTaskList(week_start=week_start, week_end=week_end)
        weeks.append(new_week)
        self.save_all_weeks(weeks)
        return new_week

    def save_week(self, week: WeeklyTaskList) -> None:
        weeks = self.load_all_weeks()
        for i, w in enumerate(weeks):
            if w.week_start == week.week_start:
                weeks[i] = week
                self.save_all_weeks(weeks)
                return
        weeks.append(week)
        self.save_all_weeks(weeks)

    def get_previous_week(self) -> WeeklyTaskList | None:
        today = date.today()
        monday = today - __import__("datetime").timedelta(days=today.weekday())
        prev_monday = monday - __import__("datetime").timedelta(days=7)
        prev_start = prev_monday.isoformat()

        weeks = self.load_all_weeks()
        for week in weeks:
            if week.week_start == prev_start:
                return week
        return None
