export type FileInfo = {
  path: string;
  size: number;
  language: string;
  line_count?: number | null;
  reason_skipped?: string | null;
};
export type Finding = {
  severity: string;
  rule_id: string;
  title: string;
  message: string;
  path: string;
  line?: number | null;
  source: string;
  evidence?: string;
};
export type Symbol = {
  name: string;
  kind: string;
  path: string;
  start_line: number;
  end_line: number;
  summary: string;
};
export type Analysis = {
  id: string;
  owner: string;
  name: string;
  url: string;
  commit_sha: string;
  default_branch: string;
  analyzed_at: string;
  status: string;
  file_count: number;
  total_bytes: number;
  languages: Record<string, number>;
  files: FileInfo[];
  symbols: Symbol[];
  findings: Finding[];
  skipped: FileInfo[];
  tool_versions: Record<string, string>;
  duration_ms: number;
};
export type AnalysisSummary = Pick<
  Analysis,
  | "id"
  | "owner"
  | "name"
  | "url"
  | "commit_sha"
  | "analyzed_at"
  | "status"
  | "file_count"
> & { findings_count: number; symbol_count: number };
export type AnalysisDetail = Omit<Analysis, "chunks">;
export type FileContent = {
  path: string;
  line_count: number | null;
  chunks: { start_line: number; end_line: number; text: string }[];
  truncated: boolean;
};
const API = "/api";
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || `Request failed (${response.status})`);
  }
  return response.json() as Promise<T>;
}
export const api = {
  history: () => request<AnalysisSummary[]>("/analyses"),
  analyze: (url: string) =>
    request<AnalysisSummary>("/analyses", {
      method: "POST",
      body: JSON.stringify({ url }),
    }),
  detail: (id: string) => request<AnalysisDetail>(`/analyses/${id}`),
  fileContent: (id: string, path: string) =>
    request<FileContent>(
      `/analyses/${id}/file-content?path=${encodeURIComponent(path)}`,
    ),
  ask: (id: string, question: string) =>
    request<{
      answer: string;
      citations: {
        path: string;
        start_line: number;
        end_line: number;
        commit_sha: string;
      }[];
      mode: string;
    }>(`/analyses/${id}/ask`, {
      method: "POST",
      body: JSON.stringify({ question }),
    }),
};
