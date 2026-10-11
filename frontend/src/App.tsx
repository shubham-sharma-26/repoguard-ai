import { FormEvent, useEffect, useMemo, useState } from "react";
import { Link, Route, Routes, useNavigate, useParams } from "react-router-dom";
import {
  Activity,
  ArrowDownToLine,
  ArrowRight,
  BookOpen,
  Bot,
  Braces,
  ChevronRight,
  CircleHelp,
  Clock3,
  Code2,
  FileCode2,
  FolderGit2,
  Github,
  History,
  LayoutDashboard,
  LoaderCircle,
  Search,
  Shield,
  ShieldAlert,
  Sparkles,
} from "lucide-react";
import {
  Analysis,
  AnalysisDetail,
  AnalysisSummary,
  api,
  Finding,
  FileContent,
  QuestionAnswer,
} from "./types";

function describeRequestError(error: unknown, fallback: string): string {
  if (error instanceof TypeError) {
    return "Could not connect to the local RepoGuard API. Check that the backend is running at http://127.0.0.1:8001.";
  }
  return error instanceof Error ? error.message : fallback;
}

function App() {
  const [history, setHistory] = useState<AnalysisSummary[]>([]);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [historyError, setHistoryError] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [url, setUrl] = useState("");
  const navigate = useNavigate();
  const refresh = async () => {
    try {
      setHistory(await api.history());
      setHistoryError("");
    } catch (e) {
      setHistoryError(
        describeRequestError(e, "Could not load saved analyses."),
      );
    } finally {
      setHistoryLoading(false);
    }
  };
  useEffect(() => {
    void refresh();
  }, []);
  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    setLoading(true);
    try {
      const result = await api.analyze(url);
      setHistory((items) => [result, ...items]);
      setHistoryError("");
      navigate(`/analysis/${result.id}`);
    } catch (e) {
      setError(describeRequestError(e, "Analysis failed"));
    } finally {
      setLoading(false);
    }
  }
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <Link to="/" className="brand">
          <span className="brand-mark">
            <Shield size={21} />
          </span>
          <span>
            RepoGuard<span className="brand-ai"> AI</span>
            <small>CODE INTELLIGENCE</small>
          </span>
        </Link>
        <div className="side-label">WORKSPACE</div>
        <Link className="nav-item active" to="/">
          <LayoutDashboard size={17} /> Overview
        </Link>
        <Link className="nav-item" to="/#recent">
          <History size={17} /> Analysis history
        </Link>
        <div className="side-label nav-gap">TOOLS</div>
        <a
          className="nav-item"
          href="http://localhost:8001/docs"
          target="_blank"
          rel="noreferrer"
        >
          <BookOpen size={17} /> API reference{" "}
          <ArrowRight size={13} className="nav-external" />
        </a>
        <div className="sidebar-bottom">
          <div className="status-dot" /> <span>Local analysis engine</span>
          <span className="version">v1.0</span>
        </div>
      </aside>
      <main className="main">
        <header className="topbar">
          <div className="breadcrumbs">
            <span>Workspace</span>
            <ChevronRight size={14} />
            <strong>Repository intelligence</strong>
          </div>
          <div className="top-actions">
            <span className="local-pill">
              <span /> LOCAL MODE
            </span>
            <a
              href="https://github.com"
              target="_blank"
              rel="noreferrer"
              aria-label="GitHub"
            >
              <Github size={18} />
            </a>
          </div>
        </header>
        <Routes>
          <Route
            path="/"
            element={
              <Home
                history={history}
                url={url}
                setUrl={setUrl}
                submit={submit}
                loading={loading}
                error={error}
                historyError={historyError}
                historyLoading={historyLoading}
                refreshHistory={() => void refresh()}
              />
            }
          />
          <Route path="/analysis/:id" element={<AnalysisPage />} />
          <Route
            path="*"
            element={
              <Home
                history={history}
                url={url}
                setUrl={setUrl}
                submit={submit}
                loading={loading}
                error={error}
                historyError={historyError}
                historyLoading={historyLoading}
                refreshHistory={() => void refresh()}
              />
            }
          />
        </Routes>
      </main>
    </div>
  );
}

