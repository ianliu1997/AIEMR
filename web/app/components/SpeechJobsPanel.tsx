'use client';

import { useEffect, useMemo, useState } from "react";
import { useSpeechJobs } from "../../sdk/hooks";
import { defaultClient, GatewayError } from "../../sdk/client";
import { SpeechJob } from "../../sdk/types";

function statusBadge(status: SpeechJob["status"]) {
  const colors: Record<SpeechJob["status"], string> = {
    uploaded: "#fbbf24",
    transcribed: "#60a5fa",
    emr_generated: "#22c55e",
    failed: "#ef4444",
  };
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "0.5rem",
        padding: "0.25rem 0.75rem",
        borderRadius: "9999px",
        background: colors[status],
        color: "#0f172a",
        fontWeight: 600,
      }}
    >
      {status.replace("_", " ")}
    </span>
  );
}

type JobDetailsProps = {
  job: SpeechJob;
};

function JobDetails({ job }: JobDetailsProps) {
  const [transcript, setTranscript] = useState<string | null>(null);
  const [emr, setEmr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setTranscript(null);
    setEmr(null);
    setError(null);
  }, [job.jobId]);

  const loadArtifacts = async () => {
    setLoading(true);
    setError(null);
    try {
      const [text, json] = await Promise.allSettled([
        defaultClient.fetchTranscript(job.jobId),
        defaultClient.fetchEmr(job.jobId),
      ]);
      if (text.status === "fulfilled") {
        setTranscript(text.value);
      }
      if (json.status === "fulfilled") {
        setEmr(JSON.stringify(json.value, null, 2));
      }
      if (text.status === "rejected" && (!(text.reason instanceof GatewayError) || text.reason.status !== 202)) {
        setError(text.reason instanceof Error ? text.reason.message : "Transcript unavailable");
      }
      if (json.status === "rejected" && (!(json.reason instanceof GatewayError) || json.reason.status !== 202)) {
        setError(json.reason instanceof Error ? json.reason.message : "EMR JSON unavailable");
      }
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="card" style={{ marginTop: "1.5rem" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h3 style={{ margin: 0 }}>Record {job.jobId}</h3>
        <button className="tab-button active" onClick={loadArtifacts} disabled={loading}>
          {loading ? "Loading…" : "Load transcript & EMR"}
        </button>
      </div>
      <p style={{ color: "#64748b" }}>
        Patient {job.patientId} • Adapter: {job.adapterKey ?? "base"} • Submitted {new Date(job.submittedAt).toLocaleString()}
      </p>
      <div className="timeline">
        {[
          { label: "Uploaded", timestamp: job.timeline?.uploadedAt },
          { label: "Transcribed", timestamp: job.timeline?.transcribedAt },
          { label: "EMR generated", timestamp: job.timeline?.emrGeneratedAt },
        ].map(({ label, timestamp }) => (
          <div key={label} className={`timeline-step ${timestamp ? "done" : ""}`}>
            <strong>{label}</strong>
            <span>{timestamp ? new Date(timestamp).toLocaleString() : "pending"}</span>
          </div>
        ))}
      </div>
      {error ? <p style={{ color: "#b91c1c" }}>{error}</p> : null}
      <div style={{ display: "grid", gap: "1rem", marginTop: "1rem" }}>
        {transcript ? (
          <section>
            <h4>Transcript</h4>
            <pre
              style={{
                whiteSpace: "pre-wrap",
                background: "#f8fafc",
                padding: "1rem",
                borderRadius: "0.75rem",
                maxHeight: "240px",
                overflowY: "auto",
              }}
            >
              {transcript}
            </pre>
          </section>
        ) : null}
        {emr ? (
          <section>
            <h4>EMR JSON</h4>
            <pre
              style={{
                whiteSpace: "pre-wrap",
                background: "#f1f5f9",
                padding: "1rem",
                borderRadius: "0.75rem",
                maxHeight: "280px",
                overflowY: "auto",
              }}
            >
              {emr}
            </pre>
          </section>
        ) : null}
      </div>
    </div>
  );
}

export function SpeechJobsPanel() {
  const { data, isLoading, isError, refetch } = useSpeechJobs();
  const [selectedJob, setSelectedJob] = useState<SpeechJob | null>(null);

  const jobs = useMemo(() => data?.jobs ?? [], [data?.jobs]);

  useEffect(() => {
    if (jobs.length && !selectedJob) {
      setSelectedJob(jobs[0]);
    }
  }, [jobs, selectedJob]);

  if (isLoading) {
    return <div className="card">Loading jobs…</div>;
  }
  if (isError) {
    return (
      <div className="card">
        <p style={{ color: "#b91c1c" }}>Unable to load jobs.</p>
        <button className="tab-button active" onClick={() => refetch()}>
          Retry
        </button>
      </div>
    );
  }

  return (
    <>
      <div className="card" style={{ display: "grid", gap: "1rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <h2 style={{ margin: 0 }}>Speech-to-EMR jobs</h2>
          <button className="tab-button" onClick={() => refetch()}>
            Refresh
          </button>
        </div>
        <div style={{ display: "grid", gap: "1rem" }}>
          {jobs.map((job) => (
            <article
              key={job.jobId}
              className="card"
              style={{
                border: selectedJob?.jobId === job.jobId ? "2px solid #1d4ed8" : "1px solid #e2e8f0",
                cursor: "pointer",
              }}
              onClick={() => setSelectedJob(job)}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <div>
                  <h3 style={{ margin: 0 }}>Patient {job.patientId}</h3>
                  <p style={{ margin: 0, color: "#64748b" }}>
                    Created {new Date(job.submittedAt).toLocaleString()} • Adapter {job.adapterKey ?? "base"}
                  </p>
                </div>
                {statusBadge(job.status)}
              </div>
              <div className="timeline" style={{ marginTop: "0.75rem" }}>
                {[
                  { label: "Uploaded", timestamp: job.timeline?.uploadedAt },
                  { label: "Transcribed", timestamp: job.timeline?.transcribedAt },
                  { label: "EMR generated", timestamp: job.timeline?.emrGeneratedAt },
                ].map(({ label, timestamp }) => (
                  <div key={label} className={`timeline-step ${timestamp ? "done" : ""}`}>
                    <strong>{label}</strong>
                    <span>{timestamp ? new Date(timestamp).toLocaleString() : "pending"}</span>
                  </div>
                ))}
              </div>
            </article>
          ))}
          {jobs.length === 0 ? <p style={{ color: "#64748b" }}>No jobs yet. Upload an audio file to get started.</p> : null}
        </div>
      </div>
      {selectedJob ? <JobDetails job={selectedJob} /> : null}
    </>
  );
}
