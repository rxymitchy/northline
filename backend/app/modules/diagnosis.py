"""Turn public signals into a visitor diagnosis. Claims stay tied to observed input."""


def build_diagnosis(source: str, research: dict, gap: dict, channel: dict | None = None) -> dict:
    signals = research.get("signals") or {}
    text = (research.get("text") or "").lower()
    facts = [str(f) for f in (gap.get("facts") or []) if f]
    if source in ("describe", "csv"):
        facts = [
            f.replace(" on the site.", " in what you described.")
            .replace("Site tells customers", "You described asking people")
            .replace("Enquiry/contact form present", "Enquiries appear to be collected in a list or form")
            for f in facts
        ]
    processes = _processes(source, signals, text, gap)
    overall = _overall(processes, gap)
    primary = next((p for p in processes if p["priority"] == "HIGH"), None) or (processes[0] if processes else None)
    automate = _automate_first(primary, overall, facts)
    workflow = _workflow(source, signals, text, processes)
    return {
        "overall": overall,
        "overall_label": {"HIGH": "High", "MEDIUM": "Medium", "LOW": "Low"}[overall],
        "uncertainty": overall == "LOW" and not processes,
        "summary": _summary(source, overall, primary, channel, research),
        "processes": processes,
        "automate_first": automate,
        "workflow": workflow,
        "facts": facts,
        "caveat": (
            "Based on the information provided, public pages, and web mentions of the company. "
            "Northline cannot see internal tools, inboxes, or staff workload."
        ),
    }


def _processes(source: str, signals: dict, text: str, gap: dict) -> list[dict]:
    rows: list[dict] = []
    if signals.get("whatsapp_channel") or "whatsapp" in text:
        if not signals.get("chatbot"):
            rows.append(
                {
                    "process": "Lead capture",
                    "human_work": "Enquiries appear to be collected in WhatsApp for someone to read and reply.",
                    "priority": "HIGH",
                    "why": "This sits at the start of the customer journey, so every new lead waits on a person opening the chat.",
                }
            )
    if signals.get("call_to_book") and not signals.get("online_booking"):
        rows.append(
            {
                "process": "Booking",
                "human_work": "People are asked to call or wait to be booked, with no visible self-serve calendar.",
                "priority": "HIGH",
                "why": "Missed calls and after-hours interest never become a confirmed slot unless a person is free.",
            }
        )
    if signals.get("enquiry_form") and not signals.get("crm_mention") and not signals.get("chatbot"):
        rows.append(
            {
                "process": "Qualification",
                "human_work": "Inbound forms appear to land for a person to sort, with no public CRM or bot mentioned.",
                "priority": "HIGH" if source in ("website", "describe") else "MEDIUM",
                "why": "Manual review before follow-up creates a repeated handoff before anyone is qualified.",
            }
        )
    if signals.get("manual_followup_language") or any(w in text for w in ("follow up", "follow-up", "get back to you", "we will call")):
        rows.append(
            {
                "process": "Follow-up",
                "human_work": "Copy or the description says a person will call or get back to the customer.",
                "priority": "MEDIUM",
                "why": "Follow-up that lives in memory is easy to drop when volume rises.",
            }
        )
    if signals.get("quote_request") and not signals.get("ecommerce"):
        rows.append(
            {
                "process": "Quoting",
                "human_work": "Quotes appear to be assembled by staff rather than a self-serve price or checkout.",
                "priority": "MEDIUM",
                "why": "Each quote is another round of typing before the customer can decide.",
            }
        )
    if source == "csv" or "excel" in text or "spreadsheet" in text:
        rows.append(
            {
                "process": "Record keeping",
                "human_work": "Work is described as living in a file or sheet that someone updates by hand.",
                "priority": "HIGH",
                "why": "The sheet becomes the system of record only if a person remembers to keep it current.",
            }
        )
    if source == "social" and not any(r["process"] == "Lead capture" for r in rows):
        rows.append(
            {
                "process": "Lead capture",
                "human_work": "Interest looks like it still depends on someone reading DMs or comments.",
                "priority": "HIGH",
                "why": "Social traffic that is not captured elsewhere disappears when the algorithm moves on.",
            }
        )
    # Deduplicate by process name, keep first (usually stronger).
    seen = set()
    out = []
    for row in rows:
        if row["process"] in seen:
            continue
        seen.add(row["process"])
        out.append(row)
    if not out and (gap.get("gaps") or []):
        out.append(
            {
                "process": "Intake",
                "human_work": str(gap["gaps"][0]),
                "priority": "MEDIUM",
                "why": "Northline found signs of a public process that still waits on a person.",
            }
        )
    return out[:5]


def _overall(processes: list[dict], gap: dict) -> str:
    if any(p["priority"] == "HIGH" for p in processes):
        return "HIGH"
    if processes or gap.get("exists"):
        return "MEDIUM"
    return "LOW"


def _summary(source: str, overall: str, primary: dict | None, channel: dict | None, research: dict | None = None) -> str:
    channel_state = (channel or {}).get("state") or ""
    mentions = bool((research or {}).get("public_mentions"))
    extra = " Public web mentions were checked alongside the link or description you sent." if mentions else ""
    if overall == "LOW":
        return (
            "Northline found limited public evidence of a repeated manual handoff. "
            "That does not mean the work is automated — only that it is not visible from what was provided."
            + extra
        )
    if primary:
        return (
            f"Based on the information provided, {primary['process'].lower()} still looks staff-dependent. "
            f"{primary['why']}"
            + extra
        )
    if channel_state:
        return channel_state + extra
    src = {"website": "the website", "social": "the profile", "csv": "the file", "describe": "the process you described"}.get(
        source, "what you sent"
    )
    return f"Northline reviewed {src} and found signs that intake still waits on a person." + extra


def _automate_first(primary: dict | None, overall: str, facts: list[str]) -> dict:
    if not primary:
        return {
            "title": "Watch the first handoff, not the whole company",
            "reason": (
                "Northline could not see a single dominant public bottleneck. "
                "If work still depends on one inbox or chat, that first capture step is usually the highest-value place to start — but that is a suggestion, not something observed here."
            ),
            "evidence": facts[:3],
        }
    return {
        "title": primary["process"],
        "reason": (
            f"Your {primary['process'].lower()} process appears to depend on manual work before the next step. "
            f"{primary['why']} "
            "Because this happens early, it is the highest-value workflow to address first."
        ),
        "evidence": facts[:4],
        "human_work": primary["human_work"],
    }


def _workflow(source: str, signals: dict, text: str, processes: list[dict]) -> list[str]:
    names = {p["process"] for p in processes}
    steps = ["Incoming enquiry"]
    if "Lead capture" in names or source in ("social", "website", "describe"):
        steps.append("capture")
    if "Qualification" in names or signals.get("enquiry_form"):
        steps.append("qualification")
    if "Record keeping" in names or "excel" in text or source == "csv":
        steps.append("CRM / database")
    else:
        steps.append("shared log")
    if "Quoting" in names:
        steps.append("quote")
    if "Booking" in names:
        steps.append("booking")
    steps.append("follow-up")
    steps.append("human handoff when needed")
    # Keep unique order
    out = []
    for step in steps:
        if step not in out:
            out.append(step)
    return out
