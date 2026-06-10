# trip_planner.py
# A LangGraph multi-node pipeline: destination → itinerary → packing list

# ── 1. IMPORTS ────────────────────────────────────────────────────────────────
from dotenv import load_dotenv          # reads .env file into os.environ
from langchain_openai import ChatOpenAI # OpenAI chat model wrapper
from langchain_core.messages import HumanMessage  # message type for the LLM
from langgraph.graph import StateGraph, START, END # graph primitives
from typing import TypedDict            # used to define the shared state schema

# ── 2. ENVIRONMENT ────────────────────────────────────────────────────────────
load_dotenv()   # automatically loads OPENAI_API_KEY from your .env file

# ── 3. LLM ────────────────────────────────────────────────────────────────────
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.7)
# One shared LLM instance reused by all three nodes.
# temperature=0.7 gives creative but coherent answers.

# ── 4. STATE SCHEMA ───────────────────────────────────────────────────────────
class TripState(TypedDict):
    """
    The single shared dictionary that flows through every node.

    Fields
    ------
    preferences   : Input. Raw string from the user, e.g.
                    "budget trip, warm weather, 5 days".
    destination   : Written by Node 1. E.g. "Bali, Indonesia".
    itinerary     : Written by Node 2. Day-by-day plan as a string.
    packing_list  : Written by Node 3. Categorised packing list.
    """
    preferences : str
    destination : str
    itinerary   : str
    packing_list: str

# ── 5. NODE 1 — destination_picker ───────────────────────────────────────────
def destination_picker(state: TripState) -> dict:
    """
    Reads  : state["preferences"]
    Writes : {"destination": <str>}

    Sends the user's raw preferences to the LLM and asks for ONE
    destination with a short reason. The returned dict is *merged*
    into the shared state by LangGraph automatically.
    """
    prompt = (
        f"A traveller has these preferences: {state['preferences']}.\n"
        "Suggest exactly ONE travel destination and give a 2-sentence "
        "reason why it is a great match. Reply with just the destination "
        "name on the first line, then the reason."
    )
    response = llm.invoke([HumanMessage(content=prompt)])
    return {"destination": response.content.strip()}

# ── 6. NODE 2 — itinerary_builder ────────────────────────────────────────────
def itinerary_builder(state: TripState) -> dict:
    """
    Reads  : state["destination"], state["preferences"]
    Writes : {"itinerary": <str>}

    Uses the destination chosen by Node 1 to produce a day-by-day
    itinerary tailored to the original trip preferences.
    """
    prompt = (
        f"Create a detailed day-by-day itinerary for a trip to "
        f"{state['destination']}. "
        f"The traveller's preferences are: {state['preferences']}. "
        "Format each day as 'Day N: <activities>'."
    )
    response = llm.invoke([HumanMessage(content=prompt)])
    return {"itinerary": response.content.strip()}

# ── 7. NODE 3 — packing_list_builder ─────────────────────────────────────────
def packing_list_builder(state: TripState) -> dict:
    """
    Reads  : state["destination"], state["itinerary"]
    Writes : {"packing_list": <str>}

    Combines destination + full itinerary to generate a sensible,
    categorised packing list (clothing, toiletries, documents, etc.).
    """
    prompt = (
        f"Based on a trip to {state['destination']} with the following "
        f"itinerary:\n{state['itinerary']}\n\n"
        "Generate a categorised packing list. Use clear category headers "
        "like Clothing, Toiletries, Documents, Electronics, Miscellaneous."
    )
    response = llm.invoke([HumanMessage(content=prompt)])
    return {"packing_list": response.content.strip()}

# ── 8. BUILD THE GRAPH ────────────────────────────────────────────────────────
builder = StateGraph(TripState)   # create the graph, bound to TripState

# Register the three nodes (name → function)
builder.add_node("destination_picker",   destination_picker)
builder.add_node("itinerary_builder",    itinerary_builder)
builder.add_node("packing_list_builder", packing_list_builder)

# Wire the edges: START → N1 → N2 → N3 → END
# Each arrow means "run this node next, passing the current state".
builder.add_edge(START,                  "destination_picker")
builder.add_edge("destination_picker",   "itinerary_builder")
builder.add_edge("itinerary_builder",    "packing_list_builder")
builder.add_edge("packing_list_builder", END)

# Compile turns the builder into an executable Runnable
graph = builder.compile()

# ── 9. RUN ────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # --- Edit this string to change your trip ---
    user_preferences = input("Enter you budget, climate, weather, duration, landscape, culture : ")
    print("🌍  Generating your personalised trip plan...\n")

    # invoke() runs the full pipeline synchronously and returns the final state
    final_state = graph.invoke({"preferences": user_preferences})

    # ── PRINT RESULTS ─────────────────────────────────────────────────────────
    print("=" * 60)
    print("📍  DESTINATION")
    print("=" * 60)
    print(final_state["destination"])

    print("\n" + "=" * 60)
    print("🗓️   ITINERARY")
    print("=" * 60)
    print(final_state["itinerary"])

    print("\n" + "=" * 60)
    print("🎒  PACKING LIST")
    print("=" * 60)
    print(final_state["packing_list"])
