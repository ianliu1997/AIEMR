'use client';

import { useEffect, useMemo, useState } from "react";
import { usePatientGraph, useRagPatients } from "../../sdk/hooks";

export function GraphViewer() {
  const { data, isLoading, isError, refetch } = useRagPatients();
  const patients = useMemo(() => data?.patients ?? [], [data?.patients]);
  const [selectedPatient, setSelectedPatient] = useState<string | undefined>(() => patients[0]?.patientId);

  useEffect(() => {
    if (patients.length && !selectedPatient) {
      setSelectedPatient(patients[0].patientId);
    }
    if (!patients.length) {
      setSelectedPatient(undefined);
    }
  }, [patients, selectedPatient]);
  const graphQuery = usePatientGraph(selectedPatient);

  if (isLoading) {
    return <div className="card">Loading graph metadata…</div>;
  }
  if (isError) {
    return (
      <div className="card">
        <p style={{ color: "#b91c1c" }}>Unable to reach the graph service.</p>
        <button className="tab-button active" onClick={() => refetch()}>
          Retry
        </button>
      </div>
    );
  }

  return (
    <div className="card" style={{ display: "grid", gap: "1.5rem" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h2 style={{ margin: 0 }}>Patient graphs</h2>
        <button className="tab-button" onClick={() => refetch()}>
          Resync
        </button>
      </div>
      <div style={{ display: "flex", gap: "1rem", flexWrap: "wrap" }}>
        {patients.map((patient) => (
          <button
            key={patient.patientId}
            className={`tab-button ${selectedPatient === patient.patientId ? "active" : ""}`}
            onClick={() => setSelectedPatient(patient.patientId)}
          >
            {patient.patientId}
          </button>
        ))}
        {patients.length === 0 ? <p style={{ color: "#64748b" }}>No ingested EMR JSON detected.</p> : null}
      </div>
      {selectedPatient ? (
        <section>
          <h3 style={{ marginTop: 0 }}>Graph summary</h3>
          {graphQuery.isError ? (
            <p style={{ color: "#b91c1c" }}>Unable to load graph data for {selectedPatient}.</p>
          ) : (
            <>
              <p style={{ color: "#475569" }}>
                Nodes {graphQuery.data?.nodes.length ?? 0} • Edges {graphQuery.data?.edges.length ?? 0}
              </p>
              <iframe
                title={`Graph for ${selectedPatient}`}
                src={`/v1/rag/patients/${selectedPatient}/graph-html`}
                style={{ width: "100%", height: "520px", borderRadius: "1rem", border: "1px solid #cbd5f5" }}
              />
            </>
          )}
        </section>
      ) : null}
    </div>
  );
}
