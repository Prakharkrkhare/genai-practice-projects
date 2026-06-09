# ── Imports ──────────────────────────────────────────────────────────────────
from dotenv import load_dotenv          # reads your .env file into os.environ
load_dotenv()                           # must be called BEFORE anything uses OPENAI_API_KEY

from typing import TypedDict            # used to define the State schema
from langgraph.graph import StateGraph, END  # StateGraph = the graph builder; END = terminal node
from langchain_openai import ChatOpenAI # thin wrapper around OpenAI's chat models


# ── 1. STATE ─────────────────────────────────────────────────────────────────
# The State is a plain TypedDict — a Python dict with typed keys.
# LangGraph passes this dict between every node automatically.
# Each node receives the full state and returns only the keys it wants to update.

class State(TypedDict):
    user_post:      str    # the raw input from the user
    rewritten_post: str    # filled by Node 1, possibly overwritten by Node 3
    is_flagged:     bool   # filled by Node 2


# ── 2. MODELS ────────────────────────────────────────────────────────────────
# Two separate model instances — different models, same interface.

gpt4o_mini = ChatOpenAI(model="gpt-4o-mini", temperature=0.3)
# temperature=0.3 → fairly deterministic; good for "rewrite professionally"

gpt4o = ChatOpenAI(model="gpt-4o", temperature=0.1)
# temperature=0.1 → very deterministic; strict rewriting needs consistency


# ── 3. BANNED WORDS LIST ─────────────────────────────────────────────────────
# Hardcoded list — swap in whatever words matter for your use case.
# All stored lowercase so comparison is case-insensitive later.

BANNED_WORDS = [
    "hate", "kill", "stupid", "idiot", "dumb",
    "attack", "destroy", "abuse", "violent", "illegal"
]


# ══════════════════════════════════════════════════════════════════════════════
# NODE DEFINITIONS
# Each node is a plain Python function:
#   - receives `state: State` (the full current state dict)
#   - returns a dict with ONLY the keys it wants to update
#   - LangGraph merges the returned dict back into the state automatically
# ══════════════════════════════════════════════════════════════════════════════


# ── NODE 1: rewriter ──────────────────────────────────────────────────────────
def rewriter(state: State) -> dict:
    """
    Takes state["user_post"] and asks GPT-4o-mini to rewrite it professionally.
    Returns {"rewritten_post": <new text>} to update the state.
    """
    prompt = (
        "Rewrite the following post to sound more professional, "
        "clear, and respectful. Keep the original meaning intact.\n\n"
        f"Post: {state['user_post']}"
    )
    # .invoke() sends one message and returns an AIMessage object
    response = gpt4o_mini.invoke(prompt)

    # response.content is the string text of the model's reply
    return {"rewritten_post": response.content}


# ── NODE 2: checker ───────────────────────────────────────────────────────────
def checker(state: State) -> dict:
    """
    Scans state["rewritten_post"] for any banned words.
    No LLM call — pure Python string logic.
    Returns {"is_flagged": True/False}.
    """
    post_lower = state["rewritten_post"].lower()  # normalize to lowercase

    # any() short-circuits: returns True the moment it finds the first match
    flagged = any(word in post_lower for word in BANNED_WORDS)

    return {"is_flagged": flagged}


# ── NODE 3: strict_rewriter ───────────────────────────────────────────────────
def strict_rewriter(state: State) -> dict:
    """
    Only reached when is_flagged=True.
    Uses GPT-4o (stronger model) with a stricter prompt to sanitize the post.
    Overwrites state["rewritten_post"] with the cleaned version.
    """
    prompt = (
        "The following post contains potentially harmful, offensive, or inappropriate content. "
        "Rewrite it strictly to remove ALL problematic language while preserving the core message. "
        "The result must be completely safe, neutral, and professional.\n\n"
        f"Post: {state['rewritten_post']}"
    )
    response = gpt4o.invoke(prompt)

    return {"rewritten_post": response.content}


# ══════════════════════════════════════════════════════════════════════════════
# CONDITIONAL EDGE LOGIC
# A routing function receives the current state and returns a string.
# That string must match one of the keys in the `path_map` dict you
# provide when registering the conditional edge.
# ══════════════════════════════════════════════════════════════════════════════

def route_after_checker(state: State) -> str:
    """
    Called automatically after Node 2 (checker) runs.
    Returns "flagged" or "clean" — these strings map to nodes/END in the graph.
    """
    if state["is_flagged"]:
        return "flagged"   # → will route to strict_rewriter
    else:
        return "clean"     # → will route to END


# ══════════════════════════════════════════════════════════════════════════════
# GRAPH ASSEMBLY
# ══════════════════════════════════════════════════════════════════════════════

# StateGraph(State) tells LangGraph what shape the shared state dict has
graph_builder = StateGraph(State)

# ── Add nodes ─────────────────────────────────────────────────────────────────
# First arg = the name you'll use to reference the node in edges
# Second arg = the Python function that implements the node
graph_builder.add_node("rewriter",        rewriter)
graph_builder.add_node("checker",         checker)
graph_builder.add_node("strict_rewriter", strict_rewriter)

# ── Set entry point ───────────────────────────────────────────────────────────
# This is the first node that runs when you call graph.invoke()
graph_builder.set_entry_point("rewriter")

# ── Add normal (unconditional) edges ─────────────────────────────────────────
# rewriter always goes to checker
graph_builder.add_edge("rewriter", "checker")

# strict_rewriter always goes to END (no further processing needed)
graph_builder.add_edge("strict_rewriter", END)

# ── Add conditional edge ──────────────────────────────────────────────────────
# After "checker" runs, call route_after_checker(state) to decide where to go.
# The path_map dict translates the returned string → actual node name or END.
graph_builder.add_conditional_edges(
    "checker",              # source node
    route_after_checker,    # routing function
    {
        "flagged": "strict_rewriter",  # "flagged" string → go to strict_rewriter node
        "clean":   END                 # "clean" string   → go to END
    }
)

# ── Compile the graph ─────────────────────────────────────────────────────────
# compile() validates the graph structure and returns a runnable object
graph = graph_builder.compile()


# ══════════════════════════════════════════════════════════════════════════════
# RUN THE GRAPH
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # The initial state — only user_post is set; other keys are filled by nodes
    initial_state = {
        "user_post": "This is so stupid. These people are all idiots and should just be destroyed.",
        "rewritten_post": "",   # placeholder; Node 1 will fill this
        "is_flagged": False     # placeholder; Node 2 will fill this
    }

    print("▶ Running Safe Content Checker pipeline...\n")

    # invoke() runs the graph synchronously from the entry point to END
    # It returns the FINAL state dict after all nodes have run
    final_state = graph.invoke(initial_state)

    # ── Print results ─────────────────────────────────────────────────────────
    print("=" * 60)
    print(f"📥 Original post:\n   {final_state['user_post']}\n")
    print(f"⚠️  Was flagged:   {final_state['is_flagged']}\n")
    print(f"📤 Final post:\n   {final_state['rewritten_post']}")
    print("=" * 60)