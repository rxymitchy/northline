TRACKS = {
    "agency_partner": {
        "label": "Digital / marketing / web agency",
        "priority": 1,
        "keywords": [
            "digital marketing",
            "marketing agency",
            "web design",
            "web agency",
            "seo agency",
            "social media agency",
            "branding agency",
            "advertising agency",
        ],
        "industry_label": "Digital / marketing agency",
    },
    "software_contract": {
        "label": "Software / AI company",
        "priority": 2,
        "keywords": [
            "software company",
            "software development",
            "ai automation",
            "ai agency",
            "it company",
            "tech company",
            "systems integrator",
        ],
        "industry_label": "Software / AI",
    },
    "operational_pain": {
        "label": "Business with messy operations",
        "priority": 3,
        "keywords": [
            "real estate",
            "property",
            "clinic",
            "hospital",
            "dental",
            "school",
            "training",
            "college",
            "tour",
            "travel",
            "safari",
            "salon",
            "spa",
            "event",
            "ecommerce",
            "wholesale",
            "shop",
        ],
        "industry_label": "Operational business",
    },
}

NAMED_TARGETS = [
    {"name": "Bluegift Digital", "track": "agency_partner"},
    {"name": "Iconic Digital Marketing Agency", "track": "agency_partner"},
    {"name": "Digitally Freed Africa", "track": "agency_partner"},
    {"name": "Nairobi Marketing", "track": "agency_partner"},
    {"name": "Nevin Digital Marketing Agency", "track": "agency_partner"},
    {"name": "Netlit Digital Web Solutions", "track": "agency_partner"},
    {"name": "Nairobi Digital Cloud Web Designers Agency", "track": "agency_partner"},
    {"name": "Windand Developers", "track": "agency_partner"},
    {"name": "Origin Digital Agency", "track": "agency_partner"},
    {"name": "Kissor Digital", "track": "agency_partner"},
    {"name": "Pinch Africa", "track": "agency_partner"},
    {"name": "Glitex Solutions Limited", "track": "software_contract"},
    {"name": "Grafame Tech", "track": "software_contract"},
    {"name": "Meta Capital", "track": "software_contract"},
    {"name": "Automatech AI Automation Agency", "track": "software_contract"},
    {"name": "Isoftke Software Solutions", "track": "software_contract"},
    {"name": "Jovatech Technologies", "track": "software_contract"},
    {"name": "Omni Agent Marketplace", "track": "software_contract"},
    {"name": "Cloudwise", "track": "software_contract"},
    {"name": "TechSphere Solutions", "track": "software_contract"},
    {"name": "Codevant Solutions", "track": "software_contract"},
    {"name": "CraftDuka", "track": "software_contract"},
    {"name": "Ifriki Innovations", "track": "software_contract"},
    {"name": "Afrinetix Solutions", "track": "software_contract"},
]

DEFAULT_ICP = """Find paying work in Nairobi/Kenya across THREE priorities — not only real estate.

Priority 1 (first): Digital/marketing/web agencies that already have clients. Their clients later need CRM integrations, WhatsApp automation, payments, dashboards, APIs, AI chatbots, automated reports, lead management, custom website/ecommerce, databases, internal tools, Odoo/ERP. I am NOT asking for a job. Ask: do you ever have clients who need technical work beyond what your current team handles? Then offer project/contract overflow engineering.

Named agencies to locate official sites for, then similar agencies: Bluegift Digital; Iconic Digital Marketing Agency; Digitally Freed Africa; Nairobi Marketing; Nevin Digital; Netlit Digital; Nairobi Digital Cloud; Windand Developers; Origin Digital Agency; Kissor Digital; Pinch Africa.

Priority 2: Software/AI companies, approached as a contract/freelance engineer. Named: Glitex Solutions; Grafame Tech; Meta Capital; Automatech; Isoftke; Jovatech; Omni Agent Marketplace; Cloudwise; TechSphere Solutions; Codevant; CraftDuka; Ifriki Innovations; Afrinetix.

Priority 3: End businesses with messy public processes — real estate, clinics, schools/training, travel, salons/spas, events, ecommerce/wholesalers (WhatsApp enquiries, booking, quotes, orders, follow-up).

Discover official websites in Kenya/Nairobi. Mix priorities with agencies first. Never invent emails or problems."""

AGENCY_QUERIES = [
    "digital marketing agency Nairobi Kenya official website",
    "web design agency Nairobi Kenya",
    "Nairobi SEO social media agency contact",
    "digital agency Kenya CRM WhatsApp automation",
    "Origin Digital Agency Nairobi",
    "Pinch Africa digital agency Kenya",
]

SOFTWARE_QUERIES = [
    "software development company Nairobi Kenya official website",
    "AI automation agency Nairobi Kenya",
    "custom software Kenya WhatsApp CRM integrations",
    "Glitex Solutions Kenya",
    "software company Nairobi contract development",
]

OPERATIONAL_QUERIES = [
    "real estate agency Nairobi WhatsApp enquire viewing",
    "clinic Nairobi book appointment WhatsApp",
    "training college Nairobi admissions enquire",
    "tour company Kenya WhatsApp quote",
    "salon spa Nairobi book appointment WhatsApp",
    "event company Nairobi registration enquire",
    "wholesale ecommerce Kenya WhatsApp order",
]


def named_for_tracks(tracks: list[str]) -> list[dict]:
    wanted = set(tracks or TRACKS.keys())
    return [n for n in NAMED_TARGETS if n["track"] in wanted]
