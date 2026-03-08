# Project Summary — Smart Rural AI Advisor

> **Team:** Creative Intelligence (CI) | **Hackathon:** AWS AI for Bharat 2026  
> **Live Prototype:** [https://d80ytlzsrax1n.cloudfront.net](https://d80ytlzsrax1n.cloudfront.net)  
> **Repository:** [github.com/Sanjay060901/smart-rural-ai-advisor](https://github.com/Sanjay060901/smart-rural-ai-advisor)

---

## What We Built

**Smart Rural AI Advisor** is a fully serverless, voice-first, multilingual AI agricultural assistant that gives Indian farmers instant, personalised guidance — in their own language — for crop management, pest/disease diagnosis, weather advisories, and government scheme navigation.

A farmer in Tamil Nadu can **speak in Tamil**: *"நெல் பயிரில் பழுப்பு நிற புள்ளிகள் தெரிகிறது"* (brown spots on my rice crop) — and receive a **spoken Tamil response** with disease diagnosis, treatment plan, and nearby KVK recommendation — all within seconds.

---

## The Problem

India's farmers face a five-fold information crisis:

1. **No expert access** — 1 agricultural officer per 1,000+ farmers
2. **Language barriers** — resources are English-only; farmers speak 13+ languages
3. **Delayed disease response** — lab visits take days; crop damage is immediate
4. **Unclaimed government benefits** — ₹2+ lakh crore in schemes go unenrolled annually
5. **Weather unpredictability** — climate change makes traditional calendars unreliable

**86% of Indian farming households are small/marginal** (< 5 acres) and are most affected by these gaps.

---

## Why AI Is Required

| Challenge | Why Only AI Can Solve It |
|-----------|------------------------|
| **Multi-step reasoning** | Correlate crop symptoms + weather + season + soil to diagnose disease and recommend treatment — requires LLM reasoning, not keyword search |
| **13-language coverage** | Building separate content per language per crop per region is infeasible — Generative AI + Amazon Translate covers all 13 from a single knowledge base |
| **Photo-based diagnosis** | Crop disease identification from leaf images requires computer vision (Nova Pro Vision) — no rule-based system can achieve this |
| **Personalisation** | Combining farmer profile + real-time weather + scheme eligibility dynamically requires reasoning, not static FAQ |
| **Voice accessibility** | End-to-end speech → intent → tools → advisory → speech pipeline is inherently an AI problem |
| **Hallucination prevention** | RAG with verified agricultural data ensures pesticide dosages, MSP values, and scheme details are factually correct |

---

## Core Features

| Feature | What It Does | AWS Service |
|---------|-------------|-------------|
| **AI Chat** | Conversational farming advisor — understands intent, calls tools, synthesises grounded advice | Amazon Bedrock (Nova Pro) with tool-calling |
| **Crop Doctor** | Upload leaf/crop photo → instant disease diagnosis with severity, treatment, and prevention | Amazon Bedrock (Nova Pro Vision) |
| **Weather Advisory** | Real-time weather + 5-day forecast → farming-specific recommendations ("irrigate today", "delay spraying") | AWS Lambda + OpenWeatherMap |
| **Govt Schemes** | Explains 10+ schemes (PM-KISAN, PMFBY, KCC, etc.) with eligibility, benefits, and application steps | Lambda + curated data |
| **Crop Advisory (RAG)** | Season, soil, and region-aware crop recommendations grounded in verified agricultural data | Bedrock Knowledge Base |
| **Farmer Profile** | Persistent profile (crops, soil, district, language) for automatic personalisation | Amazon DynamoDB |
| **Voice Input** | Speak in any of 13 languages → text | Web Speech API + Amazon Transcribe |
| **Voice Output** | Hear AI responses spoken aloud in your language | Amazon Polly + gTTS (13 languages) |
| **13 Languages** | Full UI + chat + voice: Tamil, Hindi, Telugu, Kannada, Malayalam, Bengali, Marathi, Gujarati, Punjabi, Odia, Assamese, Urdu, English | Amazon Translate |
| **Interactive Map** | Leaflet-based weather map with city quick-select and forecast overlays | React-Leaflet |
| **Guardrails** | Prompt injection defence, PII masking, toxicity detection, rate limiting, fact-checking | Code-level + Bedrock Guardrails |

---

## How AWS Services Are Used

| AWS Service | Role | Why |
|-------------|------|-----|
| **Amazon Bedrock (Nova Pro + Nova 2 Lite)** | Nova Pro: chat reasoning, tool-calling, image diagnosis. Nova 2 Lite: lightweight tasks. Bidirectional fallback — each model falls back to the other on throttle/timeout | Managed GenAI — no hosting, pay-per-use, native tool-use |
| **Bedrock Knowledge Base** | RAG retrieval for crop/pest advisories | Grounded answers from verified agricultural data |
| **Bedrock Guardrails** | Topic gating, content filtering, grounding checks | Enterprise safety for farmer-facing AI |
| **AWS Lambda (7 functions)** | All backend compute — orchestration, weather, crop, schemes, profile, image, transcribe | Serverless — zero idle cost, auto-scales |
| **Amazon API Gateway** | REST API (11 routes, CORS) | Managed API with throttling |
| **Amazon DynamoDB** | Profiles, chat sessions, rate limits, OTP codes | Serverless NoSQL, millisecond latency |
| **Amazon S3 + CloudFront** | Frontend hosting + CDN + audio storage | Low-latency delivery across India |
| **Amazon Translate** | Auto-detect + translate across 13 Indian languages | Native Indian language support |
| **Amazon Polly** | Neural TTS — Kajal (bilingual: Hindi + Indian English) | High-quality speech output |
| **Amazon Transcribe** | Speech-to-text fallback (12 Indian languages) | Firefox/Safari voice support |
| **Amazon Cognito** | Phone + PIN authentication → JWT tokens | Managed user pool; OTP displayed on-screen for prototype (see Tradeoffs below) |
| **AWS IAM** | Least-privilege policies per Lambda | Security best practice |
| **AWS Secrets Manager** | Secure API key storage | No secrets in code |
| **Amazon CloudWatch** | Logs, metrics, alarms | Operational visibility |

---

## What Value the AI Layer Adds

| Without AI | With Smart Rural AI Advisor |
|---|---|
| Farmer searches multiple English websites | Ask one question in native language → complete, personalised answer |
| Generic crop advice (same for everyone) | Advice tailored to farmer's specific location, soil, crops, and season |
| No disease diagnosis without a lab visit | Upload a photo → instant AI diagnosis with treatment plan |
| Government scheme PDFs are dense and confusing | AI explains eligibility, benefits, and step-by-step application in farmer's language |
| No after-hours help | 24/7 availability, zero cost to the farmer |
| Voice-only help = IVR with long wait times | Instant voice I/O in 13 languages with no queue |

---

## Architecture Summary

```
Farmer (13 languages, voice/text)
  → CloudFront (React SPA)
    → API Gateway (11 REST routes)
      → Agent Orchestrator Lambda (the brain)
        → Amazon Translate (detect + translate)
        → Amazon Bedrock Nova Pro (reason + tool-call)
        → Child Lambdas: Weather, Crop Advisory (KB/RAG), Schemes, Profile, Image Diagnosis
        → Post-process: fact-check, translate back, TTS (Polly/gTTS)
      → Response: { text, audio, tools_used, session_id }
```

**Key design choices:**
- **Single orchestrator with Bedrock tool-calling** — the model decides which tools to invoke, not hard-coded routing
- **Fact-checking** — every AI response is validated against real tool data before delivery
- **Model fallback** — Nova Pro ↔ Nova 2 Lite (bidirectional — each model automatically falls back to the other on throttle/timeout, ensuring 100% availability)
- **Dual-path voice** — Web Speech API (Chrome, zero latency) + Amazon Transcribe (Firefox/Safari fallback)
- **Fully serverless** — Lambda + API Gateway + DynamoDB + S3 + CloudFront — scales to zero

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Frontend** | React 18, Vite, React Router v6, React-Leaflet, DOMPurify, Marked, amazon-cognito-identity-js |
| **Backend** | Python 3.13, AWS Lambda (7 functions), boto3 |
| **AI/GenAI** | Amazon Bedrock (Nova Pro + Nova 2 Lite), Bedrock Knowledge Base (RAG), Bedrock Guardrails |
| **API** | Amazon API Gateway (REST, 11 routes, CORS-enabled) |
| **Database** | Amazon DynamoDB (4 tables: profiles, sessions, OTP, rate limits) |
| **Storage/CDN** | Amazon S3, Amazon CloudFront |
| **Translation** | Amazon Translate (13 Indian languages, auto-detect) |
| **Voice** | Amazon Polly, gTTS, Web Speech API, Amazon Transcribe |
| **Auth** | Amazon Cognito (phone + PIN → JWT), on-screen OTP for prototype |
| **IaC** | AWS SAM (CloudFormation) |
| **Region** | ap-south-1 (Mumbai) |

---

## Team

| Name | Role | Contribution |
|------|------|-------------|
| **Sanjay M** | Team Lead + Frontend | React UI, all 11 pages, voice components, i18n (13 languages), CSS, CloudFront deployment |
| **Manoj RS** | Backend + Infrastructure | 7 Lambda functions, SAM template, Bedrock integration, API Gateway, Polly/Translate, security modules |
| **Abhishek Reddy** | Data + Knowledge Base | Crop data curation, government schemes, Bedrock KB documents, S3 upload |
| **Jeevidha R** | QA + Documentation | End-to-end testing, documentation, demo video, project submission |

---

## Repository Structure

```
smart-rural-ai-advisor/
├── frontend/              # React 18 + Vite SPA — 11 pages, 13 languages
│   └── src/               # components, pages, contexts, hooks, services, i18n, utils
├── backend/
│   ├── lambdas/           # 7 Lambda functions (orchestrator, crop advisory, weather, schemes, profile, image, transcribe)
│   └── utils/             # 9 shared modules (guardrails, rate limiter, translate, polly, dynamodb, audit, cors, error, response)
├── infrastructure/        # SAM template, samconfig, deploy scripts, Cognito config
├── docs/                  # Architecture, project summary, problem statement, submission brief, KB overview, diagram
├── buildspec.yml          # AWS CodeBuild CI/CD
└── README.md
```

> **Full file-level tree available in [README.md](../README.md).**

---

## Impact Targets

| Metric | Target |
|--------|--------|
| Reduce crop loss from undiagnosed diseases | **30%** — instant photo/symptom diagnosis |
| Increase government scheme enrolment | **50%** — AI explains eligibility in native language |
| 24/7 expert-level advice | **Zero cost** — serverless, free-tier friendly |
| Language accessibility | **13 Indian languages** — 95%+ of farming population |
| Voice accessibility | **Full voice I/O** — for farmers who can't read/type |
| Response time | **< 10 seconds** — query to spoken response |

---

## Design Tradeoffs

We made deliberate engineering tradeoffs for the prototype, each with a clear production upgrade path:

| Tradeoff | Decision | Why | Production Path |
|----------|----------|-----|----------------|
| **OTP Delivery** | On-screen display instead of SMS/WhatsApp | SMS via SNS requires TRAI DLT Sender ID registration (2–4 weeks); WhatsApp Business API needs Meta verification — both infeasible in hackathon timeline | Flip `ENABLE_DEMO_OTP=false` → OTP sent via SNS SMS. Backend code path already exists. |
| **TTS Coverage** | gTTS for 11 of 13 languages | Amazon Polly only supports Hindi + English neural voices for Indian languages | Replace with Polly as AWS adds Indic language support, or integrate dedicated Indic TTS |
| **Voice Input** | Dual-path (Web Speech + Transcribe) | Web Speech API unavailable on Firefox/Safari; Transcribe adds 3–5s latency | Acceptable — Chrome/Edge cover 80%+ of Indian mobile users with zero-latency streaming |
| **Model Choice** | Nova Pro (general) + RAG, not fine-tuned | Fine-tuning needs curated datasets + compute budget + iteration cycles | RAG achieves grounded responses today; fine-tuning is a future optimisation |
| **Web App vs Native** | React SPA, not Android/iOS app | No installation barrier, works on any browser, avoids app store delays | PWA conversion for offline + push notifications is a clear next step |
| **Rate Limiting** | DynamoDB counters, not API Gateway throttling | Per-farmer fairness (not per-IP) — farmers share devices/carrier NAT | Both used: API GW for global, DynamoDB for per-farmer |

---

## Strengths & Best Practices

### Architecture
- **100% serverless** — Lambda + API Gateway + DynamoDB + S3 + CloudFront. Zero server management, auto-scaling, pay-per-use.
- **Single-responsibility Lambdas** — each function has one job, independently deployable and testable.
- **Orchestrator + tool-calling** — Bedrock decides which tools to invoke based on intent. Adding a new capability = adding a tool schema, no routing code changes.
- **Infrastructure as Code** — 100% SAM/CloudFormation. Conditional resources and startup env validation ensure correct deployments.
- **29+ feature flags** — demo → production = env var changes, not code changes. TTS, guardrails, caching, audit — all configurable.
- **Single-table DynamoDB design** — sessions, messages, cache entries share optimised layouts with composite keys and TTL auto-expiry.
- **Cascade session delete** — deleting a session atomically removes all child messages, cache entries, and audit records.

### Security & Safety
- **7-layer defence in depth** — input validation → PII masking → injection prevention → toxicity detection → rate limiting → output guardrails → Bedrock Guardrails.
- **Least-privilege IAM** — each Lambda has a dedicated role scoped to only its required resources.
- **ReDoS protection** — regex input lengths capped to prevent denial-of-service via pathological patterns.
- **Crisis helpline redirect** — self-harm/distress detection → 3 Indian helpline numbers (iCall, Vandrevala, AASRA) instead of AI response.
- **Banned pesticide detection** — 8 hazardous chemicals detected with safer alternatives suggested automatically.
- **System prompt leak prevention** — 15 marker patterns block the model from exposing internal instructions.
- **PII never in logs** — Aadhaar, phone, PAN, email masked before CloudWatch logging.
- **20+ injection patterns** — prompt injection, SQL injection, command injection blocked at every entry point.
- **Custom DOMPurify allowlist** — frontend sanitises AI markdown with curated tag/attribute whitelist.

### AI/ML Intelligence
- **RAG over fine-tuning** — grounded responses from verified data, instantly updatable.
- **3-layer hallucination prevention** — RAG + code-level fact-checking + Bedrock Guardrails.
- **21-rule system prompt** — inline MSP/NPK data, tool-first routing, cautious diagnosis mandate, multilingual output rules.
- **200-term AgriPolicy keyword set** — domain gating deflects off-topic queries without wasting model invocations.
- **Greeting shortcut** — simple greetings skip Bedrock entirely, saving cost and latency.
- **Tool result enrichment** — state filtering, cross-state scheme detection, advisory augmentation before model synthesis.
- **Quality gates** — KB retrieval requires min score (0.35) and min 2 good chunks; auto-rewrites query on low quality.
- **Freshness detection** — flags stale data for time-sensitive queries (MSP, deadlines) with explicit caveat.

### Translation & Localization
- **3-attempt translation** — Bedrock Lite → Amazon Translate → English fallback, with garbled output detection between attempts.
- **Token-based markdown protection** — placeholder tokens preserve formatting through translation round-trips.
- **700+ district name translations** — pre-computed in 7 Indian scripts for instant rendering.
- **Per-language Latin-script thresholds** — detects untranslated Latin text and auto-retries with different engine.

### System Design & Resilience
- **Graceful degradation at every layer** — model fallback (Nova Pro ↔ Nova 2 Lite, bidirectional), TTS fallback, voice fallback. Always returns something useful.
- **Category-aware response caching** — SHA-256 keys with domain-specific TTLs (weather = 1h, schemes = 12h).
- **Parallel tool execution** — ThreadPoolExecutor runs up to 5 tools concurrently per chat turn.
- **Timeout budgeting** — 25s tools, 18s TTS cutoff, 29s API GW limit. Slow services skipped; text always delivered.
- **Dual chat persistence** — localStorage for instant loads + DynamoDB for cross-device sync.
- **Early user message save** — messages persisted before Bedrock processing; never lost even if AI call fails.
- **TTL-based cleanup** — sessions, OTP, rate limits auto-expire via DynamoDB TTL. Zero cron jobs.
- **Observability** — structured JSON audit trail (7 categories, 13 action types) + CloudWatch custom metrics + PII-safe logging.

### Frontend Engineering
- **`requestIdleCallback` prefetching** — preloads data during browser idle time; zero perceived latency.
- **PageErrorBoundary** — each route isolated; component crashes don't break the app.
- **Cognito session restore** — 3-second timeout race prevents auth hangs from blocking the app.
- **15+ responsive breakpoints** — mobile-first CSS for budget Android phones and small Indian screens.
- **Staggered skeleton loaders** — shimmer animations prevent layout shift during data loads.

---

## Production Roadmap — From Prototype to Scale

Our prototype is designed to be **production-upgradeable by configuration, not rewrite**. Given the modular architecture, feature flags, and IaC foundation, we can pull all production features within **~1–2 months**:

### Phase 1 — Week 1: Core Production Hardening

| Upgrade | How |
|---------|-----|
| **SMS OTP** | Complete TRAI DLT Sender ID registration, flip `ENABLE_DEMO_OTP=false` — zero code changes |
| **Custom domain** | Route 53 + ACM certificate → branded URL (e.g., `kisanai.in`) |
| **CI/CD pipeline** | AWS CodePipeline + CodeBuild → auto-deploy on push to `main` |
| **Monitoring** | CloudWatch Alarms + SNS notifications for error spikes, latency, 5xx |

### Phase 2 — Week 2: Channels, TTS & Offline

| Upgrade | How |
|---------|-----|
| **WhatsApp channel** | WhatsApp Business API integration → reach 500M+ Indian WhatsApp users |
| **Full Indic TTS** | Replace gTTS with Amazon Polly (as voices release) or dedicated Indic TTS (AI4Bharat / IISc) |
| **Offline-first PWA** | Service Worker + IndexedDB → cached advice in low-connectivity areas |
| **Push notifications** | Weather alerts, pest warnings, scheme deadlines pushed proactively |
| **Multi-region DR** | ap-southeast-1 failover with DynamoDB Global Tables |

### Phase 3 — Weeks 3–4: KB Auto-Update, Mobile App, Analytics & Personalisation

| Upgrade | How |
|---------|-----|
| **KB Auto-Update Pipeline** | EventBridge scheduled rule → Lambda scrapes ICAR/KVK/state portals → validates & uploads to S3 → triggers Bedrock KB re-sync. Hash-based dedup, version tagging, rollback capability |
| **KB Expansion** | Add 500+ verified ICAR/KVK/state agriculture documents |
| **Native Mobile App (Android + iOS)** | React Native / Capacitor → Play Store + App Store listing with native push, camera (Crop Doctor), GPS (auto-location) |
| **Fine-tuned model** | Train on 10K+ Indian agriculture Q&A pairs via Bedrock fine-tuning |
| **Per-farmer personalisation** | ML-based recommendations from query history, crop patterns, region |
| **Analytics dashboard** | Amazon QuickSight + Athena → usage patterns, regional demand, scheme engagement |

### Future Enhancements (Post-Launch)

| Upgrade | How |
|---------|-----|
| **IoT sensor integration** | AWS IoT Core + soil/weather sensors → hyper-personalised field-level advice |
| **Marketplace integration** | Real-time mandi prices, buyer-seller connections, input purchase links |
| **Government API integration** | Aadhaar e-KYC + DigiLocker + PM-KISAN API → one-click scheme enrolment |
| **IVR/USSD channel** | Amazon Connect toll-free number → voice-first for feature phone farmers |
| **Multilingual fine-tuning** | Train on Hindi, Tamil, Telugu, Kannada corpus directly → no translation round-trip |
| **Scale to 10M+ farmers** | Multi-AZ, DynamoDB Global Tables, Lambda concurrency reserves, CDN optimisation |

> **Key insight:** Feature flags, environment-driven config, single-responsibility Lambdas, and Infrastructure-as-Code mean each phase is an *incremental addition*, never a rewrite.
