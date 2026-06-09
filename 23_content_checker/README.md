# 🛡️ Safe Content Checker — LangGraph Pipeline

A modular, AI-powered content moderation pipeline built with **LangGraph** and **OpenAI GPT models**. It automatically rewrites user posts to be more professional, scans for banned words, and applies strict sanitization when needed.

---

## 📁 Project Structure

```
safe_content_checker/
├── .env          # API key (never commit this)
└── main.py       # Full pipeline — state, nodes, graph, runner
```

---

## ⚙️ Tech Stack

| Library | Role |
|---|---|
| `langgraph` | Graph orchestration framework |
| `langchain-openai` | LLM wrapper for OpenAI models |
| `openai` | Underlying OpenAI SDK |
| `python-dotenv` | Load `.env` variables into environment |

---

## 🚀 Setup

### 1. Install dependencies
```bash
pip install langgraph langchain-openai openai python-dotenv
```

### 2. Create `.env` file
```
OPENAI_API_KEY=sk-your-key-here
```

### 3. Run the pipeline
```bash
python main.py
```

---

## 🧠 Core Concepts

### What is LangGraph?
LangGraph is a framework for building **stateful, multi-step AI workflows** as directed graphs. Each step is a node; data flows between nodes via a shared state dict.

### Key primitives used:
| Primitive | Purpose |
|---|---|
| `StateGraph` | The graph builder object |
| `TypedDict` | Defines the shape of the shared state |
| `add_node()` | Registers a function as a node |
| `add_edge()` | Adds an unconditional A → B connection |
| `add_conditional_edges()` | Routes based on a runtime decision |
| `set_entry_point()` | Declares which node runs first |
| `compile()` | Validates and locks the graph |
| `invoke()` | Runs the graph and returns final state |
| `END` | LangGraph's built-in terminal sentinel |

---

## 🗂️ State

```python
class State(TypedDict):
    user_post:      str    # raw input from user
    rewritten_post: str    # filled by Node 1, possibly updated by Node 3
    is_flagged:     bool   # set by Node 2
```

**Rules about State:**
- Every node receives the **full** state dict
- Every node returns only the keys it **modified** — LangGraph merges them back
- All keys must be **initialized** in the input, even with empty defaults
- State is **mutable across nodes** — Node 3 can overwrite Node 1's output

---

## 🔄 Workflow (Full Pipeline)

```
         ┌─────────────────────────────────────────┐
         │           user_post (input)              │
         └────────────────┬────────────────────────┘
                          ▼
              ┌───────────────────────┐
              │   NODE 1: rewriter    │  GPT-4o-mini
              │  Rewrites to          │  temp=0.3
              │  professional tone    │
              └───────────┬───────────┘
                          │ sets rewritten_post
                          ▼
              ┌───────────────────────┐
              │   NODE 2: checker     │  Pure Python
              │  Scans rewritten_post │  (no LLM call)
              │  for banned words     │
              └───────────┬───────────┘
                          │ sets is_flagged
                          ▼
                   is_flagged?
                  /           \
              False            True
                │                │
                ▼                ▼
              END    ┌───────────────────────┐
           (print)   │ NODE 3:               │  GPT-4o
                     │ strict_rewriter       │  temp=0.1
                     │ Removes all           │
                     │ problematic content   │
                     └───────────┬───────────┘
                                 │ overwrites rewritten_post
                                 ▼
                                END
                             (print)
```

---

## 🧩 Node Reference

### Node 1 — `rewriter`
- **Model:** `gpt-4o-mini` (temperature=0.3)
- **Input:** `state["user_post"]`
- **Output:** `{"rewritten_post": <text>}`
- **Purpose:** Makes the post sound professional and clear while preserving original meaning
- **When called:** Always — first node in every run

### Node 2 — `checker`
- **Model:** None — pure Python logic
- **Input:** `state["rewritten_post"]`
- **Output:** `{"is_flagged": True/False}`
- **Purpose:** Checks if any word in the post matches the `BANNED_WORDS` list (case-insensitive)
- **When called:** Always — after Node 1

