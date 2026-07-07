# AI Agent for Corporate Buyback Analysis 📈🤖

An intelligent, precision-focused AI agent designed to automate the extraction of Retail/Small Shareholder data from complex corporate filings. Specifically, this tool parses Shareholding Pattern (SHP) documents to identify the exact equity percentage held by "Individuals holding nominal share capital up to Rs. 2 lakhs," a critical metric for evaluating corporate share buyback opportunities.

## ✨ Key Features

* **Precision Data Extraction:** Utilizes targeted regex and LLM prompts to isolate data specifically from the "Category of Shareholder" table, actively avoiding "Distribution of Shareholding" tables to prevent data pollution.
* **Strict Document Validation (Fail Fast):** Built-in logic to distinguish between genuine SHP documents and Buyback Public Announcements/Investor Presentations. If the wrong document is uploaded, the agent detects it immediately to prevent hallucinated data (like mistaking a 15% SEBI regulatory reservation for actual shareholding).
* **Hybrid Fallback Engine:** If a PDF is unreadable, corrupted, or invalid, the system automatically triggers a dynamic online web search to fetch the live shareholding percentage for the given ticker.
* **User-Friendly UI:** A clean interface allowing users to upload documents, input the Current Market Price (CMP), and instantly view reconciled extraction results.

## 📁 Project Structure

* `app.py`: The main application entry point housing the user interface and input parameters.
* `agent_extractor.py`: The core LLM orchestration file that handles document ingestion, prompt management, and primary extraction logic.
* `small_shareholder_extractor.py`: A specialized, isolated module utilizing strict validation rules and robust regex targeting to accurately capture the specific small shareholder category.
* `requirements.txt`: Project dependencies and libraries.

## 🚀 Getting Started

### Prerequisites
Ensure you have Python 3.8+ installed on your machine.

### Installation

1. Clone the repository:

   git clone [https://github.com/ridhamrajparmar/buyback-ai-agent.git](https://github.com/yourusername/buyback-ai-agent.git)
   cd buyback-ai-agent

2. Create and activate a virtual environment:

    python -m venv venv
    # On Windows:
    venv\Scripts\activate
    # On macOS/Linux:
    source venv/bin/activate

3. Install the required dependencies:

    pip install -r requirements.txt

### Usage

1. Start the application:

    streamlit run app.py

2. Open your local web browser and navigate to the provided localhost URL.

3. Enter the Target Company Name and Current Market Price.

4. Upload the official Shareholding Pattern (SHP) PDF (optional).

5. Execute the agent to retrieve the validated Retail Shareholding Percentage.

## 🧠 Architecture & Logic Flow

1. Ingestion: User provides a company name and an optional PDF.

2. Pre-Processing: The text is extracted line-by-line. The agent checks for critical keywords (shareholding pattern, category of shareholder) to ensure document validity.

3. Targeted Search: The script scans specifically for the Individuals holding nominal share capital up to Rs. 2 lakhs row, ignoring "in excess of" categories.

4. Validation: If the extracted number fails sanity checks (e.g., returns None or an impossibly low/high value), the agent drops the PDF result.

5. Fallback: The fetch_shareholding_online() function activates, pulling the latest data from live web sources.