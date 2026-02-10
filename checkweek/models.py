"""Data models for weekly task management."""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Optional

from checkweek.config import ROUTINES_FILE, TASKS_FILE


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


class TaskType(str, Enum):
    ONCE = "once"
    ROUTINE = "routine"


@dataclass
class Task:
    title: str
    task_type: TaskType = TaskType.ONCE
    status: TaskStatus = TaskStatus.TODO
    tag: TaskTag = TaskTag.OTHER
    due_date: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    notion_page_id: Optional[str] = None
    target_count: int = 1
    current_count: int = 0
    routine_id: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "task_type": self.task_type.value,
            "status": self.status.value,
            "tag": self.tag.value,
            "due_date": self.due_date,
            "created_at": self.created_at,
            "notion_page_id": self.notion_page_id,
            "target_count": self.target_count,
            "current_count": self.current_count,
            "routine_id": self.routine_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Task:
        # 하위 호환성: task_type 없으면 once
        task_type_str = data.get("task_type", "once")
        try:
            task_type = TaskType(task_type_str)
        except ValueError:
            task_type = TaskType.ONCE

        return cls(
            id=data["id"],
            title=data["title"],
            task_type=task_type,
            status=TaskStatus(data["status"]),
            tag=TaskTag(data["tag"]),
            due_date=data.get("due_date"),
            created_at=data.get("created_at", datetime.now().isoformat()),
            notion_page_id=data.get("notion_page_id"),
            target_count=data.get("target_count", 1),
            current_count=data.get("current_count", 0),
            routine_id=data.get("routine_id"),
        )


@dataclass
class RoutineDefinition:
    """루틴 정의: 매주 자동 생성되는 반복 업무 템플릿."""

    title: str
    tag: TaskTag = TaskTag.OTHER
    target_count: int = 1
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "tag": self.tag.value,
            "target_count": self.target_count,
        }

    @classmethod
    def from_dict(cls, data: dict) -> RoutineDefinition:
        return cls(
            id=data["id"],
            title=data["title"],
            tag=TaskTag(data.get("tag", "other")),
            target_count=data.get("target_count", 1),
        )

    def create_task(self) -> Task:
        """이 루틴 정의에서 새 주간 Task를 생성."""
        return Task(
            title=self.title,
            task_type=TaskType.ROUTINE,
            tag=self.tag,
            target_count=self.target_count,
            current_count=0,
            routine_id=self.id,
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

    def check_task(self, task_id: str) -> bool:
        """체크: 일회성은 완료, 루틴은 count+1."""
        for task in self.tasks:
            if task.id == task_id:
                if task.task_type == TaskType.ONCE:
                    task.current_count = 1
                    task.status = TaskStatus.DONE
                else:
                    if task.current_count < task.target_count:
                        task.current_count += 1
                        if task.current_count >= task.target_count:
                            task.status = TaskStatus.DONE
                return True
        return False

    def uncheck_task(self, task_id: str) -> bool:
        """체크 해제: 일회성은 미완료, 루틴은 count-1."""
        for task in self.tasks:
            if task.id == task_id:
                if task.task_type == TaskType.ONCE:
                    task.current_count = 0
                    task.status = TaskStatus.TODO
                else:
                    if task.current_count > 0:
                        task.current_count -= 1
                        task.status = TaskStatus.TODO
                return True
        return False

    def get_incomplete_tasks(self) -> list[Task]:
        return [t for t in self.tasks if t.status != TaskStatus.DONE]

    def has_routine(self, routine_id: str) -> bool:
        """이 주에 해당 루틴 ID의 Task가 이미 존재하는지 확인."""
        return any(t.routine_id == routine_id for t in self.tasks)

    def get_summary(self) -> dict:
        total = len(self.tasks)
        done = sum(1 for t in self.tasks if t.status == TaskStatus.DONE)
        once_tasks = [t for t in self.tasks if t.task_type == TaskType.ONCE]
        routine_tasks = [t for t in self.tasks if t.task_type == TaskType.ROUTINE]

        once_done = sum(1 for t in once_tasks if t.status == TaskStatus.DONE)
        routine_done = sum(1 for t in routine_tasks if t.status == TaskStatus.DONE)

        # 루틴 전체 진행률 (각 루틴의 current/target 합산)
        routine_current = sum(t.current_count for t in routine_tasks)
        routine_target = sum(t.target_count for t in routine_tasks)

        return {
            "total": total,
            "done": done,
            "once_total": len(once_tasks),
            "once_done": once_done,
            "routine_total": len(routine_tasks),
            "routine_done": routine_done,
            "routine_current": routine_current,
            "routine_target": routine_target,
            "completion_rate": f"{done / total * 100:.0f}%" if total > 0 else "0%",
        }


class TaskStore:
    """Persistent storage for weekly task lists."""

    def __init__(self, file_path: Path | None = None):
        self.file_path = file_path or TASKS_FILE
        self.routines_path = ROUTINES_FILE

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
        monday = today - timedelta(days=today.weekday())
        sunday = monday + timedelta(days=6)
        week_start = monday.isoformat()
        week_end = sunday.isoformat()

        weeks = self.load_all_weeks()
        for week in weeks:
            if week.week_start == week_start:
                # 기존 주가 있으면 루틴 자동 추가 확인
                self._ensure_routines(week)
                self.save_week(week)
                return week

        # 새 주 생성 + 루틴 자동 추가
        new_week = WeeklyTaskList(week_start=week_start, week_end=week_end)
        self._ensure_routines(new_week)
        weeks.append(new_week)
        self.save_all_weeks(weeks)
        return new_week

    def _ensure_routines(self, week: WeeklyTaskList) -> None:
        """루틴 정의에서 아직 생성되지 않은 루틴 Task를 추가."""
        routines = self.load_routines()
        for routine in routines:
            if not week.has_routine(routine.id):
                week.add_task(routine.create_task())

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
        monday = today - timedelta(days=today.weekday())
        prev_monday = monday - timedelta(days=7)
        prev_start = prev_monday.isoformat()

        weeks = self.load_all_weeks()
        for week in weeks:
            if week.week_start == prev_start:
                return week
        return None

    # --- Routine management ---

    def load_routines(self) -> list[RoutineDefinition]:
        """루틴 정의 목록 로드."""
        self.routines_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.routines_path.exists():
            return []
        with open(self.routines_path) as f:
            data = json.load(f)
        return [RoutineDefinition.from_dict(r) for r in data.get("routines", [])]

    def save_routines(self, routines: list[RoutineDefinition]) -> None:
        """루틴 정의 목록 저장."""
        self.routines_path.parent.mkdir(parents=True, exist_ok=True)
        data = {"routines": [r.to_dict() for r in routines]}
        with open(self.routines_path, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def add_routine(self, routine: RoutineDefinition) -> None:
        """루틴 정의 추가."""
        routines = self.load_routines()
        routines.append(routine)
        self.save_routines(routines)

    def remove_routine(self, routine_id: str) -> bool:
        """루틴 정의 삭제."""
        routines = self.load_routines()
        for i, r in enumerate(routines):
            if r.id == routine_id:
                routines.pop(i)
                self.save_routines(routines)
                return True
        return False
