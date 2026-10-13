from datetime import datetime, timezone

from app.extensions import db
from app.models.offer import Offer, OfferProperty, OfferSection
from app.models.property import Property
from app.schemas.property import PropertySchema, PublicPropertySchema
from app.services import crm_service

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
            text=section_data.get("text"),
            position=section_index,
        )
        offer.sections.append(section)

        for item in section_data.get("properties", []):
            prop = Property.query.filter_by(id=item["property_id"], agency_id=agency_id).first()
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


def list_offers(agency_id: str):
    return Offer.query.filter_by(agency_id=agency_id).order_by(Offer.created_at.desc()).all()


def get_offer(agency_id: str, offer_id: str) -> Offer:
    offer = Offer.query.filter_by(id=offer_id, agency_id=agency_id).first()
    if offer is None:
        raise OfferError("Offer not found", 404)
    return offer


def create_offer(agency_id: str, created_by: str, data: dict) -> Offer:
    offer = Offer(
        agency_id=agency_id,
        created_by=created_by,
        title=data["title"],
        operation=data.get("operation", "BOTH"),
        currency=data.get("currency", "USD"),
        show_price=data.get("show_price", True),
        branded=data.get("branded", True),
        expires_at=_naive_utc(data.get("expires_at")),
        welcome_title=data.get("welcome_title"),
        welcome_date_label=data.get("welcome_date_label"),
        welcome_content=data.get("welcome_content"),
        client_name=data.get("client_name"),
        client_email=data.get("client_email"),
        client_phone=data.get("client_phone"),
        status="DRAFT",
    )
    db.session.add(offer)
    _sync_sections(agency_id, offer, data.get("sections", []))
    db.session.commit()
    return offer


def update_offer(agency_id: str, offer_id: str, data: dict) -> Offer:
    offer = get_offer(agency_id, offer_id)

    sections = data.pop("sections", None)
    if "expires_at" in data:
        data["expires_at"] = _naive_utc(data["expires_at"])

    for field, value in data.items():
        setattr(offer, field, value)

    if sections is not None:
        _sync_sections(agency_id, offer, sections)
    elif "operation" in data:
        for offer_property in offer.offer_properties:
            _check_operation(offer, offer_property.property)

    db.session.commit()
    return offer


def delete_offer(agency_id: str, offer_id: str) -> None:
    offer = get_offer(agency_id, offer_id)
    db.session.delete(offer)
    db.session.commit()


def send_offer(agency_id: str, offer_id: str) -> Offer:
    offer = get_offer(agency_id, offer_id)
    if offer.status != "DRAFT":
        raise OfferError("Only draft offers can be sent", 400)
    offer.status = "SENT"
    db.session.commit()
    return offer


def get_offer_by_token(token: str) -> Offer:
    offer = Offer.query.filter_by(token=token).first()
    if offer is None or offer.status == "DRAFT":
        raise OfferError("Offer not found", 404)

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if offer.expires_at and offer.expires_at < now and offer.status not in TERMINAL_STATUSES:
        offer.status = "EXPIRED"
        db.session.commit()
    elif offer.status == "SENT":
        offer.status = "VIEWED"
        db.session.commit()

    return offer


def create_public_offer_inquiry(token: str, data: dict) -> Offer:
    """Visitor hits "Contact us" on the public offer page — dual-writes into
    the CRM (Client + Interaction + Inquiry), same as a property inquiry
    from the public portal (Phase 4), just tagged to this offer."""
    offer = Offer.query.filter_by(token=token).first()
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
                "text": section.text,
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
        "welcomeContent": offer.welcome_content,
        "clientName": offer.client_name,
        "clientEmail": offer.client_email,
        "clientPhone": offer.client_phone,
        "sections": sections_payload,
        "total": sum(all_display_prices) if all_display_prices else None,
        "createdAt": offer.created_at.isoformat(),
        "updatedAt": offer.updated_at.isoformat(),
    }

    if not public:
        data["agencyId"] = offer.agency_id
        data["clientId"] = offer.client_id

    return data
