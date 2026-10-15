from datetime import date

from app.extensions import db
from app.models import Client, Task
from app.services import crm_service, feed
from app.utils import trash
from app.utils.tenancy import agent_scope, is_member


class TaskError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def visible_tasks(query):
    """An AGENT sees the tasks assigned to them or that they created."""
    scope = agent_scope()
    if scope:
        return query.filter(db.or_(Task.assigned_agent_id == scope, Task.created_by == scope))
    return query


def list_tasks(
    agency_id: str,
    *,
    status: str = "open",
    client_id: str | None = None,
    assigned_to: str | None = None,
) -> list[Task]:
    query = visible_tasks(Task.query.filter_by(agency_id=agency_id))
    if status == "open":
        query = query.filter(Task.done_at.is_(None))
    elif status == "done":
        query = query.filter(Task.done_at.isnot(None))
    if client_id:
        query = query.filter(Task.client_id == client_id)
    if assigned_to:
        query = query.filter(Task.assigned_agent_id == assigned_to)
    # Dated ones first (soonest, so overdue lead), the undated after.
    return query.order_by(Task.due_date.is_(None), Task.due_date, Task.created_at.desc()).limit(500).all()


def get_task(agency_id: str, task_id: str) -> Task:
    task = visible_tasks(Task.query.filter_by(id=task_id, agency_id=agency_id)).first()
    if task is None:
        raise TaskError("Task not found", 404)
    return task


def _check_assignee(agency_id: str, target: str | None) -> None:
    scope = agent_scope()
    if scope and target not in (scope, None):
        raise TaskError("Forbidden", 403)
    if target and not is_member(agency_id, target):
        raise TaskError("Agent not found", 404)


def create_task(agency_id: str, created_by: str, data: dict) -> Task:
    if data.get("client_id"):
        # Goes through the client's own visibility, so an agent can't pin a task on someone else's client.
        try:
            crm_service.get_client(agency_id, data["client_id"])
        except crm_service.ClientError as err:
            raise TaskError(err.message, err.status_code) from err

    assigned = data.get("assigned_agent_id", created_by) if "assigned_agent_id" in data else created_by
    _check_assignee(agency_id, assigned)

    task = Task(
        agency_id=agency_id,
        client_id=data.get("client_id"),
        assigned_agent_id=assigned,
        created_by=created_by,
        title=data["title"].strip(),
        notes=data.get("notes"),
        due_date=data.get("due_date"),
    )
    db.session.add(task)
    db.session.commit()
    feed.notify_task_assigned(task, created_by)
    return task


def update_task(agency_id: str, task_id: str, user_id: str, data: dict) -> Task:
    task = get_task(agency_id, task_id)
    previous_assignee = task.assigned_agent_id

    if "assigned_agent_id" in data:
        _check_assignee(agency_id, data["assigned_agent_id"])
        task.assigned_agent_id = data["assigned_agent_id"]
    if "title" in data:
        task.title = data["title"].strip()
    if "notes" in data:
        task.notes = data["notes"]
    if "due_date" in data:
        task.due_date = data["due_date"]
    if "done" in data:
        task.done_at = trash.now() if data["done"] else None

    db.session.commit()
    if task.assigned_agent_id != previous_assignee:
        feed.notify_task_assigned(task, user_id)
    return task


def delete_task(agency_id: str, task_id: str) -> None:
    task = get_task(agency_id, task_id)
    db.session.delete(task)
    db.session.commit()


def is_overdue(task: Task) -> bool:
    return task.done_at is None and task.due_date is not None and task.due_date < date.today()


def client_names(tasks: list[Task]) -> dict[str, str]:
    ids = {task.client_id for task in tasks if task.client_id}
    if not ids:
        return {}
    return {row.id: row.name for row in Client.query.filter(Client.id.in_(ids)).all()}
