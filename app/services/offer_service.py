from datetime import datetime, timezone

from sqlalchemy.orm import selectinload

from app import i18n
from app.extensions import db
from app.models.agency import Agency
from app.models.booking import Booking
from app.models.client import Client, Interaction
from app.models.offer import Offer, OfferProperty, OfferSection, OfferService
from app.models.service import Service
from app.models.property import Property
from app.schemas.property import PropertySchema, PublicPropertySchema
from app.services import crm_service, feed
from app.services.property_service import property_load_options
from app.services.notifications import notify_offer_sent, staff_locale
from app.utils import rich_text, trash
from app.utils.tenancy import agent_scope

_property_schema = PropertySchema()
_public_property_schema = PublicPropertySchema()

TERMINAL_STATUSES = ("EXPIRED",)


class OfferError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _naive_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _apply_discount(price: float | None, discount_type: str, discount_value: float) -> float | None:
    if price is None:
        return None
    if discount_type == "PERCENT":
        return round(price * (1 - discount_value / 100), 2)
    if discount_type == "FIXED":
        return max(round(price - discount_value, 2), 0)
    return price


LISTING_NAMES = {"SALE": "venta", "RENT": "alquiler"}


def _check_operation(offer: Offer, prop: Property) -> None:
    """A sale offer only holds properties for sale, a rental one only rentals."""
    if offer.operation != "BOTH" and prop.listing_type != offer.operation:
        raise OfferError(
            f"«{prop.title}» es de {LISTING_NAMES.get(prop.listing_type, prop.listing_type)} "
            f"y la oferta es de {LISTING_NAMES[offer.operation]}",
            400,
        )


def _sync_sections(agency_id: str, offer: Offer, sections_data: list[dict]) -> None:
    offer.sections.clear()
    offer.offer_properties.clear()

    position = 0
    for section_index, section_data in enumerate(sections_data):
        section = OfferSection(
            title=section_data.get("title"),
            text=rich_text.sanitize(section_data.get("text"), inline=True),
            position=section_index,
        )
        offer.sections.append(section)

        for item in section_data.get("properties", []):
            prop_query = Property.query.filter_by(id=item["property_id"], agency_id=agency_id)
            if agent_scope():  # an agent can only offer what's assigned to them
                prop_query = prop_query.filter(Property.assigned_agent_id == agent_scope())
            prop = prop_query.first()
            if prop is None:
                raise OfferError(f"Property {item['property_id']} not found", 404)
            _check_operation(offer, prop)
            offer.offer_properties.append(
                OfferProperty(
                    property_id=prop.id,
                    section=section,
                    position=position,
                    price_override=item.get("price_override"),
                    discount_type=item.get("discount_type", "NONE"),
                    discount_value=item.get("discount_value", 0),
                    security_deposit=item.get("security_deposit"),
                    bottom_text=item.get("bottom_text"),
                )
            )
            position += 1


def _assign_client(agency_id: str, offer: Offer, client_id: str | None) -> None:
    """Links the offer to a CRM client and copies its contact details, or
    unlinks it (and clears them) when client_id is None."""
    if client_id is None:
        offer.client_id = None
        offer.client_name = None
        offer.client_email = None
        offer.client_phone = None
        return
    client = crm_service.visible_clients(Client.query.filter_by(id=client_id, agency_id=agency_id)).first()
    if client is None:
        raise OfferError("Client not found", 404)
    offer.client_id = client.id
    offer.client_name = client.name
    offer.client_email = client.email
    offer.client_phone = client.phone


def _sync_services(agency_id: str, offer: Offer, items: list[dict]) -> None:
    """Replaces the offer's services with the ones sent, in order. Each keeps
    the copy the editor sent; the link to the library is kept only when that
    service is this agency's."""
    offer.offer_services.clear()
    ids = {item["service_id"] for item in items if item.get("service_id")}
    own = (
        {service.id for service in Service.query.filter(
                Service.agency_id == agency_id, Service.deleted_at.is_(None), Service.id.in_(ids)
            ).all()}
        if ids
        else set()
    )
    for position, item in enumerate(items):
        offer.offer_services.append(
            OfferService(
                service_id=item.get("service_id") if item.get("service_id") in own else None,
                position=position,
                name=item["name"],
                type=item.get("type", "OTHER"),
                description=item.get("description"),
                image_url=item.get("image_url"),
                unit=item.get("unit", "SERVICE"),
                unit_price=item.get("unit_price"),
                quantity=item.get("quantity", 1),
                date=item.get("date"),
                note=item.get("note"),
            )
        )


