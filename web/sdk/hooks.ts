import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { GatewayClient, defaultClient } from "./client";
import { RagQuery, RagQueryMode } from "./types";

type ClientOverride = { client?: GatewayClient };

export function useSpeechAdapters(opts: ClientOverride = {}) {
  const client = opts.client ?? defaultClient;
  return useQuery({
    queryKey: ["speech", "adapters"],
    queryFn: () => client.listSpeechAdapters(),
  });
}

export function useSpeechJobs(patientId?: string, opts: ClientOverride = {}) {
  const client = opts.client ?? defaultClient;
  return useQuery({
    queryKey: ["speech", "jobs", patientId ?? "all"],
    queryFn: () => client.listSpeechJobs(patientId ? { patientId } : undefined),
    refetchInterval(data) {
      const hasPending = data?.jobs?.some((job) => job.status !== "emr_generated" && job.status !== "failed");
      return hasPending ? 5000 : false;
    },
  });
}

export function useUploadSpeechJob(opts: ClientOverride = {}) {
  const client = opts.client ?? defaultClient;
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (form: FormData) => client.createSpeechJob(form),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["speech", "jobs"] });
      queryClient.invalidateQueries({ queryKey: ["speech", "patients"] });
    },
  });
}

export function useSpeechPatients(opts: ClientOverride = {}) {
  const client = opts.client ?? defaultClient;
  return useQuery({
    queryKey: ["speech", "patients"],
    queryFn: () => client.listSpeechPatients(),
    refetchInterval: 10000,
  });
}

export function usePatientGraph(patientId: string | undefined, opts: ClientOverride = {}) {
  const client = opts.client ?? defaultClient;
  return useQuery({
    enabled: Boolean(patientId),
    queryKey: ["rag", "graph", patientId],
    queryFn: () => client.getPatientGraph(patientId!),
  });
}

export function useRagPatients(opts: ClientOverride = {}) {
  const client = opts.client ?? defaultClient;
  return useQuery({
    queryKey: ["rag", "patients"],
    queryFn: () => client.listRagPatients(),
    refetchInterval: 15000,
  });
}

export function useRagQuery(opts: ClientOverride = {}) {
  const client = opts.client ?? defaultClient;
  return useMutation({
    mutationFn: (body: RagQuery) => client.queryRag(body),
  });
}

export function useRagQueryWithDocument(opts: ClientOverride = {}) {
  const client = opts.client ?? defaultClient;
  return useMutation({
    mutationFn: (input: { question: string; mode?: RagQueryMode; patientIds?: string[]; file: File }) => {
      const fd = new FormData();
      fd.set("question", input.question);
      fd.set("mode", input.mode ?? "hybrid");
      if (input.patientIds?.length) {
        fd.set("patientIds", input.patientIds.join(","));
      }
      fd.set("document", input.file);
      return client.queryRagWithDocument(fd);
    },
  });
}
