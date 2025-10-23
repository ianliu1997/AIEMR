'use client';

import { ChangeEvent, FormEvent, useMemo, useState } from "react";
import { useSpeechAdapters, useUploadSpeechJob } from "../../sdk/hooks";

type SpeechUploadFormProps = {
  onUploaded?: () => void;
};

export function SpeechUploadForm({ onUploaded }: SpeechUploadFormProps) {
  const [patientId, setPatientId] = useState("");
  const [adapterKey, setAdapterKey] = useState<string | undefined>();
  const [topicsInput, setTopicsInput] = useState("");
  const [audioFile, setAudioFile] = useState<File | null>(null);
  const adaptersQuery = useSpeechAdapters();
  const uploadMutation = useUploadSpeechJob();

  const adapters = useMemo(() => adaptersQuery.data?.adapters ?? [], [adaptersQuery.data]);

  const handleFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    setAudioFile(file ?? null);
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!patientId || !audioFile) {
      return;
    }
    const fd = new FormData();
    fd.set("patientId", patientId);
    if (adapterKey) {
      fd.set("adapterKey", adapterKey);
    }
    const topics = topicsInput
      .split(",")
      .map((topic) => topic.trim())
      .filter(Boolean);
    topics.forEach((topic) => fd.append("topics", topic));
    fd.set("audio", audioFile);
    await uploadMutation.mutateAsync(fd);
    setAudioFile(null);
    setTopicsInput("");
    if (typeof onUploaded === "function") {
      onUploaded();
    }
  };

  return (
    <form className="card" onSubmit={handleSubmit}>
      <h2 style={{ marginTop: 0 }}>Upload consultation audio</h2>
      <p style={{ marginBottom: "1.5rem", color: "#64748b" }}>
        Submit a WAV recording to trigger transcription and EMR generation. Status will update automatically.
      </p>
      <div style={{ display: "grid", gap: "1rem" }}>
        <label style={{ display: "grid", gap: "0.5rem" }}>
          <span>Patient ID</span>
          <input
            type="text"
            required
            value={patientId}
            onChange={(event) => setPatientId(event.target.value)}
            placeholder="PAT_12345"
            style={{ padding: "0.75rem", borderRadius: "0.75rem", border: "1px solid #cbd5f5" }}
          />
        </label>
        <label style={{ display: "grid", gap: "0.5rem" }}>
          <span>Adapter (topic)</span>
          <select
            value={adapterKey ?? ""}
            onChange={(event) => setAdapterKey(event.target.value || undefined)}
            style={{ padding: "0.75rem", borderRadius: "0.75rem", border: "1px solid #cbd5f5" }}
          >
            <option value="">Auto (base)</option>
            {adapters.map((adapter) => (
              <option key={adapter.key} value={adapter.key}>
                {adapter.label}
              </option>
            ))}
          </select>
        </label>
        <label style={{ display: "grid", gap: "0.5rem" }}>
          <span>Topics (comma separated, optional)</span>
          <input
            type="text"
            value={topicsInput}
            onChange={(event) => setTopicsInput(event.target.value)}
            placeholder="menstrual history, medications"
            style={{ padding: "0.75rem", borderRadius: "0.75rem", border: "1px solid #cbd5f5" }}
          />
        </label>
        <label
          style={{
            display: "grid",
            gap: "0.5rem",
          }}
        >
          <span>Audio file (WAV)</span>
          <input
            type="file"
            accept=".wav,audio/wav"
            required
            onChange={handleFileChange}
            style={{ padding: "0.75rem", borderRadius: "0.75rem", border: "1px dashed #cbd5f5", background: "#f8fafc" }}
          />
        </label>
      </div>
      <button
        className="tab-button active"
        type="submit"
        disabled={uploadMutation.isPending}
        style={{ marginTop: "1.5rem", alignSelf: "flex-start" }}
      >
        {uploadMutation.isPending ? "Uploading…" : "Submit audio"}
      </button>
      {uploadMutation.isError ? (
        <p style={{ color: "#b91c1c" }}>
          {(uploadMutation.error as Error).message ?? "Upload failed. Please retry."}
        </p>
      ) : null}
    </form>
  );
}
