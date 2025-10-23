import { v4 as uuid } from "uuid";
import {
  GraphResponse,
  ListRagPatientsResponse,
  ListSpeechAdaptersResponse,
  ListSpeechJobsResponse,
  ListSpeechPatientsResponse,
  Problem,
  RagAnswer,
  RagQuery,
  RagSyncResponse,
  SpeechJob,
} from "./types";

export type GatewayClientOptions = {
  baseUrl?: string;
  correlationId?: string;
};

type HttpMethod = "GET" | "POST";

export class GatewayError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly problem?: Problem,
  ) {
    super(message);
    this.name = "GatewayError";
  }
}

async function parseProblem(res: Response): Promise<Problem | undefined> {
  const contentType = res.headers.get("content-type") ?? "";
  if (!contentType.includes("application/problem+json")) return undefined;
  try {
    return (await res.json()) as Problem;
  } catch {
    return undefined;
  }
}

export class GatewayClient {
  private readonly baseUrl: string;
  private readonly correlationId: string;

  constructor(opts: GatewayClientOptions = {}) {
    this.baseUrl = opts.baseUrl ?? process.env.NEXT_PUBLIC_GATEWAY_BASE_URL ?? "";
    this.correlationId = opts.correlationId ?? uuid();
  }

  private buildUrl(path: string): string {
    if (!this.baseUrl) return path;
    return `${this.baseUrl.replace(/\/$/, "")}${path}`;
  }

  private async request<T>(
    path: string,
    method: HttpMethod,
    init?: RequestInit,
  ): Promise<{ data: T; correlationId: string; status: number; raw: Response }> {
    const headers = new Headers(init?.headers);
    headers.set("x-correlation-id", this.correlationId);
    const res = await fetch(this.buildUrl(path), {
      ...init,
      method,
      headers,
    });
    if (!res.ok) {
      const problem = await parseProblem(res);
      throw new GatewayError(problem?.title ?? `HTTP ${res.status}`, res.status, problem);
    }
    const correlationId = res.headers.get("x-correlation-id") ?? this.correlationId;
    let data: T;
    if (res.status === 204) {
      data = undefined as T;
    } else {
      data = (await res.json()) as T;
    }
    return { data, correlationId, status: res.status, raw: res };
  }

  async health(): Promise<{ status: string }> {
    const { data } = await this.request<{ status: string }>("/healthz", "GET");
    return data;
  }

  async readiness(): Promise<{ status: string }> {
    const { data } = await this.request<{ status: string }>("/readyz", "GET");
    return data;
  }

  async listSpeechAdapters(): Promise<ListSpeechAdaptersResponse> {
    const { data } = await this.request<ListSpeechAdaptersResponse>("/v1/speech/adapters", "GET");
    return data;
  }

  async listSpeechJobs(params?: { patientId?: string }): Promise<ListSpeechJobsResponse> {
    const search = new URLSearchParams();
    if (params?.patientId) {
      search.set("patientId", params.patientId);
    }
    const query = search.toString();
    const path = query ? `/v1/speech/jobs?${query}` : "/v1/speech/jobs";
    const { data } = await this.request<ListSpeechJobsResponse>(path, "GET");
    return data;
  }

  async createSpeechJob(payload: FormData): Promise<SpeechJob> {
    const { data } = await this.request<SpeechJob>("/v1/speech/jobs", "POST", {
      body: payload,
    });
    return data;
  }

  async getSpeechJob(jobId: string): Promise<SpeechJob> {
    const { data } = await this.request<SpeechJob>(`/v1/speech/jobs/${jobId}`, "GET");
    return data;
  }

  async fetchTranscript(jobId: string): Promise<string> {
    const res = await fetch(this.buildUrl(`/v1/speech/jobs/${jobId}/transcript`), {
      method: "GET",
      headers: {
        "x-correlation-id": this.correlationId,
        accept: "text/plain, application/json",
      },
    });
    if (res.status === 202) {
      throw new GatewayError("Transcript not ready", res.status);
    }
    if (!res.ok) {
      const problem = await parseProblem(res);
      throw new GatewayError(problem?.title ?? `HTTP ${res.status}`, res.status, problem);
    }
    return res.text();
  }

  async fetchEmr(jobId: string): Promise<Record<string, unknown>> {
    const res = await fetch(this.buildUrl(`/v1/speech/jobs/${jobId}/emr`), {
      method: "GET",
      headers: {
        "x-correlation-id": this.correlationId,
        accept: "application/json",
      },
    });
    if (res.status === 202) {
      throw new GatewayError("EMR not ready", res.status);
    }
    if (!res.ok) {
      const problem = await parseProblem(res);
      throw new GatewayError(problem?.title ?? `HTTP ${res.status}`, res.status, problem);
    }
    return res.json();
  }

  async listSpeechPatients(): Promise<ListSpeechPatientsResponse> {
    const { data } = await this.request<ListSpeechPatientsResponse>("/v1/speech/patients", "GET");
    return data;
  }

  async triggerRagSync(): Promise<RagSyncResponse> {
    const { data } = await this.request<RagSyncResponse>("/v1/rag/ingest/sync", "POST");
    return data;
  }

  async listRagPatients(): Promise<ListRagPatientsResponse> {
    const { data } = await this.request<ListRagPatientsResponse>("/v1/rag/patients", "GET");
    return data;
  }

  async getPatientGraph(patientId: string): Promise<GraphResponse> {
    const { data } = await this.request<GraphResponse>(`/v1/rag/patients/${patientId}/graph`, "GET");
    return data;
  }

  async getPatientGraphHtml(patientId: string): Promise<string> {
    const res = await fetch(this.buildUrl(`/v1/rag/patients/${patientId}/graph-html`), {
      method: "GET",
      headers: {
        "x-correlation-id": this.correlationId,
        accept: "text/html",
      },
    });
    if (!res.ok) {
      const problem = await parseProblem(res);
      throw new GatewayError(problem?.title ?? `HTTP ${res.status}`, res.status, problem);
    }
    return res.text();
  }

  async queryRag(body: RagQuery): Promise<RagAnswer> {
    const { data } = await this.request<RagAnswer>("/v1/rag/query", "POST", {
      body: JSON.stringify(body),
      headers: {
        "content-type": "application/json",
      },
    });
    return data;
  }

  async queryRagWithDocument(form: FormData): Promise<RagAnswer> {
    const { data } = await this.request<RagAnswer>("/v1/rag/query-with-document", "POST", {
      body: form,
    });
    return data;
  }
}

export const defaultClient = new GatewayClient();
