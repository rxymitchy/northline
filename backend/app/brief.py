from html import escape


BRAND = "Northline"


def build_brief(
    name: str,
    site: str,
    gap: dict,
    opportunity: dict,
    peers: dict,
    emailed: bool,
    channel: dict | None = None,
    diagnosis: dict | None = None,
) -> dict:
    facts = gap.get("facts") or opportunity.get("facts") or []
    if facts and isinstance(facts[0], dict):
        facts = [f.get("observation") or f.get("claim") or "" for f in facts]
    facts = [str(f) for f in facts if f]
    gaps = gap.get("gaps") or []
    similar = peers.get("similar") or []
    right = peers.get("doing_it_right") or []
    industry = peers.get("industry") or ""
    diagnosis = diagnosis or {}
    observed = (
        diagnosis.get("summary")
        or opportunity.get("observed_problem")
        or gap.get("summary")
        or "Northline reviewed what you sent and noted how work appears to move."
    )
    offer = (diagnosis.get("automate_first") or {}).get("reason") or opportunity.get("automation_opportunity") or ""
    html = _html_doc(name, site, industry, observed, facts, gaps, offer, similar, right, channel or {}, diagnosis)
    text = _text_doc(name, site, industry, observed, facts, gaps, offer, similar, right, channel or {}, diagnosis)
    return {
        "title": f"{name}: Northline operations snapshot",
        "industry": industry,
        "html": html,
        "text": text,
        "similar": similar,
        "doing_it_right": right,
        "diagnosis": diagnosis,
        "channel": channel or {},
        "emailed": emailed,
    }


def _bullets(items: list, empty: str) -> str:
    if not items:
        return f"<p class='empty'>{escape(empty)}</p>"
    lis = "".join(f"<li>{escape(str(i))}</li>" for i in items)
    return f"<ul>{lis}</ul>"


def _peer_list(rows: list) -> str:
    if not rows:
        return "<p class='empty'>No comparable operating companies were attached to this report yet.</p>"
    bits = []
    for row in rows:
        url = escape(row.get("website") or "")
        name = escape(row.get("name") or url)
        why = escape(row.get("why") or row.get("snippet") or "")
        bits.append(
            f"<li><a href=\"{url}\">{name}</a>"
            f"{f'<span>{why}</span>' if why else ''}</li>"
        )
    return f"<ul class='peers'>{''.join(bits)}</ul>"


def _process_table(processes: list) -> str:
    if not processes:
        return "<p class='empty'>No repeated public process stood out clearly.</p>"
    rows = []
    for p in processes:
        rows.append(
            "<tr>"
            f"<td>{escape(p.get('process') or '')}</td>"
            f"<td>{escape(p.get('human_work') or '')}</td>"
            f"<td>{escape(p.get('priority') or '')}</td>"
            f"<td>{escape(p.get('fix') or p.get('why') or '')}</td>"
            "</tr>"
        )
    return (
        "<table class='ops'><thead><tr>"
        "<th>Area</th><th>What happens now</th><th>Priority</th><th>What to do</th>"
        "</tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
    )


def _workflow_html(steps: list) -> str:
    if not steps:
        return ""
    return "<p class='flow'>" + " → ".join(escape(s) for s in steps) + "</p>"


