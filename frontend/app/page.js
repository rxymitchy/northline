"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "../lib/api";

const SAMPLE = `Find paying work in Nairobi/Kenya across THREE priorities — not only real estate.

Priority 1 (first): Digital/marketing/web agencies that already have clients. Ask whether they ever have clients who need technical work beyond their team, then offer project/contract overflow engineering.

Priority 2: Software/AI companies as a contract/freelance engineer.

Priority 3: End businesses with messy public processes (real estate, clinics, schools, travel, salons, events, ecommerce/wholesale).`;

export default function HomePage() {
  const [icp, setIcp] = useState(SAMPLE);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [runs, setRuns] = useState([]);
  const [health, setHealth] = useState(null);

  async function refresh() {
    try {
      const [r, h] = await Promise.all([api("/api/runs"), api("/api/health")]);
      setRuns(r);
      setHealth(h);
    } catch (err) {
      setError(err.message);
    }
  }

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 4000);
    return () => clearInterval(t);
  }, []);

  async function startRun() {
    setBusy(true);
    setError("");
    try {
      const run = await api("/api/runs", {
        method: "POST",
        body: JSON.stringify({ icp }),
      });
      window.location.href = `/runs/${run.id}`;
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="wrap">
      <header className="top">
        <div>
          <h1>Find Clients Agent</h1>
          <p>Find paying clients: agency overflow work, software contract work, then messy operations.</p>
        </div>
        {health && (
          <p className="muted">
            Search: {health.search_provider} · OpenAI: {health.openai_configured ? "on" : "missing key"} · Send: disabled
          </p>
        )}
      </header>

      <div className="card">
        <label htmlFor="icp">Ideal customer / search request</label>
        <textarea id="icp" value={icp} onChange={(e) => setIcp(e.target.value)} />
        <div className="row">
          <button onClick={startRun} disabled={busy}>
            {busy ? "Starting…" : "Run Prospecting"}
          </button>
        </div>
        {error && <p className="muted">{error}</p>}
      </div>

      <div className="card">
        <h2 style={{ marginTop: 0, fontSize: 18 }}>Recent runs</h2>
        {runs.length === 0 && <p className="muted">No runs yet.</p>}
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>Status</th>
              <th>ICP</th>
              <th>Found</th>
              <th>Researched</th>
              <th>Qualified</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {runs.map((run) => (
              <tr key={run.id}>
                <td>{run.id}</td>
                <td>{run.status}</td>
                <td>{run.icp_text.slice(0, 80)}{run.icp_text.length > 80 ? "…" : ""}</td>
                <td>{run.discovered_count}</td>
                <td>{run.researched_count}</td>
                <td>{run.qualified_count}</td>
                <td>
                  <Link href={`/runs/${run.id}`}>Open</Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
