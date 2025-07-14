import re
import os
import asyncio
import datetime
import nest_asyncio
import streamlit as st
from dotenv import load_dotenv
from html2text import html2text
from browserbase import browserbase
from kayak import kayak_hotel_search
from langgraph.constants import Send
from pydantic import Field, BaseModel
from langchain_openai import ChatOpenAI
from playwright.async_api import async_playwright
from langchain_core.messages import SystemMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import MessagesState, START, END, StateGraph
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

async def browserbase(url: str) -> str:
    try:
        async with async_playwright() as p:
            print("Connecting to Browserbase...")
            browser = await p.chromium.connect_over_cdp(
                "wss://connect.browserbase.com?apiKey=" + os.environ["BROWSERBASE_API_KEY"] + "&projectId=" + os.environ["BROWSERBASE_PROJECT_ID"]
            )
            print("Connected to Browserbase.")
            context = await browser.new_context()
            page = await context.new_page()
            print("Navigating to URL...")
            await page.goto(url, timeout=60000)
            print("Waiting for page load...")
            await page.wait_for_load_state("networkidle", timeout=60000)
            content = html2text(await page.content())
            print("Page content retrieved.")
            await browser.close()
            return content
    except Exception as e:
        print(f"Error: {str(e)}")
        return f"Error: {str(e)}"

def kayak_hotel_search(
    location_query: str, check_in_date: str, check_out_date: str, num_adults: int = 2
) -> str:
    """
    Generates a Kayak URL for hotel searches.
    """
    print(f"Generating Kayak Hotel URL for {location_query} from {check_in_date} to {check_out_date} for {num_adults} adults")
    URL = f"https://www.kayak.co.in/hotels/{location_query}/{check_in_date}/{check_out_date}/{num_adults}adults"
    return URL

def extract_hotels_clean(text: str, max_hotels: int = 5) -> str:
    """
    Extracts a concise, readable hotel summary from raw Browserbase-Kayak output.
    """
    text = text[:70000]  # Truncate for safety

    hotel_pattern = re.compile(
        r"\[(.*?)\]\((/hotels/.*?)\).*?(\d\.\d)\s+([A-Za-z]+)\s+\((\d{2,6})\).*?(\d+)\s+stars",
        re.DOTALL
    )
    price_pattern = re.compile(r"₹\s*([\d,]+)")

    hotels = []
    matches = list(hotel_pattern.finditer(text))

    for match in matches[:max_hotels]:
        name = match.group(1).strip()
        link = "https://www.kayak.co.in" + match.group(2).strip()
        score = match.group(3).strip()
        rating_desc = match.group(4).strip()
        reviews = match.group(5).strip()
        stars = match.group(6).strip()

        # Find the first price after this hotel match
        following_text = text[match.end():match.end()+1000]  # Look ahead
        price_match = price_pattern.search(following_text)
        price = price_match.group(1) if price_match else "N/A"

        hotel_summary = f"""
### {name}
- ⭐ {stars} stars | {score}/10 {rating_desc} ({reviews} reviews)
- 💲 Price from: ₹{price}
- 🔗 [View Deal]({link})
"""
        hotels.append(hotel_summary.strip())

    if not hotels:
        return "⚠️ No hotels found in the extracted data."

    return "\n\n".join(hotels)


class HotelSearchSchema(BaseModel):
  location:str
  check_in_date:str
  check_out_date:str
  num_adults:int

class HotelAgentSchema(MessagesState):
  location:str
  check_in_date:str
  check_out_date:str
  num_adults:int
  hotel_results: str
  markdown_results: str
  feedback:str
  filters:list[str] = Field(default_factory=list)

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



async def search_for_hotels(state: dict):
    print(f"Searching for hotels in {state['location']} from {state['check_in_date']} to {state['check_out_date']} for {state['num_adults']} adults")

    request = kayak_hotel_search(
        state['location'],
        state['check_in_date'],
        state['check_out_date'],
        state['num_adults']
    )

    hotel_results = await browserbase(request)
    hotel_results = extract_hotels_clean(hotel_results)
    print(hotel_results)

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
    st.markdown(state['markdown_results'])
    choice = input("If you approve the current results or want to end the search, type **all good**.\nOtherwise, provide feedback to adjust the search:\n")
    # choice = "all good"
    return {"feedback": choice}

def route(state: HotelAgentSchema):
    decision_output = llm.invoke([
        SystemMessage(content=decision_prompt.format(feedback=state['feedback']))
    ] + state['messages'])

    decision = decision_output.content.strip().lower()

    if "end" in decision:
        return END

    elif "search again" in decision:
      structured_llm = llm.with_structured_output(HotelSearchSchema)
      parameters_output = structured_llm.invoke([
          SystemMessage(content=parameters_prompt.format(feedback=state['feedback']))
      ])
      filters_output = llm.invoke([
            SystemMessage(content=filters_prompt.format(feedback=state['feedback']))
        ])
      state['filters'] = filters_output.content.strip().split("\n")

      updates = parameters_output.model_dump()

      return Send("hotel_search_agent", {
            "location": parameters_output.location if parameters_output.location else state['location'],
            "check_in_date": parameters_output.check_in_date if parameters_output.check_in_date else state['check_in_date'],
            "check_out_date": parameters_output.check_out_date if parameters_output.check_out_date else state['check_out_date'],
            "num_adults": parameters_output.num_adults if parameters_output.num_adults else state['num_adults'],
      })



    else:
        filters_output = llm.invoke([
            SystemMessage(content=filters_prompt.format(feedback=state['feedback']))
        ])
        state['filters'] = filters_output.content.strip().split("\n")
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
        with st.spinner("Searching for hotels... This may take a few minutes."):
            try:
                result = asyncio.get_event_loop().run_until_complete(run_search())
                st.success("Search completed!")
                st.markdown("## Hotel Results")
                st.markdown(result["markdown_results"])
            except Exception as e:
                st.error(f"An error occurred during the search: {str(e)}")


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