def _html_doc(name, site, industry, observed, facts, gaps, offer, similar, right, channel, diagnosis) -> str:
    overall = diagnosis.get("overall_label") or diagnosis.get("overall") or "Not rated"
    automate = diagnosis.get("automate_first") or {}
    site_line = " · ".join(x for x in (site, industry) if x)
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{escape(name)}: {BRAND}</title>
<style>
  body {{ font-family: Georgia, 'Times New Roman', serif; color: #1a1a1a; max-width: 680px; margin: 0 auto; padding: 32px 20px; line-height: 1.5; }}
  h1 {{ font-size: 26px; font-weight: 600; margin: 0 0 6px; }}
  .sub {{ color: #5f6368; margin: 0 0 8px; font-family: Arial, sans-serif; font-size: 13px; }}
  h2 {{ font-size: 16px; margin: 28px 0 8px; font-family: Arial, sans-serif; font-weight: 600; }}
  ul {{ padding-left: 18px; }}
  li {{ margin: 6px 0; }}
  .peers span {{ display: block; color: #5f6368; font-size: 13px; font-family: Arial, sans-serif; }}
  .empty {{ color: #5f6368; }}
  a {{ color: #15803d; }}
  .foot {{ margin-top: 36px; color: #80868b; font-size: 12px; font-family: Arial, sans-serif; }}
  table.ops {{ width: 100%; border-collapse: collapse; font-family: Arial, sans-serif; font-size: 13px; }}
  table.ops th, table.ops td {{ border-bottom: 1px solid #e5e7eb; text-align: left; padding: 8px 6px; vertical-align: top; }}
  table.ops th {{ color: #6b7280; font-size: 11px; text-transform: uppercase; }}
  .flow {{ font-family: Arial, sans-serif; font-size: 14px; }}
  .sev {{ font-family: Arial, sans-serif; font-weight: 700; letter-spacing: .04em; }}
</style></head><body>
  <h1>{escape(name)}</h1>
  <p class="sub">{escape(site_line + (" · " if site_line else "") + "operations snapshot from " + BRAND)}</p>
  <p class="sub">See what's still manual</p>
  <h2>Business operations snapshot</h2>
  <p>Manual work score: <span class="sev">{escape(str(overall).upper())}</span></p>
  <p>{escape(str(observed))}</p>
  {_process_table(diagnosis.get("processes") or [])}
  <h2>Start here</h2>
  <p><b>{escape(automate.get("title") or "Start with how new enquiries reach you")}</b></p>
  <p>{escape(automate.get("reason") or offer or "")}</p>
  {_steps(automate.get("steps") or [])}
  <h2>What we saw</h2>
  {_bullets(automate.get("evidence") or facts, "Nothing stood out clearly enough to quote.")}
  <h2>How it could work</h2>
  {_workflow_html(diagnosis.get("workflow") or [])}
  {_channel_html(channel)}
  <p class="foot">{escape(diagnosis.get("caveat") or "Public pages and what you submitted only. We do not invent emails or internal problems.")}</p>
</body></html>"""


def _steps(items: list) -> str:
    items = [str(i) for i in items if i]
    if not items:
        return ""
    return "<ol>" + "".join(f"<li>{escape(i)}</li>" for i in items) + "</ol>"


def _channel_html(channel: dict) -> str:
    if not channel or not (channel.get("state") or channel.get("missing") or channel.get("explore")):
        return ""
    parts = ["<h2>Notes on what you sent</h2>"]
    if channel.get("state"):
        parts.append(f"<p>{escape(str(channel['state']))}</p>")
    if channel.get("missing"):
        parts.append("<h2>What’s missing</h2>")
        parts.append(_bullets([str(m) for m in channel["missing"]], ""))
    if channel.get("explore"):
        parts.append("<h2>Other ideas</h2>")
        parts.append(_bullets([str(m) for m in channel["explore"]], ""))
    return "\n".join(parts)


def _text_doc(name, site, industry, observed, facts, gaps, offer, similar, right, channel, diagnosis) -> str:
    overall = diagnosis.get("overall_label") or diagnosis.get("overall") or "Not rated"
    automate = diagnosis.get("automate_first") or {}
    processes = diagnosis.get("processes") or []
    workflow = diagnosis.get("workflow") or []
    bits = [
        f"{name}",
        f"{site} {('· ' + industry) if industry else ''}".strip(),
        "See what's still manual",
        "",
        "BUSINESS OPERATIONS SNAPSHOT",
        f"Manual work score: {str(overall).upper()}",
        observed,
        "",
    ]
    if processes:
        bits.append("Area / what happens now / priority / what to do")
        for p in processes:
            bits.append(f"* {p.get('process')}: {p.get('human_work')} [{p.get('priority')}] {p.get('fix') or p.get('why')}")
        bits.append("")
    bits += [
        "START HERE",
        automate.get("title") or "",
        automate.get("reason") or offer or "",
        *[f"{i}. {s}" for i, s in enumerate(automate.get("steps") or [], 1)],
        "",
        "HOW IT COULD WORK",
        " → ".join(workflow) if workflow else "New enquiry → instant reply → saved in one list → reminder → a person steps in when needed",
        "",
    ]
    if channel and channel.get("state"):
        bits += ["NOTES ON WHAT YOU SENT", channel.get("state"), ""]
    bits += [
        diagnosis.get("caveat") or "",
        f"{BRAND}",
        "",
    ]
    return "\n".join(bits)
