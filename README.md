# 🏨 HotelFinder – Project Overview

HotelFinderis a **Streamlit web app** that demonstrates how to build an AI-driven hotel-search assistant by combining:

| Layer | Technology | What it does |
|-------|------------|--------------|
| **User Interface** | **Streamlit** | Renders an interactive web form (location, dates, guests) and shows Markdown results + feedback box |
| **Browsing / Scraping** | **Browserbase + Playwright** | Spins up a remote Chromium instance, opens a generated Kayak URL, and fetches the rendered HTML |
| **LLM Orchestration** | **LangGraph** | Coordinates the agent workflow (search → summarise → collect feedback → reroute) in a stateful graph |
| **Language Model** | **OpenAI GPT-4.1** (via `langchain-openai`) | Summarises raw HTML into a clean hotel list and decides next steps based on user feedback |
| **Data Schema & Validation** | **Pydantic** | Ensures structured inputs/outputs for LLM calls (search parameters, decision routing, etc.) |

---

## 1. How the App Works – Step by Step

1. **User inputs search parameters**  
   Location, check-in/out dates, and number of adults are captured by Streamlit widgets.

2. **Kayak URL generation**  
https://www.kayak.co.in/hotels/{location}/{check_in}/{check_out}/{num_adults}adults


3. **Remote browsing via Browserbase**  
* Connect to Browserbase over CDP (Chromium DevTools Protocol).  
* Load the Kayak page, wait for `networkidle`, pull down the full HTML.  
* Convert HTML → Markdown using `html2text`.

4. **Hotel extraction**  
Regex grabs hotel name, rating, reviews, star count, and price.  
Returns a concise Markdown list (max 5 hotels by default).

5. **LLM summarisation**  
GPT-4o gets a *system prompt* (`summarization_prompt`) and the extracted list →  
returns polished Markdown with filters, bullet points, call-to-action.

6. **Display & Human feedback loop**  
* The Markdown is shown in the Streamlit app.  
* User types feedback (e.g. “only 4-star hotels under ₹10 000”) or *all good*.

7. **LLM routing**  
GPT-4o reads the feedback via `decision_prompt` and outputs one of:  
* **search again** → start a brand-new search with new parameters.  
* **rewrite existing results** → re-summarise the same list with filters applied.  
* **end** → finish the conversation.

8. **Stateful coordination**  
LangGraph keeps a `HotelAgentSchema` object in memory, passing updated state (results, filters, feedback) between nodes until the workflow ends.

---

## 2. Important Files & Configuration

| File | Purpose |
|------|---------|
| `app_langgraph_openai.py` | Main Streamlit application |
| `requirements.txt` | All Python dependencies. Install with:<br>`pip install -r requirements.txt` |
| `.env` | Store your **Browserbase API key** and **project ID** here |
| `assets/browser-base.png` | Logo shown in the sidebar |
| `utils.py` | contains extra needed utilty function such as generating the hotels url for browser base to scrape content, and regex to get hotel data|
---

## 3. Environment Variables

| Variable | Description |
|----------|-------------|
| `BROWSERBASE_API_KEY` | Authenticates your CDP connection to Browserbase |
| `BROWSERBASE_PROJECT_ID` | Identifies which Browserbase project / quota to use |

You can either put them in `.env` *or* enter the API key in the Streamlit sidebar.

---

## 4. Running the App Locally

```bash
# 1. Clone / download the repo
git clone https://github.com/mahmoudmokhiamar/hotel-booking-langgraph.git
cd hotel-booking-langgraph

# 2. Create & activate a virtual environment
python -m venv .venv
# macOS/Linux
source .venv/bin/activate
# Windows
# .venv\\Scripts\\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. (Optional) add your Browserbase creds to .env
echo "BROWSERBASE_API_KEY=bb-..."      >> .env
echo "BROWSERBASE_PROJECT_ID=proj_..." >> .env
echo "OPENAI_API_KEY=sk-..." >> .env

# 5. Launch Streamlit
streamlit run app_langgraph_openai.py
