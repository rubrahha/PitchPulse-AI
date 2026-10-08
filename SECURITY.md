# Deployment and security guide

This is a **working prototype / local-first reference implementation**, not a security-audited public SaaS.

- Keep `.env` out of Git and ZIPs, and rotate accidentally exposed keys. API keys are read server-side only.
- Do not expose the application to the public internet without user authentication and authorization, HTTPS, bot protection, per-account usage limits, central request throttling, privacy disclosure, operational monitoring, and a trusted persistent cache.
- The included limiter is per process and per IP; it is NOT a replacement for production API-gateway throttling.
- The sports APIs have license, cache, commercial-use, rate-limit and geographic restrictions; check each contract.
- Native browser speech recognition may involve browser vendor speech services and can be denied even when microphone capture permission is ON. The in-app hardware test calls `getUserMedia` independently of speech recognition and closes the stream immediately.
- Optional OpenAI voice fallback sends a user-triggered recording to `api.openai.com/v1/audio/transcriptions`; this incurs API fees and is separate from browser speech permission. Local `faster-whisper` fallback processes speech on this machine after model download. No voice recording is stored in the application database, but transient OS/decoder and provider handling applies.
- The speech upload route caps audio at 8 MB, supports explicit audio MIME types only, is locally bound by default, and shares the IP rate limiter with chat. **It does not authenticate users** and must not be exposed publicly as-is.
- The local Ollama setting is accepted only for `http://localhost` / `127.0.0.1` / `::1`. If you need remote Ollama, add proper authentication and TLS and review SSRF and tenancy risks.
- Response generation submits the current question, brief conversation history and selected headline/score context to the configured LLM. No chat transcripts are stored by this project by default.
- System safety headers, input limits, output escaping, upstream request timeouts, DNS-resolved fixed API destinations and XML entity protection reduce risk but do not guarantee security.
- Docker deployment binds only to the loopback port. Run `docker compose up --build` after adding `.env`. To serve across an intranet or internet, use a properly hardened reverse proxy and authentication; do not merely change bind host.
- Upstream headlines should not be considered independently verified facts; maintain source links and publication times.