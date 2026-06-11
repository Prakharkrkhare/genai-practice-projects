"""
Multi-User Journal Assistant
==============================
Uses LangGraph + MongoDB checkpointing to give each user a
persistent, ever-growing conversation memory.

Architecture at a glance:
  State  →  { messages: list }          (grows every turn)
  Node   →  chatbot()                   (calls GPT-4o-mini)
  Graph  →  START → chatbot → END       (one-node pipeline)
  Saver  →  MongoDBSaver                (persists State to MongoDB)
  Key    →  thread_id = username        (one memory lane per user)
"""

# ─────────────────────────────────────────────
# 1. IMPORTS
# ─────────────────────────────────────────────
import os                                         # read env vars
from typing import Annotated                      # for type hints

from dotenv import load_dotenv                    # load .env file

# LangGraph core
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages   # reducer: appends messages

# LangChain message types
from langchain_core.messages import (
    HumanMessage,    # wraps user text
    AIMessage,       # wraps assistant text
    SystemMessage,   # wraps the system prompt
)

# LangChain OpenAI wrapper
from langchain_openai import ChatOpenAI

# MongoDB checkpointer — saves/loads graph state
from langgraph.checkpoint.mongodb import MongoDBSaver

# typing_extensions for TypedDict (defines our State shape)
from typing_extensions import TypedDict


# ─────────────────────────────────────────────
# 2. LOAD ENVIRONMENT VARIABLES
# ─────────────────────────────────────────────
load_dotenv()   # reads OPENAI_API_KEY (and anything else) from .env

MONGO_URI = os.getenv(
    "MONGO_URI",
    "mongodb://admin:admin@localhost:27017"   # default for local Docker
)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")


# ─────────────────────────────────────────────
# 3. STATE DEFINITION
# ─────────────────────────────────────────────
# TypedDict tells LangGraph what our state object looks like.
# Annotated[list, add_messages] means:
#   - "messages" is a list
#   - When two states are merged, use add_messages() as the reducer
#     (i.e., append new messages to the existing list rather than replacing it)
class State(TypedDict):
    messages: Annotated[list, add_messages]


# ─────────────────────────────────────────────
# 4. THE LANGUAGE MODEL
# ─────────────────────────────────────────────
llm = ChatOpenAI(
    model="gpt-4o-mini",       # fast and cheap; swap for gpt-4o if desired
    api_key=OPENAI_API_KEY,    # pulled from .env
    temperature=0.7,           # slight creativity; 0 = deterministic
)

# System prompt — tells the model its role and what it remembers
SYSTEM_PROMPT = SystemMessage(content=(
    "You are a warm, empathetic personal journal assistant. "
    "You remember everything the user has shared with you across "
    "all past sessions. Reference past conversations naturally "
    "when relevant. Help the user reflect, track their thoughts, "
    "celebrate wins, and process challenges. Be concise but caring."
))


# ─────────────────────────────────────────────
# 5. THE CHATBOT NODE
# ─────────────────────────────────────────────
def chatbot(state: State) -> dict:
    """
    The single node in our graph.

    Receives the full State (which includes ALL messages from past
    sessions thanks to MongoDB checkpointing), prepends the system
    prompt, calls GPT-4o-mini, and returns the new AI message.

    LangGraph will automatically merge this return value into State
    using the add_messages reducer — so it appends, never overwrites.
    """
    # Prepend system prompt to the full message history
    full_history = [SYSTEM_PROMPT] + state["messages"]

    # Call the LLM with the complete history
    response = llm.invoke(full_history)

    # Return only the new message — LangGraph handles the merge
    return {"messages": [response]}


# ─────────────────────────────────────────────
# 6. BUILD THE GRAPH
# ─────────────────────────────────────────────
def build_graph(checkpointer) -> object:
    """
    Constructs and compiles the LangGraph StateGraph.

    The checkpointer is injected here at compile time.
    Every .invoke() call will:
      1. Load state from MongoDB using the thread_id in config
      2. Run the graph nodes
      3. Save the updated state back to MongoDB
    """
    builder = StateGraph(State)         # create a graph with our State shape

    builder.add_node("chatbot", chatbot)  # register our node

    # Wire up: START → chatbot → END
    builder.add_edge(START, "chatbot")
    builder.add_edge("chatbot", END)

    # compile() locks the graph and attaches the checkpointer
    return builder.compile(checkpointer=checkpointer)


# ─────────────────────────────────────────────
# 7. THREAD_ID HELPERS
# ─────────────────────────────────────────────
def thread_exists(checkpointer, thread_id: str) -> bool:
    """
    Checks if a checkpoint already exists for this thread_id.

    MongoDBSaver.get() returns None if no checkpoint exists yet,
    or the latest checkpoint object if it does.
    """
    config = {"configurable": {"thread_id": thread_id}}
    checkpoint = checkpointer.get(config)          # None → never used
    return checkpoint is not None


def make_config(thread_id: str) -> dict:
    """
    Builds the config dict that LangGraph needs to identify
    which memory lane (thread) to load and save.

    This is THE key concept: same thread_id = same memory.
    """
    return {"configurable": {"thread_id": thread_id}}


