from marshmallow import Schema, fields, validate, validates_schema, ValidationError


class TaskSchema(Schema):
    title = fields.Str(required=True, validate=validate.Length(min=2, max=200))
    notes = fields.Str(allow_none=True, validate=validate.Length(max=2000))
    due_date = fields.Date(data_key="dueDate", allow_none=True)
    client_id = fields.Str(data_key="clientId", allow_none=True)
    assigned_agent_id = fields.Str(data_key="assignedAgentId", allow_none=True)


class TaskUpdateSchema(Schema):
    title = fields.Str(validate=validate.Length(min=2, max=200))
    notes = fields.Str(allow_none=True, validate=validate.Length(max=2000))
    due_date = fields.Date(data_key="dueDate", allow_none=True)
    assigned_agent_id = fields.Str(data_key="assignedAgentId", allow_none=True)
    done = fields.Bool()

    @validates_schema
    def not_empty(self, data, **kwargs):
        if not data:
            raise ValidationError("Nothing to update")
