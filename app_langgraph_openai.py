import os
import datetime
from enum import Enum
import nest_asyncio
import streamlit as st
from dotenv import load_dotenv
from langgraph.constants import Send
from pydantic import Field, BaseModel
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage
from langgraph.checkpoint.memory import MemorySaver
from streamlit.runtime.scriptrunner import StopException
from langgraph.graph import MessagesState, START, END, StateGraph
from utils import browserbase,kayak_hotel_search,extract_hotels_clean
import sys, asyncio
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# Page configuration
st.set_page_config(page_title="🏨 HotelFinder Pro", layout="wide")

# Title and subtitle with custom HTML for blue color
st.markdown("<h1 style='color: #0066cc;'>🏨 HotelFinder Pro</h1>", unsafe_allow_html=True)
st.subheader("Powered by Browserbase and Langgraph")

# Sidebar for API key input
with st.sidebar:
    # Add Browserbase logo and Configuration header in the same line
    # Browserbase Configuration
    col1, col2 = st.columns([1, 3])
    with col1:
        # Add vertical space to align with header
        st.write("")
        st.image("./assets/browser-base.png", width=65)
    with col2:
        st.header("Browserbase Configuration")

    # Add hyperlink to get API key
    st.markdown("[Get your API key](https://browserbase.ai)", unsafe_allow_html=True)

    browserbase_api_key = st.text_input("Enter your Browserbase API Key", type="password")

    # Store API key as environment variable
    if browserbase_api_key:
        os.environ["BROWSERBASE_API_KEY"] = browserbase_api_key
        st.success("Browserbase API Key stored successfully!")

# Load environment variables
load_dotenv()  # take environment variables from .env.

# Main content
st.markdown("---")

# Hotel search form
st.header("Search for Hotels")
col1, col2 = st.columns(2)

with col1:
    location = st.text_input("Location", placeholder="Enter city, area, or landmark")
    num_adults = st.number_input("Number of Adults", min_value=1, max_value=10, value=2)

with col2:
    check_in_date = st.date_input("Check-in Date", datetime.date.today())
    check_out_date = st.date_input("Check-out Date", datetime.date.today() + datetime.timedelta(days=1))
    # Add more options if needed

search_button = st.button("Search Hotels")


nest_asyncio.apply()

class DecisionOption(Enum):
    search_again = "search again"
    rewrite_existing_results = "rewrite existing results"
    end = "end"

class DecisionResponse(BaseModel):
    decision: DecisionOption

class HotelSearchSchema(BaseModel):
    """Structured parameters for a brand-new hotel search."""
    location: str = Field(description="Destination, e.g. 'Cairo, Egypt'")
    check_in_date: str = Field(description="YYYY-MM-DD")
    check_out_date: str = Field(description="YYYY-MM-DD")
    num_adults: int = Field(ge=1, description="Number of adult guests")

class HotelAgentSchema(MessagesState):
    """All state carried through the LangGraph workflow."""
    location: str
    check_in_date: str
    check_out_date: str
    num_adults: int
    hotel_results: str
    markdown_results: str
    feedback: str
    filters: list[str] = Field(default_factory=list)

llm = ChatOpenAI(model="gpt-4.1", temperature=0)

summarization_prompt = """
# HotelFinder Pro - Customer Results Presentation

## **Your Role:**
You are an expert **Hotel Concierge AI**, tasked with helping potential customers make informed hotel booking decisions.

## **Your Task:**
Given the raw hotel search results from a search agent, your job is to:

1. **Summarize and present the hotel options** in a **clear, appealing, and informative way**.
2. Ensure that the presentation is **customer-friendly**, using concise descriptions, bullet points, and easy-to-read formatting.
3. Highlight key aspects of each hotel:
   - Name
   - Price per night
   - Location
   - Star Rating (if available)
   - Amenities (e.g., Free Wi-Fi, Breakfast, Pool, etc.)
   - Booking Link (if available)

## **Filtering Instructions:**
If `filters` are provided, apply them strictly:
- Only include hotels that match the user's specific requirements.
- Example filters may include:
   - Maximum price
   - Minimum star rating
   - Required amenities (e.g., free cancellation, breakfast included)

If no hotels match the filters, politely inform the customer and suggest removing or relaxing some filters.

## **User's Original Request:**
- **Location:** {location}
- **Check-in Date:** {check_in_date}
- **Check-out Date:** {check_out_date}

## **Input Data:**
- **Raw Hotel Search Results:**
{results}

- **User Filters (if any):**
{filters}

## **Output Format:**

Please structure your response with the following:

### **Top Matching Hotels for {location} ({check_in_date} – {check_out_date}):**

[List the hotels here with clear bullet points or numbered format.]

### **Summary of Applied Filters:**
[Briefly explain any filters applied to narrow down the results.]

### **Next Steps / Call to Action:**
Provide a polite closing statement encouraging the customer to proceed with booking, adjust filters, or perform another search.

---
## **Output Guidelines:**

- **Output must be in raw Markdown** (no HTML)
- Use clean and readable formatting
- Be concise, helpful, and friendly

## **Tone:**
- Friendly and professional
- Customer-centric
- Clear and concise
"""