function Home({
  history,
  url,
  setUrl,
  submit,
  loading,
  error,
  historyError,
  historyLoading,
  refreshHistory,
}: {
  history: AnalysisSummary[];
  url: string;
  setUrl: (v: string) => void;
  submit: (e: FormEvent) => void;
  loading: boolean;
  error: string;
  historyError: string;
  historyLoading: boolean;
  refreshHistory: () => void;
}) {
  const totalFiles = history.reduce((sum, item) => sum + item.file_count, 0);
  const totalFindings = history.reduce(
    (sum, item) => sum + item.findings_count,
    0,
  );
  return (
    <div className="page">
      <section className="hero">
        <div className="eyebrow">
          <Sparkles size={14} /> REPOSITORY INTELLIGENCE
        </div>
        <h1>
          Understand any codebase.
          <br />
          <span>Find what matters.</span>
        </h1>
        <p className="hero-copy">
          A clear, evidence-backed view into public GitHub repositories.
          <br />
          Structure, static analysis, and source-grounded answers in one place.
        </p>
        <div className="submit-card">
          <form onSubmit={submit}>
            <div className="input-icon">
              <Github size={18} />
            </div>
            <input
              aria-label="GitHub repository URL"
              placeholder="https://github.com/owner/repository"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              required
            />
            <button disabled={loading}>
              {loading ? (
                <>
                  <LoaderCircle className="spin" size={16} /> Analyzing
                </>
              ) : (
                <>
                  Analyze repository <ArrowRight size={16} />
                </>
              )}
            </button>
          </form>
          {error && (
            <div className="error-message">
              <ShieldAlert size={15} />
              {error}
            </div>
          )}
          <div className="form-hint">
            <Shield size={13} /> Public repositories only <span>·</span> Pinned
            to a specific commit <span>·</span> No source code execution
          </div>
        </div>
      </section>
      <section className="stats-row">
        <Stat
          icon={<FolderGit2 />}
          label="Repositories analyzed"
          value={
            historyError || historyLoading ? "—" : history.length.toString()
          }
          detail={historyError ? "history unavailable" : "saved locally"}
        />
        <Stat
          icon={<FileCode2 />}
          label="Files indexed"
          value={
            historyError || historyLoading ? "—" : totalFiles.toLocaleString()
          }
          detail={historyError ? "history unavailable" : "across analyses"}
        />
        <Stat
          icon={<ShieldAlert />}
          label="Findings detected"
          value={
            historyError || historyLoading
              ? "—"
              : totalFindings.toLocaleString()
          }
          detail={historyError ? "history unavailable" : "tool-reported"}
        />
      </section>
      <section id="recent" className="recent-section">
        <div className="section-heading">
          <div>
            <h2>Recent analyses</h2>
            <p>Your repository snapshots, pinned to their analyzed commits.</p>
          </div>
          <span className="count-badge">
            {historyLoading && history.length === 0
              ? "Loading…"
              : historyError && history.length === 0
                ? "Unavailable"
                : `${history.length} ${history.length === 1 ? "analysis" : "analyses"}`}
          </span>
        </div>
        {historyError && (
          <div className="error-message" role="alert">
            <ShieldAlert size={15} />
            Could not load saved analysis history: {historyError}
            <button type="button" onClick={refreshHistory}>
              Retry
            </button>
          </div>
        )}
        {historyLoading && history.length === 0 ? (
          <div className="empty-state" role="status">
            <LoaderCircle className="spin" /> Loading saved analyses…
          </div>
        ) : history.length === 0 && historyError ? null : history.length ===
          0 ? (
          <div className="empty-state">
            <div className="empty-icon">
              <Code2 size={23} />
            </div>
            <strong>Your workspace is ready</strong>
            <p>
              Paste a public GitHub URL above to generate your first repository
              analysis.
            </p>
            <a href="#top" className="text-link">
              Explore the analysis pipeline <ArrowRight size={14} />
            </a>
          </div>
        ) : (
          <div className="repo-list">
            {history.map((item) => (
              <Link
                to={`/analysis/${item.id}`}
                className="repo-row"
                key={item.id}
              >
                <div className="repo-icon">
                  <Github size={19} />
                </div>
                <div className="repo-main">
                  <strong>
                    {item.owner}
                    <span>/</span>
                    {item.name}
                  </strong>
                  <small>{item.url}</small>
                </div>
                <div className="repo-meta">
                  <span>
                    <FileCode2 size={14} />
                    {item.file_count} files
                  </span>
                  <span>
                    <ShieldAlert size={14} />
                    {item.findings_count} findings
                  </span>
                  <span>
                    <Clock3 size={14} />
                    {new Date(item.analyzed_at).toLocaleDateString()}
                  </span>
                </div>
                <ArrowRight className="row-arrow" size={17} />
              </Link>
            ))}
          </div>
        )}
      </section>
      <section className="feature-strip">
        <Feature
          icon={<Braces />}
          title="Code structure"
          text="Symbols and file structure extracted from source."
        />
        <Feature
          icon={<ShieldAlert />}
          title="Static analysis"
          text="Ruff and Bandit findings with source references."
        />
        <Feature
          icon={<Bot />}
          title="Evidence-grounded Q&A"
          text="Lexical retrieval with verifiable snapshot citations."
        />
      </section>
      <footer>
        RepoGuard AI <span>·</span> Static analysis supports review; it does not
        prove a repository is secure.
      </footer>
    </div>
  );
}
function Stat({
  icon,
  label,
  value,
  detail,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  detail: string;
}) {
  return (
    <div className="stat-card">
      <div className="stat-top">
        <span className="stat-icon">{icon}</span>
        <span>{label}</span>
      </div>
      <strong>{value}</strong>
      <small>{detail}</small>
    </div>
  );
}
function Feature({
  icon,
  title,
  text,
}: {
  icon: React.ReactNode;
  title: string;
  text: string;
}) {
  return (
    <div className="feature">
      <span>{icon}</span>
      <div>
        <strong>{title}</strong>
        <p>{text}</p>
      </div>
    </div>
  );
}

