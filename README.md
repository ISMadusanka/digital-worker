# Digital Worker

A Python application that acts as a "digital worker" capable of operating Windows applications by "seeing" the screen via OCR, reasoning about what to do using a LangChain agent (GPT-4o), and acting through mouse/keyboard automation.

## Architecture

1. **Perceive**: PyAutoGUI takes a screenshot → Google Document AI OCR extracts text & bounding boxes → Preprocessor converts to pixel coordinates.
2. **Reason**: LangChain Agent receives the UI state and decides the next action (e.g., "Click button 5").
3. **Act**: PyAutoGUI moves the mouse and clicks/types.
4. **Verify**: Loop repeats until the goal is met.

## Prerequisites

1. **Python 3.10+**
2. **OpenAI API Key** (for GPT-4o)
3. **Google Cloud Project** with:
   - Billing enabled.
   - Document AI API enabled.
   - An OCR Processor created in the Document AI console.
   - A Service Account JSON key.

## Setup

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure environment:**
   Copy the example config and fill in your keys:
   ```bash
   cp .env.example .env
   ```

## Usage

1. Open the target application (e.g., Windows Calculator).
2. Run the worker:
   ```bash
   python main.py
   ```
3. Type your goal, e.g., `Calculate 25 + 17`.

**⚠️ SAFETY:** The worker will take control of your mouse. If things go wrong, violently move your mouse cursor to any of the four corners of your screen. This triggers a `FailSafeException` and instantly stops the bot.