decision_prompt = """
## Task: Determine Next Action Based on User Feedback

Given the user's feedback, decide the next action.

### Input:
{feedback}

### Decision Options:

- If the user wants a **completely new search** (e.g., change of location or dates), respond with:

**search again**

- If the user wants to **refine the current results** (e.g., adjust price, filter by amenities), respond with:

**rewrite existing results**

- If the user is **satisfied** (e.g., says "all good", "ok", "thanks", "no changes"), respond with:

**end**

### Output:

Respond with exactly **one of**:

- search again
- rewrite existing results
- end
"""

filters_prompt = """
## Task: Extract Filters from Feedback

Given the user's feedback about hotel search results, extract a **list of filters** to refine the hotel options.

### Input:
{feedback}

### Output Format:
Respond with a **plain list**, one filter per line. Do not include explanations.

### Example Output:
- Only show hotels under $200
- Must have free cancellation
- At least 4-star rating
"""
parameters_prompt = """
## Task: Extract new hotel search parameters from user feedback.

### Input:
{feedback}

### Output Format (JSON):

{{
  "location": "City or destination (e.g. 'Cairo, Egypt')",
  "check_in_date": "YYYY-MM-DD",
  "check_out_date": "YYYY-MM-DD"
  "num_adults": Number
}}
"""



async def search_for_hotels(state: HotelSearchSchema):
    print(f"Searching for hotels in {state['location']} from {state['check_in_date']} to {state['check_out_date']} for {state['num_adults']} adults")

    request = kayak_hotel_search(
        state['location'],
        state['check_in_date'],
        state['check_out_date'],
        state['num_adults']
    )

    hotel_results = await browserbase(request)
    hotel_results = extract_hotels_clean(hotel_results)
    return {"hotel_results": hotel_results}


def summarize_hotels(state: dict):
    print(state['hotel_results'])
    prompt = summarization_prompt.format(
        location=state['location'],
        check_in_date=state['check_in_date'],
        check_out_date=state['check_out_date'],
        results=state['hotel_results'],
        filters=state.get('filters', [])
    )
    output = llm.invoke([SystemMessage(content=prompt)] + state['messages'])
    return {"markdown_results": output.content}

def human_feedback(state: HotelAgentSchema):
    st.markdown(state["markdown_results"])
    choice = input("If you approve the current results or want to end the search, type **all good**.\nOtherwise, provide feedback to adjust the search:\n")
    return {"feedback": choice}



def route(state: HotelAgentSchema):
    decision_resp: DecisionResponse = (
        llm.with_structured_output(DecisionResponse)
           .invoke(
               [SystemMessage(content=decision_prompt.format(feedback=state["feedback"]))
               ] + state["messages"]
           )
    )

    decision = decision_resp.decision
    if decision is DecisionOption.end:
        return END

    if decision is DecisionOption.search_again:
        params: HotelSearchSchema = (
            llm.with_structured_output(HotelSearchSchema)
               .invoke([SystemMessage(content=parameters_prompt.format(feedback=state["feedback "]))])
        )
        filters_output = llm.invoke([
            SystemMessage(content=filters_prompt.format(feedback=state["feedback"]))
        ])
        state["filters"] = filters_output.content.strip().split("\n")

        return Send(
            "hotel_search_agent",
            {
                "location":      params.location      or state["location"],
                "check_in_date": params.check_in_date or state["check_in_date"],
                "check_out_date":params.check_out_date or state["check_out_date"],
                "num_adults":    params.num_adults    or state["num_adults"],
            },
        )

    filters_output = llm.invoke([
        SystemMessage(content=filters_prompt.format(feedback=state["feedback"]))
    ])
    state["filters"] = filters_output.content.strip().split("\n")
    return "hotel_results_showcaser"


builder = StateGraph(HotelAgentSchema)
builder.add_node("hotel_search_agent",search_for_hotels)
builder.add_node("hotel_results_showcaser",summarize_hotels)
builder.add_node("human_feedback",human_feedback)


builder.add_edge(START,"hotel_search_agent")
builder.add_edge("hotel_search_agent","hotel_results_showcaser")
builder.add_edge("hotel_results_showcaser","human_feedback")
#if there is no human_feedback go to END.
builder.add_conditional_edges("human_feedback", route, ["hotel_search_agent", "hotel_results_showcaser", END])


memory = MemorySaver()

graph = builder.compile(checkpointer=memory)


async def run_search():
    return await graph.ainvoke(
        {
            "location": location,
            "check_in_date": check_in_date.strftime('%Y-%m-%d'),
            "check_out_date": check_out_date.strftime('%Y-%m-%d'),
            "num_adults": num_adults,
        },
        config={"configurable": {"thread_id": "1"}}
    )

if search_button:
    if not os.environ.get("BROWSERBASE_API_KEY"):
        st.error("Please enter your Browserbase API Key in the sidebar first!")
    elif check_out_date <= check_in_date:
        st.error("Check-out date must be after check-in date!")
    else:
        with st.spinner("Searching for hotels…"):
            try:
                result = asyncio.get_event_loop().run_until_complete(run_search())
                st.success("Search completed!")
                st.markdown("## Hotel Results")
                st.markdown(result["markdown_results"])
            except StopException:
                st.stop()
            except Exception as e:
                st.error(f"An unexpected error occurred: {e}")


st.markdown("---")
st.markdown("""
### About HotelFinder Pro
This application uses AI agents to search for hotels and find the best accommodations for you.
Simply enter your desired location, dates, and number of guests to get started.

Features:
- Real-time hotel availability
- Comprehensive price comparison
- Detailed hotel information and amenities
- Multiple booking options
""")