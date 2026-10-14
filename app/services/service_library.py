"""An agency's library of services and experiences (butler, chef, yacht…)."""
from app.extensions import db
from app.models.offer import OfferService
from app.models.service import Service


class ServiceError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def list_services(agency_id: str):
    return Service.query.filter_by(agency_id=agency_id).order_by(Service.name).all()


def get_service(agency_id: str, service_id: str) -> Service:
    service = Service.query.filter_by(id=service_id, agency_id=agency_id).first()
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
    """Offers keep their own copy of each service, so they're not affected."""
    service = get_service(agency_id, service_id)
    # Explicit rather than trusting ON DELETE SET NULL, which not every database enforces.
    OfferService.query.filter_by(service_id=service.id).update({"service_id": None})
    db.session.delete(service)
    db.session.commit()
