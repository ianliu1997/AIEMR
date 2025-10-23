'use client';

import { ChangeEvent, FormEvent, useMemo, useState } from "react";
import { useRagPatients } from "../../sdk/hooks";
import { useRagQuery, useRagQueryWithDocument } from "../../sdk/hooks";
import { RagQueryMode } from "../../sdk/types";

export function RagChat() {
  const [question, setQuestion] = useState("");
  const [mode, setMode] = useState<RagQueryMode>("hybrid");
  const [selectedPatients, setSelectedPatients] = useState<string[]>([]);
  const [document, setDocument] = useState<File | null>(null);

  const { data: patientsData } = useRagPatients();
  const patients = useMemo(() => patientsData?.patients ?? [], [patientsData?.patients]);

  const queryMutation = useRagQuery();
  const queryWithDocMutation = useRagQueryWithDocument();

  const handlePatientsToggle = (patientId: string) => {
    setSelectedPatients((prev) =>
      prev.includes(patientId) ? prev.filter((id) => id !== patientId) : [...prev, patientId],
    );
  };

  const handleFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0] ?? null;
    setDocument(file);
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!question) return;
    if (document) {
      await queryWithDocMutation.mutateAsync({
        question,
        mode,
        patientIds: selectedPatients.length ? selectedPatients : undefined,
        file: document,
      });
    } else {
      await queryMutation.mutateAsync({
        question,
        mode,
        patientIds: selectedPatients.length ? selectedPatients : undefined,
      });
    }
  };

  const result = queryMutation.data ?? queryWithDocMutation.data;

  return (
    <div className="card" style={{ display: "grid", gap: "1.5rem" }}>
      <form onSubmit={handleSubmit} style={{ display: "grid", gap: "1rem" }}>
        <h2 style={{ marginTop: 0 }}>Ask the chart</h2>
        <label style={{ display: "grid", gap: "0.5rem" }}>
          <span>Question</span>
          <textarea
            required
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            rows={3}
            placeholder="What medications is the patient currently prescribed?"
            style={{ padding: "0.75rem", borderRadius: "0.75rem", border: "1px solid #cbd5f5" }}
          />
        </label>
        <div style={{ display: "flex", gap: "1rem", flexWrap: "wrap" }}>
          <label style={{ display: "grid", gap: "0.25rem" }}>
            <span>Mode</span>
            <select
              value={mode}
              onChange={(event) => setMode(event.target.value as RagQueryMode)}
              style={{ padding: "0.75rem", borderRadius: "0.75rem", border: "1px solid #cbd5f5" }}
            >
              <option value="hybrid">Hybrid (graph + vector)</option>
              <option value="graph">Graph only</option>
            </select>
          </label>
          <label style={{ display: "grid", gap: "0.25rem" }}>
            <span>Attach document (optional)</span>
            <input
              type="file"
              accept=".txt,.md,.rtf"
              onChange={handleFileChange}
              style={{ padding: "0.75rem", borderRadius: "0.75rem", border: "1px dashed #cbd5f5", background: "#f8fafc" }}
            />
          </label>
        </div>
        <div>
          <p style={{ fontWeight: 600, marginBottom: "0.5rem" }}>Restrict to patients (optional)</p>
          <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
            {patients.map((patient) => {
              const active = selectedPatients.includes(patient.patientId);
              return (
                <button
                  key={patient.patientId}
                  type="button"
                  className={`tab-button ${active ? "active" : ""}`}
                  onClick={() => handlePatientsToggle(patient.patientId)}
                >
                  {patient.patientId}
                </button>
              );
            })}
            {patients.length === 0 ? <span style={{ color: "#94a3b8" }}>No patients indexed yet.</span> : null}
          </div>
        </div>
        <button
          className="tab-button active"
          type="submit"
          disabled={queryMutation.isPending || queryWithDocMutation.isPending}
        >
          {(queryMutation.isPending || queryWithDocMutation.isPending) ? "Querying…" : "Ask"}
        </button>
      </form>
      {result ? (
        <section>
          <h3>Answer</h3>
          <p style={{ fontSize: "1.15rem", lineHeight: 1.6 }}>{result.answer}</p>
          {result.contextJson ? (
            <details>
              <summary style={{ cursor: "pointer", fontWeight: 600 }}>View supporting context</summary>
              <pre
                style={{
                  whiteSpace: "pre-wrap",
                  background: "#f1f5f9",
                  padding: "1rem",
                  borderRadius: "0.75rem",
                  maxHeight: "320px",
                  overflowY: "auto",
                }}
              >
                {result.contextJson}
              </pre>
            </details>
          ) : null}
          {result.evidenceNodeIds?.length ? (
            <p style={{ color: "#475569" }}>Evidence nodes: {result.evidenceNodeIds.join(", ")}</p>
          ) : null}
        </section>
      ) : null}
    </div>
  );
}
