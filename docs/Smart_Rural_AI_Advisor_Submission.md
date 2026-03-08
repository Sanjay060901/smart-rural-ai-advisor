# Smart Rural AI Advisor — Submission Brief

> **Team:** Creative Intelligence (CI) | **Hackathon:** AWS AI for Bharat 2026  
> **Region:** ap-south-1 (Mumbai) | **Runtime:** Python 3.13, React 18 | **IaC:** AWS SAM

---

## Quick Links

| Artifact | Link |
|----------|------|
| **Live Prototype** | [https://d80ytlzsrax1n.cloudfront.net](https://d80ytlzsrax1n.cloudfront.net) |
| **GitHub Repository** | [github.com/Sanjay060901/smart-rural-ai-advisor](https://github.com/Sanjay060901/smart-rural-ai-advisor) |
| **Demo Video** | [Watch on YouTube](https://youtu.be/PYYTB6gH1rI?si=38Iub-dKBXA8XEz2) |
| **Project PPT** | *Uploaded to dashboard* |

---

## 1. Problem We Solve

**86% of Indian farming households are small/marginal** (< 5 acres) and face five critical information gaps:

| Gap | Scale of Impact |
|-----|----------------|
| **No expert access** | 1 extension officer per 1,000+ farmers — most never receive personalised advice |
| **Language barriers** | Resources are English-only; farmers speak 13+ languages — eligible benefits go unclaimed |
| **Delayed disease response** | Lab diagnosis takes days; a 48-hour delay can mean 30–50% crop damage |
| **Unclaimed govt benefits** | ₹2+ lakh crore in schemes (PM-KISAN, PMFBY, KCC) go unenrolled annually |
| **Weather unpredictability** | Climate change disrupts traditional farming calendars — no farming-specific weather advice exists |

**Bottom line:** India's farmers who produce the nation's food are the least served by information technology.

---

## 2. Our Solution

**Smart Rural AI Advisor** is a fully serverless, voice-first, multilingual AI agricultural assistant built on AWS. It provides Indian farmers with instant, personalised farming guidance — in their own language — through a simple web interface accessible on any smartphone.

### What Makes It Different

| Differentiator | How |
|---------------|-----|
| **Voice-first, not text-first** | Full voice I/O in 13 Indian languages — usable by farmers who can't read/type |
| **AI reasons, not just searches** | Amazon Bedrock Nova Pro performs multi-step reasoning: correlate symptoms + weather + season + soil → deliver diagnosis + treatment |
| **Grounded in verified data** | RAG (Bedrock Knowledge Base) ensures crop advice, MSP values, and pesticide dosages are factual |
| **Photo-based diagnosis** | Upload a leaf photo → Nova Pro Vision returns disease, severity, treatment in seconds |
| **Personalised** | Farmer profile (crops, soil, district, language) makes every interaction contextually relevant |
| **Zero cost to farmer** | Serverless on AWS — scales to zero, free-tier friendly, no app installation required |

---

## 3. Why AI Is Required

Traditional software (static FAQs, IVR hotlines, portals) cannot solve these gaps:

| Challenge | Why Only Generative AI Can Solve It |
|-----------|-------------------------------------|
| **Multi-step reasoning** | "My rice has brown spots and it rained yesterday" → correlate symptoms + weather + season + location → diagnose blast disease → recommend treatment. This is LLM reasoning, not keyword matching. |
| **13-language support** | Building separate content for each language × crop × region is infeasible. GenAI + Amazon Translate covers all 13 from a single knowledge base. |
| **Photo diagnosis** | Identifying crop diseases from leaf images requires vision AI (Nova Pro Vision). No rule-based system can achieve this. |
| **Personalisation at scale** | Dynamically combining farmer profile + live weather + scheme eligibility requires reasoning — not static lookup. |
| **Voice accessibility** | The full pipeline (speech → intent → tools → advisory → speech) is inherently an AI problem. |
| **Hallucination prevention** | RAG with verified agricultural data ensures the AI doesn't fabricate pesticide dosages or MSP values. |

**In one line:** Without Generative AI, building a system that reasons across weather + crop science + pest databases + government policy — in 13 languages, with voice — would be infeasible for any team.

---

## 4. How AWS Services Are Used

### 4a. Generative AI (Amazon Bedrock)

| Bedrock Capability | How We Use It |
|-------------------|---------------|
| **Nova Pro (Converse API)** | Primary foundation model — chat reasoning, intent detection, and tool-calling (5 tools: weather, crop, pest, schemes, profile) |
| **Nova Pro Vision** | Crop disease diagnosis from farmer-uploaded photos — returns disease name, severity, treatment |
| **Nova 2 Lite** | Lightweight tasks (text localization, advisory formatting) + bidirectional fallback with Nova Pro — each model falls back to the other on throttle/timeout, ensuring 100% model availability and reducing cost |
| **Bedrock Knowledge Base** | RAG retrieval over curated Indian agricultural documents — grounds crop/pest advisories in verified data |
| **Bedrock Guardrails** | Optional topic gating (agriculture only), content filtering, and grounding checks |

**Tool-Use Flow:** Nova Pro receives 5 tool schemas. Based on farmer intent, it autonomously decides which tools to call. The orchestrator executes tools (child Lambdas), feeds results back, and the model synthesises a natural-language advisory — all within a single API call cycle.

### 4b. Full AWS Service Map

| AWS Service | Purpose | Why This Service |
|-------------|---------|-----------------|
| **Amazon Bedrock** | Chat reasoning, tool-calling, image diagnosis | Managed GenAI — no hosting, native tool-use |
| **Bedrock Knowledge Base** | RAG for crop advisories | Grounded answers from verified data |
| **Bedrock Guardrails** | Content safety | Enterprise-grade filtering |
| **AWS Lambda** (7 functions) | All backend compute | Serverless — zero idle cost |
| **Amazon API Gateway** | REST API (11 routes, CORS) | Managed API with throttling |
| **Amazon DynamoDB** (4 tables) | Profiles, sessions, rate limits, OTP | Millisecond latency, free-tier friendly |
| **Amazon S3** | Frontend assets, audio, KB docs | Durable storage |
| **Amazon CloudFront** | CDN for React SPA | Edge delivery across India |
| **Amazon Translate** | 13 Indian languages, auto-detect | Native Indian language support |
| **Amazon Polly** | Neural TTS (Hindi + English) | High-quality speech |
| **gTTS** | TTS for all 13 languages | Covers languages Polly doesn't |
| **Amazon Transcribe** | Speech-to-text fallback (12 languages) | Firefox/Safari voice support |
| **Amazon Cognito** | Phone + PIN authentication → JWT tokens | Managed user pool; on-screen OTP for prototype (see Tradeoffs) |
| **AWS IAM** | Least-privilege per Lambda | Security best practice |
| **AWS Secrets Manager** | Secure API key storage | No secrets in code |
| **Amazon CloudWatch** | Logs, metrics, alarms | Observability |

---

## 5. What Value the AI Layer Adds

| Without AI | With Smart Rural AI Advisor |
|---|---|
| Farmer searches multiple English websites for crop advice | Ask one question in Tamil/Hindi/Telugu → get a complete, personalised answer with audio |
| Generic advice — same for everyone regardless of soil, location, season | Every response is tailored to the farmer's specific crops, soil type, district, and current season |
| No disease diagnosis without travelling to a lab (days of delay) | Upload a photo → instant AI diagnosis with treatment plan + nearby KVK recommendation |
| Government scheme PDFs are 50-page documents in English | AI explains eligibility, ₹6,000/year benefits, and step-by-step application in farmer's language |
| IVR helplines have long wait times and limited language support | 24/7 instant responses in 13 languages with full voice I/O — zero wait time |
| No connection between weather data and farming decisions | "It will rain tomorrow — delay pesticide spraying, irrigate after 2 days" with crop-specific context |

---

## 6. Core Features — Detail

### AI Chat (Primary Feature)
- Farmer speaks or types in any of 13 Indian languages
- Agent Orchestrator Lambda: language detection → Bedrock Nova Pro reasoning → tool invocation → post-processing → translation → TTS
- 5 tools called autonomously by the model: weather, crop advisory (RAG), pest diagnosis, govt schemes, farmer profile
- Fact-checking: every AI response is validated against real tool data before delivery
- Chat history persisted in DynamoDB (30-day retention)

### Crop Doctor (Image Diagnosis)
- Farmer uploads leaf/crop photo (JPEG, PNG, WebP, GIF — max 4 MB)
- Nova Pro Vision analyses the image (temperature: 0.3 for diagnostic precision)
- Returns: confidence level, disease name, severity, organic treatment, chemical treatment, prevention steps, urgency, recommendation to visit KVK
- PII sanitisation on output — no personal data in AI responses
- Result translated to farmer's language

### Weather Advisory
- Real-time weather + 5-day forecast via OpenWeatherMap
- 100+ Indian district name aliases for robust location matching
- Farming-specific advisories: irrigation timing, pesticide spray windows, frost/heat warnings
- Interactive Leaflet map with city quick-select

### Government Schemes
- 10+ curated schemes: PM-KISAN (₹6,000/yr), PMFBY (crop insurance), KCC (credit card), Soil Health Card, PMKSY (irrigation), eNAM (online market), PKVY (organic farming), NFSM (food security)
- Each scheme: name, benefits, eligibility criteria, application steps, helpline, website URL
- AI explains eligibility based on farmer's profile

### Farmer Profile
- Persistent storage: name, state, district, crops, soil type, land size (acres), preferred language
- Auto-personalises all future interactions
- Phone + PIN authentication via Amazon Cognito (JWT tokens); OTP verification displayed on-screen for the prototype (see Tradeoffs section below)
- Profile data used by AI to fill missing context in queries

### Multilingual Voice I/O
- **Voice input:** Web Speech API (Chrome/Edge — streaming, zero latency) + Amazon Transcribe (Firefox/Safari — batch fallback, 12 languages)
- **Voice output:** Amazon Polly (Kajal neural voice — bilingual: Hindi + Indian English) + gTTS (all 13 languages)
- **Translation:** Amazon Translate with auto-detection, chunking for long responses (9000-byte chunks), retry on excessive Latin script

---

## 7. Security & Reliability

### Security — 7-Layer Defence

| Layer | Detail |
|-------|--------|
| **Input Validation** | Max 2,000 chars, control char removal, image ≤ 4 MB |
| **PII Masking** | Aadhaar, phone, PAN, bank account, email, IFSC — masked in logs + responses |
| **Injection Prevention** | 20+ regex patterns: prompt injection, SQL injection, command injection |
| **Toxicity Detection** | Harm, sabotage, banned pesticides, self-harm (→ crisis helpline) |
| **Rate Limiting** | DynamoDB sliding-window: 15/min, 120/hr, 500/day per farmer |
| **Output Guardrails** | Fact-check vs tool data, PII removal, HTML stripping, max 8,000 chars |
| **Bedrock Guardrails** | Topic gating, content filtering, grounding checks |

### Reliability

| Feature | Implementation |
|---------|---------------|
| **Model Fallback** | Nova Pro ↔ Nova 2 Lite — bidirectional: each model automatically falls back to the other on throttle/timeout |
| **Tool Timeouts** | 25s per tool, 29s API Gateway limit, 5s buffer |
| **KB Retry** | Exponential backoff: 1s → 2s → 4s, max 3 attempts |
| **TTS Failover** | Polly → gTTS with exponential backoff |
| **Fast Path** | Pre-structured queries bypass full Bedrock converse for lower latency |
| **Session Persistence** | DynamoDB + localStorage, 30-day TTL |

---

## 8. Architecture

```
Farmer (mobile/desktop, 13 languages, voice/text)
  → Amazon CloudFront (React 18 SPA, S3 origin)
    → Amazon API Gateway (11 REST routes, CORS)
      → Agent Orchestrator Lambda (the brain)
        ├── Amazon Translate (detect language, translate to English)
        ├── Amazon Bedrock Nova Pro (reason + decide tools)
        ├── Child Lambdas (parallel, 25s timeout each):
        │   ├── Weather → OpenWeatherMap API
        │   ├── Crop Advisory → Bedrock KB (RAG, 8 candidates, score ≥ 0.35)
        │   ├── Govt Schemes → curated data
        │   ├── Farmer Profile → DynamoDB
        │   └── Image Analysis → Nova Pro Vision
        ├── Post-process: fact-check, validate, translate back
        ├── TTS: Polly (Hindi/English) or gTTS (11 other languages)
        └── Persist: DynamoDB (chat_sessions)
      → Response: { reply, audio_url, tools_used, session_id }

  + Transcribe Speech Lambda (Firefox/Safari voice fallback)
  + Health Check Lambda (stack health)
```

### DynamoDB Tables

| Table | Key | Purpose |
|-------|-----|---------|
| `farmer_profiles` | farmer_id | Name, state, district, crops, soil, land size, language |
| `chat_sessions` | session_id + timestamp | Chat messages, session context, farmer_id as attribute (30-day TTL) |
| `otp_codes` | phone_number | OTP verification (short-lived TTL) |
| `rate_limits` | rate_key + window | Hit count per time window (auto-cleanup TTL) |

---

## 9. Tech Stack

| Layer | Technology |
|-------|-----------|
| **Frontend** | React 18, Vite, React Router v6, React-Leaflet, DOMPurify, Marked, amazon-cognito-identity-js |
| **Backend** | Python 3.13, AWS Lambda (7 functions), boto3 |
| **AI/GenAI** | Amazon Bedrock (Nova Pro + Nova 2 Lite), Bedrock Knowledge Base, Bedrock Guardrails |
| **API** | Amazon API Gateway (REST, 11 routes) |
| **Database** | Amazon DynamoDB (4 tables) |
| **Storage/CDN** | Amazon S3 + CloudFront |
| **Translation** | Amazon Translate (13 Indian languages) |
| **Voice** | Amazon Polly, gTTS, Web Speech API, Amazon Transcribe |
| **Auth** | Amazon Cognito (phone + PIN → JWT), on-screen OTP for prototype |
| **IaC** | AWS SAM (CloudFormation) |
| **CI/CD** | AWS CodeBuild (buildspec.yml) |

---

## 10. Supported Languages (13)

| # | Language | Voice In | Voice Out |
|---|----------|----------|-----------|
| 1 | English | Web Speech API | Amazon Polly (Kajal) |
| 2 | Hindi | Web Speech API | Amazon Polly (Kajal) |
| 3 | Tamil | Web Speech / Transcribe | gTTS |
| 4 | Telugu | Web Speech / Transcribe | gTTS |
| 5 | Kannada | Web Speech / Transcribe | gTTS |
| 6 | Malayalam | Web Speech / Transcribe | gTTS |
| 7 | Bengali | Web Speech / Transcribe | gTTS |
| 8 | Marathi | Web Speech / Transcribe | gTTS |
| 9 | Gujarati | Web Speech / Transcribe | gTTS |
| 10 | Punjabi | Web Speech / Transcribe | gTTS |
| 11 | Odia | Web Speech / Transcribe | gTTS |
| 12 | Assamese | Web Speech / Transcribe | gTTS |
| 13 | Urdu | Web Speech / Transcribe | gTTS |

---

## 11. Team

| Name | Role | Contribution |
|------|------|-------------|
| **Sanjay M** | Team Lead + Frontend | React UI, all 11 pages, voice components, i18n, CSS, CloudFront |
| **Manoj RS** | Backend + Infrastructure | 7 Lambdas, SAM template, Bedrock integration, API Gateway, security |
| **Abhishek Reddy** | Data + Knowledge Base | Crop data, scheme data, KB documents, S3 |
| **Jeevidha R** | QA + Documentation | Testing, docs, demo video, submission |

---

## 12. Impact Targets

| Metric | Target | How |
|--------|--------|-----|
| Reduce crop loss | **30%** | Instant AI photo + symptom diagnosis |
| Increase scheme enrolment | **50%** | AI explains eligibility in native language |
| 24/7 expert advice | **Zero cost** | Serverless, free-tier friendly |
| Language coverage | **13 languages** | 95%+ of India's farming population |
| Voice accessibility | **Full I/O** | For farmers who can't read/type |
| Response time | **< 10s** | Query → reasoning → tools → translated voice response |

---

## 13. Demo Walkthrough

The demo video walks through the full capabilities of Smart Rural AI Advisor:

- **Dashboard** — The localised homepage displays a daily farming tip, season indicator (Rabi/Kharif), and quick-action cards for all features.
- **AI Chat** — Farmers can ask natural-language questions like *"What is the weather in Chennai for the next 3 days?"* — the AI autonomously calls the right backend tools, retrieves real data, and responds with a farming advisory plus audio playback.
- **Voice Input** — Farmers can speak in their native language (e.g., Tamil: *"நெல் பயிரில் பழுப்பு நிற புள்ளிகள் தெரிகிறது"*) and receive a spoken AI response with pest diagnosis in the same language.
- **Crop Doctor** — Upload a photo of a diseased leaf, select the crop and state, and get an instant AI diagnosis with disease name, severity, and treatment steps.
- **Government Schemes** — Browse schemes like PM-KISAN, PMFBY, and Soil Health Card with eligibility details, benefits, and step-by-step application guidance.
- **Farmer Profile** — Save personal details (name, district, crops, soil type) so that all future AI responses are automatically personalised to the farmer's context.
- **Multilingual Support** — Switch between any of the 13 supported Indian languages — the entire UI, chat responses, and audio output adapt instantly.

---

## 14. Evaluator Notes

- **Live URL:** [https://d80ytlzsrax1n.cloudfront.net](https://d80ytlzsrax1n.cloudfront.net) — works on any modern browser; Chrome recommended for best voice experience
- **No installation required** — fully web-based, mobile-responsive
- **Repository is trimmed** for submission clarity — legacy experiments and debug scripts archived
- **Knowledge Base source docs** summarised in `docs/KB_OVERVIEW.md`; live KB is deployed in ap-south-1
- **All infrastructure defined** in `infrastructure/template.yaml` (SAM/CloudFormation)
- **Security:** PII masking, injection prevention, rate limiting, Bedrock Guardrails — all production-grade
- **Authentication:** Cognito handles real auth (phone + PIN → JWT). OTP is generated server-side and displayed on-screen for the prototype — see Tradeoffs section for rationale.

---

## 15. Design Tradeoffs & Rationale

We document our tradeoffs transparently to show deliberate engineering decisions:

| Tradeoff | Decision | Rationale | Production Path |
|----------|----------|-----------|----------------|
| **OTP Delivery** | On-screen display (not SMS/WhatsApp) | SMS via SNS requires **TRAI DLT Sender ID registration** (India regulation) — a 2–4 week process requiring a registered business entity. WhatsApp Business API needs **Meta business verification** + BSP onboarding. Both infeasible in hackathon timeline. | Flip `ENABLE_DEMO_OTP=false` → OTP via SNS SMS. Backend code path already exists behind feature flag. |
| **TTS for 11 languages** | gTTS instead of Polly | Amazon Polly supports only Hindi + English neural voices for India. gTTS covers all 13 languages for free. | Replace with Polly as AWS adds Indic voices, or integrate dedicated Indic TTS service. |
| **Voice input dual-path** | Web Speech API + Transcribe fallback | Web Speech unavailable on Firefox/Safari. Transcribe adds 3–5s latency but ensures universal support. | Chrome/Edge (80%+ Indian mobile users) get zero-latency streaming; others get reliable fallback. |
| **General model + RAG** | Nova Pro + Knowledge Base, not fine-tuned | Fine-tuning needs curated datasets, compute budget, and iteration cycles. RAG achieves grounded domain-specific responses without training overhead. | Fine-tuning is a future optimisation once training data is established. |
| **Web app vs native** | React SPA, not Android/iOS | No installation, works on any browser, no app store delays. Farmers have limited storage. | PWA conversion for offline + push notifications is a clear next step. |
| **Per-farmer rate limiting** | DynamoDB counters, not just API GW throttling | Farmers may share devices or use same IP (carrier NAT). Per-`farmer_id` counters ensure individual fairness. | Both used: API GW for global protection, DynamoDB for per-farmer limits. |

---

## 16. Strengths & Best Practices

### Architectural Excellence
- **100% serverless** — Lambda + API Gateway + DynamoDB + S3 + CloudFront. Zero servers, auto-scaling, pay-per-use. Scales to zero when idle.
- **Single-responsibility Lambdas** — 7 functions, each with one job. Independently deployable, testable, debuggable.
- **Orchestrator + tool-calling** — Bedrock decides which tools to invoke based on farmer intent. Adding a capability = adding a tool schema — zero routing code changes.
- **Infrastructure as Code** — 100% SAM/CloudFormation. Reproducible, version-controlled, no manual console changes. Conditional resources and custom outputs ensure correct deployments.
- **29+ feature flags** — TTS engine, guardrail strictness, cache TTL, audit verbosity, model IDs — all configurable without redeployment. Demo → production is an env-var flip.
- **Single-table DynamoDB design** — sessions, messages, and cache entries share optimised table layouts with composite keys and TTL-based auto-expiry. No cron jobs needed.
- **Cascade session delete** — deleting a chat session atomically removes all child messages, cache entries, and audit records. Zero orphaned data.
- **Startup environment validation** — Lambda cold starts validate all required environment variables are present before processing any request.

### Security & Safety (7-Layer Defence in Depth)
- **Layered security pipeline** — input validation → PII masking → injection prevention → toxicity detection → rate limiting → output guardrails → Bedrock Guardrails. No single point of failure.
- **Least-privilege IAM** — each Lambda has a scoped role. Weather Lambda cannot touch DynamoDB; Crop Advisory cannot invoke Polly.
- **ReDoS protection** — regex input lengths capped to prevent denial-of-service via pathological regex patterns.
- **Crisis helpline redirect** — self-harm / distress detection triggers immediate display of 3 Indian helpline numbers (iCall, Vandrevala Foundation, AASRA) instead of an AI response.
- **Banned pesticide detection** — 8 specific hazardous chemicals (endosulfan, monocrotophos, etc.) detected with safer alternatives suggested automatically.
- **System prompt leak prevention** — 15 marker patterns in AI output are checked to prevent the model from exposing internal system instructions.
- **PII never in logs** — Aadhaar, phone, PAN, email, bank account, IFSC masked before CloudWatch logging.
- **20+ injection patterns** — prompt injection, SQL injection, command injection blocked at every Lambda entry point independently.
- **Custom DOMPurify allowlist** — frontend sanitises all AI-generated markdown with a curated tag/attribute whitelist preventing XSS.
- **Chat title sanitisation** — user-provided session titles are sanitised to prevent stored XSS.
- **Chat idempotency** — duplicate message submissions within a short window are detected and deduplicated.

### AI/ML Intelligence
- **RAG grounding** — crop advice comes from verified Knowledge Base documents, not model priors.
- **3-layer hallucination prevention** — RAG + code-level fact-checking + Bedrock Guardrails grounding checks.
- **21-rule system prompt** — inline MSP/NPK reference data, tool-first routing policy, cautious diagnosis mandate, and multilingual output rules — all in one structured prompt.
- **200-term AgriPolicy keyword set** — domain gating ensures only agriculture-relevant queries reach Bedrock tools; off-topic queries are politely deflected.
- **Greeting shortcut** — simple greetings ("hi", "vanakkam", "namaste") skip Bedrock entirely, saving cost and latency.
- **Multilingual intent classification** — Tamil, Hindi, and Telugu agricultural keywords detected natively without translation round-trip.
- **Tool-first routing policy** — system prompt instructs the model to prefer tool invocations over generating answers from memory, ensuring grounded responses.
- **Tool result enrichment** — raw tool outputs are post-processed with state filtering, cross-state scheme detection, and advisory augmentation before being passed to the model.
- **Strict soil evidence guard** — soil recommendations require actual soil data from profile or tool results; the model cannot fabricate soil parameters.
- **Cautious pest diagnosis** — never hard-asserts a disease; lists probabilities and always recommends KVK confirmation.
- **Quality gates** — KB retrieval min score 0.35, min 2 good chunks; auto-rewrites query on low quality.
- **Freshness detection** — flags stale data for time-sensitive queries (MSP prices, scheme deadlines) with an explicit caveat.

### Translation & Localization Intelligence
- **3-attempt translation strategy** — Bedrock Lite → Amazon Translate → graceful English fallback, with garbled output detection between each attempt.
- **Token-based markdown protection** — replaces markdown syntax with placeholder tokens before translation, restores after — prevents Translate from corrupting formatting.
- **700+ district name translations** — pre-computed translations in 7 Indian scripts for instant, accurate location rendering without API calls.
- **Per-language Latin-script thresholds** — detects when a translation returned too much Latin script (e.g., Tamil output with English words) and auto-retries with a different engine.
- **Tamil-specific post-processing** — handles unique Tamil Unicode rendering quirks and agri-term translation artifacts.
- **Indic output normalisation** — corrects numbered list renumbering, agricultural term translation artifacts, and script-specific rendering issues.
- **Chunked translation** — long responses are split into chunks to stay within Translate API limits while preserving sentence boundaries.

### System Design & Resilience
- **Graceful degradation at every layer** — model fallback (Nova Pro ↔ Nova 2 Lite — bidirectional, each falls back to the other), TTS fallback (Polly → gTTS → silent), voice fallback (Web Speech → Transcribe). Always returns something useful.
- **Category-aware response caching** — SHA-256 hashed keys with domain-specific TTLs (weather = 1 h, schemes = 12 h) eliminate redundant Bedrock calls and reduce cost.
- **Parallel tool execution** — `ThreadPoolExecutor` runs up to 5 tool invocations concurrently per chat turn, reducing multi-tool latency.
- **Context window management** — sliding window (500 chars × 40 messages) keeps conversations efficient without token overflow.
- **Timeout budgeting** — 25s tools, 18s TTS cutoff, 29s API GW limit. Slow services are skipped; text is always delivered.
- **Dual chat persistence** — localStorage for instant page loads + DynamoDB for cross-device sync and durability.
- **Session eviction** — max 20 sessions per user; oldest auto-archived to prevent unbounded storage growth.
- **Early user message save** — user messages are persisted to DynamoDB *before* Bedrock processing, so data is never lost even if the AI call fails.
- **In-memory profile cache** — 120-second TTL cache avoids redundant DynamoDB reads for profile data within a session.
- **TTL-based cleanup** — sessions (30 days), OTP (5 min), rate limits (minutes/hours/days) all auto-expire via DynamoDB TTL. Zero cron jobs.
- **Atomic operations** — DynamoDB `if_not_exists` for rate limiting prevents race conditions under concurrent requests.
- **Connection pooling** — 25 max concurrent connections reused across child Lambda invocations.
- **gTTS exponential backoff + jitter** — TTS failures retry with exponential delay and random jitter to avoid thundering herd.

### Frontend Engineering
- **`requestIdleCallback` prefetching** — preloads chat history and profile data during browser idle time; zero perceived latency on page transitions.
- **PageErrorBoundary** — each route wrapped in an error boundary; a single component crash doesn't take down the app.
- **Cognito session restore** — 3-second timeout race: if token refresh hangs, the app loads anyway with cached state.
- **Orphan Cognito user cleanup** — detects users who signed up but never completed profile and offers cleanup.
- **15+ responsive breakpoints** — mobile-first CSS optimised for budget Android phones and small Indian-market screens.
- **Staggered skeleton loaders** — shimmer animations prevent layout shift while data loads.
- **Auto-refresh presigned URLs** — expired S3 audio URLs are silently refreshed in the background.
- **6-field timestamp normalisation** — handles multiple timestamp formats from DynamoDB and API to ensure consistent display.
- **ResizeObserver scroll pill** — auto-shows "scroll to bottom" indicator when new messages arrive below the viewport.
- **ARIA attributes** — chat messages, voice buttons, and navigation elements include accessibility roles and labels.

### Observability & Audit
- **Structured JSON audit trail** — 7 event categories and 13 action types; every guardrail block, PII detection, tool invocation, and policy decision is logged with structured metadata.
- **PII-safe logging** — audit logs capture event metadata (action type, category, timestamp) without exposing farmer personal data.
- **CloudWatch custom metrics** — tool execution latency, cache hit rates, and guardrail trigger counts tracked as custom metrics for operational dashboards.
- **Bedrock guardrail audit** — every guardrail intervention (topic gate, toxicity block, grounding failure) logged with the triggering input pattern.

---

## 17. Production Roadmap — Future Plans

Our prototype is **production-upgradeable by configuration, not rewrite**. Given the modular architecture, feature flags, and IaC foundation, we can deliver all production features within **~1–2 months**:

### Phase 1 — Week 1: Core Production Hardening
- **SMS OTP:** Complete TRAI DLT registration, flip `ENABLE_DEMO_OTP=false` — zero code changes
- **Custom domain:** Route 53 + ACM → branded URL (e.g., `kisanai.in`)
- **CI/CD:** CodePipeline + CodeBuild → auto-deploy on push
- **Alerting:** CloudWatch Alarms + SNS for error spikes, latency, 5xx

### Phase 2 — Week 2: Channels, TTS & Offline
- **WhatsApp channel** via Business API → 500M+ Indian users
- **Full Indic TTS** — Polly (as voices release) or AI4Bharat/IISc TTS
- **Offline-first PWA** — Service Worker + IndexedDB for low-connectivity areas
- **Push notifications** — weather alerts, pest warnings, scheme deadlines
- **Multi-region DR** — ap-southeast-1 failover with DynamoDB Global Tables

### Phase 3 — Weeks 3–4: KB Auto-Update, Mobile App, Analytics & Personalisation
- **KB Auto-Update Pipeline** — EventBridge cron → Lambda scrapes ICAR/KVK/state portals → validates & deduplicates → uploads to S3 → triggers Bedrock KB re-sync. Version-tagged, rollback-capable.
- **KB Expansion** — 500+ verified ICAR/KVK/state agriculture documents
- **Native Mobile App (Android + iOS)** — React Native / Capacitor → Play Store + App Store listing with native push, camera (Crop Doctor), GPS (auto-location)
- **Fine-tuned Nova Pro** on 10K+ Indian agriculture Q&A pairs
- **Per-farmer personalisation** from query history, crop patterns, location
- **Redis rate limiting** (ElastiCache) + WAF for abuse prevention
- **QuickSight analytics** — usage patterns, regional demand, scheme engagement

### Future Enhancements (Post-Launch)
- **IoT sensors** (AWS IoT Core) → real-time soil moisture, pH, temperature
- **Marketplace** — mandi prices, buyer-seller connections, input purchasing
- **Govt API integration** — Aadhaar e-KYC, DigiLocker, PM-KISAN → one-click scheme enrolment
- **IVR/USSD via Amazon Connect** → voice-first for feature phone farmers
- **Multilingual fine-tuning** — native Hindi/Tamil/Telugu models, no translation round-trip
- **Scale to 10M+ farmers** — multi-AZ, Lambda concurrency reserves, DynamoDB on-demand

```
PROTOTYPE               →  PRODUCTION (Weeks 1–2)      →  SCALE (Weeks 3–4 + Post-Launch)
On-screen OTP           →  SNS SMS OTP                →  Aadhaar e-KYC
gTTS (13 langs)         →  Polly + Indic TTS          →  Regional fine-tuned TTS
React SPA               →  PWA (offline)              →  Native Android + iOS App
Nova Pro + RAG          →  Fine-tuned Nova Pro        →  Multilingual fine-tuned
Manual KB updates       →  Automated KB pipeline      →  Auto-ingest from govt APIs
Browser-only            →  + WhatsApp channel         →  + IVR + USSD + mobile apps
Single region           →  Multi-region DR            →  Global CDN + edge
```

> **For evaluators:** Our architecture is *designed* for this evolution. Feature flags, env-driven config, micro-Lambdas, and IaC mean each phase is an incremental addition — never a rewrite.

---

## Submission Checklist

| Deliverable | Status |
|-------------|--------|
| **Project PPT** | Uploaded to dashboard |
| **GitHub Repository** | [github.com/Sanjay060901/smart-rural-ai-advisor](https://github.com/Sanjay060901/smart-rural-ai-advisor) (public) |
| **Working Prototype** | [https://d80ytlzsrax1n.cloudfront.net](https://d80ytlzsrax1n.cloudfront.net) (live) |
| **Demo Video** | [Watch on YouTube](https://youtu.be/PYYTB6gH1rI?si=38Iub-dKBXA8XEz2) |
| **Project Summary** | `docs/PROJECT_SUMMARY.md` |

---

<p align="center"><strong>Built with ❤️ for Bharat's farmers — AWS AI for Bharat Hackathon 2026</strong></p>
