"""Fixed option catalogs mirroring kennedys-loggia's property form checkboxes/selects.

These are plain string catalogs (not DB-backed lookup tables) — same approach
Kennedys uses: checkbox groups against a hardcoded option list, stored as a
JSON array column on the row, not a normalized many-to-many.
"""

LOCATION_FEATURES = (
    "Waterfront",
    "Prime Waterfront",
    "Beachfront",
    "Resort Access",
    "Walking distance to a village",
    "Private",
    "City",
    "Downtown",
    "Seaside",
    "Mountain",
    "Private beach/sea access",
    "Walking distance to the beach",
    "Walking distance to town",
    "Ski in/Ski out",
    "Sea Access",
    "Beach Access",
)

VIEW_OPTIONS = (
    "Sea View",
    "Direct Sea View",
    "City View",
    "Nature View",
    "Panoramic View",
    "Lake View",
    "Forest View",
    "Sunset View",
    "Sunrise View",
    "Mountain View",
    "Town View",
    "Ocean View",
    "Water View",
)

OUTDOOR_AMENITIES = (
    "Pool",
    "Rooftop Pool",
    "Plunge Pool",
    "Pool Bar",
    "Heated pool",
    "Jacuzzi",
    "Outdoor kitchen",
    "Outdoor Gym",
    "Dining & Lounge Area",
    "Cinema",
    "Ice plunge",
    "Sauna",
    "Playground",
    "Helipad",
    "Private Dock",
    "Access to a dock",
    "Private Parking",
    "BBQ",
    "Tennis Court",
    "Basketball Court",
    "Ski in/out",
    "Sun Deck",
    "Fire Pit",
    "Outdoor Fireplace",
    "Roof Terrace",
    "Yoga Shala",
    "Landscaped Gardens",
    "Boxing Ring",
    "Golf",
    "Beach Volleyball Court",
    "Children's Play Area",
    "Outdoor Shower",
    "Sound System",
    "Gated Property",
    "Table tennis",
    "CCTV Camera",
)

INDOOR_AMENITIES = (
    "Indoor Pool",
    "Gym",
    "Fitness room",
    "Hammam",
    "Sauna",
    "Massage room",
    "Home Cinema",
    "Club",
    "Elevator",
    "Spa Area",
    "Professional Kitchen",
    "Wine Cellar",
    "Fireplace",
    "Ski Room",
    "Cigar Lounge",
    "Laundry Facilities",
    "Spa and Wellness Centre",
    "Game Room",
    "Billiard",
    "Playroom",
    "Music/Recording Studio",
    "Staff quarters",
    "Smart Home Technology",
    "Office/Workspace",
    "Children's Play Area",
    "Alarm System",
    "Safe Boxes",
    "Fully equipped kitchen",
    "Airconditioning",
    "Underfloor heating",
    "Solar panels",
    "Security cameras",
    "Central heating",
    "Double glazed windows",
    "Security system",
    "Wood flooring",
    "Internal staircase",
)

PROPERTY_STATUS_RENT = (
    "Fully staffed",
    "Semi staffed",
    "Housekeeping & Daily cleaning",
    "Suitable for children",
    "Suitable for events",
    "Suitable for the disabled",
    "Pet friendly",
)

PROPERTY_STATUS_SALE = (
    "For Sale",
    "Under Contract",
    "Sold",
    "New Construction",
    "Renovated",
    "Investment Property",
    "Luxury Property",
)

# Trimmed from Kennedys' original list: dropped luxury-concierge-only entries
# (chef/butler, welcome drinks/basket, in-villa dining, personal trainer, yoga
# instructor, spa treatments, boat/yacht arrangement, event planning) that
# don't apply to a typical small/medium agency's rental.
INCLUDED_SERVICES = (
    "Housekeeping",
    "Daily housekeeping",
    "Pool Maintenance",
    "Change of linen",
    "Change of towels",
    "24/7 Reception",
    "Airport transfer",
    "Concierge service",
    "Security",
    "Gardener",
    "Babysitting",
    "Laundry service",
    "Daily breakfast",
    "Car rental arrangement",
    "Grocery pre-stocking",
)

POOL_TYPES = (
    "Private",
    "Shared",
    "Infinity",
    "Heated",
    "Plunge Pool",
    "Indoor Pool",
    "Child-Friendly Pool",
)

