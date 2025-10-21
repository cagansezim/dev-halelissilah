# AI-Enterprise-Stack 🛠️
**Local, open-source agentic development + V&V platform for Mac Studio (M3 Ultra, 512 GB UMA)**  
**Models:** FP16/BF16 on `llama.cpp` (Metal), large context (64k+).  
**Agents:** OpenHands (interactive), optional SWE-agent (headless).  
**Services:** RAG (Milvus), Jira façade (MCP-style), Orchestrator (dual-LLM routing), Phoenix (traces), Portainer (ops).  
**Quality Gates:** Tests, RTM, prompt evals, security scans, docs.

---

## Table of contents
- [1. What this repo gives you](#1-what-this-repo-gives-you)
- [2. Architecture](#2-architecture)
- [3. Requirements](#3-requirements)
- [4. Install & model preparation](#4-install--model-preparation)
- [5. Configuration](#5-configuration)
- [6. Start everything (Quickstart)](#6-start-everything-quickstart)
- [7. Daily runbook](#7-daily-runbook)
- [8. Using the system](#8-using-the-system)
- [9. Repo layout](#9-repo-layout)
- [10. CI, Docs, and Traceability](#10-ci-docs-and-traceability)
- [11. Monitoring & Observability](#11-monitoring--observability)
- [12. Performance tuning (Metal, big contexts)](#12-performance-tuning-metal-big-contexts)
- [13. Security & Guardrails](#13-security--guardrails)
- [14. Troubleshooting](#14-troubleshooting)
- [15. FAQ](#15-faq)
- [16. License](#16-license)

---

## 1. What this repo gives you

- **Two local LLM servers** (FP16/BF16) via `llama.cpp` + **Metal**:
  - **Reasoning**: (e.g., Mixtral 8×22B FP16 or Llama-3.1-70B FP16) with **64k–128k** context.
  - **Coding**: (e.g., DeepSeek-Coder-V2 FP16) with large context and concurrency.
- **Orchestrator API** with **dual-agent routing** (reasoning vs code tools).
- **RAG service** (Milvus + hybrid re-ranking) for grounded answers and planning.
- **MCP-style Jira façade** (simple REST wrapper).
- **OpenHands** integration (UI cockpit) + optional **SWE-agent** lane.
- **Operational tooling**: Portainer (containers), Phoenix (LLM traces), health scripts.
- **Quality gates**: Dockerized tests, RTM (requirements-tests mapping), prompt evals, lint/type/security scans.
- **Docs system**: MkDocs + ADRs + C4 folder.

---

## 2. Architecture

```
                 ┌────────────────────────────┐
                 │     OpenHands (UI)         │
                 │  (dev cockpit for agents)  │
                 └────────────┬───────────────┘
                              │  HTTP (OpenAI API)
     ┌────────────────────────┴────────────────────────┐
     │                                                 │
┌────▼─────┐                                 ┌─────────▼─────────┐
│ Reasoning│ http://localhost:8081/v1        │   Coding LLM      │ http://localhost:8082/v1
│ LLM      │ llama.cpp + Metal (FP16)        │ llama.cpp + Metal │
│ (64k+)   │ plan/summarize/review           │ (code, tests, PR) │
└────┬─────┘                                 └─────────┬─────────┘
     │                                                │
     │                ┌───────────────────────────────┴───────────┐
     │                │            Orchestrator API               │
     │                │  (LangChain; routes to Reason/Code LLMs)  │
     │                │  Tools: git, docker tests, Jira           │
     │                └───────┬───────────────────────┬───────────┘
     │                        │                       │
     │                        │                       │
┌────▼───────┐        ┌───────▼───────┐        ┌──────▼───────┐
│   RAG      │        │  MCP-Jira     │        │   Phoenix    │
│ (Milvus)   │        │ façade (REST) │        │ (LLM traces) │
└────┬───────┘        └───────┬───────┘        └──────┬───────┘
     │                        │                       │
     │                        │                       │
     └────────►  Portainer (containers)  ◄────────────┘
```

**Flow (typical):** Jira issue → OpenHands plans with RAG → Orchestrator routes “plan” to Reasoning LLM and “implement/test” to Coding LLM → code/test in Docker → PR → CI gates → Docs & RAG updated.

---

## 3. Requirements

- **Hardware:** Mac Studio **M3 Ultra + 512 GB unified memory**
- **macOS:** Sonoma / Sequoia (ARM64)
- **Installed:**
  - [Homebrew](https://brew.sh/)
  - Docker Desktop for Mac (Apple Silicon)
  - Python 3.12 (Homebrew is fine)
  - Git
  - (Optional) `uv` for OpenHands one-liner
- **Accounts/Tokens:** Jira Cloud email + API token

---

## 4. Install & model preparation

1) **Clone / create the repo structure**:

```bash
mkdir -p ~/dev/ai-enterprise-stack
cd ~/dev/ai-enterprise-stack
git init
```

2) **Install local tools**:

```bash
./scripts/install_deps.sh
```

3) **Build `llama.cpp` with Metal + convert models to FP16/BF16**:

- Put your HF model directories somewhere (e.g., `~/hf/mixtral-8x22b-instruct`, `~/hf/deepseek-coder-v2-instruct`).
- Edit lines inside `./scripts/models_prepare_fp16.sh` to point to your paths, then:

```bash
./scripts/models_prepare_fp16.sh
```

> This creates GGUF **FP16** files under `~/llama.cpp/llama.cpp/models/…`.  
> **Do not quantize.**

---

## 5. Configuration

Edit `./.env`:

```dotenv
REASON_BASE=http://localhost:8081/v1
CODE_BASE=http://localhost:8082/v1
OPENAI_API_KEY=dummy

# Large contexts:
CTX_REASON=65536
CTX_CODE=49152

# RAG:
RAG_COLLECTION=docs
EMB_MODEL=intfloat/e5-large-v2
HEAD_URL=${REASON_BASE}

# Jira:
JIRA_BASE_URL=https://yourorg.atlassian.net
JIRA_EMAIL=you@yourorg.com
JIRA_API_TOKEN=put_token_here
```

> **Model paths:** If you didn’t use the default, set:
> - `REASON_MODEL_PATH=/ABS/PATH/to/your/reasoning-f16.gguf`
> - `CODE_MODEL_PATH=/ABS/PATH/to/your/coder-f16.gguf`

---

## 6. Start everything (Quickstart)

**A) Start LLM servers (two terminals):**
```bash
# Terminal 1 – Reasoning (64k default; use *_128k.sh for 128k RoPE)
./scripts/llama_launch_reason.sh

# Terminal 2 – Coding
./scripts/llama_launch_code.sh
```

**B) Bring up infra/services:**
```bash
make up
make rag-build && make rag-run
make orch-build && make orch-run
```

**C) Seed RAG & verify:**
```bash
./scripts/ingest_docs.sh
./scripts/health_check.sh
```

**D) OpenHands cockpit (interactive agents):**
```bash
uvx --python 3.12 --from openhands-ai openhands serve
# UI → Providers:
#   Reasoning: http://localhost:8081/v1
#   Coding:    http://localhost:8082/v1
```

---

## 7. Daily runbook

1) Start Reasoning & Coding servers:
```bash
./scripts/llama_launch_reason.sh
./scripts/llama_launch_code.sh
```

2) Start services:
```bash
./scripts/services_up.sh
```

3) Health checks:
```bash
./scripts/health_check.sh
```

4) Work in **OpenHands** (interactive) or label Jira issues `auto-fix` for a headless lane (SWE-agent, if you add it).

5) Observe:
- Portainer: `https://localhost:9001`
- Phoenix: `http://localhost:6006`
- Logs: `./scripts/logs_follow.sh`

6) End of day:
```bash
./scripts/services_down.sh
# stop the two llama.cpp servers (Ctrl+C each terminal)
```

---

## 8. Using the system

### Orchestrator API (manual calls)
- **Reasoning task:**
```bash
curl "http://localhost:9000/run?q=Summarize%20issue%20PROJ-123%20and%20list%205%20steps&mode=reason"
```

- **Coding task (branch + tests):**
```bash
curl "http://localhost:9000/run?q=Create%20branch%20feature/PROJ-123%20and%20write%20unit%20tests&mode=code"
```

### RAG Q&A
```bash
curl "http://localhost:8000/ask?q=What%20is%20our%20release%20checklist%3F"
```

### Jira façade examples
```bash
# get issue
curl "http://localhost:7001/issue/PROJ-123"

# comment
curl -X POST "http://localhost:7001/issue/PROJ-123/comment" \
  -H "content-type: application/json" -d '{"body":"PR opened: https://github.com/org/repo/pull/42"}'
```

---

## 9. Repo layout

```
.
├─ .env
├─ Makefile
├─ infra/compose.yaml                # Milvus, ArangoDB, Portainer, Phoenix, MCP-Jira
├─ scripts/                          # launch, health, logs, ingest, model prep
├─ services/
│  ├─ rag/                           # RAG FastAPI (Milvus + re-rank)
│  ├─ orchestrator/                  # dual-agent API (reason/code tools)
│  │  └─ mcp-jira/                   # Jira façade
│  └─ observability/phoenix/         # Phoenix Dockerfile
├─ agents/tools/                     # jira/git/docker tools
├─ .devcontainer/devcontainer.json   # reproducible dev box
├─ Dockerfile.dev                    # dockerized tests for CI/agents
├─ .github/workflows/                # ci.yml, prompt-evals.yml, docs.yml
├─ promptfooconfig.yaml              # prompt evals (promptfoo)
├─ docs/ & mkdocs.yml                # docs/ADRs/C4
├─ tests/rtm.yaml & tools/verify_rtm.py
└─ ...
```

---

## 10. CI, Docs, and Traceability

- **CI** (GitHub Actions):
  - Lint (`ruff`, `mypy`), security (`bandit`, `safety`), **secrets scan** (`gitleaks`)
  - **RTM** verifier (issues ↔ tests)
  - Dockerized test run (from `Dockerfile.dev`)
- **Prompt Evals**: `promptfoo` against your Reasoning endpoint to catch regressions (e.g., PII leakage).
- **Docs**: MkDocs (Material) builds on `main`. Add ADRs via `docs/architecture/adr/` (use any numbering scheme).
- **Traceability**: keep `tests/rtm.yaml` up to date; ensure PR template asks for it.

---

## 11. Monitoring & Observability

- **Portainer** (`https://localhost:9001`):
  - Service health, logs, stats, and shell into containers.
- **Phoenix** (`http://localhost:6006`):
  - Ready to receive traces; add OpenInference hooks later in Orchestrator if you want prompt/tool spans.
- **Health script**: `./scripts/health_check.sh`
- **Follow logs**: `./scripts/logs_follow.sh`

---

## 12. Performance tuning (Metal, big contexts)

- **Context (`-c`)**: Start **64k** Reasoning / **48–64k** Coding.  
  For **128k**, use the `*_128k.sh` launchers (RoPE scaling) unless you have native 128k weights.  
- **Batch (`-b`)**: Higher = better throughput, but single-request latency may rise.  
  Start: Reasoning **1024**, Coding **768**; tune down if edits feel sluggish.  
- **Parallel (`--parallel`)**: Controls concurrent requests. Increase only if you truly need simultaneous jobs.  
- **Threads (`-t`)**: 20–32 is a good range; ensure CPU feeder doesn’t starve GPU.  
- **`-ngl 999`**: Full GPU offload (Metal). Reduce only if you see memory pressure.  
- **Summarize-then-Plan**: Even with 64k+, orchestrator’s summarize pass keeps prompts crisp and reduces drift.

---

## 13. Security & Guardrails

- Agents **never** execute host shell commands; they use **Dockerfile.dev** only.  
- Store tokens in `.env` or macOS Keychain; **never** commit them.  
- Enable **branch protection**: require CI + prompt evals + code review.  
- Timeouts / iteration caps in OpenHands or headless lanes (SWE-agent config).  
- PR template enforces: tests updated, docs updated, RTM entry added.

---

## 14. Troubleshooting

**Models don’t start / OOM**  
- Lower `-c` (context) or `-b` (batch), remove `--mlock`, or reduce `--parallel`.
- Confirm GGUF files are **FP16/BF16** and paths are correct.

**Orchestrator 500s**  
- Check that both LLM servers are up:  
  `curl http://localhost:8081/v1/models` and `…8082…`
- Verify `.env` is loaded for the container (use `orch-run` target).

**RAG returns empty contexts**  
- Ensure Milvus is healthy in Portainer.
- Re-run `./scripts/ingest_docs.sh` with real content.
- Increase `k` in `/ask?k=…` or adjust `budget_tokens`.

**Jira 401/403**  
- Double-check `JIRA_EMAIL` and `JIRA_API_TOKEN`.
- Try the façade endpoints directly to see the raw error.

**OpenHands doesn’t call your servers**  
- In OpenHands UI, set providers explicitly to `http://localhost:8081/v1` and `http://localhost:8082/v1`.
- Some clients require an API key header; `OPENAI_API_KEY=dummy` works for llama.cpp.

---

## 15. FAQ

**Can I run a third LLM server for PR reviews alone?**  
Yes—copy a launcher script, tune `-b` smaller and `temperature` lower. Point PR-review tools at that port.

**What about vLLM?**  
You can add vLLM for batch evals, but on Apple Silicon, `llama.cpp` + Metal is typically faster/leaner for local use.

**How big can the context go?**  
64k is the sweet spot. 128k is possible with RoPE scaling; pair it with RAG + summarize-refine for best accuracy.

**Do I need quantization?**  
No—your 512 GB UMA runs FP16/BF16 fine. Quantization is optional for even more concurrency.

---

## 16. License

This stack glues open-source components. Respect each component’s license (Milvus, ArangoDB, Phoenix, `llama.cpp`, model licenses, etc.). Place your project’s license in `LICENSE`.