# ─────────────────────────────────────────────
# 8. CLI MENU
# ─────────────────────────────────────────────
def get_user_config(checkpointer) -> tuple[str, dict]:
    """
    Displays the startup menu and returns (username, config).

    Option 1 — Existing user:
        Loads their full chat history from MongoDB automatically
        (LangGraph does this transparently via the checkpointer).

    Option 2 — New user:
        If the name was used before, warns the user.
        Creates a fresh thread by using a new thread_id
        (we suffix with a counter to make it unique).
    """
    print("\n" + "═" * 50)
    print("   📓  PERSONAL JOURNAL ASSISTANT")
    print("═" * 50)
    print("\n  1. Continue as existing user")
    print("  2. Start as a new user")
    print()

    while True:
        choice = input("  Enter 1 or 2: ").strip()
        if choice in ("1", "2"):
            break
        print("  ⚠  Please enter 1 or 2.")

    name = input("\n  Enter your name: ").strip().lower().replace(" ", "_")
    if not name:
        name = "anonymous"

    if choice == "1":
        # ── EXISTING USER ──────────────────────────────────────
        # We use the name directly as the thread_id.
        # If this name has been used before, MongoDB has their history.
        # If not, they'll just start with an empty state (no error).
        thread_id = name
        if thread_exists(checkpointer, thread_id):
            print(f"\n  ✅ Welcome back, {name.capitalize()}! Loading your history...")
        else:
            print(f"\n  ℹ️  No history found for '{name}'. Starting fresh.")
        return name, make_config(thread_id)

    else:
        # ── NEW USER ────────────────────────────────────────────
        # We want a guaranteed-fresh thread.
        # Strategy: find a thread_id that doesn't exist yet.
        # e.g., "alice" → "alice_2" → "alice_3" ...
        thread_id = name
        if thread_exists(checkpointer, thread_id):
            # Name taken — find next available slot
            counter = 2
            while thread_exists(checkpointer, f"{name}_{counter}"):
                counter += 1
            thread_id = f"{name}_{counter}"
            print(f"\n  ℹ️  '{name}' already exists. Creating new thread: '{thread_id}'")
        else:
            print(f"\n  ✅ Welcome, {name.capitalize()}! Creating your journal...")

        return name, make_config(thread_id)


# ─────────────────────────────────────────────
# 9. CHAT LOOP
# ─────────────────────────────────────────────
def chat_loop(graph, config: dict, username: str):
    """
    The main conversation loop.

    Each iteration:
      1. Gets user input
      2. Wraps it in a HumanMessage
      3. Invokes the graph — which loads history, runs chatbot node,
         saves updated history, returns new state
      4. Extracts and prints the last AI message
    """
    print(f"\n  📓 Journal open. Type 'exit' to close.\n")
    print("─" * 50)

    while True:
        # ── GET USER INPUT ──────────────────────────────────────
        try:
            user_input = input(f"\n  You: ").strip()
        except (KeyboardInterrupt, EOFError):
            # Ctrl+C or Ctrl+D — exit gracefully
            print("\n\n  👋 Journal saved. See you next time!")
            break

        if not user_input:
            continue                           # ignore empty input

        if user_input.lower() == "exit":
            print("\n  👋 Journal saved. Your memories are safe. See you next time!")
            break

        # ── WRAP IN HumanMessage ────────────────────────────────
        # HumanMessage is LangChain's typed wrapper for user text.
        # LangGraph needs typed messages (not raw strings) so the
        # add_messages reducer can handle them correctly.
        human_msg = HumanMessage(content=user_input)

        # ── INVOKE THE GRAPH ────────────────────────────────────
        # graph.invoke() does four things automatically:
        #   a) Loads the checkpoint for this thread_id from MongoDB
        #   b) Merges our new HumanMessage into the loaded state
        #   c) Runs the chatbot node (which calls GPT-4o-mini)
        #   d) Saves the updated state (all messages) back to MongoDB
        #
        # The returned `result` is the FINAL state after all nodes ran.
        result = graph.invoke(
            {"messages": [human_msg]},   # input: just the new message
            config=config,               # which thread to load/save
        )

        # ── EXTRACT THE AI REPLY ────────────────────────────────
        # result["messages"] is the FULL message list (all history).
        # The last message is always the freshest AI reply.
        ai_reply = result["messages"][-1]

        # ai_reply is an AIMessage object — .content holds the text
        print(f"\n  Assistant: {ai_reply.content}")
        print("-" * 50)


# ─────────────────────────────────────────────
# 10. MAIN ENTRY POINT
# ─────────────────────────────────────────────
def main():
    """
    Main function — wires everything together.

    THE WITH-BLOCK RULE explained here:
    ─────────────────────────────────────
    MongoDBSaver.from_conn_string() opens a MongoDB connection.
    That connection must stay open for the entire lifetime of graph
    operations. The `with` block guarantees:
      • The connection opens when we enter the block
      • The connection closes (cleanly) when we exit the block,
        even if an exception is raised
    
    Any graph.invoke() call OUTSIDE this `with` block would fail
    because the connection would already be closed. So ALL graph
    calls must live inside the `with` block.
    """
    if not OPENAI_API_KEY:
        print("\n  ❌ Error: OPENAI_API_KEY not set in .env file.")
        print("  Create a .env file with: OPENAI_API_KEY=sk-...")
        return

    print("\n  🔌 Connecting to MongoDB...")

    # Open MongoDB connection — stays open for the entire `with` block
    with MongoDBSaver.from_conn_string(MONGO_URI) as checkpointer:

        # Build and compile the graph with the live checkpointer
        graph = build_graph(checkpointer)

        # Show menu, get username and config (thread_id)
        username, config = get_user_config(checkpointer)

        # Enter the chat loop — all graph calls happen here (inside `with`)
        chat_loop(graph, config, username)

    # MongoDB connection is now closed — safe exit
    print("\n  🔒 MongoDB connection closed.")


# ─────────────────────────────────────────────
# 11. RUN
# ─────────────────────────────────────────────
if __name__ == "__main__":
    main()
