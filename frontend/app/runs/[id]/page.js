"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { api } from "../../../lib/api";

function badgeClass(score) {
  if (score == null) return "badge";
  if (score >= 80) return "badge high";
  if (score >= 60) return "badge medium";
  if (score >= 40) return "badge low";
  return "badge reject";
}

export default function RunPage() {
  const params = useParams();
  const runId = params.id;
  const [data, setData] = useState(null);
  const [logs, setLogs] = useState([]);
  const [error, setError] = useState("");

  async function load() {
    try {
      const [run, l] = await Promise.all([
        api(`/api/runs/${runId}`),
        api(`/api/runs/${runId}/logs`),
      ]);
      setData(run);
      setLogs(l);
    } catch (err) {
      setError(err.message);
    }
  }

  useEffect(() => {
    load();
    const t = setInterval(load, 3000);
    return () => clearInterval(t);
  }, [runId]);

  if (error) return <div className="wrap">{error}</div>;
  if (!data) return <div className="wrap">Loading…</div>;

  return (
    <div className="wrap">
      <header className="top">
        <div>
          <h1>Run #{data.id}</h1>
          <p>{data.icp_text}</p>
        </div>
        <nav>
          <Link href="/">Home</Link>
        </nav>
      </header>

      <div className="card">
        <p>
          Status: <strong>{data.status}</strong>
          {data.error ? ` — ${data.error}` : ""}
        </p>
        <p className="muted">
          Discovered {data.discovered_count} · Researched {data.researched_count} · Qualified {data.qualified_count} ·
          Rejected {data.rejected_count} · Est. cost ${Number(data.estimated_cost_usd || 0).toFixed(4)}
        </p>
        <div className="actions">
          <a className="btn secondary" href={`http://127.0.0.1:8000/api/runs/${runId}/export.csv`}>
            Export CSV
          </a>
        </div>
      </div>

      <div className="card">
        <h2 style={{ marginTop: 0, fontSize: 18 }}>Prospects</h2>
        <table>
          <thead>
            <tr>
              <th>Score</th>
              <th>Company</th>
              <th>Location</th>
              <th>Confidence</th>
              <th>Observed problem</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {data.companies.map((c) => (
              <tr key={c.id}>
                <td>
                  <span className={badgeClass(c.lead_score)}>{c.lead_score ?? "—"}</span>
                </td>
                <td>
                  <Link href={`/prospects/${c.id}`}>{c.name}</Link>
                  <div className="muted">{c.website}</div>
                </td>
                <td>{c.location}</td>
                <td>{c.confidence || "—"}</td>
                <td>{c.observed_problem || "—"}</td>
                <td>{c.status}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {data.companies.length === 0 && <p className="muted">Waiting for discovery…</p>}
      </div>

      <div className="card">
        <h2 style={{ marginTop: 0, fontSize: 18 }}>Logs</h2>
        {logs.map((log) => (
          <div key={log.id} className="muted">
            [{log.event_type}] {log.message}
          </div>
        ))}
      </div>
    </div>
  );
}