def _serialize_services(offer: Offer, *, public: bool) -> tuple[list[dict], float | None]:
    """The offer's services and what they add up to (only when prices are shown)."""
    payload = []
    total = 0.0
    priced = False
    for item in offer.offer_services:
        line = item.unit_price * item.quantity if item.unit_price is not None else None
        if line is not None:
            total += line
            priced = True
        entry = {
            "id": item.id,
            "name": item.name,
            "type": item.type,
            "description": item.description,
            "imageUrl": item.image_url,
            "unit": item.unit,
            "quantity": item.quantity,
            "date": item.date.isoformat() if item.date else None,
            "note": item.note,
            "unitPrice": item.unit_price if (offer.show_price or not public) else None,
            "total": line if (offer.show_price or not public) else None,
        }
        if not public:
            entry["serviceId"] = item.service_id
        payload.append(entry)
    shown_total = total if priced and (offer.show_price or not public) else None
    return payload, shown_total


def _offer_load_options():
    """Everything serialize_offer reads, in a handful of queries instead of
    several per property in the offer."""
    return (
        selectinload(Offer.sections),
        selectinload(Offer.offer_services),
        selectinload(Offer.offer_properties)
        .joinedload(OfferProperty.property)
        .options(*property_load_options()),
    )


def _own_offers(query):
    """An AGENT sees only the offers they made."""
    scope = agent_scope()
    return query.filter(Offer.created_by == scope) if scope else query


def list_offers(agency_id: str):
    return (
        _own_offers(Offer.query.options(*_offer_load_options()).filter_by(agency_id=agency_id, deleted_at=None))
        .order_by(Offer.created_at.desc())
        .all()
    )


def get_offer(agency_id: str, offer_id: str, *, trashed: bool = False) -> Offer:
    """A live offer, or with trashed=True one in the trash."""
    query = _own_offers(Offer.query.options(*_offer_load_options()).filter_by(id=offer_id, agency_id=agency_id))
    query = query.filter(Offer.deleted_at.isnot(None) if trashed else Offer.deleted_at.is_(None))
    offer = query.first()
    if offer is None:
        raise OfferError("Offer not found", 404)
    return offer


def create_offer(agency_id: str, created_by: str, data: dict) -> Offer:
    offer = Offer(
        agency_id=agency_id,
        created_by=created_by,
        title=data["title"],
        reference_code=data.get("reference_code"),
        operation=data.get("operation", "BOTH"),
        currency=data.get("currency", "USD"),
        show_price=data.get("show_price", True),
        branded=data.get("branded", True),
        expires_at=_naive_utc(data.get("expires_at")),
        welcome_title=data.get("welcome_title"),
        welcome_date_label=data.get("welcome_date_label"),
        welcome_content=rich_text.sanitize(data.get("welcome_content")),
        client_name=data.get("client_name"),
        client_email=data.get("client_email"),
        client_phone=data.get("client_phone"),
        status="DRAFT",
    )
    db.session.add(offer)
    if data.get("client_id"):
        _assign_client(agency_id, offer, data["client_id"])
    _sync_sections(agency_id, offer, data.get("sections", []))
    _sync_services(agency_id, offer, data.get("services", []))
    db.session.commit()
    return offer


