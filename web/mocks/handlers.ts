import { http, HttpResponse } from "msw";
import {
  GraphResponse,
  ListRagPatientsResponse,
  ListSpeechAdaptersResponse,
  ListSpeechJobsResponse,
  ListSpeechPatientsResponse,
  RagAnswer,
  SpeechJob,
} from "../sdk/types";

const sampleAdapters: ListSpeechAdaptersResponse = {
  adapters: [
    { key: "base", label: "General Medicine" },
    { key: "seg_MedicalHistory", label: "Medical History LoRA", topics: ["history"] },
  ],
};

const sampleJobs: ListSpeechJobsResponse = {
  jobs: [
    {
      jobId: "demo-1",
      patientId: "PAT_DEMO",
      status: "emr_generated",
      adapterKey: "base",
      submittedAt: new Date(Date.now() - 5 * 60 * 1000).toISOString(),
      transcriptFileId: "transcript_demo",
      emrFileId: "emr_demo",
      transcriptUrl: "/mock/transcript",
      emrUrl: "/mock/emr",
      timeline: {
        uploadedAt: new Date(Date.now() - 7 * 60 * 1000).toISOString(),
        transcribedAt: new Date(Date.now() - 6 * 60 * 1000).toISOString(),
        emrGeneratedAt: new Date(Date.now() - 5 * 60 * 1000).toISOString(),
      },
    } satisfies SpeechJob,
  ],
};

const sampleSpeechPatients: ListSpeechPatientsResponse = {
  patients: [
    {
      patientId: "PAT_DEMO",
      latestStatus: "emr_generated",
      latestJobId: "demo-1",
      recordCount: 1,
      lastUpdatedAt: new Date(Date.now() - 5 * 60 * 1000).toISOString(),
    },
  ],
};

const sampleGraphPatients: ListRagPatientsResponse = {
  patients: [
    {
      patientId: "PAT_DEMO",
      hasGraph: true,
      graphHtmlUrl: "/mock/graph.html",
      nodeCount: 12,
      edgeCount: 18,
      lastIngestedAt: new Date(Date.now() - 2 * 60 * 1000).toISOString(),
    },
  ],
};

const sampleGraphResponse: GraphResponse = {
  patientId: "PAT_DEMO",
  nodes: [
    { id: "Patient:1", attrs: { label: "Patient", type: "Patient" } },
    { id: "Visit:1", attrs: { label: "Visit Jan", type: "Visit" } },
  ],
  edges: [{ source: "Patient:1", target: "Visit:1", attrs: { label: "HAS_VISIT" } }],
};

const sampleAnswer: RagAnswer = {
  question: "What medications is the patient taking?",
  mode: "hybrid",
  answer: "The patient is currently on Metformin 500mg twice daily.",
  contextJson: JSON.stringify({ PAT_DEMO: { medications: ["Metformin 500mg"] } }, null, 2),
  evidenceNodeIds: ["Value:medication:metformin"],
};

export const handlers = [
  http.get("/v1/speech/adapters", () => HttpResponse.json(sampleAdapters)),
  http.get("/v1/speech/jobs", () => HttpResponse.json(sampleJobs)),
  http.get("/v1/speech/patients", () => HttpResponse.json(sampleSpeechPatients)),
  http.post("/v1/speech/jobs", async ({ request }) => {
    await request.formData(); // consume to avoid warnings
    return HttpResponse.json(sampleJobs.jobs[0], { status: 202 });
  }),
  http.post("/v1/rag/ingest/sync", () =>
    HttpResponse.json({ status: "queued", startedAt: new Date().toISOString() }),
  ),
  http.get("/v1/rag/patients", () => HttpResponse.json(sampleGraphPatients)),
  http.get("/v1/rag/patients/PAT_DEMO/graph", () => HttpResponse.json(sampleGraphResponse)),
  http.get("/v1/rag/patients/PAT_DEMO/graph-html", () =>
    HttpResponse.html("<html><body><h1>Graph</h1></body></html>"),
  ),
  http.post("/v1/rag/query", () => HttpResponse.json(sampleAnswer)),
  http.post("/v1/rag/query-with-document", () => HttpResponse.json(sampleAnswer)),
];
