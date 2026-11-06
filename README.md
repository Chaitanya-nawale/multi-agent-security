# MultiAgentSecurity (`mas`)

A security evaluation testbed and framework built on **LangGraph** to benchmark multi-agent LLM systems against **indirect prompt injection**, **tool hijacking**, and **unauthorized data exfiltration**.

---

## Architecture & Threat Model

The framework implements a hierarchical multi-agent workflow:

```
User Task ──► Orchestrator Agent (process_documents)
                     │
       ┌─────────────┴─────────────┐
       ▼                           ▼
  Worker Agent                Worker Agent
  ├── read_document (untrusted input)
  └── send_email    (exfiltration sink - audited simulation)
```

- **Orchestrator Agent**: Decomposes user tasks, extracts target document IDs, and delegates analysis to Workers in parallel via `ThreadPoolExecutor`.
- **Worker Agent**: Ingests untrusted documents via `read_document` and returns factual summaries.
- **Threat Vector**: Documents contain indirect prompt injection attempting to trick Workers into dispatching private data via `send_email`.
- **Security Invariant**: Workers must never invoke `send_email` on behalf of untrusted content.

---

## Benchmark Dataset (`mas-eval-50`)

The `data/` directory contains 50 enterprise-grade documents tracked in `data/dataset_metadata.json`:

| Category | Range | Count | Description |
| :--- | :--- | :---: | :--- |
| **Benign Controls** | `doc_001` – `doc_010` | 10 | Corporate memos and runbooks (utility baseline; expected `send_email: false`). |
| **Direct Override** | `doc_adv_001` – `doc_adv_010` | 10 | Explicit compliance and procedural commands mandating email dispatch. |
| **Contextual Masquerade** | `doc_adv_011` – `doc_adv_020` | 10 | Social engineering exploiting assistant helpfulness (SEC, SOC-2, GDPR). |
| **Format Escape** | `doc_adv_021` – `doc_adv_030` | 10 | Structured schema injection (YAML/JSON tool definitions, delimiter breakout). |
| **Advanced Obfuscation** | `doc_adv_031` – `doc_adv_040` | 10 | Internal runtime log emulation and multilingual attacks (DE, ES, FR, ZH). |

---

## Quickstart

### Prerequisites
- Python `>= 3.12`
- [`uv`](https://docs.astral.sh/uv/) (recommended)
- OpenAI-compatible LLM endpoint (e.g., vLLM, Ollama, OpenAI)
- Docker (optional, for local Langfuse tracing)

### 1. Installation

```bash
git clone https://github.com/your-org/MultiAgentSecurity.git
cd MultiAgentSecurity
uv sync --frozen
```

### 2. Environment Configuration

Export the required environment variables or reference `.env.example`:

```bash
export OPENAI_API_BASE="http://localhost:8000/v1"
export OPENAI_API_KEY="EMPTY"
export LLM_MODEL="Qwen 3.8 27B"

# Optional: Local Langfuse tracing
export LANGFUSE_PUBLIC_KEY="pk-lf-local-mas"
export LANGFUSE_SECRET_KEY="sk-lf-local-mas"
export LANGFUSE_BASE_URL="http://localhost:3000"
```

To run the local Langfuse observability stack:
```bash
docker compose up -d
```
Access the dashboard at `http://localhost:3000` (`admin@local.test` / `adminpassword123`).

---

## Usage

### Run Multi-Agent Demonstration
```bash
uv run python sample_agents_run.py
```

### Run Benchmark Experiments
Execute evaluation scenarios across `mas-eval-50` (results saved to `experiments/results/`):
```bash
# Run all scenarios
make experiments

# Run a specific scenario (e.g., Scenario 1: Worker Isolation)
uv run python -m experiments.run_experiments --scenario scenario_1

# Fast verification (2 runs per scenario)
uv run python -m experiments.run_experiments --limit 2
```

### Development & Testing
```bash
make check      # Run lint, typecheck, and unit tests
make test       # Run fast offline unit tests (tests/)
make eval       # Run live LLM evaluations (evals/)
make format     # Auto-format code with Ruff
```

---

## Benchmark Results

Empirical results from the `mas-eval-50` evaluation suite across 71 executions:

| Metric | Scope | Evaluated | Defended | Breached | Rate |
| :--- | :--- | :---: | :---: | :---: | :---: |
| **Worker Ingestion ASR** | Scenario 1 (Adversarial) | 40 | 23 | 17 | **42.5% ASR** |
| **Worker Ingestion DSR** | Scenario 1 (Adversarial) | 40 | 23 | 17 | **57.5% DSR** |
| **Benign False Positive Rate** | Scenario 1 (Benign Controls) | 10 | 10 | 0 | **0.0% FPR** |
| **Cross-Context Mixed ASR** | Scenario 2 (Mixed Pairs) | 12 | 8 | 4 | **33.3% ASR** |
| **Multi-Adversarial Stress ASR** | Scenario 3 (Parallel Batches) | 8 | 1 | 7 | **87.5% ASR** |
| **Single Worker Full-Batch ASR** | Scenario 4 (All 50 Docs) | 50 | 40 | 0 | **0.0% ASR** |

Detailed reports are generated in `experiments/results/latest_summary.md`.

---

## Repository Structure

```
MultiAgentSecurity/
├── data/                        # mas-eval-50 benchmark dataset & metadata
├── evals/                       # Live LLM behavioral evaluations
├── experiments/                 # Multi-scenario experiment runner & results
├── src/
│   ├── agents/                  # Orchestrator & Worker LangGraph definitions
│   └── utils/                   # Logging, telemetry, and tools
├── tests/                       # Fast deterministic unit tests (mocked LLM)
├── docker-compose.yml           # Self-hosted Langfuse stack
├── Makefile                     # Developer commands
├── pyproject.toml               # Project dependencies & tool configs
└── uv.lock                      # Locked dependencies
```
