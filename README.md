# PitchPulse AI v1.3 — Sports AI Chat & Voice (Windows)

A **local-first cricket and football assistant** using FastAPI, a clean chat-first responsive UI, voice input/output, genuine source-linked news and optional match APIs. A real LLM is used only when **your OpenAI API key** or a **running Ollama model** is configured. Without an LLM, the app provides limited headline-reader responses rather than pretending to reason. No fabricated match scores or demo sports articles are shipped.

## Quick start in VS Code (Windows 10/11)

1. Install Python **3.12** (stable) and use Chrome or Edge.
2. Unzip the archive. Open the inner `PitchPulse_AI` folder with **File → Open Folder** in VS Code.
3. Open VS Code Terminal → New Terminal (PowerShell) and run:

   ```powershell
   .\run.cmd
   ```

   The launcher creates `.venv` and `.env` (if missing), installs Python dependencies and opens `http://127.0.0.1:8000`.
4. **If migrating from v1.2:** stop the old server, copy only your private `.env` file into the new project folder, and restart. Never share the `.env` file.
5. `run.cmd` is a Windows command launcher; do **not** run `python run` or type the command inside Python's `>>>` REPL.

For an already-installed `.venv`, this alternative in the VS Code terminal starts a developer reload server:

```powershell
.\.venv\Scripts\python.exe -m uvicorn sportpulse.main:app --host 127.0.0.1 --port 8000 --reload
```

## AI setup (required for reasoning and proper sports explanations)

Edit `.env` and restart `run.cmd`:

```ini
LLM_PROVIDER=openai
OPENAI_API_KEY=your_private_api_key
OPENAI_MODEL=gpt-4.1-mini
```

OpenAI API usage incurs separate fees; a ChatGPT Plus/Pro subscription does **not** automatically give API credits. Alternatively run Ollama locally:

```ini
LLM_PROVIDER=ollama
OLLAMA_MODEL=llama3.2
OLLAMA_BASE_URL=http://127.0.0.1:11434
```

Install Ollama from https://ollama.com, pull `llama3.2`, and make sure the Ollama service is running. Local model speed depends on hardware.

## Using the new simpler UI

- **Message bar:** type questions and press `Enter` to send or `Shift+Enter` for a newline. While generating, the send arrow becomes a stop button to cancel that request.
- **Voice:** tap **Voice**, speak and watch partial transcription appear. When recognized, the text goes into the message composer so you can edit it. Press **Enter** to submit. **Auto-send voice** is OFF by default; enable it to submit automatically.
- **Interrupt speech:** tapping Voice or **Stop audio** cancels spoken playback. The **Read aloud** toggle mutes/unmutes automatic spoken replies. Assistant messages also have a **Listen** replay button.
- **Microphone check:** **Test microphone** verifies hardware capture independent of Chrome's speech recognition service.
- **Backup voice transcription:** if native browser speech recognition is denied, configure OpenAI or offline faster-whisper. Then click Voice again to record. Click again to transcribe; recording stops automatically after 20 seconds. Chrome site permission can be ON while its speech recognition engine rejects a request.
- **Explore:** optional right panel for current source-linked headlines and provider match scores. It stays closed until needed and refreshes while open at five-minute intervals.
- **New conversation:** clears the current chat and its LLM follow-up context. Chats are not written to localStorage or a server-side database.
- **Sidebar:** switch sports focus or ask suggested cricket/football questions.

### Voice backup setup

**OpenAI transcription:** set `OPENAI_API_KEY=...` and `STT_PROVIDER=auto` (or `openai`). The recording is uploaded to the OpenAI transcription API and may incur fees.

**Offline transcription:** first start/stop the app, then run `setup_offline_voice.cmd`, keep `STT_PROVIDER=auto` or set `STT_PROVIDER=local`, then restart `run.cmd`. Downloads the `faster-whisper` model on first use; later audio is processed on your machine. `STT_LOCAL_MODEL=tiny` is the faster baseline; `base` may improve quality.

