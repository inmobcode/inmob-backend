from flask import jsonify, request
from marshmallow import ValidationError

from app.blueprints.tasks import bp
from app.schemas.task import TaskSchema, TaskUpdateSchema
from app.services import task_service
from app.utils.tenancy import current_agency_id, current_user_id


def serialize(task, names: dict[str, str]) -> dict:
    return {
        "id": task.id,
        "title": task.title,
        "notes": task.notes,
        "dueDate": task.due_date.isoformat() if task.due_date else None,
        "doneAt": task.done_at.isoformat() + "Z" if task.done_at else None,
        "overdue": task_service.is_overdue(task),
        "assignedAgentId": task.assigned_agent_id,
        "createdBy": task.created_by,
        "client": {"id": task.client_id, "name": names.get(task.client_id, "")} if task.client_id else None,
        "createdAt": task.created_at.isoformat() + "Z",
    }


def _one(task) -> dict:
    return serialize(task, task_service.client_names([task]))


def _load(schema):
    try:
        return schema.load(request.get_json(silent=True) or {}), None
    except ValidationError as err:
        return None, (jsonify({"message": "Validation error", "errors": err.messages}), 400)


@bp.route("/", methods=["GET"])
def list_tasks():
    """`?status=open|done|all`, `?clientId=…`, `?assignedTo=me|<userId>`."""
    assigned_to = request.args.get("assignedTo")
    if assigned_to == "me":
        assigned_to = current_user_id()
    tasks = task_service.list_tasks(
        current_agency_id(),
        status=request.args.get("status", "open"),
        client_id=request.args.get("clientId"),
        assigned_to=assigned_to,
    )
    names = task_service.client_names(tasks)
    return jsonify([serialize(task, names) for task in tasks])


@bp.route("/", methods=["POST"])
def create_task():
    data, error = _load(TaskSchema())
    if error:
        return error
    try:
        task = task_service.create_task(current_agency_id(), current_user_id(), data)
    except task_service.TaskError as err:
        return jsonify({"message": err.message}), err.status_code
    return jsonify(_one(task)), 201


@bp.route("/<task_id>", methods=["PATCH"])
def update_task(task_id):
    data, error = _load(TaskUpdateSchema())
    if error:
        return error
    try:
        task = task_service.update_task(current_agency_id(), task_id, current_user_id(), data)
    except task_service.TaskError as err:
        return jsonify({"message": err.message}), err.status_code
    return jsonify(_one(task))


@bp.route("/<task_id>", methods=["DELETE"])
def delete_task(task_id):
    try:
        task_service.delete_task(current_agency_id(), task_id)
    except task_service.TaskError as err:
        return jsonify({"message": err.message}), err.status_code
    return "", 204
