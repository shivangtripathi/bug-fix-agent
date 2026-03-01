# 🐛 BugFix Agent

A conversational, multi-agent system that diagnoses and fixes bugs in Python codebases — powered by Google Gemini and backed by ChromaDB semantic search.

---

## ✨ Features

- **Conversational interface** — describe the bug in plain English; the agent asks clarifying questions until it understands the issue
- **Semantic code search** — ChromaDB vector index over your repo enables relevant code retrieval
- **AI-powered planning** — generates a structured fix plan (files to modify, patches, bash commands, tests)
- **Safe execution** — shows diffs and asks for confirmation before applying any changes
- **Test generation** — auto-generates pytest tests for the fixed code
- **LangSmith tracing** — full observability of every LLM call (optional)

---

## 🔄 Overall Workflow

```
User describes bug
       │
       ▼
 ConversationAgent  ──── guardrail check ────► (re-prompt if off-topic)
  (multi-turn Q&A)
       │ bug fully understood
       ▼
  PlannerAgent
  · Semantic search via ChromaDB
  · Generates: patches, tests, bash commands
       │
       ▼
  [User reviews & approves plan]
       │
       ├──► ExecutorAgent   → applies AST-level patches to source files
       │
       ├──► TestGeneratorAgent → writes pytest test files
       │
       └──► TestRunnerAgent → runs pytest, reports pass/fail
                │
                ▼
         RepoIndexer.reindex()   (ChromaDB updated with fixed code)
                │
                ▼
          Bug Report + git diff
```

---

## 🚀 Setup

### 1. Clone the repository

```bash
git clone https://github.com/shivangtripathi/bug-fix-agent
cd bug-fix-agent
```

### 2. Create and activate a virtual environment

```bash
python -m venv venv
source venv/bin/activate      # macOS / Linux
# venv\Scripts\activate       # Windows
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

Copy the example below into a `.env` file in the project root:

```env
# ── LLM Provider ────────────────────────────────────────────────
LLM_PROVIDER=gemini             # "gemini" or other which supports structured model output 

# ── Google Gemini ────────────────────────────────────────────────
GOOGLE_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-2.5-flash   # Must support structured/JSON output (e.g. gemini-2.5-pro, gemini-2.5-flash)

# ── LangSmith Tracing (optional) ────────────────────────────────
LANGSMITH_API_KEY=your_langsmith_api_key_here
LANGSMITH_TRACING=true
LANGSMITH_PROJECT=bugfix-agent