### Node 3 — `strict_rewriter`
- **Model:** `gpt-4o` (temperature=0.1)
- **Input:** `state["rewritten_post"]`
- **Output:** `{"rewritten_post": <cleaned text>}`
- **Purpose:** Aggressively sanitizes content to be completely safe and neutral
- **When called:** Only when `is_flagged=True`

---

## 🚦 Edge Reference

| Edge Type | From | To | Condition |
|---|---|---|---|
| Normal | `rewriter` | `checker` | Always |
| Conditional | `checker` | `END` | `is_flagged=False` |
| Conditional | `checker` | `strict_rewriter` | `is_flagged=True` |
| Normal | `strict_rewriter` | `END` | Always |

### How conditional edges work
```python
def route_after_checker(state: State) -> str:
    if state["is_flagged"]:
        return "flagged"   # string key → maps to strict_rewriter
    else:
        return "clean"     # string key → maps to END

graph_builder.add_conditional_edges(
    "checker",
    route_after_checker,
    {
        "flagged": "strict_rewriter",
        "clean":   END
    }
)
```
The routing function returns a **string**. That string must match a key in the `path_map` dict — a mismatch causes a runtime error.

---

## 🚫 Banned Words

Defined as a hardcoded list in `main.py`:
```python
BANNED_WORDS = [
    "hate", "kill", "stupid", "idiot", "dumb",
    "attack", "destroy", "abuse", "violent", "illegal"
]
```

**To customize:** Add or remove words from this list. All comparisons are lowercased, so `"Kill"`, `"KILL"`, and `"kill"` are all caught.

---

## 🖨️ Output Format

```
▶ Running Safe Content Checker pipeline...

============================================================
📥 Original post:
   <user's raw input>

⚠️  Was flagged:   True / False

📤 Final post:
   <rewritten or sanitized post>
============================================================
```

---

## ⚠️ Important Notes & Gotchas

**State initialization** — Always seed all keys in the initial state dict, even with empty defaults (`""`, `False`). LangGraph will raise a `KeyError` if a node reads an uninitialized key.

**Routing strings must match exactly** — The string returned by your routing function must be an exact key in the `path_map` dict. Typos here cause silent routing failures.

**Nodes return partial dicts** — Return only the keys you changed. LangGraph merges them back in. Do not return the full state.

**Node 3 overwrites Node 1's output** — Both write to `rewritten_post`. This is intentional; the final value is the last writer's output.

**temperature settings matter:**
- `gpt-4o-mini` at `0.3` → creative enough to rewrite naturally
- `gpt-4o` at `0.1` → very deterministic; good for strict, consistent sanitization

**No memory between runs** — Each `graph.invoke()` call is stateless. State only lives for one run.

---

## 🔧 Extending the Project

| Goal | How |
|---|---|
| Add more banned words | Append to `BANNED_WORDS` list |
| Change the LLM | Swap model name in `ChatOpenAI(model=...)` |
| Add a logging node | Create a new function, `add_node()`, insert `add_edge()` calls |
| Use async execution | Replace `graph.invoke()` with `await graph.ainvoke()` |
| Add human-in-the-loop | Use LangGraph's `interrupt_before` or `interrupt_after` on a node |
| Persist state across runs | Integrate LangGraph's built-in checkpointing with `SqliteSaver` or `MemorySaver` |
| Stream output token by token | Use `graph.stream()` instead of `graph.invoke()` |

---

## 📌 Quick Reference — LangGraph API

```python
from langgraph.graph import StateGraph, END

g = StateGraph(MyState)       # create graph with state schema
g.add_node("name", fn)        # register a node
g.set_entry_point("name")     # first node to run
g.add_edge("a", "b")          # unconditional edge
g.add_conditional_edges(      # branching edge
    "source_node",
    routing_fn,               # returns a string
    {"string": "target_node"} # string → node map
)
graph = g.compile()           # validate and build
result = graph.invoke(state)  # run; returns final state
```

---

## 📄 License

MIT — free to use, modify, and distribute.