function AnalysisPage() {
  const { id = "" } = useParams();
  const [analysis, setAnalysis] = useState<AnalysisDetail | null>(null);
  const [error, setError] = useState("");
  const [tab, setTab] = useState("overview");
  const [filter, setFilter] = useState("");
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<QuestionAnswer | null>(null);
  const [citationPreview, setCitationPreview] = useState<FileContent | null>(
    null,
  );
  const [citationError, setCitationError] = useState("");
  const [asking, setAsking] = useState(false);
  useEffect(() => {
    api
      .detail(id)
      .then(setAnalysis)
      .catch((e) => setError(e.message));
  }, [id]);
  const findings = useMemo(
    () =>
      analysis?.findings.filter((f) =>
        `${f.path} ${f.rule_id} ${f.message}`
          .toLowerCase()
          .includes(filter.toLowerCase()),
      ) ?? [],
    [analysis, filter],
  );
  if (error)
    return (
      <div className="page">
        <div className="error-panel">
          <ShieldAlert />
          {error}
          <Link to="/">Return to workspace</Link>
        </div>
      </div>
    );
  if (!analysis)
    return (
      <div className="loading-view">
        <LoaderCircle className="spin" /> Loading analysis snapshot…
      </div>
    );
  const tabs = [
    ["overview", "Overview"],
    ["files", "Files"],
    ["symbols", "Code structure"],
    ["findings", "Findings"],
    ["ask", "Ask RepoGuard"],
  ];
  async function openCitation(path: string) {
    setCitationPreview(null);
    setCitationError("");
    try {
      setCitationPreview(await api.fileContent(id, path));
    } catch (e) {
      setCitationError(describeRequestError(e, "Could not load cited source"));
    }
  }
  async function ask(e: FormEvent) {
    e.preventDefault();
    setAsking(true);
    try {
      setAnswer(await api.ask(id, question));
    } catch (e) {
      setAnswer({
        answer: describeRequestError(e, "Request failed"),
        citations: [],
        mode: "error",
        retrieval_mode: "lexical",
        generation_mode: "none",
        provider_status: "error",
        provider_message: "The Q&A request failed.",
        evidence_sufficient: false,
      });
    } finally {
      setAsking(false);
    }
  }
  return (
    <div className="page analysis-page">
      <div className="analysis-heading">
        <div>
          <div className="eyebrow">
            <Activity size={14} /> ANALYSIS SNAPSHOT
          </div>
          <h1 className="repo-title">
            <Github size={27} />
            {analysis.owner}
            <span>/</span>
            {analysis.name}
          </h1>
          <a
            className="commit-line"
            href={analysis.url}
            target="_blank"
            rel="noreferrer"
          >
            {analysis.url} <span>·</span>{" "}
            <code>{analysis.commit_sha.slice(0, 12)}</code> <span>·</span>{" "}
            branch: {analysis.default_branch}
          </a>
        </div>
        <div className="download-menu">
          <a className="outline-button" href={`/api/analyses/${id}/report.md`}>
            <ArrowDownToLine size={15} /> Export report
          </a>
          <a className="json-link" href={`/api/analyses/${id}/report.json`}>
            JSON
          </a>
        </div>
      </div>
      <div className="snapshot-banner">
        <span className="status-dot" /> Completed <span>·</span>{" "}
        {new Date(analysis.analyzed_at).toLocaleString()} <span>·</span>{" "}
        {(analysis.duration_ms / 1000).toFixed(1)}s <span>·</span> Snapshot{" "}
        <code>{analysis.commit_sha.slice(0, 8)}</code>
      </div>
      <div className="tabs" role="tablist">
        {tabs.map(([key, label]) => (
          <button
            key={key}
            className={tab === key ? "selected" : ""}
            onClick={() => setTab(key)}
            role="tab"
            aria-selected={tab === key}
          >
            {label}
            {key === "findings" && (
              <span className="tab-count">{analysis.findings.length}</span>
            )}
          </button>
        ))}
      </div>
      {tab === "overview" && (
        <>
          <div className="stats-row analysis-stats">
            <Stat
              icon={<FileCode2 />}
              label="Files indexed"
              value={analysis.file_count.toLocaleString()}
              detail={`${(analysis.total_bytes / 1024).toFixed(1)} KB source analyzed`}
            />
            <Stat
              icon={<Braces />}
              label="Symbols extracted"
              value={analysis.symbols.length.toLocaleString()}
              detail="functions · classes · imports"
            />
            <Stat
              icon={<ShieldAlert />}
              label="Tool findings"
              value={analysis.findings.length.toLocaleString()}
              detail="Ruff + Bandit"
            />
          </div>
          <div className="content-grid">
            <section className="panel language-panel">
              <div className="panel-title">
                <div>
                  <h3>Language distribution</h3>
                  <p>Files classified by extension</p>
                </div>
                <Code2 size={18} />
              </div>
              {Object.entries(analysis.languages)
                .sort((a, b) => b[1] - a[1])
                .slice(0, 10)
                .map(([lang, count]) => (
                  <div className="language-row" key={lang}>
                    <span>{lang}</span>
                    <div className="bar-track">
                      <i
                        style={{
                          width: `${Math.max(2, (count / Math.max(1, analysis.file_count)) * 100)}%`,
                        }}
                      />
                    </div>
                    <b>{count}</b>
                  </div>
                ))}
            </section>
            <section className="panel snapshot-panel">
              <div className="panel-title">
                <div>
                  <h3>Snapshot details</h3>
                  <p>Reproducibility metadata</p>
                </div>
                <CircleHelp size={18} />
              </div>
              <Detail
                label="Pinned commit"
                value={analysis.commit_sha.slice(0, 16)}
              />
              <Detail label="Default branch" value={analysis.default_branch} />
              <Detail
                label="Analysis duration"
                value={`${analysis.duration_ms} ms`}
              />
              <Detail
                label="Skipped files"
                value={`${analysis.skipped.length} (limits or unsupported content)`}
              />
              <Detail
                label="Ruff"
                value={analysis.tool_versions.ruff ?? "unavailable"}
              />
              <Detail
                label="Bandit"
                value={analysis.tool_versions.bandit ?? "unavailable"}
              />
              {Object.entries(analysis.analysis_coverage ?? {}).map(
                ([language, status]) => (
                  <Detail
                    key={language}
                    label={`${language} analysis`}
                    value={status.replaceAll("_", " ")}
                  />
                ),
              )}
            </section>
          </div>
          <div className="notice">
            <Shield size={17} />
            <span>
              <strong>Interpret results with context.</strong> Findings come
              from static tools. No repository code was executed. Absence of
              findings does not establish that code is secure.
            </span>
          </div>
        </>
      )}
      {tab === "files" && (
        <div className="panel table-panel">
          <div className="panel-title">
            <div>
              <h3>Repository files</h3>
              <p>Paths from the pinned repository snapshot</p>
            </div>
            <span className="count-badge">{analysis.files.length} files</span>
          </div>
          <FileList analysisId={id} files={analysis.files} />
        </div>
      )}
      {tab === "symbols" && (
        <div className="panel table-panel">
          <div className="panel-title">
            <div>
              <h3>Code structure</h3>
              <p>
                Python AST and JavaScript/TypeScript syntax symbols with source
                lines
              </p>
            </div>
            <span className="count-badge">
              {analysis.symbols.length} symbols
            </span>
          </div>
          {analysis.symbols.length === 0 ? (
            <Empty>
              No symbols were extracted from supported Python, JavaScript, or
              TypeScript files. Unsupported and malformed files are skipped
              safely.
            </Empty>
          ) : (
            <div className="symbol-list">
              {analysis.symbols.map((s, i) => (
                <div
                  className="symbol-row"
                  key={`${s.path}-${s.start_line}-${i}`}
                >
                  <span className={`symbol-kind ${s.kind}`}>{s.kind}</span>
                  <strong>{s.name}</strong>
                  <code>
                    {s.path}:{s.start_line}-{s.end_line}
                  </code>
                  {s.summary && <small>{s.summary}</small>}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
      {tab === "findings" && (
        <div className="panel table-panel">
          <div className="panel-title">
            <div>
              <h3>Static analysis findings</h3>
              <p>Tool-reported issues. Verify each result against source.</p>
            </div>
            <div className="filter-box">
              <Search size={15} />
              <input
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
                placeholder="Filter path or rule"
              />
            </div>
          </div>
          {findings.length === 0 ? (
            <Empty>
              {filter
                ? "No findings match this filter."
                : `No findings were reported for analyzed languages. Coverage: ${
                    Object.entries(analysis.analysis_coverage ?? {})
                      .map(
                        ([language, status]) =>
                          `${language}: ${status.replaceAll("_", " ")}`,
                      )
                      .join(" · ") || "not reported"
                  }.`}
            </Empty>
          ) : (
            <div className="finding-list">
              {findings.map((f, i) => (
                <FindingCard key={`${f.path}-${f.rule_id}-${i}`} finding={f} />
              ))}
            </div>
          )}
        </div>
      )}
      {tab === "ask" && (
        <div className="chat-layout">
          <section className="panel chat-panel">
            <div className="panel-title">
              <div>
                <h3>
                  <Bot size={18} /> Ask about this repository
                </h3>
                <p>
                  Optional embeddings and generation work on this pinned
                  snapshot. Source excerpts are sent to OpenAI only when its
                  provider key is configured.
                </p>
              </div>
              <span className="local-pill">
                <span /> {analysis.embedding_status.toUpperCase()} EMBEDDINGS
              </span>
            </div>
            <div className="chat-empty">
              <div className="bot-orb">
                <Sparkles size={21} />
              </div>
              <strong>Ask a question about the code</strong>
              <p>
                Try “Where are the main classes defined?” or “Find code related
                to authentication.”
              </p>
            </div>
            {answer && (
              <div className="answer-box">
                <div className="answer-label">
                  <Sparkles size={14} /> REPOGUARD RESPONSE
                </div>
                <div className="rag-badges" aria-live="polite">
                  <span>Retrieval: {answer.retrieval_mode}</span>
                  <span>
                    Generation: {answer.generation_mode.replaceAll("_", " ")}
                  </span>
                  <span>
                    Provider: {answer.provider_status.replaceAll("_", " ")}
                  </span>
                  {!answer.evidence_sufficient && (
                    <span>Insufficient evidence</span>
                  )}
                </div>
                <small className="provider-message">
                  {answer.provider_message}
                </small>
                <p>{answer.answer}</p>
                {answer.citations.length > 0 && (
                  <div className="citations">
                    {answer.citations.map((c, i) => (
                      <button
                        type="button"
                        className="citation-link"
                        key={`${c.path}-${c.start_line}-${i}`}
                        onClick={() => void openCitation(c.path)}
                      >
                        <FileCode2 size={14} />
                        <code>
                          {c.path}:{c.start_line}-{c.end_line}
                        </code>
                        <small>{c.commit_sha.slice(0, 8)}</small>
                      </button>
                    ))}
                  </div>
                )}
                {citationError && (
                  <p className="preview-note">{citationError}</p>
                )}
                {citationPreview && (
                  <div className="citation-preview">
                    <strong>{citationPreview.path}</strong>
                    {citationPreview.chunks.map((chunk) => (
                      <div
                        className="source-chunk"
                        key={`${chunk.start_line}-${chunk.end_line}`}
                      >
                        <small>
                          Lines {chunk.start_line}–{chunk.end_line}
                        </small>
                        <pre>{chunk.text}</pre>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
            <form className="ask-form" onSubmit={ask}>
              <input
                aria-label="Question about repository"
                placeholder="Ask a question about this codebase…"
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                required
                minLength={3}
              />
              <button disabled={asking}>
                {asking ? (
                  <LoaderCircle className="spin" size={16} />
                ) : (
                  <ArrowRight size={17} />
                )}
              </button>
            </form>
          </section>
          <aside className="panel prompt-panel">
            <h3>Suggested questions</h3>
            {[
              "Where are functions and classes defined?",
              "Which files contain the most code?",
              "What static analysis findings were detected?",
            ].map((q) => (
              <button key={q} onClick={() => setQuestion(q)}>
                {q}
                <ArrowRight size={14} />
              </button>
            ))}
            <p>
              <Shield size={14} /> Repository content is treated as untrusted
              input. LLM explanations are not configured.
            </p>
          </aside>
        </div>
      )}
    </div>
  );
}
function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div className="detail-row">
      <span>{label}</span>
      <code>{value}</code>
    </div>
  );
}
function Empty({ children }: { children: React.ReactNode }) {
  return (
    <div className="inline-empty">
      <Code2 size={20} />
      {children}
    </div>
  );
}
function FileList({
  analysisId,
  files,
}: {
  analysisId: string;
  files: Analysis["files"];
}) {
  const [q, setQ] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const [preview, setPreview] = useState<Awaited<
    ReturnType<typeof api.fileContent>
  > | null>(null);
  const [previewError, setPreviewError] = useState("");
  const filtered = files
    .filter((f) => f.path.toLowerCase().includes(q.toLowerCase()))
    .slice(0, 300);
  return (
    <>
      <div className="filter-box file-search">
        <Search size={15} />
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search files"
        />
        <span>{filtered.length} shown</span>
      </div>
      {selected && (
        <div className="source-preview">
          <div className="preview-heading">
            <FileCode2 size={14} /> <code>{selected}</code>
            <button
              type="button"
              onClick={() => {
                setSelected(null);
                setPreview(null);
              }}
              aria-label="Close file preview"
            >
              ×
            </button>
          </div>
          {previewError && <p className="preview-note">{previewError}</p>}
          {preview?.chunks.length
            ? preview.chunks.map((chunk) => (
                <div
                  className="source-chunk"
                  key={`${chunk.start_line}-${chunk.end_line}`}
                >
                  <small>
                    Lines {chunk.start_line}–{chunk.end_line}
                  </small>
                  <pre>{chunk.text}</pre>
                </div>
              ))
            : !previewError && (
                <p className="preview-note">
                  No text excerpts are available for this file.
                </p>
              )}
          {preview?.truncated && (
            <p className="preview-note">
              Preview is limited to indexed excerpts from this snapshot.
            </p>
          )}
        </div>
      )}
      <div className="file-list">
        {filtered.map((file) => (
          <button
            className="file-row"
            type="button"
            key={file.path}
            aria-expanded={selected === file.path}
            style={{
              paddingLeft: `${18 + Math.min(file.path.split("/").length - 1, 5) * 12}px`,
            }}
            onClick={() => {
              setSelected(file.path);
              setPreview(null);
              setPreviewError("");
              void api
                .fileContent(analysisId, file.path)
                .then(setPreview)
                .catch((error: unknown) => {
                  setPreviewError(
                    error instanceof Error
                      ? error.message
                      : "Could not load file preview",
                  );
                });
            }}
          >
            <FileCode2 size={15} />
            <code>{file.path}</code>
            <span>{file.language}</span>
            <small>{file.size.toLocaleString()} B</small>
          </button>
        ))}
      </div>
      {files.length > 300 && (
        <p className="table-footnote">Showing up to 300 matching files.</p>
      )}
    </>
  );
}
function FindingCard({ finding: f }: { finding: Finding }) {
  return (
    <article className="finding-card">
      <div className="finding-top">
        <span className={`severity ${f.severity}`}>{f.severity}</span>
        <code>{f.rule_id}</code>
        <span className="finding-source">{f.source}</span>
      </div>
      <strong>{f.title}</strong>
      <p>{f.message}</p>
      <div className="finding-location">
        <FileCode2 size={13} />
        <code>
          {f.path}
          {f.line ? `:${f.line}` : ""}
        </code>
      </div>
      {f.evidence && (
        <details>
          <summary>Evidence</summary>
          <pre>{f.evidence}</pre>
        </details>
      )}
    </article>
  );
}

export default App;
