# Digital Worker

A Python "digital worker" that operates a **Windows 11** desktop the way a person
would — it *sees* the screen, *reasons* about the goal with a multimodal LangChain
agent (GPT-4o), and *acts* visibly through the real mouse, keyboard, and apps. It
is built to carry out **long, multi-app tasks**, e.g.:

> "Create a folder on the Desktop and make a summary document about today's
> trending news."
>
> → creates the folder → opens the browser → searches Google News → reads the
> headlines → opens Notepad/Word → writes the summary → saves it into the folder.

## How it works

```
        ┌─────────────┐    plan      ┌──────────────────────────────┐
 goal → │   Planner   │ ───────────► │  Observe → Decide → Act loop │
        └─────────────┘              └──────────────────────────────┘
                                            │            ▲
                                  screenshot │            │ one action
                              + UI elements  ▼            │ (mouse/keyboard/
                                   ┌────────────────┐     │  power tool)
                                   │  Perception    │     │
                                   │  (UIA + vision)│─────┘
                                   └────────────────┘
```

1. **Plan** — the goal is decomposed into an ordered checklist of steps.
2. **Perceive** — each turn captures the screen and detects on-screen elements:
   - **Native Windows UI Automation (UIA)** reads the accessibility tree for
     exact element names, types, and coordinates — **no GPU/OCR server required**.
   - The screenshot is annotated with numbered **Set-of-Mark** boxes and sent to
     the **vision** model, so the agent can target "element 7" instead of guessing
     pixels.
   - *(Optional)* **OmniParser** GPU backend is still available as a fallback.
3. **Reason & Act** — the agent picks the single best next action and calls one
   tool (click / type / hotkey / open app / read screen text / create file…).
4. **Loop** — the screen is re-observed and the agent adapts until it calls
   `finish()`.

**Visible-GUI by default:** the agent produces every artifact by operating the
real apps the user can watch — it creates folders in File Explorer, types and
saves documents in Notepad/Word, and reads the web in the browser. Core tools:
the full mouse/keyboard set, `open_application`, `read_screen_text` (grab page/
document text), `wait`, and `finish`.

Setting `ENABLE_POWER_TOOLS=true` additionally exposes silent helpers
(`create_folder`, `write_text_file`, `create_document`, `run_shell_command`) that
produce files directly — faster, but not something the user sees happen.

## Prerequisites

1. **Windows 11** (UI Automation perception is Windows-only).
2. **Python 3.10+**.
3. **OpenAI API key** for a vision-capable model (`gpt-4o`).
4. *(Optional)* An **OmniParser** server, only if you set `PERCEPTION_BACKEND` to
   `omniparser` or `hybrid`.

## Setup

```powershell
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure environment
Copy-Item .env.example .env
#   then edit .env and set OPENAI_API_KEY
```

The defaults (`PERCEPTION_BACKEND=uia`, `USE_VISION=true`) need only an OpenAI key.

## Usage

```powershell
python main.py
```

A floating control appears. Type a goal and press **Run**, e.g.:

- `Create a folder named "News" on my desktop and save a summary of today's trending news in it`
- `Open Calculator and compute 25 + 17`
- `Open Notepad, write a short poem about Windows, and save it to the desktop`

## Configuration highlights (`.env`)

| Setting | Default | Purpose |
|---|---|---|
| `OPENAI_MODEL` | `gpt-4o` | Vision-capable model used for reasoning. |
| `PERCEPTION_BACKEND` | `uia` | `uia` (native) · `omniparser` · `hybrid`. |
| `USE_VISION` | `true` | Send the annotated screenshot to the model. |
| `SET_OF_MARK` | `true` | Draw numbered element boxes for ID-based targeting. |
| `USE_PLANNER` | `true` | Generate a step checklist up front. |
| `ENABLE_POWER_TOOLS` | `false` | Also expose silent file/folder/doc/shell tools (non-visible). |
| `MAX_AGENT_ITERATIONS` | `80` | Budget for long multi-step tasks. |
| `VERIFY_AFTER_ACTION` | `false` | Optional per-action LLM verification. |

## Safety

The worker controls your real mouse and keyboard. To abort instantly, **slam the
mouse cursor into any screen corner** — this trips PyAutoGUI's fail-safe and stops
the bot. You can also press **Stop** in the UI.