def update_offer(agency_id: str, offer_id: str, data: dict) -> Offer:
    offer = get_offer(agency_id, offer_id)

    sections = data.pop("sections", None)
    services = data.pop("services", None)
    if "client_id" in data:
        _assign_client(agency_id, offer, data.pop("client_id"))
    if "expires_at" in data:
        data["expires_at"] = _naive_utc(data["expires_at"])
    if "welcome_content" in data:
        data["welcome_content"] = rich_text.sanitize(data["welcome_content"])

    for field, value in data.items():
        setattr(offer, field, value)

    if services is not None:
        _sync_services(agency_id, offer, services)
    if sections is not None:
        _sync_sections(agency_id, offer, sections)
    elif "operation" in data:
        for offer_property in offer.offer_properties:
            _check_operation(offer, offer_property.property)

    db.session.commit()
    return offer


def delete_offer(agency_id: str, offer_id: str) -> None:
    """Moves the offer to the trash; its public link stops working until it's restored."""
    offer = get_offer(agency_id, offer_id)
    offer.deleted_at = trash.now()
    db.session.commit()


def list_trashed_offers(agency_id: str):
    purge_trashed_offers(agency_id)
    return (
        _own_offers(
            Offer.query.options(*_offer_load_options()).filter(
                Offer.agency_id == agency_id, Offer.deleted_at.isnot(None)
            )
        )
        .order_by(Offer.deleted_at.desc())
        .all()
    )


def restore_offer(agency_id: str, offer_id: str) -> Offer:
    offer = get_offer(agency_id, offer_id, trashed=True)
    offer.deleted_at = None
    db.session.commit()
    return offer


def _delete_for_good(offer: Offer) -> None:
    # Bookings made from it stay; they just stop pointing at it.
    Booking.query.filter_by(offer_id=offer.id).update({"offer_id": None})
    db.session.delete(offer)


def delete_offer_forever(agency_id: str, offer_id: str) -> None:
    _delete_for_good(get_offer(agency_id, offer_id, trashed=True))
    db.session.commit()


def purge_trashed_offers(agency_id: str) -> None:
    """Deletes for good what has been in the trash longer than TRASH_DAYS."""
    for offer in Offer.query.filter(
        Offer.agency_id == agency_id,
        Offer.deleted_at.isnot(None),
        Offer.deleted_at < trash.purge_cutoff(),
    ).all():
        _delete_for_good(offer)
    db.session.commit()


def send_offer(agency_id: str, offer_id: str) -> Offer:
    """Publishes a draft's link and emails it to the offer's client. An offer
    already out can be sent again, which only re-emails the client."""
    offer = get_offer(agency_id, offer_id)
    if offer.status in TERMINAL_STATUSES:
        raise OfferError("Esta oferta venció", 400)
    client = db.session.get(Client, offer.client_id) if offer.client_id else None
    if offer.status != "DRAFT" and client is None:
        raise OfferError("La oferta ya está publicada y no tiene cliente al que enviársela", 400)
    if offer.status == "DRAFT":
        offer.status = "SENT"
    if client is not None:
        # Leave a trace in the client's history, like inquiries do.
        db.session.add(
            Interaction(
                client_id=client.id,
                type="EMAIL",
                content=i18n.t(
                    staff_locale(db.session.get(Agency, offer.agency_id)),
                    "note.offer_sent",
                    offer=offer.title,
                    email=client.email,
                ),
            )
        )
    db.session.commit()
    notify_offer_sent(offer)
    return offer


def get_offer_by_token(token: str) -> Offer:
    offer = Offer.query.options(*_offer_load_options()).filter_by(token=token, deleted_at=None).first()
    if offer is None or offer.status == "DRAFT":
        raise OfferError("Offer not found", 404)

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if offer.expires_at and offer.expires_at < now and offer.status not in TERMINAL_STATUSES:
        offer.status = "EXPIRED"
        db.session.commit()
    elif offer.status == "SENT":
        offer.status = "VIEWED"
        db.session.commit()
        feed.notify_offer_viewed(offer)

    return offer


