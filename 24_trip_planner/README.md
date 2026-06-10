# 🌍 LangGraph Trip Planner

A multi-node AI pipeline built with **LangGraph** that takes a traveller's raw preferences and produces a full trip plan — destination, day-by-day itinerary, and a categorised packing list — by chaining three GPT-4o-mini calls through a shared state graph.

---

## Tech Stack

| Library | Purpose |
|---|---|
| `langgraph` | Graph engine — builds and runs the node pipeline |
| `langchain` | Core abstractions (messages, runnables) |
| `langchain-openai` | ChatOpenAI wrapper for GPT-4o-mini |
| `python-dotenv` | Loads `OPENAI_API_KEY` from `.env` |

---

## Project Structure

```
trip_planner/
├── trip_planner.py   # Main pipeline — all nodes, graph, and runner
├── .env              # Your OpenAI API key (never commit this)
└── README.md         # This file
```

---

## Setup

**1. Install dependencies**
```bash
pip install langgraph langchain langchain-openai python-dotenv
```

**2. Create a `.env` file**
```
OPENAI_API_KEY=sk-...
```

**3. Run**
```bash
python trip_planner.py
```

---

## How It Works — The Full Workflow

```
User string (preferences)
        │
        ▼
  ┌──────────┐
  │  START   │  ← graph.invoke({"preference": user_preferences})
  └──────────┘
        │
        ▼
┌──────────────────────┐
│  Node 1              │  reads  → preference
│  destination_setter  │  calls  → gpt-4o-mini
│                      │  writes → destination
└──────────────────────┘
        │
        ▼
┌──────────────────────┐
│  Node 2              │  reads  → destination, preference
│  itinerary_builder   │  calls  → gpt-4o-mini
│                      │  writes → itinerary
└──────────────────────┘
        │
        ▼
┌──────────────────────┐
│  Node 3              │  reads  → destination, itinerary
│  packing_list        │  calls  → gpt-4o-mini
│                      │  writes → packing_list
└──────────────────────┘
        │
        ▼
   ┌─────────┐
   │   END   │  ← final_state contains all four fields
   └─────────┘
```

Every node receives the **full shared state**, reads what it needs, and returns **only the key(s) it writes**. LangGraph merges each return dict back into the state before passing it to the next node.

---

## The Shared State — `trip_planner` (TypedDict)

```python
class trip_planner(TypedDict):
    preference  : str   # INPUT  — provided at graph.invoke()
    destination : str   # Node 1 fills this
    itinerary   : str   # Node 2 fills this
    packing_list: str   # Node 3 fills this
```

- Defined using Python's `TypedDict` — it is just a plain dict with type hints.
- All four keys exist for the lifetime of the graph run.
- Nodes only write their own key; they never overwrite each other's output.

---

## Node Breakdown

### Node 1 — `destination_setter`

```python
builder.add_node("dp", destination_setter)
```

- **Reads:** `state["preference"]`
- **Prompt:** Asks GPT-4o-mini to suggest exactly one destination with a 2-sentence reason.
- **Writes:** `{"destination": "..."}`

### Node 2 — `itinerary_builder`

```python
builder.add_node("ib", itinerary_builder)
```

- **Reads:** `state["destination"]`, `state["preference"]`
- **Prompt:** Asks GPT-4o-mini for a day-by-day itinerary formatted as `Day N: <activities>`.
- **Writes:** `{"itinerary": "..."}`

### Node 3 — `packing_list`

```python
builder.add_node("plb", packing_list)
```

- **Reads:** `state["destination"]`, `state["itinerary"]`
- **Prompt:** Asks GPT-4o-mini for a packing list with headers: Clothing, Toiletries, Documents, Electronics, Miscellaneous.
- **Writes:** `{"packing_list": "..."}`

---

## Edge Wiring

```python
builder.add_edge(START, "dp")   # always enter at Node 1
builder.add_edge("dp",  "ib")   # after Node 1, run Node 2
builder.add_edge("ib",  "plb")  # after Node 2, run Node 3
builder.add_edge("plb", END)    # after Node 3, finish
```

`add_edge(A, B)` = unconditional transition. No branching, no loops — a pure sequential pipeline. The graph is compiled once with `builder.compile()` and reused for every `graph.invoke()` call.

---

## Key Concepts to Remember

### Why nodes return a dict, not the full state

```python
# ✅ Correct — return only what you write
return {"destination": response.content.strip()}

# ❌ Wrong — don't return the whole state
return state
```

LangGraph calls `.update()` on the current state with whatever your node returns. Returning the full state would still work but is wasteful and can accidentally overwrite values.

### graph.invoke() vs calling the function directly

```python
# ❌ Calling the node function directly — dict returned to nobody
destination_setter({"preference": "..."})   # state["destination"] never gets set

# ✅ Using the graph — LangGraph merges the return dict into state
final_state = graph.invoke({"preference": "..."})   # all fields populated
```

The node function is just a plain Python function. The **graph engine** is the one that catches return values and merges them into the shared state. Without the graph, nothing is persisted.

### State flows forward only

Each node can only read fields that were written by a **previous** node (or the initial input). Node 3 can read `destination` (written by Node 1) and `itinerary` (written by Node 2). It cannot read `packing_list` because that is what it is currently producing.

---

## Common Bugs & Fixes

| Bug | Symptom | Fix |
|---|---|---|
| Typo in return key (`"itenerary"`) | Next node reads empty string silently | Match key exactly to `TypedDict` field name |
| Wrong node name in `add_edge` | `ValueError` at compile/invoke time | Node name in `add_edge` must match `add_node` registration |
| Variable name typo at `graph.invoke()` | `NameError` at runtime | Check variable name matches exactly |
| Calling node function without graph | State never updates | Always use `graph.invoke()` |

---

## Customising the Trip

Edit the `user_preferences` string at the bottom of `trip_planner.py`:

```python
user_preferences = "budget trip, warm sunny weather, 5 days, beach and culture mix"
```

Any plain English description works. The LLM interprets it — no special formatting needed.

---

## Extending the Pipeline

To add a fourth node (e.g. a budget estimator):

**1. Add the field to state**
```python
class trip_planner(TypedDict):
    ...
    budget_estimate: str   # new field
```

**2. Write the node function**
```python
def budget_estimator(state: trip_planner) -> dict:
    prompt = f"Estimate the total budget for this trip to {state['destination']}..."
    response = llm.invoke([HumanMessage(content=prompt)])
    return {"budget_estimate": response.content.strip()}
```

**3. Register and wire it**
```python
builder.add_node("be", budget_estimator)
builder.add_edge("plb", "be")    # was: add_edge("plb", END)
builder.add_edge("be",  END)
```

The rest of the graph is untouched.

---

## Output Example

```
============================================================
📍  DESTINATION
============================================================
Bali, Indonesia
Bali is a perfect match for a budget traveller seeking warm sunny weather...

============================================================
🗓️   ITINERARY
============================================================
Day 1: Arrive in Denpasar, check into a budget guesthouse in Seminyak...
Day 2: Visit Tanah Lot temple at sunrise, explore Canggu...
...

============================================================
🎒  PACKING LIST
============================================================
Clothing:
- Lightweight t-shirts (x5)
- Swimwear (x2)
...
Documents:
- Passport (valid 6+ months)
- Travel insurance printout
...
```
