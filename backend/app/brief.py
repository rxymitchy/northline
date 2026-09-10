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
) -> dict:
    facts = gap.get("facts") or opportunity.get("facts") or []
    gaps = gap.get("gaps") or []
    similar = peers.get("similar") or []
    right = peers.get("doing_it_right") or []
    industry = peers.get("industry") or "this space"
    observed = opportunity.get("observed_problem") or gap.get("summary") or "We read the public site and noted how customers reach you."
    offer = opportunity.get("automation_opportunity") or "Tighten the public enquiry path so fewer leads wait on a person."
    html = _html_doc(name, site, industry, observed, facts, gaps, offer, similar, right, channel or {})
    text = _text_doc(name, site, industry, observed, facts, gaps, offer, similar, right, channel or {})
    return {
        "title": f"{name} — sample brief",
        "industry": industry,
        "html": html,
        "text": text,
        "similar": similar,
        "doing_it_right": right,
        "emailed": emailed,
    }


def _bullets(items: list, empty: str) -> str:
    if not items:
        return f"<p class='empty'>{escape(empty)}</p>"
    lis = "".join(f"<li>{escape(str(i))}</li>" for i in items)
    return f"<ul>{lis}</ul>"


def _peer_list(rows: list) -> str:
    if not rows:
        return "<p class='empty'>None found yet. After you open similar companies, download again to include them here.</p>"
    bits = []
    for row in rows:
        url = escape(row.get("website") or "")
        name = escape(row.get("name") or url)
        snip = escape(row.get("snippet") or "")
        bits.append(
            f"<li><a href=\"{url}\">{name}</a>"
            f"{f'<span>{snip}</span>' if snip else ''}</li>"
        )
    return f"<ul class='peers'>{''.join(bits)}</ul>"


def _channel_html(channel: dict) -> str:
    if not channel:
        return ""
    state = channel.get("state") or ""
    missing = channel.get("missing") or []
    explore = channel.get("explore") or []
    parts = ["<h2>Comment on what you sent</h2>", f"<p>{escape(str(state))}</p>"]
    if missing:
        parts.append("<h2>What’s missing</h2>")
        parts.append(_bullets([str(m) for m in missing], ""))
    if explore:
        parts.append("<h2>Extra suggestions</h2>")
        parts.append(_bullets([str(m) for m in explore], ""))
    return "\n".join(parts)


def _html_doc(name, site, industry, observed, facts, gaps, offer, similar, right, channel) -> str:
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{escape(name)} brief</title>
<style>
  body {{ font-family: Georgia, 'Times New Roman', serif; color: #1a1a1a; max-width: 640px; margin: 0 auto; padding: 32px 20px; line-height: 1.5; }}
  h1 {{ font-size: 26px; font-weight: 600; margin: 0 0 6px; }}
  .sub {{ color: #5f6368; margin: 0 0 28px; font-family: Arial, sans-serif; font-size: 13px; }}
  h2 {{ font-size: 16px; margin: 28px 0 8px; font-family: Arial, sans-serif; font-weight: 600; }}
  ul {{ padding-left: 18px; }}
  li {{ margin: 6px 0; }}
  .peers span {{ display: block; color: #5f6368; font-size: 13px; font-family: Arial, sans-serif; }}
  .empty {{ color: #5f6368; }}
  a {{ color: #1a73e8; }}
  .foot {{ margin-top: 36px; color: #80868b; font-size: 12px; font-family: Arial, sans-serif; }}
</style></head><body>
  <h1>{escape(name)}</h1>
  <p class="sub">{escape(site)} · {escape(industry)} · sample brief from {BRAND}</p>
  <p class="sub">Manual work is quietly ruining the company</p>
  <h2>What we saw</h2>
  <p>{escape(str(observed))}</p>
  {_bullets([str(f) for f in facts], "Public pages did not give much to quote.")}
  {_channel_html(channel)}
  <h2>Likely constraint</h2>
  {_bullets([str(g) for g in gaps], "No obvious public automation gap on the pages we could read.")}
  <h2>What “doing it right” usually looks like</h2>
  <p>{escape(str(offer))}</p>
  <h2>Companies with similar constraints</h2>
  {_peer_list(similar)}
  <h2>Companies doing it right</h2>
  {_peer_list(right)}
  <p class="foot">Public pages only. We do not invent emails or internal problems. You asked for this brief.</p>
</body></html>"""


def _text_doc(name, site, industry, observed, facts, gaps, offer, similar, right, channel) -> str:
    def lines(title, items, fmt):
        body = "\n".join(fmt(i) for i in items) if items else "- None found on this pass."
        return f"{title}\n{body}\n"

    return (
        f"{name}\n{site} · {industry}\n"
        "Manual work is quietly ruining the company\n\n"
        f"What we saw\n{observed}\n"
        + lines("", facts, lambda f: f"- {f}")
        + (
            f"\nComment on what you sent\n{channel.get('state')}\n"
            + (lines("What’s missing", channel.get("missing") or [], lambda m: f"- {m}") if channel.get("missing") else "")
            + (lines("Extra suggestions", channel.get("explore") or [], lambda m: f"- {m}") if channel.get("explore") else "")
            if channel
            else ""
        )
        + "\nLikely constraint\n"
        + (("\n".join(f"- {g}" for g in gaps) + "\n") if gaps else "- No obvious public gap.\n")
        + f"\nWhat doing it right usually looks like\n{offer}\n\n"
        + lines(
            "Companies with similar constraints",
            similar,
            lambda r: f"- {r.get('name')}: {r.get('website')}",
        )
        + "\n"
        + lines(
            "Companies doing it right",
            right,
            lambda r: f"- {r.get('name')}: {r.get('website')}",
        )
        + f"\n— {BRAND}\n"
    )
