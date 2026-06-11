# 📓 Multi-User Journal Assistant

A persistent, memory-enabled CLI chatbot built with **LangGraph + MongoDB**.  
Each user gets their own isolated conversation history that survives across script restarts.

---

## Table of Contents

1. [What This Project Does](#what-this-project-does)
2. [Tech Stack & Why Each Tool Was Chosen](#tech-stack--why-each-tool-was-chosen)
3. [Project Structure](#project-structure)
4. [Setup & Installation](#setup--installation)
5. [Complete Workflow — How It Runs](#complete-workflow--how-it-runs)
6. [Key Concepts Explained](#key-concepts-explained)
7. [Code Map — Every Function](#code-map--every-function)
8. [MongoDB — What Gets Stored](#mongodb--what-gets-stored)
9. [Important Patterns to Remember](#important-patterns-to-remember)
10. [Common Errors & Fixes](#common-errors--fixes)
11. [How to Extend This Project](#how-to-extend-this-project)
12. [Revision Checklist](#revision-checklist)

---

## What This Project Does

- A command-line journal assistant powered by GPT-4o-mini
- Multiple users can use it — each user has a completely separate memory lane
- Conversation history **persists across restarts** — close the script, reopen it, the AI still remembers everything
- User identity is handled by a simple name → used as a key in MongoDB

**Input → Output:**
```
You type a message → AI reads full history → AI replies → everything saved to MongoDB
```

---

## Tech Stack & Why Each Tool Was Chosen

| Tool | What it does in this project | Why this tool |
|---|---|---|
| `langgraph` | Builds the stateful AI pipeline (graph) | Handles state + memory natively |
| `langchain-openai` | Wraps GPT-4o-mini API calls | Clean interface to OpenAI |
| `langchain-core` | Provides `HumanMessage`, `AIMessage`, `SystemMessage` | Typed messages the graph understands |
| `langgraph-checkpoint-mongodb` | Saves/loads graph state to MongoDB | Persistent memory across restarts |
| `pymongo` | Python driver to talk to MongoDB | Required by the checkpointer |
| `python-dotenv` | Reads `.env` file into environment | Keeps secrets out of the code |

---

## Project Structure

```
project/
│
├── journal_assistant.py    ← main file, all logic lives here
├── requirements.txt        ← all pip dependencies
├── .env                    ← your secrets (never commit this)
├── .env.example            ← template to show what .env needs
└── README.md               ← this file
```

---

## Setup & Installation

### Step 1 — Start MongoDB with Docker
```bash
docker run -d \
  --name journal-mongo \
  -p 27017:27017 \
  -e MONGO_INITDB_ROOT_USERNAME=admin \
  -e MONGO_INITDB_ROOT_PASSWORD=admin \
  mongo:7
```
Verify it's running:
```bash
docker ps | grep journal-mongo
```

### Step 2 — Create Python environment
```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### Step 3 — Create your `.env` file
```bash
cp .env.example .env
# open .env and paste your OpenAI API key
```

Your `.env` should look like:
```
OPENAI_API_KEY=sk-your-key-here
MONGO_URI=mongodb://admin:admin@localhost:27017
```

### Step 4 — Run
```bash
python journal_assistant.py
```

---

## Complete Workflow — How It Runs

This is the exact order of execution every time you run the script.

### Phase 1 — Startup (runs once)

```
python journal_assistant.py
        ↓
if __name__ == "__main__": main()
        ↓
load_dotenv()              ← reads .env file
        ↓
os.getenv(OPENAI_API_KEY)  ← if missing → print error → exit
os.getenv(MONGO_URI)       ← defaults to localhost if not set
        ↓
with MongoDBSaver.from_conn_string(MONGO_URI) as checkpointer:
        ↓
    build_graph(checkpointer)   ← assemble the AI pipeline
```

### Phase 2 — Graph Build (runs once, inside with block)

```
build_graph(checkpointer)
        ↓
StateGraph(State)               ← blank graph, State = {messages: list}
        ↓
add_node("chatbot", chatbot)    ← register the AI function
        ↓
add_edge(START → chatbot → END) ← wire the pipeline
        ↓
compile(checkpointer=cp)        ← lock + attach MongoDB saver
        ↓
returns compiled graph object
```

### Phase 3 — CLI Menu (runs once)

```
get_user_config(checkpointer)
        ↓
print menu: 1 = existing user, 2 = new user
        ↓
input choice  ← if not 1 or 2: loop and ask again
        ↓
input name → lowercase → replace spaces with "_"
        ↓
        ├── Choice 1 (existing user)
        │       thread_id = name
        │       checkpointer.get(config) → None?
        │           Yes → "starting fresh"
        │           No  → "welcome back, loading history"
        │
        └── Choice 2 (new user)
                thread_id = name
                already taken? → try name_2, name_3… until free
                "welcome, creating your journal"
        ↓
make_config(thread_id)
→ returns {"configurable": {"thread_id": "alice"}}
        ↓
return (username, config) to main()
```

### Phase 4 — Chat Loop (repeats until exit)

```
chat_loop(graph, config, username)
        ↓
┌─────────────────────────────────────────┐
│  while True:                            │
│          ↓                              │
│  input("You: ")                         │
│          ↓                              │
│  Ctrl+C / Ctrl+D? → print bye → break  │
│          ↓                              │
│  empty string? → continue (loop again) │
│          ↓                              │
│  == "exit"? → print bye → break        │
│          ↓                              │
│  HumanMessage(content=user_input)       │
│          ↓                              │
│  graph.invoke(                          │
│    {"messages": [human_msg]},           │
│    config=config                        │
│  )                                      │
│    ↓ inside invoke:                     │
│    1. load checkpoint from MongoDB      │
│    2. merge new message into state      │
│    3. run chatbot node → GPT-4o-mini    │
│    4. save updated state to MongoDB     │
│          ↓                              │
│  result["messages"][-1].content         │
│          ↓                              │
│  print AI reply                         │
│          ↓                              │
│  (loop back to top)                     │
└─────────────────────────────────────────┘
        ↓ (after break)
MongoDB connection closes cleanly (with block exits)
```

---

## Key Concepts Explained

### 1. Checkpointer

The checkpointer is middleware between your graph and MongoDB. After every node finishes, it serialises the entire `State` (your messages list) and writes it to MongoDB. On the next `invoke()` call, it loads that state back automatically. Your code never manually reads or writes MongoDB — the checkpointer does it.

```
Node runs → Checkpointer serialises State → MongoDB stores it
Next call → MongoDB gives it back → Checkpointer deserialises → Node receives full history
```

### 2. thread_id

A string that acts as the primary key for a user's conversation history. Every `invoke()` call passes a config dict with `thread_id`. The checkpointer uses this to know which documents to read and write.

```python
config = {"configurable": {"thread_id": "alice"}}
# All invoke() calls with "alice" share the same message history
# "bob" gets a completely separate history — never mixed
```

**Same thread_id = same memory lane. Different thread_id = completely isolated.**

### 3. The `with` Block Rule

`MongoDBSaver` opens real TCP connections to MongoDB. The `with` block keeps those connections open for the entire lifetime of the program, then closes them cleanly on exit — even if an exception occurs.

```python
# CORRECT — everything inside the with block
with MongoDBSaver.from_conn_string(URI) as checkpointer:
    graph = build_graph(checkpointer)
    chat_loop(graph, config, username)   # ← inside = connection open

# WRONG — graph.invoke() outside the with block = connection already closed = crash
```

### 4. State and add_messages Reducer

```python
class State(TypedDict):
    messages: Annotated[list, add_messages]
```

`add_messages` is a **reducer** — it tells LangGraph how to merge new messages into existing state. Instead of replacing the list, it appends. This is what makes history accumulate rather than reset each turn.

### 5. HumanMessage / AIMessage / SystemMessage

LangGraph requires typed message objects, not raw strings. The type tells the LLM who sent each message.

```python
SystemMessage  → sets the AI's role/persona (sent once, prepended)
HumanMessage   → what the user typed
AIMessage      → what the AI replied (returned by llm.invoke())
```

### 6. graph.invoke() — four things in one call

```python
result = graph.invoke({"messages": [human_msg]}, config=config)
```

This single line does, in order:
1. **Load** — fetch latest checkpoint for this thread_id from MongoDB
2. **Merge** — append new HumanMessage to the loaded history (via add_messages)
3. **Run** — execute chatbot node → full history → GPT-4o-mini → AIMessage
4. **Save** — write updated state back to MongoDB

### 7. Why `result["messages"][-1]`?

`result` is the final State dict. `result["messages"]` is the full accumulated list. The last item `[-1]` is always the freshest — the AI's reply to your most recent message.

---

## Code Map — Every Function

| Function | Where | What it does |
|---|---|---|
| `main()` | bottom | Entry point. Opens MongoDB, calls build_graph, get_user_config, chat_loop |
| `build_graph(checkpointer)` | middle | Creates and compiles the LangGraph pipeline |
| `chatbot(state)` | middle | The single graph node. Calls GPT-4o-mini with full history |
| `get_user_config(checkpointer)` | middle | Shows menu, resolves thread_id, returns config dict |
| `thread_exists(checkpointer, thread_id)` | middle | Checks if MongoDB has any checkpoint for this thread_id |
| `make_config(thread_id)` | middle | Builds the `{"configurable": {"thread_id": ...}}` dict |
| `chat_loop(graph, config, username)` | middle | The main while loop — gets input, invokes graph, prints reply |

---

## MongoDB — What Gets Stored

LangGraph creates a database called `langgraph` with two collections:

**`checkpoints`** — one document per state snapshot:
```json
{
  "thread_id": "alice",
  "checkpoint_id": "uuid-v4-string",
  "parent_checkpoint_id": "previous-uuid",
  "checkpoint": {
    "channel_values": {
      "messages": [ ...all HumanMessage and AIMessage objects... ]
    },
    "channel_versions": { "messages": 4 }
  },
  "metadata": { "step": 3, "source": "loop" }
}
```

**`checkpoint_writes`** — pending writes for multi-node graphs (not heavily used in single-node graphs like this one)

**Key point:** every `invoke()` call adds a new checkpoint document. Old ones are kept — you have a full audit trail of every state the graph ever reached.

---

## Important Patterns to Remember

### Pattern 1 — always use with block for MongoDBSaver
```python
with MongoDBSaver.from_conn_string(MONGO_URI) as checkpointer:
    # ALL graph code goes here
```

### Pattern 2 — config dict structure
```python
config = {"configurable": {"thread_id": "some_unique_id"}}
# Pass this to every graph.invoke() and checkpointer.get() call
```

### Pattern 3 — invoke input is only the NEW message
```python
# You only pass the new message — NOT the full history
# LangGraph loads history from MongoDB automatically
result = graph.invoke({"messages": [HumanMessage(content=text)]}, config=config)
```

### Pattern 4 — get the AI reply
```python
ai_reply = result["messages"][-1]   # last message = freshest AI reply
print(ai_reply.content)             # .content holds the text string
```

### Pattern 5 — check if thread exists
```python
config = {"configurable": {"thread_id": thread_id}}
checkpoint = checkpointer.get(config)   # None = no history, object = has history
```

---

## Common Errors & Fixes

| Error | Cause | Fix |
|---|---|---|
| `OPENAI_API_KEY not set` | Missing or wrong key in .env | Check .env file, ensure no spaces around `=` |
| `Connection refused 27017` | MongoDB not running | Run the docker command from setup step 1 |
| `ModuleNotFoundError` | Package not installed | Run `pip install -r requirements.txt` in your venv |
| `RuntimeError: connection closed` | graph.invoke() called outside with block | Move all graph calls inside the `with` block |
| AI doesn't remember past sessions | Wrong thread_id used | Ensure you're entering the same name as before |
| `authentication failed` | Wrong MongoDB credentials | Check MONGO_URI matches your docker run command |

---

## How to Extend This Project

These additions make it resume-worthy (in order of difficulty):

### Easy — Add timestamps to messages
Store when each entry was written. Show "you said this on Monday" in the summary.

### Medium — Emotion/mood tracking
After each message, make a second LLM call: "what is the user's mood in one word?"  
Store mood separately. Show a weekly mood summary.

### Medium — Message summarisation
When `len(state["messages"]) > 20`, summarise old messages into a single compact block.  
Prevents the context window growing forever — a real production problem.

### Hard — Semantic search over history
Use OpenAI embeddings to vectorise each message.  
Store vectors in MongoDB Atlas or Qdrant.  
Let the user ask: "what did I say about my job last month?" and return relevant old entries.

### Hard — Web interface
Replace the CLI with a FastAPI backend + simple HTML/JS frontend.  
Now it's a deployable app, not a terminal script.

---

## Revision Checklist

Use this to test yourself. Cover the answers and try to recall each one.

- [ ] What does `load_dotenv()` do and where does it read from?
- [ ] Why must everything be inside the `with MongoDBSaver(...)` block?
- [ ] What is a `thread_id` and how does it create user isolation?
- [ ] What are the 4 things `graph.invoke()` does internally?
- [ ] Why do we use `HumanMessage` instead of passing raw strings?
- [ ] What does `add_messages` do differently from a normal list assignment?
- [ ] Why is `result["messages"][-1]` always the AI's latest reply?
- [ ] What does `checkpointer.get(config)` return when no history exists?
- [ ] What is the difference between `SystemMessage`, `HumanMessage`, and `AIMessage`?
- [ ] What does `build_graph()` return and what three things happen inside it?
- [ ] In the new-user flow, what happens if the name "alice" is already taken?
- [ ] What two MongoDB collections does LangGraph create automatically?
- [ ] What does the `chatbot(state)` function receive and what must it return?
- [ ] What is a reducer in LangGraph context? What does `add_messages` do?
- [ ] Why does the chat loop use `while True` and what are the three ways to exit it?

---

*Built with LangGraph 0.2+, LangChain, MongoDB 7, Python 3.11+*