def create_public_offer_inquiry(token: str, data: dict) -> Offer:
    """Visitor hits "Contact us" on the public offer page — dual-writes into
    the CRM (Client + Interaction + Inquiry), same as a property inquiry
    from the public portal (Phase 4), just tagged to this offer."""
    offer = Offer.query.filter_by(token=token, deleted_at=None).first()
    if offer is None or offer.status == "DRAFT":
        raise OfferError("Offer not found", 404)
    if offer.status == "EXPIRED":
        raise OfferError("This offer has expired", 400)

    inquiry = crm_service.log_inquiry(
        offer.agency_id,
        name=data["name"],
        email=data["email"],
        phone=data.get("phone"),
        message=data.get("message"),
        inquiry_type="OFFER",
        source="OFFER",
        offer_id=offer.id,
        locale=i18n.request_locale(),
    )

    if not offer.client_id:
        offer.client_id = inquiry.client_id
    if not offer.client_name:
        offer.client_name = data["name"]
    if not offer.client_email:
        offer.client_email = data["email"]

    db.session.commit()
    return offer


def serialize_offer(offer: Offer, *, public: bool = False) -> dict:
    property_schema = _public_property_schema if public else _property_schema

    properties_by_section: dict[str | None, list[OfferProperty]] = {}
    for offer_property in offer.offer_properties:
        # The client doesn't see properties the agency moved to the trash.
        if public and offer_property.property.deleted_at is not None:
            continue
        properties_by_section.setdefault(offer_property.section_id, []).append(offer_property)

    all_display_prices: list[float] = []

    def _serialize_item(offer_property: OfferProperty) -> dict:
        base_price = (
            offer_property.price_override
            if offer_property.price_override is not None
            else offer_property.property.price
        )
        has_discount = offer_property.discount_type != "NONE" and offer_property.discount_value
        display_price = (
            _apply_discount(base_price, offer_property.discount_type, offer_property.discount_value)
            if offer.show_price
            else None
        )
        if display_price is not None:
            all_display_prices.append(display_price)

        return {
            "id": offer_property.id,
            "propertyId": offer_property.property_id,
            "priceOverride": offer_property.price_override,
            "discountType": offer_property.discount_type,
            "discountValue": offer_property.discount_value,
            "securityDeposit": offer_property.security_deposit,
            "bottomText": offer_property.bottom_text,
            "position": offer_property.position,
            "initialPrice": base_price if (offer.show_price and has_discount) else None,
            "displayPrice": display_price,
            "property": property_schema.dump(offer_property.property),
        }

    sections_payload = []
    for section in offer.sections:
        sections_payload.append(
            {
                "id": section.id,
                "title": section.title,
                "text": rich_text.sanitize(section.text, inline=True),
                "position": section.position,
                "properties": [
                    _serialize_item(op) for op in properties_by_section.get(section.id, [])
                ],
            }
        )

    ungrouped = properties_by_section.get(None, [])
    if ungrouped:
        sections_payload.append(
            {
                "id": None,
                "title": None,
                "text": None,
                "position": len(offer.sections),
                "properties": [_serialize_item(op) for op in ungrouped],
            }
        )

    services_payload, services_total = _serialize_services(offer, public=public)

    data = {
        "id": offer.id,
        "token": offer.token,
        "title": offer.title,
        "operation": offer.operation,
        "currency": offer.currency,
        "showPrice": offer.show_price,
        "branded": offer.branded,
        "status": offer.status,
        "expiresAt": offer.expires_at.isoformat() if offer.expires_at else None,
        "welcomeTitle": offer.welcome_title,
        "welcomeDateLabel": offer.welcome_date_label,
        # Also cleaned on the way out: text stored before the editor existed never went through it.
        "welcomeContent": rich_text.sanitize(offer.welcome_content),
        "clientName": offer.client_name,
        "clientEmail": offer.client_email,
        "clientPhone": offer.client_phone,
        "sections": sections_payload,
        "total": sum(all_display_prices) if all_display_prices else None,
        "services": services_payload,
        "servicesTotal": services_total,
        "createdAt": offer.created_at.isoformat(),
        "updatedAt": offer.updated_at.isoformat(),
    }

    if not public:
        data["agencyId"] = offer.agency_id
        data["clientId"] = offer.client_id
        data["referenceCode"] = offer.reference_code
        data["deletedAt"] = offer.deleted_at.isoformat() if offer.deleted_at else None

    return data