Chrome's browser speech recognition may use external browser services. **No permanent always-on/wake-word listening is implemented.** Microphone capture is user-initiated; audio is not written to an application chat database. Browsers require your permission and their own speech service may fail even when recording access succeeds.

## Current news and scores

Without news/sports API keys the BBC Sport and Google News RSS headlines may still work. Add the optional provider keys to `.env` for live-ish cricket/football data:

```ini
CRICKET_API_KEY=your_cricketdata_org_key
FOOTBALL_API_KEY=your_football_data_org_key
CRICKET_CACHE_SECONDS=1200
FOOTBALL_CACHE_SECONDS=180
NEWS_CACHE_SECONDS=180
```

- Cricket: CricketData (CricAPI) currentMatches, https://cricketdata.org/live-cricket-score-api/ — cached **20 minutes** by default, not ball-by-ball real-time. Subscription-dependent.
- Football: football-data.org v4 API, https://www.football-data.org/ — cached 3 minutes and coverage depends on API plan.
- Headlines: BBC Sport + Google News RSS search. Headlines and snippets only; the app does not ingest full articles. The browser shows source links, timestamps and availability information.
- The LLM is given only available source context for current claims. It is instructed not to guess scores, injuries or transfers, but LLMs can still make mistakes; verify consequential facts with original sources.

## Sports LLM questions to try

```
Explain DRS in cricket in simple words.
Why do teams use a high defensive line in football?
Compare a cricket captain's role with a football manager.
How many overs are in a T20 match?
Give me the latest India cricket headlines with sources.
Who won India vs Pakistan today? Only tell me if the result is verified.
What's the current Arsenal vs Chelsea score? Only use verified score data.
Explain that again in simple Hinglish.
```

Questions about timeless rules/strategy avoid unnecessary live-score/news calls. Match-specific questions filter to relevant provider games rather than substituting unrelated results. Short conversation context (up to 6 turns) is included for follow-ups. For best quality, configure the OpenAI or Ollama model.

## Structure

```text
PitchPulse_AI/
  run.cmd, run.ps1             Windows launcher (port 8000)
  check_setup.ps1              PowerShell backend diagnostics
  setup_offline_voice.cmd/.ps1 Optional offline speech model installation
  .env.example                 Environment template — copy to .env
  requirements.txt             Backend dependencies
  requirements-dev.txt         Test dependencies
  Dockerfile, compose.yaml     Loopback-only container setup
  SECURITY.md                  Deployment cautions
  sportpulse/
    main.py                    FastAPI routes /api/chat, /api/news, /api/matches, /api/transcribe
    brain.py                   LLM prompt, news grounding, score matching, follow-ups
    providers.py               RSS, cricket and football API adapters; caching
    speech.py                  Optional cloud / offline recording transcription
    config.py                  Server-side keys and settings
    static/
      index.html               Chat-first interface
      style.css                Desktop/mobile UI styles
      app.js                   Chat, microphone, TTS, panel interactions
  tests/                       API, providers, audio, Windows, sports LLM contract tests
```

## Tests and diagnostics

Install development dependencies and run the test suite inside the project folder:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
powershell -ExecutionPolicy Bypass -File .\check_setup.ps1
```

The sports LLM tests use **HTTP mocks, not a real paid OpenAI model**. They validate request formatting, source selection, missing-score handling and follow-up history. A live model test requires your own valid API credentials and internet access. Browser UI was exercised in an isolated simulated environment; real microphone and Windows Chrome speech service still require checking on your machine.

## Security

This is a **functional local-first project**, not a security-audited public SaaS. Never publish `.env`, never put API keys in client JavaScript, and do not expose port 8000 on the public internet without authentication, TLS, rate limits, privacy/consent notice and operations monitoring. Read `SECURITY.md`.