JACUZZI_TYPES = (
    "Portable Hot Tub",
    "In-Ground Jacuzzi",
    "Portable Jacuzzi",
    "Custom-Built Jacuzzi",
    "Outdoor Jacuzzi",
    "Indoor Jacuzzi",
    "Jacuzzi with Waterfall",
    "Jacuzzi with LED Lighting",
)

# Real-estate's own pool-block checkbox lists are slightly different from the
# shared Main-tab outdoor/indoor amenities catalogs above (a few extra
# beach/sea-access options) — kept separate on purpose, matching the source.
REAL_ESTATE_OUTDOOR_FACILITIES = (
    "Helipad",
    "Private Dock",
    "Private Beach Access",
    "Private Sea Access",
    "Beach Access",
    "Sea Access",
    "Ski in/out",
    "Sun Deck",
    "Fire Pit",
    "Outdoor Fireplace",
    "Roof Terrace",
    "Yoga Shala",
    "Outdoor Kitchen",
    "BBQ",
    "Tennis Court",
    "Landscaped Gardens",
    "Boxing Ring",
    "Basketball Court",
    "Golf",
    "Paddle court",
    "Beach Volleyball Court",
    "Children's Play Area",
)

REAL_ESTATE_INDOOR_FACILITIES = (
    "Elevator",
    "Home Cinema",
    "Spa and Wellness Centre",
    "Sauna",
    "Hammam",
    "Massage room",
    "Wine Cellar",
    "Game Room",
    "Billiard",
    "Club",
    "Music/Recording Studio",
    "Professional Kitchen",
    "Staff quarters",
    "Smart Home Technology",
    "Office/Workspace",
    "Children's Play Area",
    "Alarm System",
    "Safe Boxes",
    "Fully equipped kitchen",
    "Airconditioning",
)

ACCOMMODATION_TYPES = (
    "VILLA",
    "CHALET",
    "APARTMENT",
    "SEASONAL_PROPERTY",
    "HOUSE",
    "PENTHOUSE",
    "MAISONETTE",
    "DETACHED_VILLA",
    "SEMI_DETACHED_VILLA",
    "HOTEL",
    "HOTEL_ROOM",
)

# Trimmed from Kennedys' original catalog: dropped ultra-luxury/historic
# categories (Castle, Chateau, Manor, Estate, Luxury Estates, Villa Complex,
# Residential Complex, Cottage, Farm) that targeted their Greek-islands
# portfolio specifically, not a generic small/medium agency's listings.
# Added back Commercial/Office, which Kennedys' own catalog has no use for
# (they don't sell commercial real estate) but most agencies need.
REAL_ESTATE_TYPES = (
    "HOUSE",
    "APARTMENT",
    "PENTHOUSE",
    "VILLA",
    "TOWNHOUSE",
    "CONDO",
    "MAISONETTE",
    "DETACHED_VILLA",
    "SEMI_DETACHED_VILLA",
    "BUILDING",
    "LAND",
    "COMMERCIAL",
    "OFFICE",
    "HOTEL",
)

# Union of both — the DB column just needs to accept whichever catalog applies
# for the property's own listing_type; schema-level validation picks the
# right catalog per request (see schemas/property.py).
ALL_PROPERTY_TYPES = tuple(sorted(set(ACCOMMODATION_TYPES) | set(REAL_ESTATE_TYPES)))

LOCATION_CATEGORY_OPTIONS = (
    "PRIVATE",
    "PART_OF_COMPLEX",
    "PART_OF_HOTEL",
    "PART_OF_RESORT",
)

ENERGY_CERTIFICATE_OPTIONS = (
    "A++",
    "A+",
    "A",
    "B+",
    "B",
    "C",
    "D",
    "E",
    "F",
    "G",
    "under_publication",
)

POOL_ENTITY_TYPES = ("POOL", "JACUZZI")

RECOMMENDATION_PRIORITIES = ("LOW", "MEDIUM", "HIGH")
RECOMMENDATION_STATUSES = ("PROPOSED", "APPROVED", "DONE")

PHOTO_SECTIONS = (
    "GENERAL",
    "BEDROOMS",
    "INDOOR_LIVING",
    "POOL",
    "OUTDOOR",
    "ADDED_FACILITIES",
    "VIEWS",
)
