"""An agency's library of services and experiences (butler, chef, yacht…)."""
from app.extensions import db
from app.models.offer import OfferService
from app.models.service import Service
from app.utils import trash


class ServiceError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def list_services(agency_id: str):
    return Service.query.filter_by(agency_id=agency_id, deleted_at=None).order_by(Service.name).all()


def get_service(agency_id: str, service_id: str, *, trashed: bool = False) -> Service:
    """A live service, or with trashed=True one in the trash."""
    query = Service.query.filter_by(id=service_id, agency_id=agency_id)
    query = query.filter(Service.deleted_at.isnot(None) if trashed else Service.deleted_at.is_(None))
    service = query.first()
    if service is None:
        raise ServiceError("Service not found", 404)
    return service


def create_service(agency_id: str, data: dict) -> Service:
    service = Service(agency_id=agency_id, **data)
    db.session.add(service)
    db.session.commit()
    return service


def update_service(agency_id: str, service_id: str, data: dict) -> Service:
    service = get_service(agency_id, service_id)
    for field, value in data.items():
        setattr(service, field, value)
    db.session.commit()
    return service


def delete_service(agency_id: str, service_id: str) -> None:
    """Moves the service to the trash. Offers keep their own copy of it, so they're not affected."""
    service = get_service(agency_id, service_id)
    service.deleted_at = trash.now()
    db.session.commit()


def list_trashed_services(agency_id: str):
    purge_trashed_services(agency_id)
    return (
        Service.query.filter(Service.agency_id == agency_id, Service.deleted_at.isnot(None))
        .order_by(Service.deleted_at.desc())
        .all()
    )


def restore_service(agency_id: str, service_id: str) -> Service:
    service = get_service(agency_id, service_id, trashed=True)
    service.deleted_at = None
    db.session.commit()
    return service


def _delete_for_good(service: Service) -> None:
    # Explicit rather than trusting ON DELETE SET NULL, which not every database enforces.
    OfferService.query.filter_by(service_id=service.id).update({"service_id": None})
    db.session.delete(service)


def delete_service_forever(agency_id: str, service_id: str) -> None:
    _delete_for_good(get_service(agency_id, service_id, trashed=True))
    db.session.commit()


def purge_trashed_services(agency_id: str) -> None:
    """Deletes for good what has been in the trash longer than TRASH_DAYS."""
    for service in Service.query.filter(
        Service.agency_id == agency_id,
        Service.deleted_at.isnot(None),
        Service.deleted_at < trash.purge_cutoff(),
    ).all():
        _delete_for_good(service)
    db.session.commit()
