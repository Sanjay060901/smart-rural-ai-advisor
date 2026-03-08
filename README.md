# 🌾 Smart Rural AI Advisor

### AI-Powered Agricultural Advisory for Bharat's Farmers

> **Hackathon:** AWS AI for Bharat 2026  
> **Team:** Creative Intelligence (CI)  
> **Live Prototype:** [https://d80ytlzsrax1n.cloudfront.net](https://d80ytlzsrax1n.cloudfront.net)  
> **Demo Video:** [Watch on YouTube](https://youtu.be/PYYTB6gH1rI?si=38Iub-dKBXA8XEz2)  
> **Repository:** [github.com/Sanjay060901/smart-rural-ai-advisor](https://github.com/Sanjay060901/smart-rural-ai-advisor)

> Note: Internal regression scripts and prompt datasets were archived from the submission-facing repository to keep evaluation focused on the live prototype and production code.

---

## Project Summary

**Smart Rural AI Advisor** is a fully serverless, voice-first, multilingual AI agricultural assistant built on AWS. It gives Indian farmers instant, personalised guidance — in their own language — for crop management, pest/disease diagnosis, weather advisories, and government scheme navigation. A farmer can speak in Tamil, Hindi, or any of 13 Indian languages and receive a spoken response with actionable advice within seconds. The system uses **Amazon Bedrock (Nova Pro + Nova 2 Lite)** with agentic tool-calling, **RAG via Bedrock Knowledge Base**, 7-layer security, and bidirectional model fallback — all deployed as Infrastructure-as-Code with zero servers to manage.

---

## Table of Contents

1. [Project Summary](#project-summary)
2. [Problem Statement](#problem-statement)
3. [Our Solution](#our-solution)
4. [Why AI Is Required](#why-ai-is-required)
5. [Key Features](#key-features)
6. [Architecture](#architecture)
7. [AWS Services & How They're Used](#aws-services--how-theyre-used)
8. [Generative AI on AWS — Deep Dive](#generative-ai-on-aws--deep-dive)
9. [Supported Languages](#supported-languages)
10. [Live Prototype](#live-prototype)
11. [Demo Walkthrough](#demo-walkthrough)
12. [Tech Stack](#tech-stack)
13. [Project Structure](#project-structure)
14. [Local Development](#local-development)
15. [API Reference](#api-reference)
16. [Impact & Metrics](#impact--metrics)
17. [Design Tradeoffs & Rationale](#design-tradeoffs--rationale)
18. [Strengths & Best Practices](#strengths--best-practices)
19. [Production Roadmap — Future Plans](#production-roadmap--future-plans)
20. [Team](#team)

---

## Problem Statement

**70% of India's population depends on agriculture**, yet small-scale farmers face critical information gaps:

| Challenge | Scale |
|---|---|
| **No access to expert advice** | Agricultural extension officers cover 1000+ farmers each |
| **Language barriers** | Most resources are in English; farmers speak Tamil, Hindi, Telugu, Kannada, and 9 more languages |
| **Delayed pest / disease response** | By the time a disease is identified, significant crop loss has already occurred |
| **Unawareness of government schemes** | ₹2+ lakh crore in benefits go unclaimed every year |
| **Weather unpredictability** | Climate change makes traditional farming calendars unreliable |

**Target users:** Small and marginal farmers (< 5 acres) across India — primarily Tamil Nadu, Andhra Pradesh, Telangana, Karnataka — ages 25–65, often with limited English literacy, using an Android smartphone with basic internet.

---

## Our Solution

**Smart Rural AI Advisor** is a fully serverless, voice-first, multilingual AI assistant that gives Indian farmers instant, personalised agricultural guidance — in their own language — through a simple web interface.

Farmers can **speak or type** in any of **13 Indian languages**. The AI:

1. **Understands** the query (intent, language, entities)
2. **Retrieves real data** — live weather, curated crop advisories, government scheme details
3. **Reasons** over the data to produce actionable, grounded advice
4. **Validates** the response against tool outputs to prevent hallucination
5. **Responds** in the farmer's language with **audio playback** so even low-literacy users benefit

---

## Why AI Is Required

Traditional information systems (static FAQs, IVR hotlines, PDFs) fail rural farmers for three reasons:

| Limitation | How Generative AI Solves It |
|---|---|
| **One language only** | Amazon Bedrock (Nova Pro) + Amazon Translate handle 13 Indian languages natively — no separate content for each language |
| **Generic, not contextual** | The AI reasons across a farmer's profile (crops, soil, location, season) to deliver **personalised** advice in real time |
| **No expert reasoning** | Foundation models perform multi-step reasoning: correlate symptoms → retrieve pest data → cross-check weather → suggest treatment — mimicking an agricultural scientist |
| **Crop disease diagnosis** | Nova Pro Vision analyses uploaded crop/leaf photos and returns a diagnosis with treatment steps — no lab visit needed |
| **Voice accessibility** | Voice input (Web Speech API + Amazon Transcribe) and voice output (Amazon Polly + gTTS) make the system usable for farmers who cannot read or type comfortably |

**Bottom line:** Without Generative AI, building a system that reasons across weather + crop science + pest databases + government policy — in 13 languages, with voice — would be infeasible for a small team.

---

## Key Features

| Feature | Description | AWS Service |
|---|---|---|
| 💬 **AI Chat** | Conversational farming advisor with tool-calling and grounded responses | Amazon Bedrock (Nova Pro) |
| 🌤️ **Weather** | Real-time weather + 5-day forecast + farming-specific advisory | AWS Lambda + OpenWeather API |
| 🌾 **Crop Advisory** | Season-, soil-, and region-aware crop recommendations | Lambda + Bedrock Knowledge Base |
| 🐛 **Pest & Disease** | Symptom-based diagnosis with organic & chemical treatments; cautious, confirmation-first framing | Bedrock (Nova Pro) reasoning |
| 📋 **Govt Schemes** | Eligibility, benefits, and application steps for 10+ central/state schemes (PM-KISAN, PMFBY, etc.) | Lambda + curated knowledge base |
| 📸 **Crop Doctor** | Upload a leaf/crop photo → AI diagnoses the disease with severity and treatment plan | Bedrock (Nova Pro Vision) |
| 👤 **Farmer Profile** | Persistent farm details (crops, soil, district) for personalised responses | Amazon DynamoDB |
| 🎤 **Voice Input** | Speak in any supported language → converted to text | Web Speech API + Amazon Transcribe |
| 🔊 **Voice Output** | Hear AI responses spoken aloud in your language | Amazon Polly + gTTS |
| 🌐 **13 Languages** | Full UI + chat + voice in Tamil, Hindi, Telugu, Kannada, Malayalam, Bengali, Marathi, Gujarati, Punjabi, Odia, Assamese, Urdu, English | Amazon Translate |
| 🔒 **Guardrails** | Topic gating, hallucination prevention, rate limiting, Bedrock Guardrails | Bedrock Guardrails + code-level policy |
| 🗺️ **Interactive Weather Map** | Leaflet-based map with city quick-select and forecast overlays | React-Leaflet + Lambda |

---

## Architecture

### High-Level Flow

```
 ┌────────────────────┐
 │  Farmer (Mobile /  │
 │  Desktop Browser)  │
 └────────┬───────────┘
          │  HTTPS
          ▼
 ┌────────────────────┐        ┌─────────────────────────────────────────────────┐
 │  React 18 + Vite   │        │  Amazon CloudFront (CDN)                        │
 │  Single-Page App   │◄──────►│  S3 Static Hosting                              │
 │  13-language i18n  │        └─────────────────────────────────────────────────┘
 └────────┬───────────┘
          │  REST API
          ▼
 ┌────────────────────┐
 │  Amazon API Gateway│  ── 11 routes, CORS-enabled, ap-south-1
 └────────┬───────────┘
          │
          ▼
 ┌──────────────────────────────────────────────────────────────────────────────┐
 │                     AWS Lambda Functions (Python 3.13)                       │
 │                                                                              │
 │  ┌─────────────────────────────────────────────────────────────────────┐     │
 │  │  Agent Orchestrator (the brain)                                     │     │
 │  │                                                                     │     │
 │  │  1. Amazon Translate  ─ detect language, translate to English       │     │
 │  │  2. Amazon Bedrock    ─ Nova Pro: intent + tool-calling + reasoning │     │
 │  │  3. Tool Execution    ─ invoke child Lambdas for real data          │     │
 │  │  4. Post-Processing   ─ fact-check, format, translate back          │     │
 │  │  5. Amazon Polly/gTTS ─ generate audio in farmer's language         │     │
 │  │  6. DynamoDB          ─ persist chat history + session context      │     │
 │  └────────────┬────────────────────────────────────────────────────────┘     │
 │               │ invoke                                                       │
 │    ┌──────────┼──────────┬──────────────┬───────────────┐                    │
 │    ▼          ▼          ▼              ▼               ▼                    │
 │  Weather   Crop       Govt          Farmer          Image                    │
 │  Lookup    Advisory   Schemes       Profile         Analysis                 │
 │  Lambda    Lambda     Lambda        Lambda          Lambda                   │
 │    │         │          │              │               │                     │
 │    ▼         ▼          ▼              ▼               ▼                     │
 │ OpenWeather Bedrock KB Curated      DynamoDB       Bedrock                   │
 │ API         (RAG)      JSON Data    (profiles)     Nova Pro Vision           │
 │                                                                              │
 │  + Transcribe Speech Lambda (Amazon Transcribe — voice-to-text fallback)     │
 │  + Health Check Lambda (inline — stack health)                               │
 └──────────────────────────────────────────────────────────────────────────────┘
```

### What Makes This Architecture Different

| Design Choice | Rationale |
|---|---|
| **Single orchestrator with tool-calling** | Amazon Bedrock Nova Pro decides which tools to invoke; no hard-coded routing — the model reasons about the farmer's intent |
| **Fact-checking & hallucination prevention** | Every AI response is grounded against real tool data; code-level policy + Bedrock Guardrails catch unsupported claims |
| **Cautious pest diagnosis** | The system never hard-asserts a single disease from symptoms alone — it lists probable causes and recommends confirmation |
| **Only the Reasoning layer has tools** | Principle of least privilege — translation, fact-checking, and communication are handled without tool access |
| **gTTS for Indic TTS** | Amazon Polly supports 2 Indian languages; gTTS covers all 13 for free, ensuring full voice coverage |
| **Web Speech API + Transcribe dual-path** | Chrome/Edge get zero-latency client-side recognition; Firefox/Safari fall back to Amazon Transcribe (12 Indian languages) |
| **Fully serverless on AWS** | Lambda + API Gateway + DynamoDB + S3 + CloudFront — zero server management, scales to zero, stays within free-tier for demos |

---

## AWS Services & How They're Used

| AWS Service | Purpose in This Project | Why This Service |
|---|---|---|
| **Amazon Bedrock** | Foundation model access (Nova Pro + Nova 2 Lite) — Nova Pro for chat reasoning, tool-calling, and crop image diagnosis; Nova 2 Lite for lightweight tasks + bidirectional fallback (each model falls back to the other on throttle/timeout) | Managed Gen AI — no model hosting, pay-per-use, supports tool-use natively |
| **Amazon Bedrock Knowledge Base** | RAG (Retrieval-Augmented Generation) over curated farming documents for crop advisories | Grounded answers from verified agricultural data instead of hallucinated responses |
| **Amazon Bedrock Guardrails** | Content filtering, topic gating, grounding checks | Enterprise-grade safety for farmer-facing AI |
| **AWS Lambda** | 7 serverless functions + 1 inline health check — all backend compute | Zero idle cost, auto-scaling, Python 3.13 runtime |
| **Amazon API Gateway** | REST API with 11 routes, CORS, regional deployment | Managed API layer with throttling and monitoring |
| **Amazon DynamoDB** | Farmer profiles, chat session history, rate-limit counters, OTP codes | Serverless NoSQL — millisecond latency, free-tier friendly |
| **Amazon S3** | Static frontend hosting, audio file storage, knowledge-base documents | Durable object storage integrated with CloudFront |
| **Amazon CloudFront** | CDN for the React frontend — low-latency delivery across India | Edge locations in Mumbai, Chennai, Bangalore, Delhi |
| **Amazon Translate** | Auto-detect language and translate between English and 13 Indian languages | Native support for Indian languages with auto-detection |
| **Amazon Polly** | Text-to-speech for English and Hindi responses | Neural voice — Kajal (bilingual: Hindi + Indian English) |
| **Amazon Transcribe** | Speech-to-text fallback for Firefox/Safari users in 12 Indian languages | Covers browsers where Web Speech API is unavailable |
| **Amazon Cognito** | User authentication for farmer profile management | Managed auth with phone-number + PIN → JWT tokens; OTP displayed on-screen for prototype (no SMS) |
| **AWS IAM** | Least-privilege policies for every Lambda function | Security best practice — each function only accesses what it needs |
| **Amazon CloudWatch** | Logging, metrics, and alarms for all Lambda functions | Operational visibility and debugging |

---

## Generative AI on AWS — Deep Dive

### Foundation Model: Amazon Nova Pro (`apac.amazon.nova-pro-v1:0`)

We use **Amazon Nova Pro** via the **Amazon Bedrock Converse API** for:

1. **Conversational reasoning** — The orchestrator sends the farmer's query along with tool definitions; Nova Pro decides which tools to call, interprets the results, and composes a natural-language advisory.

2. **Tool-use (function calling)** — Nova Pro receives 5 tool schemas (weather, crop, pest, schemes, profile) and autonomously decides which to invoke based on intent. The orchestrator executes the tool, feeds results back, and the model synthesises a final answer.

3. **Crop disease vision** — When a farmer uploads a photo, Nova Pro Vision analyses the image and returns a structured diagnosis (disease name, confidence, severity, treatment steps).

4. **Multilingual output** — Nova Pro generates responses in English; Amazon Translate converts to/from the farmer's language. The model's system prompt includes India-specific agricultural context (Kharif/Rabi seasons, local crop varieties, Indian government schemes).

### Secondary Model: Amazon Nova 2 Lite (`global.amazon.nova-2-lite-v1:0`)

Nova 2 Lite serves two roles: (1) **lightweight tasks** — used directly for simpler operations like Bedrock-based text localization and advisory formatting, keeping costs low and latency minimal; (2) **bidirectional fallback** — if Nova Pro hits a throttle or timeout, the system retries with Nova 2 Lite; conversely, if Nova 2 Lite fails, the system retries with Nova Pro. Either model can cover for the other, ensuring the farmer always gets a response.

### RAG with Bedrock Knowledge Base

Crop advisory queries are augmented with a **Bedrock Knowledge Base** containing curated Indian agricultural documents (crop calendars, soil maps, best practices). This ensures recommendations are grounded in verified data rather than model priors.

### Bedrock Guardrails

An optional Bedrock Guardrail layer provides:
- **Topic gating** — blocks non-agricultural queries
- **Grounding checks** — ensures responses are supported by tool data
- **Content filtering** — prevents harmful or irrelevant content

### Value the AI Layer Adds

| Without AI | With AI |
|---|---|
| Farmer must search multiple websites in English | Ask one question in their language, get a complete answer |
| Generic crop advice (same for everyone) | Personalised to farmer's location, soil, crops, and season |
| No disease diagnosis without a lab visit | Upload a photo → instant AI diagnosis with treatment plan |
| Government scheme PDFs are dense and confusing | AI explains eligibility, benefits, and step-by-step application |
| No after-hours help | 24/7 availability, zero cost to the farmer |

---

## Supported Languages

| # | Language | Script | Voice In | Voice Out |
|---|---|---|---|---|
| 1 | English | Latin | ✅ Web Speech | ✅ Amazon Polly (Kajal) |
| 2 | Hindi | Devanagari | ✅ Web Speech | ✅ Amazon Polly (Kajal) |
| 3 | Tamil | Tamil | ✅ Web Speech / Transcribe | ✅ gTTS |
| 4 | Telugu | Telugu | ✅ Web Speech / Transcribe | ✅ gTTS |
| 5 | Kannada | Kannada | ✅ Web Speech / Transcribe | ✅ gTTS |
| 6 | Malayalam | Malayalam | ✅ Web Speech / Transcribe | ✅ gTTS |
| 7 | Bengali | Bengali | ✅ Web Speech / Transcribe | ✅ gTTS |
| 8 | Marathi | Devanagari | ✅ Web Speech / Transcribe | ✅ gTTS |
| 9 | Gujarati | Gujarati | ✅ Web Speech / Transcribe | ✅ gTTS |
| 10 | Punjabi | Gurmukhi | ✅ Web Speech / Transcribe | ✅ gTTS |
| 11 | Odia | Odia | ✅ Web Speech / Transcribe | ✅ gTTS |
| 12 | Assamese | Bengali | ✅ Web Speech / Transcribe | ✅ gTTS |
| 13 | Urdu | Nastaliq | ✅ Web Speech / Transcribe | ✅ gTTS |

---

## Live Prototype

| Resource | URL |
|---|---|
| **Frontend (CloudFront)** | [https://d80ytlzsrax1n.cloudfront.net](https://d80ytlzsrax1n.cloudfront.net) |
| **API Gateway** | `https://YOUR_API_ID.execute-api.ap-south-1.amazonaws.com/Prod/` |
| **Health Check** | `https://YOUR_API_ID.execute-api.ap-south-1.amazonaws.com/Prod/health` |

> Evaluators can open the CloudFront URL on any modern browser (Chrome recommended for voice input). No installation required.

---

## Demo Walkthrough

> 🎬 **Full demo video:** [Watch on YouTube](https://youtu.be/PYYTB6gH1rI?si=38Iub-dKBXA8XEz2)

The demo video walks through the full capabilities of Smart Rural AI Advisor:

- **Dashboard** — The localised homepage displays a daily farming tip, season indicator (Rabi/Kharif), and quick-action cards for all features.
- **AI Chat** — Farmers can ask natural-language questions like *"What is the weather in Chennai for the next 3 days?"* — the AI autonomously calls the right backend tools, retrieves real data, and responds with a farming advisory plus audio playback.
- **Voice Input** — Farmers can speak in their native language (e.g., Tamil: *"நெல் பயிரில் பழுப்பு நிற புள்ளிகள் தெரிகிறது"*) and receive a spoken AI response with pest diagnosis in the same language.
- **Crop Doctor** — Upload a photo of a diseased leaf, select the crop and state, and get an instant AI diagnosis with disease name, severity, and treatment steps.
- **Government Schemes** — Browse schemes like PM-KISAN, PMFBY, and Soil Health Card with eligibility details, benefits, and step-by-step application guidance.
- **Farmer Profile** — Save personal details (name, district, crops, soil type) so that all future AI responses are automatically personalised to the farmer's context.
- **Multilingual Support** — Switch between any of the 13 supported Indian languages — the entire UI, chat responses, and audio output adapt instantly.

---

## Tech Stack

| Layer | Technology |
|---|---|
| **Frontend** | React 18, Vite, React Router, React-Leaflet, DOMPurify, Marked |
| **Backend** | Python 3.13, AWS Lambda (7 functions), boto3 |
| **AI / Gen AI** | Amazon Bedrock (Nova Pro + Nova 2 Lite), Bedrock Knowledge Base, Bedrock Guardrails |
| **API** | Amazon API Gateway (REST, 11 routes, CORS) |
| **Database** | Amazon DynamoDB (4 tables: farmer profiles, chat sessions, OTP codes, rate limits) |
| **Storage** | Amazon S3 (audio, KB docs), Amazon CloudFront (CDN) |
| **Translation** | Amazon Translate (13 Indian languages, auto-detect) |
| **Voice** | Amazon Polly, gTTS, Web Speech API, Amazon Transcribe |
| **Auth** | Amazon Cognito (phone + PIN → JWT), on-screen OTP for prototype |
| **Infra-as-Code** | AWS SAM (CloudFormation) |
| **Region** | ap-south-1 (Mumbai) — lowest latency for Indian users |

---

## Project Structure

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

---

## Local Development

### Prerequisites

- **Node.js 18+** (frontend)
- **Python 3.11+** (Lambda development)
- **AWS CLI** configured with `ap-south-1` credentials
- **AWS SAM CLI** (for infrastructure deployment)

### Run Frontend Locally

```bash
cd frontend
npm install
npm run dev          # Opens http://localhost:5173
```

Configure `frontend/.env` from `frontend/.env.example` before local run.

### Deploy Full Stack (SAM)

Set secrets in your shell (never commit secrets in config files). Preferred: use a Secrets Manager ARN.

```bash
export OPENWEATHER_API_KEY_SECRET_ARN='arn:aws:secretsmanager:ap-south-1:<account-id>:secret:<secret-name>'
# Fallback (legacy): export OPENWEATHER_API_KEY='<your-real-key>'
```

```bash
bash infrastructure/deploy.sh
```

### Deploy Full Stack (Windows / CloudFormation)

```powershell
$env:OPENWEATHER_API_KEY_SECRET_ARN = "arn:aws:secretsmanager:ap-south-1:<account-id>:secret:<secret-name>"
# Fallback (legacy): $env:OPENWEATHER_API_KEY = "<your-real-key>"
./infrastructure/deploy_cfn.ps1
```

Optional CI helper: `buildspec.yml` is included for teams that want to run SAM build/deploy through AWS CodeBuild.

## API Reference

| Method | Endpoint | Lambda | Description |
|---|---|---|---|
| `POST` | `/chat` | AgentOrchestrator | AI chat — text in, text + audio out |
| `POST` | `/voice` | AgentOrchestrator | Voice-optimised chat |
| `POST` | `/image-analyze` | ImageAnalysis | Crop photo → disease diagnosis |
| `POST` | `/transcribe` | TranscribeSpeech | Audio → text (Amazon Transcribe) |
| `GET` | `/weather/{location}` | WeatherLookup | Real-time weather + forecast |
| `GET` | `/schemes` | GovtSchemes | Government scheme directory |
| `GET/PUT/DELETE` | `/profile/{farmerId}` | FarmerProfile | Farmer profile CRUD |
| `POST` | `/otp/send` | FarmerProfile | Generate OTP (displayed on-screen for prototype) |
| `POST` | `/otp/verify` | FarmerProfile | Verify OTP |
| `POST` | `/pin/reset` | FarmerProfile | Reset farmer PIN |
| `GET` | `/health` | HealthCheck (inline) | Stack health check |

Base URL: `https://YOUR_API_ID.execute-api.ap-south-1.amazonaws.com/Prod`

---

## Impact & Metrics

| Metric | Target |
|---|---|
| Reduce crop loss from undiagnosed diseases | **30%** — instant AI diagnosis from photo or symptom description |
| Increase government scheme enrolment | **50%** — AI explains eligibility and application steps in the farmer's language |
| 24/7 expert-level agricultural advice | **Zero cost** to the farmer — fully serverless, within AWS free-tier for moderate usage |
| Language accessibility | **13 Indian languages** — covers 95%+ of India's farming population |
| Voice accessibility | **Full voice I/O** — usable by farmers who cannot read or type comfortably |

---

## Design Tradeoffs & Rationale

| Decision | What We Did | Why | Production Path |
|---|---|---|---|
| **OTP Delivery** | OTP displayed on-screen (`demo_otp` in API response) instead of SMS/WhatsApp | TRAI DLT regulations require 2–4 weeks for Sender ID/template registration; WhatsApp Business API requires Meta verification + BSP onboarding — infeasible in hackathon timeline | Enable SNS SMS delivery via `ENABLE_DEMO_OTP=false` flag once DLT registration is approved |
| **TTS Engine** | Amazon Polly (Hindi + English) + gTTS fallback for other languages | Polly supports only 2 of 13 target languages today; gTTS provides broader coverage with acceptable quality | Migrate to Amazon Polly as new Indic voices are released |
| **Voice Input** | Web Speech API (primary) + Amazon Transcribe (fallback) | Browser-native recognition gives near-zero latency on Chrome/Edge; Transcribe covers Firefox/Safari | Unified Transcribe path as browser support matures |
| **Foundation Model** | Nova Pro primary + Nova 2 Lite secondary (bidirectional fallback) | Nova Pro excels at tool-use and reasoning; Nova 2 Lite handles lightweight tasks and provides a cheaper safety net. Each model falls back to the other on throttle/timeout — ensuring 100% availability | Evaluate Claude or Titan if multilingual tool-use quality needs improvement |
| **Delivery Channel** | Mobile-optimised web app (PWA-ready) | No app store approvals; instant access via link; works on any smartphone browser | Wrap in Capacitor/TWA for store listing; add WhatsApp chatbot channel |
| **Rate Limiting** | DynamoDB-based token counters | Avoids API Gateway usage-plan coupling; works within free-tier; per-user granularity | Move to Redis/ElastiCache if sub-millisecond enforcement is needed |

---

## Strengths & Best Practices

### Architectural Excellence
- **100% Serverless** — zero idle cost; auto-scales from 1 to 10,000 concurrent farmers with no capacity planning.
- **Infrastructure-as-Code** — single `template.yaml` creates the entire stack in one command. Conditional resources and startup environment validation ensure deployment correctness.
- **Micro-Lambda pattern** — 7 single-responsibility functions; isolated deployments and blast-radius containment.
- **29+ feature flags** — TTS engine, guardrail strictness, cache TTL, audit verbosity, model IDs — all configurable without redeployment. Demo → production is an env-var flip.
- **Single-table DynamoDB design** — sessions, messages, and cache entries share optimised table layouts with composite keys and TTL-based auto-expiry. No cron jobs.
- **Cascade session delete** — deleting a chat session atomically removes all child messages, cache entries, and audit records — zero orphaned data.

### Security & Safety (7-Layer Defence in Depth)
- **Layered security pipeline** — input validation → PII masking → injection prevention → toxicity detection → rate limiting → output guardrails → Bedrock Guardrails. No single point of failure.
- **Least-privilege IAM** — every Lambda has a dedicated role scoped only to the resources it accesses. Weather Lambda cannot touch DynamoDB.
- **ReDoS protection** — regex input lengths capped to prevent denial-of-service via pathological patterns.
- **Crisis helpline redirect** — self-harm / distress detection triggers immediate display of 3 Indian helpline numbers (iCall, Vandrevala, AASRA) instead of an AI response.
- **Banned pesticide detection** — 8 hazardous chemicals (endosulfan, monocrotophos, etc.) detected with safer alternatives suggested automatically.
- **System prompt leak prevention** — 15 marker patterns in AI output are checked to prevent the model from exposing internal system instructions.
- **PII never in logs** — Aadhaar, phone, PAN, email, bank account, IFSC masked before CloudWatch logging.
- **Custom DOMPurify allowlist** — frontend sanitises AI-generated markdown with a curated tag/attribute whitelist preventing XSS.
- **No hardcoded secrets** — API keys in Secrets Manager; config injected via CloudFormation environment variables.

### System Design & Resilience
- **Graceful fallback chain** — Polly → gTTS → silent; Nova Pro ↔ Nova 2 Lite (bidirectional — each falls back to the other) → error card; Web Speech → Transcribe. Always returns something useful.
- **Category-aware response caching** — SHA-256 hashed keys with domain-specific TTLs (weather = 1 h, schemes = 12 h) eliminate redundant Bedrock calls and save cost.
- **Parallel tool execution** — `ThreadPoolExecutor` runs up to 5 tool invocations concurrently per chat turn, reducing multi-tool latency.
- **Context window management** — sliding window (500 chars × 40 messages) keeps conversations efficient without token overflow.
- **Timeout budgeting** — 25 s tools, 18 s TTS cutoff, 29 s API GW hard limit. Slow services are skipped, text always delivered.
- **Dual chat persistence** — localStorage for instant page loads + DynamoDB for cross-device sync and durability.
- **Session eviction** — max 20 sessions per user; oldest auto-archived to prevent unbounded growth.
- **Connection pooling** — 25 max concurrent HTTP connections reused across child Lambda invocations.
- **Idempotent APIs** — OTP verify, profile PUT, and chat are safe to retry without side-effects.

### AI / ML Intelligence
- **RAG over hallucination** — Bedrock Knowledge Base grounds every crop advisory in verified government/ICAR data.
- **21-rule system prompt** — inline MSP/NPK reference data, tool-first routing policy, cautious diagnosis mandate, and multilingual output rules — all in one structured prompt.
- **200-term AgriPolicy keyword set** — domain gating ensures only agriculture-relevant queries reach Bedrock tools; off-topic queries are politely deflected.
- **Greeting shortcut** — simple greetings ("hi", "vanakkam", "namaste") skip Bedrock entirely, saving cost and latency.
- **Tool result enrichment** — raw tool data is post-processed with state filtering, cross-state scheme detection, and advisory augmentation before being passed to the model.
- **Quality gates** — KB retrieval requires min score (0.35) and min 2 good chunks; auto-rewrites query on low quality.
- **Freshness detection** — flags stale data for time-sensitive queries (MSP prices, scheme deadlines) with a caveat.
- **Cautious pest diagnosis** — never hard-asserts a disease; lists probabilities and always recommends KVK confirmation.

### Translation & Localization Intelligence
- **3-attempt translation strategy** — Bedrock Lite → Amazon Translate → graceful English fallback, with garbled output detection between each attempt.
- **Token-based markdown protection** — replaces markdown syntax with placeholder tokens before translation, restores after — prevents Translate from corrupting formatting.
- **700+ district name translations** — pre-computed translations in 7 Indian scripts for instant, accurate location rendering.
- **Per-language Latin-script thresholds** — detects when a translation returned too much Latin script (e.g., Tamil output with English words) and auto-retries.
- **Tamil-specific post-processing** — handles unique Tamil Unicode rendering quirks and agri-term translation artifacts.

### Frontend Engineering
- **`requestIdleCallback` prefetching** — preloads chat history and profile data during browser idle time; zero perceived latency on page transitions.
- **PageErrorBoundary** — each route wrapped in an error boundary; a single component crash doesn't take down the app.
- **Cognito session restore** — 3-second timeout race: if token refresh hangs, the app loads anyway with cached state.
- **Orphan Cognito user cleanup** — detects users who signed up but never completed profile creation and offers cleanup.
- **15+ responsive breakpoints** — mobile-first CSS optimised for budget Android phones and small Indian-market screens.
- **Staggered skeleton loaders** — shimmer animations prevent layout shift while data loads.
- **Auto-refresh presigned URLs** — expired S3 audio URLs are silently refreshed in the background.

### Observability & Audit
- **Structured JSON audit trail** — 7 event categories and 13 action types; every guardrail block, PII detection, and policy decision is logged.
- **PII-safe logging** — audit logs capture event metadata without exposing farmer personal data.
- **CloudWatch custom metrics** — tool execution latency, cache hit rates, and guardrail trigger counts tracked as custom metrics.
- **Bedrock guardrail audit** — every guardrail intervention (topic gate, toxicity block, grounding failure) logged with the triggering input.

---

## Production Roadmap — Future Plans

Our prototype is **production-upgradeable by configuration, not rewrite**. Given the modular architecture, feature flags, and IaC foundation, we can deliver all production features within **~1–2 months**:

| Phase | Timeline | Key Upgrades |
|-------|----------|-------------|
| **Phase 1** | Week 1 | SMS OTP (TRAI DLT registration + `ENABLE_DEMO_OTP=false`), custom domain (Route 53 + ACM), CI/CD pipeline (CodePipeline), CloudWatch alarms + alerting |
| **Phase 2** | Week 2 | WhatsApp Business API channel, full Indic TTS (Polly/AI4Bharat), offline-first PWA, push notifications (weather/pest alerts), multi-region DR |
| **Phase 3** | Weeks 3–4 | **KB Auto-Update Pipeline** (EventBridge → Lambda scrapes ICAR/KVK portals → S3 → Bedrock KB re-sync), KB expansion (500+ docs), **native mobile app (Android + iOS)**, fine-tuned Nova Pro, per-farmer personalisation, QuickSight analytics |
| **Future** | Post-launch | IoT soil/weather sensors (AWS IoT Core), marketplace (mandi prices), Aadhaar e-KYC + PM-KISAN API, IVR/USSD (Amazon Connect), multilingual fine-tuning, scale to 10M+ farmers |

```
PROTOTYPE (Today)         →  PRODUCTION (Weeks 1–2)         →  SCALE (Weeks 3–4 + Post-Launch)
On-screen OTP             →  SNS SMS OTP                  →  Aadhaar e-KYC
gTTS (13 languages)       →  Polly + Indic TTS            →  Regional fine-tuned TTS
React SPA                 →  PWA (offline)                →  Native Android + iOS App
Nova Pro + RAG            →  Fine-tuned Nova Pro          →  Multilingual fine-tuned
Manual KB updates         →  Automated KB pipeline        →  Auto-ingest from govt APIs
Browser-only              →  + WhatsApp channel           →  + IVR + USSD + mobile apps
Single region (Mumbai)    →  Multi-region DR              →  Global CDN + edge compute
```

> **Architecture designed for evolution:** Feature flags, environment-driven config, single-responsibility Lambdas, and Infrastructure-as-Code mean each phase is an *incremental addition* — never a rewrite.

---

## Team

| Name | Role | Contribution |
|---|---|---|
| **Sanjay M** | Team Lead + Frontend | React UI, all pages, voice components, i18n, CSS, CloudFront deployment |
| **Manoj RS** | Backend + Infrastructure | 7 Lambda functions, SAM template, Bedrock integration, API Gateway, Polly/Translate |
| **Abhishek Reddy** | Data + Knowledge Base | Crop data curation, government schemes, Bedrock KB documents, S3 upload |
| **Jeevidha R** | QA + Documentation | End-to-end testing, documentation, demo video, project submission |

---

## Submission Checklist

| Deliverable | Status | Link |
|---|---|---|
| **Project PPT** | 📋 Ready | *Uploaded to dashboard* |
| **GitHub Repository** | ✅ Public | [github.com/Sanjay060901/smart-rural-ai-advisor](https://github.com/Sanjay060901/smart-rural-ai-advisor) |
| **Working Prototype** | ✅ Live | [https://d80ytlzsrax1n.cloudfront.net](https://d80ytlzsrax1n.cloudfront.net) |
| **Demo Video** | 🎬 Ready | [Watch on YouTube](https://youtu.be/PYYTB6gH1rI?si=38Iub-dKBXA8XEz2) |
| **Project Summary** | ✅ Complete | See [docs/PROJECT_SUMMARY.md](docs/PROJECT_SUMMARY.md) |

---

<p align="center">
  Built with ❤️ for Bharat's farmers — <strong>AWS AI for Bharat Hackathon 2026</strong>
</p>
