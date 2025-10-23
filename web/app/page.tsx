"use client";

import { useMemo, useState } from "react";
import { SpeechUploadForm } from "./components/SpeechUploadForm";
import { SpeechJobsPanel } from "./components/SpeechJobsPanel";
import { GraphViewer } from "./components/GraphViewer";
import { RagChat } from "./components/RagChat";

type TabKey = "speech" | "graph" | "qa";

const TAB_LABELS: Record<TabKey, string> = {
  speech: "Transcribe → EMR",
  graph: "Patient Graph",
  qa: "Ask the Chart",
};

export default function HomePage() {
  const [activeTab, setActiveTab] = useState<TabKey>("speech");
  const tabs = useMemo(() => Object.entries(TAB_LABELS) as Array<[TabKey, string]>, []);

  return (
    <main style={{ maxWidth: "1200px", margin: "0 auto", padding: "2rem 1.5rem 4rem" }}>
      <header style={{ marginBottom: "2rem" }}>
        <h1 style={{ fontSize: "2.5rem", marginBottom: "0.5rem" }}>AIEMR Demo Control Center</h1>
        <p style={{ color: "#475569", fontSize: "1.1rem", maxWidth: "720px" }}>
          Upload clinical conversations, monitor transcription and EMR generation, explore the patient knowledge graph,
          and ask focused questions backed by hybrid retrieval.
        </p>
      </header>

      <nav style={{ display: "flex", gap: "1rem", marginBottom: "2rem", flexWrap: "wrap" }}>
        {tabs.map(([key, label]) => (
          <button
            key={key}
            className={`tab-button ${activeTab === key ? "active" : ""}`}
            onClick={() => setActiveTab(key)}
          >
            {label}
          </button>
        ))}
      </nav>

      <section style={{ display: activeTab === "speech" ? "grid" : "none", gap: "2rem" }}>
        <SpeechUploadForm />
        <SpeechJobsPanel />
      </section>

      <section style={{ display: activeTab === "graph" ? "block" : "none" }}>
        <GraphViewer />
      </section>

      <section style={{ display: activeTab === "qa" ? "block" : "none" }}>
        <RagChat />
      </section>
    </main>
  );
}