# ── Tuning ──────────────────────────────────────────────────────
MAX_CONTEXT_CHARS=32000
CHROMA_N_RESULTS=5
COMPRESSION_THRESHOLD_CHARS=32000
```

---

## 🔑 Getting API Keys

### Google Gemini API Key

1. Go to **[Google AI Studio](https://aistudio.google.com/app/apikey)**
2. Sign in with your Google account
3. Click **"Create API key"**
4. Copy the key and set it as `GOOGLE_API_KEY` in your `.env`

> **Free tier available.** Gemini Flash models have a generous free quota.

### LangSmith API Key _(optional — for tracing & observability)_

1. Sign up at **[smith.langchain.com](https://smith.langchain.com)**
2. Navigate to **Settings → API Keys**
3. Click **"Create API Key"**
4. Copy the key and set it as `LANGSMITH_API_KEY` in your `.env`
5. Set `LANGSMITH_TRACING=true` to enable tracing

> LangSmith is optional. Set `LANGSMITH_TRACING=false` (or omit) to disable it entirely.

---

## 💬 Usage

### Index your repository

Before the first chat session, index the target repository so the agent can semantically search your code:

```bash
python cli.py reindex --repo path/to/your/repo
```

### Start a bug-fixing session

```bash
python cli.py chat --repo path/to/your/repo
```

The agent will prompt you to describe the bug. Walk through the conversation — when it has enough context, it will produce a fix plan, show you the proposed patches, and ask for confirmation before making any changes.

### Demo repository

A small demo repo with intentional bugs lives in `demo_repo/`. Try it out:

```bash
python cli.py chat --repo ./demo_repo
```

---

## 🗂️ Project Structure

```
bug-fix-agent/
├── agents/
│   ├── orchestrator.py       # Coordinates all agents
│   ├── conversation_agent.py # Multi-turn dialogue + guardrails
│   ├── planner.py            # Generates fix plan via semantic search
│   ├── executor.py           # Applies patches to source files
│   ├── test_generator.py     # Generates pytest test files
│   ├── test_runner.py        # Runs pytest and reports results
│   ├── guardrails.py         # Validates messages are bug-related
│   └── llm_factory.py        # Gemini / Ollama LLM factory
├── tools/
│   ├── indexing.py           # ChromaDB repo indexer
│   ├── ast_editor.py         # AST-level code patcher (libcst)
│   ├── file_tools.py         # File read/write utilities
│   └── bash_tool.py          # Safe bash command runner
├── schemas/                  # Pydantic schemas for plan & patches
├── demo_repo/                # Sample buggy Python project
├── config.py                 # Settings loaded from .env
├── cli.py                    # Typer CLI entrypoint
└── requirements.txt
```

---

## 🧠 Design Decisions

| Decision | Rationale |
|---|---|
| **Multi-turn conversation before planning** | Forces the LLM to gather enough context (reproduction steps, affected function, expected vs. actual output) before committing to a fix plan, reducing hallucinated patches. |
| **AST-level editing (`libcst`)** | Editing the AST instead of raw strings preserves formatting, avoids off-by-one line errors, and makes patches surgically precise at the function level. |
| **ChromaDB semantic search** | Simple grep misses semantically related code (e.g. a helper called by the buggy function). Vector search retrieves contextually relevant snippets even when keyword matches fail. |
| **Structured output (Pydantic `StructuredPlan`)** | Forcing the planner LLM to emit a validated JSON schema eliminates free-form prose responses and makes patch application deterministic. |
| **LLM-based history compression** | Rather than truncating old messages (losing context), a summarisation LLM condenses older turns into a dense factual summary, keeping the bug history while staying within the token budget. |
| **Guardrail classifier** | A lightweight LLM classifier runs before every turn to block off-topic messages. Short confirmational replies (`yes`, `ok`, `looks good`) bypass the classifier entirely via a fast-path allowlist to avoid false positives. |

---

## 🔐 Permission System

Every destructive action is gated behind an explicit user prompt — nothing is applied silently. The gates run in order:

```
1. "Fix ready. Show details?"         → Preview proposed patches (diff view)
          ↓ yes
2. "Apply this fix?"                   → Commit to the overall plan
          ↓ yes
3. "Apply code patches?"               → Write changes to source files
          ↓ yes (patches applied)
4. "Run bash command `<cmd>`?"         → One prompt per bash command in the plan
          ↓ yes / no (per command)
5. "Generate test files?"              → Write AI-generated pytest files
          ↓ yes
6. "Run tests?"                        → Execute pytest and show results
```

If any gate is declined the session continues — you can keep chatting and try again, or exit cleanly. A patch retry loop is also available if the patcher fails (e.g. due to a merge conflict).

---

## ⚙️ Configuration Reference

| Variable | Default | Description |
|---|---|---|
| `LLM_PROVIDER` | `gemini` | `gemini` or `ollama` |
| `GOOGLE_API_KEY` | — | Gemini API key (required for Gemini) |
| `GEMINI_MODEL` | `gemini-2.0-flash` | Gemini model name — **must support structured/JSON output** |
| `OLLAMA_MODEL` | `gemma:2b` | Ollama model name |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL |
| `LANGSMITH_API_KEY` | — | LangSmith key (optional) |
| `LANGSMITH_TRACING` | `false` | Enable LangSmith tracing |
| `LANGSMITH_PROJECT` | `bugfix-agent` | LangSmith project name |
| `MAX_CONTEXT_CHARS` | `32000` | Max chars fed to LLM |
| `CHROMA_N_RESULTS` | `5` | Number of semantic search hits |
| `COMPRESSION_THRESHOLD_CHARS` | `32000` | Trigger LLM history compression above this |

---

## 📦 Dependencies

| Package | Purpose |
|---|---|
| `langchain` + `langchain-google-genai` | LLM abstraction & Gemini integration |
| `langsmith` | Tracing & observability |
| `chromadb` | Vector store for semantic code search |
| `libcst` | AST-level Python code editing |
| `typer` + `rich` | CLI & pretty output |
| `pydantic` | Schema validation for plans/patches |
| `pytest` | Running generated tests |
