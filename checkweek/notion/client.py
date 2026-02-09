"""Notion API client for weekly task sync."""

from __future__ import annotations

from datetime import date
from typing import Any, Optional

from notion_client import Client

from checkweek.config import AppConfig
from checkweek.models import Task, TaskStatus, TaskTag, WeeklyTaskList


# Notion status mapping
STATUS_TO_NOTION = {
    TaskStatus.TODO: "Not started",
    TaskStatus.IN_PROGRESS: "In progress",
    TaskStatus.DONE: "Done",
}

NOTION_TO_STATUS = {v: k for k, v in STATUS_TO_NOTION.items()}

TAG_TO_NOTION = {
    TaskTag.WORK: "Work",
    TaskTag.PERSONAL: "Personal",
    TaskTag.STUDY: "Study",
    TaskTag.HEALTH: "Health",
    TaskTag.MEETING: "Meeting",
    TaskTag.OTHER: "Other",
}


class NotionClient:
    """Handles all Notion API interactions for weekly task management."""

    def __init__(self, config: AppConfig | None = None):
        self.config = config or AppConfig.load()
        if not self.config.notion.api_key:
            raise ValueError(
                "Notion API key not configured. "
                "Set NOTION_API_KEY env var or run 'checkweek config'."
            )
        self.client = Client(auth=self.config.notion.api_key)
        self.database_id = self.config.notion.database_id

    def create_weekly_database(self, parent_page_id: str | None = None) -> str:
        """Create a new 'Weekly Todo List' database in Notion.

        Returns the database ID.
        """
        parent_id = parent_page_id or self.config.notion.parent_page_id
        if not parent_id:
            raise ValueError(
                "Parent page ID required. "
                "Set NOTION_PARENT_PAGE_ID or pass it explicitly."
            )

        response = self.client.databases.create(
            parent={"type": "page_id", "page_id": parent_id},
            title=[{"type": "text", "text": {"content": "Weekly Todo List"}}],
            properties={
                "할 일": {"title": {}},
                "상태": {
                    "status": {
                        "options": [
                            {"name": "Not started", "color": "default"},
                            {"name": "In progress", "color": "blue"},
                            {"name": "Done", "color": "green"},
                        ],
                        "groups": [
                            {
                                "name": "To-do",
                                "option_ids": [],
                                "color": "gray",
                            },
                            {
                                "name": "In progress",
                                "option_ids": [],
                                "color": "blue",
                            },
                            {
                                "name": "Complete",
                                "option_ids": [],
                                "color": "green",
                            },
                        ],
                    }
                },
                "날짜": {"date": {}},
                "태그": {
                    "multi_select": {
                        "options": [
                            {"name": tag_name, "color": color}
                            for tag_name, color in [
                                ("Work", "blue"),
                                ("Personal", "green"),
                                ("Study", "purple"),
                                ("Health", "red"),
                                ("Meeting", "yellow"),
                                ("Other", "gray"),
                            ]
                        ]
                    }
                },
                "주차": {"rich_text": {}},
            },
        )

        db_id = response["id"]
        self.database_id = db_id
        self.config.notion.database_id = db_id
        self.config.save()
        return db_id

    def sync_week_to_notion(self, week: WeeklyTaskList) -> WeeklyTaskList:
        """Sync an entire weekly task list to Notion.

        Creates or updates pages for each task. Returns updated week
        with notion_page_id populated on tasks.
        """
        if not self.database_id:
            raise ValueError("Database ID not set. Run 'checkweek setup-notion' first.")

        for task in week.tasks:
            if task.notion_page_id:
                self._update_notion_page(task, week)
            else:
                page_id = self._create_notion_page(task, week)
                task.notion_page_id = page_id

        week.synced_to_notion = True
        return week

    def _create_notion_page(self, task: Task, week: WeeklyTaskList) -> str:
        """Create a new Notion page for a task."""
        properties = self._build_properties(task, week)
        response = self.client.pages.create(
            parent={"database_id": self.database_id},
            properties=properties,
        )
        return response["id"]

    def _update_notion_page(self, task: Task, week: WeeklyTaskList) -> None:
        """Update an existing Notion page for a task."""
        properties = self._build_properties(task, week)
        self.client.pages.update(
            page_id=task.notion_page_id,
            properties=properties,
        )

    def _build_properties(self, task: Task, week: WeeklyTaskList) -> dict:
        """Build Notion properties dict for a task."""
        properties: dict[str, Any] = {
            "할 일": {"title": [{"text": {"content": task.title}}]},
            "상태": {"status": {"name": STATUS_TO_NOTION[task.status]}},
            "태그": {
                "multi_select": [{"name": TAG_TO_NOTION.get(task.tag, "Other")}]
            },
            "주차": {
                "rich_text": [
                    {
                        "text": {
                            "content": f"{week.week_start} ~ {week.week_end}"
                        }
                    }
                ]
            },
        }

        if task.due_date:
            properties["날짜"] = {"date": {"start": task.due_date}}

        return properties

    def fetch_tasks_from_notion(self) -> list[dict]:
        """Fetch all tasks from the Notion database."""
        if not self.database_id:
            raise ValueError("Database ID not set.")

        results = []
        has_more = True
        start_cursor = None

        while has_more:
            kwargs: dict[str, Any] = {"database_id": self.database_id}
            if start_cursor:
                kwargs["start_cursor"] = start_cursor

            response = self.client.databases.query(**kwargs)
            results.extend(response["results"])
            has_more = response.get("has_more", False)
            start_cursor = response.get("next_cursor")

        return results

    def parse_notion_task(self, page: dict) -> Task:
        """Parse a Notion page into a Task object."""
        props = page["properties"]

        title = ""
        if props.get("할 일", {}).get("title"):
            title = props["할 일"]["title"][0]["plain_text"]

        status = TaskStatus.TODO
        if props.get("상태", {}).get("status"):
            notion_status = props["상태"]["status"]["name"]
            status = NOTION_TO_STATUS.get(notion_status, TaskStatus.TODO)

        tag = TaskTag.OTHER
        if props.get("태그", {}).get("multi_select"):
            tag_name = props["태그"]["multi_select"][0]["name"]
            for t, n in TAG_TO_NOTION.items():
                if n == tag_name:
                    tag = t
                    break

        due_date = None
        if props.get("날짜", {}).get("date"):
            due_date = props["날짜"]["date"]["start"]

        return Task(
            title=title,
            status=status,
            tag=tag,
            due_date=due_date,
            notion_page_id=page["id"],
        )
