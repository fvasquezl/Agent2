# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Current state

This is an early-stage successor to the sibling project `../Agent1` (a Spanish-language CLI chat agent on Groq's OpenAI-compatible API, with tool calling and Postgres/Supabase long-term memory). Right now it only holds files copied from Agent1: `agent.py`, `long_term_memory.py` and `requirements.txt` are byte-identical to `../Agent1/src/agent1/agent.py`, `../Agent1/src/agent1/long_term_memory.py` and `../Agent1/requirements.txt`.

**It does not run as-is.** Both modules import from the `agent1` package (`agent1.memory`, `agent1.tools`, `agent1.tools.memory`, `agent1.long_term_memory`, `agent1.config`), none of which exist in this directory, and the local `venv/` (Python 3.14.7) has no packages installed. Before running anything, decide with the user whether to:
- vendor the missing modules (`memory.py`, `config.py`, `tools/base.py`, `tools/memory.py`, `cli.py` from `../Agent1/src/agent1/`) into this repo and rewrite the imports, or
- keep depending on Agent1 (`pip install -e ../Agent1` into this venv).

There is no git repo, `pyproject.toml`, README, test suite or linter config yet. `../Agent1/pyproject.toml` has the `basedpyright` config (Python 3.14, standard mode) if type checking is wanted here.

## Setup

```
source venv/bin/activate
pip install -r requirements.txt
```

The code expects a `.env` with `GROQ_API_KEY` and `DATABASE_URL` (Postgres connection string, Supabase in practice). Agent1's `config.py` loads it with `load_dotenv()` and exits with a Spanish message if a key is missing. It hardcodes `MODEL = "openai/gpt-oss-120b"`, `MEMORY_MAX_MESSAGES = 10` and `USER_ID = "1"`.

`python long_term_memory.py` is a manual smoke test: it reads and prints the stored memories for `USER_ID`.

## Architecture

- **`agent.py`**: `Agent.chat(user_text)` runs the tool-calling loop.
  - It builds the messages: the system prompt, then short-term memory (`SimpleMemory`, a sliding window of recent user/assistant turns), then the user message.
  - It calls Groq with every tool's schema. Each `tool_call` is dispatched by name through `_run_tool` → `tool.func(**json_args)`; an unknown tool or bad arguments returns `{"error": ...}` to the model. Results are appended as `role: tool` messages, and the loop repeats until the model replies with plain content.
  - Only the final user/assistant text goes into short-term memory; tool-call messages do not.
- **The system prompt is a template.** `SYSTEM_PROMPT` contains `{memories_text}`, which `_build_system_prompt()` fills on every turn with the 20 most recent long-term memories. Literal braces added to the prompt must be escaped as `{{ }}` because of `str.format`. If the database fails (`psycopg.Error`), the prompt gets a placeholder and the chat continues.
- **The long-term memory tool is always registered.** The prompt tells the model to save personal info with `guardar_memoria_largo_plazo`, so `Agent.__init__` always appends `crear_herramientas_memoria(ltm, user_id)` to whatever tools are passed in. That tool is a closure over the `LongTermMemory` instance and `user_id`.
- **`long_term_memory.py`**: `LongTermMemory` opens a new psycopg connection for each call, with `dict_row` and `prepare_threshold=None`. Prepared statements are disabled because of Supabase's pooler. It reads and writes the `public.largo_plazo(user_id, memory, created_at)` table. `format_memories` renders `YYYY-MM-DD HH:MM:<memory>` lines in local time, which the prompt uses so the model can reason about recency.
- **Tools** (Agent1's `tools/base.py`): a frozen `Tool` dataclass with `name`, `description`, `parameters` (JSON Schema) and `func`; `schema()` returns the Groq tool param. By convention, tool functions return a dict on success or a Spanish `"ERROR: ..."` string on failure, and print a `Herramienta ... llamada con ...` trace line.

## Conventions

User-facing text, prompts, tool names and descriptions, and code comments are in Spanish. Keep it that way.
