"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { api } from "../../../lib/api";

export default function ProspectPage() {
  const params = useParams();
  const id = params.id;
  const [data, setData] = useState(null);
  const [note, setNote] = useState("");
  const [error, setError] = useState("");

  async function load() {
    try {
      setData(await api(`/api/prospects/${id}`));
    } catch (err) {
      setError(err.message);
    }
  }

  useEffect(() => {
    load();
  }, [id]);

  async function decide(action) {
    const res = await api(`/api/prospects/${id}/decision`, {
      method: "POST",
      body: JSON.stringify({ action }),
    });
    setNote(res.note || `Marked ${res.status}`);
    load();
  }

  async function feedback(target, value) {
    await api(`/api/prospects/${id}/feedback`, {
      method: "POST",
      body: JSON.stringify({ target, value }),
    });
    load();
  }

  if (error) return <div className="wrap">{error}</div>;
  if (!data) return <div className="wrap">Loading…</div>;

  const contact = data.contacts[0];
  const opp = data.opportunities[0];
  const mail = data.outreach[0];
  const facts = (data.fact_inference && data.fact_inference.facts) || (opp && opp.facts) || [];
  const inferences = (data.fact_inference && data.fact_inference.inferences) || (opp && opp.inferences) || [];
  const breakdown = data.score_breakdown || {};

  return (
    <div className="wrap">
      <header className="top">
        <div>
          <h1>{data.name}</h1>
          <p>
            {data.website ? <a href={data.website} target="_blank" rel="noreferrer">{data.website}</a> : "No website"} ·{" "}
            {data.location} · {data.industry}
          </p>
        </div>
        <nav>
          {data.run_id ? <Link href={`/runs/${data.run_id}`} style={{ marginRight: 12 }}>Back to run</Link> : null}
          <Link href="/">Home</Link>
        </nav>
      </header>

      <div className="card">
        <p>
          Score <strong>{data.lead_score ?? "—"}</strong> · Confidence <strong>{data.confidence || "—"}</strong> · Status{" "}
          <strong>{data.status}</strong>
        </p>
        <p className="muted">{data.description}</p>
        <p className="muted">
          Source: {data.source} {data.source_url ? `· ${data.source_url}` : ""}
        </p>
        <p className="muted">Cheap filter: {data.cheap_filter_score} — {data.cheap_filter_reason}</p>
        <div className="actions">
          <button className="good" onClick={() => decide("approve")}>Approve</button>
          <button className="danger" onClick={() => decide("reject")}>Reject</button>
          <button className="secondary" onClick={() => feedback("prospect", "good")}>Prospect good</button>
          <button className="secondary" onClick={() => feedback("prospect", "bad")}>Prospect bad</button>
          <button className="secondary" onClick={() => feedback("opportunity", "good")}>Opportunity good</button>
          <button className="secondary" onClick={() => feedback("opportunity", "bad")}>Opportunity bad</button>
        </div>
        {note && <p className="muted">{note}</p>}
        <p className="muted">
          Feedback: prospect {data.feedback || "—"} · opportunity {data.opportunity_feedback || "—"}
        </p>
        <p className="muted">Email sending is disabled until you explicitly enable it.</p>
      </div>

      <div className="grid2">
        <div className="card">
          <h2 style={{ marginTop: 0, fontSize: 18 }}>Facts (observed)</h2>
          {Array.isArray(facts) && facts.length ? facts.map((f, i) => (
            <div className="fact" key={i}>
              {typeof f === "string" ? f : f.observation}
              {f.source_hint ? <div className="muted">{f.source_hint}</div> : null}
            </div>
          )) : <p className="muted">No facts extracted.</p>}
          <h2 style={{ fontSize: 18 }}>Inferences (not proven)</h2>
          {Array.isArray(inferences) && inferences.length ? inferences.map((f, i) => (
            <div className="inference" key={i}>
              {typeof f === "string" ? f : `${f.claim} (based on: ${f.based_on})`}
              {f.confidence ? <div className="muted">Inference confidence: {f.confidence}</div> : null}
            </div>
          )) : <p className="muted">No inferences.</p>}
        </div>
        <div className="card">
          <h2 style={{ marginTop: 0, fontSize: 18 }}>Opportunity</h2>
          <p><strong>Observed problem:</strong> {data.observed_problem || "—"}</p>
          <p><strong>Automation:</strong> {data.automation_opportunity || "—"}</p>
          <p><strong>Recommended offer:</strong> {data.recommended_offer || "—"}</p>
          <p><strong>WhatsApp:</strong> {data.whatsapp || "—"}</p>
          <h3 style={{ fontSize: 15 }}>Why this score</h3>
          <p className="muted">{breakdown.why}</p>
          {breakdown.breakdown && (
            <ul className="muted">
              {Object.entries(breakdown.breakdown).map(([k, v]) => (
                <li key={k}>{k}: {v}</li>
              ))}
            </ul>
          )}
          {data.page_signals && (
            <pre className="mono">{JSON.stringify(data.page_signals, null, 2)}</pre>
          )}
        </div>
      </div>

      <div className="card">
        <h2 style={{ marginTop: 0, fontSize: 18 }}>Decision-maker</h2>
        {contact ? (
          <>
            <p>{contact.name || "Name not found"} — {contact.role || "role inferred"}</p>
            <p>Email: {contact.email || "none found"}</p>
            <p>
              <strong>{contact.verification_note}</strong>
              {contact.verified ? " (public email found on site)" : ""}
            </p>
            <p className="muted">{contact.rationale}</p>
          </>
        ) : (
          <p className="muted">CONTACT NOT VERIFIED</p>
        )}
      </div>

      <div className="card">
        <h2 style={{ marginTop: 0, fontSize: 18 }}>Outreach draft</h2>
        {mail ? (
          <>
            <p><strong>Subject:</strong> {mail.subject}</p>
            <pre className="mono">{mail.body}</pre>
            <p className="muted"><strong>Why this pitch:</strong> {mail.pitch_rationale}</p>
            <p className="muted">Outreach status: {mail.status}</p>
          </>
        ) : (
          <p className="muted">No outreach generated (below score threshold or no qualifying pain evidence).</p>
        )}
      </div>
    </div>
  );
}
