import re
import os
from html2text import html2text
from playwright.async_api import async_playwright
import sys, asyncio
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

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