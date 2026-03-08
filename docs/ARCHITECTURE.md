# Architecture — Smart Rural AI Advisor

> **Stack:** smart-rural-ai | **Region:** ap-south-1 (Mumbai) | **Runtime:** Python 3.13, React 18 | **IaC:** AWS SAM (CloudFormation)

---

## 1. High-Level System Diagram

```
 ┌───────────────────────────┐
 │  Farmer (Mobile / Desktop │
 │  Browser — 13 languages)  │
 └────────────┬──────────────┘
              │  HTTPS
              ▼
 ┌───────────────────────────┐       ┌─────────────────────────────────────┐
 │  React 18 + Vite SPA      │       │  Amazon CloudFront (CDN)            │
 │  Voice I/O, i18n, Maps    │◄─────►│  S3 Static Hosting (frontend dist/) │
 └────────────┬──────────────┘       └─────────────────────────────────────┘
              │  REST API calls
              ▼
 ┌───────────────────────────┐
 │  Amazon API Gateway       │  ── 11 routes, CORS-enabled, regional
 └────────────┬──────────────┘
              │
              ▼
 ┌──────────────────────────────────────────────────────────────────────────────┐
 │                     AWS Lambda Functions (Python 3.13)                       │
 │                                                                              │
 │  ┌─────────────────────────────────────────────────────────────────────┐     │
 │  │  AGENT ORCHESTRATOR — The Brain                                     │     │
 │  │                                                                     │     │
 │  │  1. Amazon Translate   → detect language, translate to English      │     │
 │  │  2. Amazon Bedrock     → Nova Pro: intent + tool-calling + reason   │     │
 │  │  3. Tool Execution     → invoke child Lambdas for live data         │     │
 │  │  4. Post-Processing    → fact-check, validate, translate back       │     │
 │  │  5. Amazon Polly/gTTS  → generate audio in farmer's language        │     │
 │  │  6. DynamoDB           → persist chat history + session context     │     │
 │  │  7. Rate Limiter       → DynamoDB sliding-window (15/min, 500/day)  │     │
 │  └────────────┬────────────────────────────────────────────────────────┘     │
 │               │ invokes (parallel, with timeout)                             │
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
 │  + Transcribe Speech Lambda  (Amazon Transcribe — voice fallback)            │
 │  + Health Check Lambda       (inline — stack health)                         │
 └──────────────────────────────────────────────────────────────────────────────┘
              │
              ▼
 ┌──────────────────────────────────────────────────────────────────────────────┐
 │  Supporting AWS Services                                                     │
 │                                                                              │
 │  Amazon DynamoDB ─── farmer_profiles, chat_sessions, otp_codes, rate_limits  │
 │  Amazon S3       ─── frontend assets, TTS audio, KB source documents         │
 │  Amazon Cognito  ─── phone + PIN authentication (JWT tokens)                 │
 │  Amazon CloudWatch── logs, metrics, alarms for all Lambdas                   │
 │  AWS IAM         ─── least-privilege policies per Lambda function            │
 │  AWS Secrets Mgr ─── secure storage for OpenWeather API key                  │
 └──────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. AWS Services Inventory

| AWS Service | Role in System | Why This Service |
|---|---|---|
| **Amazon Bedrock (Nova Pro + Nova 2 Lite)** | Nova Pro: chat reasoning, tool-calling, crop image diagnosis. Nova 2 Lite: lightweight tasks (text localization, simple queries). Bidirectional fallback — each model falls back to the other on throttle/timeout | Managed GenAI — no model hosting, pay-per-use, native tool-use support |
| **Bedrock Knowledge Base** | RAG retrieval over curated crop/farming documents | Grounded answers from verified data, reduces hallucination |
| **Bedrock Guardrails** | Content filtering, topic gating, grounding checks | Enterprise-grade safety for farmer-facing AI |
| **AWS Lambda** | 7 serverless functions + 1 inline health check | Zero idle cost, auto-scaling, Python 3.13 |
| **Amazon API Gateway** | REST API with 11 routes, CORS, regional deployment | Managed API layer with throttling and monitoring |
| **Amazon DynamoDB** | Profiles, chat sessions, rate-limit counters, OTP codes | Serverless NoSQL, millisecond latency, free-tier friendly |
| **Amazon S3** | Frontend hosting, TTS audio files, KB documents | Durable object storage integrated with CloudFront |
| **Amazon CloudFront** | CDN for React SPA — low-latency delivery across India | Edge locations in Mumbai, Chennai, Bangalore, Delhi |
| **Amazon Translate** | Auto-detect + translate between English and 13 Indian languages | Native Indian language support with auto-detection |
| **Amazon Polly** | Neural TTS for Hindi + Indian English (Kajal — bilingual neural voice) | High-quality neural voices |
| **gTTS** | TTS for all 13 languages (Polly fallback) | Free, covers all Indian languages Polly doesn't |
| **Amazon Transcribe** | Speech-to-text fallback for Firefox/Safari (12 Indian languages) | Covers browsers where Web Speech API is unavailable |
| **Amazon Cognito** | Farmer authentication via phone + PIN | Managed user pool with JWT token issuance; OTP displayed on-screen in prototype (see [Tradeoffs](#15-design-tradeoffs--rationale)) |
| **AWS IAM** | Least-privilege policies per Lambda | Security best practice — each function accesses only what it needs |
| **AWS Secrets Manager** | Secure storage of OpenWeather API key | No API keys in code or environment variables |
| **Amazon CloudWatch** | Logging, metrics, alarms for all functions | Operational visibility and debugging |

---

## 3. Lambda Functions — Detail

| # | Function | CodeUri | Memory | Timeout | Endpoints | External Deps |
|---|----------|---------|--------|---------|-----------|---------------|
| 1 | **Agent Orchestrator** | `backend/lambdas/agent_orchestrator/` | 256 MB | 30 s | `POST /chat`, `POST /voice` | gTTS ≥ 2.5.0 |
| 2 | **Crop Advisory** | `backend/lambdas/crop_advisory/` | 256 MB | 30 s | *(invoked by orchestrator)* | — |
| 3 | **Weather Lookup** | `backend/lambdas/weather_lookup/` | 256 MB | 30 s | `GET /weather/{location}` | requests 2.31.0 |
| 4 | **Govt Schemes** | `backend/lambdas/govt_schemes/` | 256 MB | 30 s | `GET /schemes` | — |
| 5 | **Farmer Profile** | `backend/lambdas/farmer_profile/` | 256 MB | 30 s | `GET/PUT/DELETE /profile/{farmerId}`, `POST /otp/send`, `POST /otp/verify`, `POST /pin/reset` | — |
| 6 | **Image Analysis** | `backend/lambdas/image_analysis/` | **512 MB** | **60 s** | `POST /image-analyze` | — |
| 7 | **Transcribe Speech** | `backend/lambdas/transcribe_speech/` | 256 MB | **60 s** | `POST /transcribe` | — |
| 8 | **Health Check** | *(inline)* | 256 MB | 30 s | `GET /health` | — |

### IAM Policies (Least-Privilege)

| Lambda | Permissions |
|--------|-------------|
| **Agent Orchestrator** | `bedrock:InvokeModel, Converse, ConverseStream, ApplyGuardrail` · `lambda:InvokeFunction` (child Lambdas) · `dynamodb:*` on chat_sessions, farmer_profiles, rate_limits · `translate:TranslateText` · `comprehend:DetectDominantLanguage` · `polly:SynthesizeSpeech` · `s3:GetObject, PutObject` · `cloudwatch:PutMetricData` |
| **Crop Advisory** | `bedrock:RetrieveAndGenerate, Retrieve` |
| **Image Analysis** | `bedrock:InvokeModel` · `translate:TranslateText` |
| **Weather Lookup** | `secretsmanager:GetSecretValue` |
| **Farmer Profile** | `dynamodb:*` on farmer_profiles, otp_codes · `cognito-idp:AdminDeleteUser, AdminSetUserPassword` · `cloudwatch:GetMetricStatistics` |
| **Transcribe Speech** | `transcribe:StartTranscriptionJob, GetTranscriptionJob` · `s3:PutObject, GetObject` |

---

## 4. DynamoDB Tables

| Table | Partition Key | Sort Key | Purpose | TTL |
|-------|--------------|----------|---------|-----|
| `farmer_profiles` | `farmer_id` | — | Farmer name, state, district, crops, soil type, land size, language | — |
| `chat_sessions` | `session_id` | `timestamp` | Chat messages, session context, farmer_id as attribute | 30 days (`ttl`) |
| `otp_codes` | `phone_number` | — | OTP code, creation/expiry timestamps | Short-lived (`ttl`) |
| `rate_limits` | `rate_key` | `window` | Hit count per time window | Auto-cleanup (`ttl_epoch`) |

---

## 5. API Gateway Routes

| Method | Path | Lambda | Description |
|--------|------|--------|-------------|
| `POST` | `/chat` | Agent Orchestrator | AI chat — text in, text + audio out |
| `POST` | `/voice` | Agent Orchestrator | Voice-optimised chat |
| `POST` | `/image-analyze` | Image Analysis | Crop photo → disease diagnosis |
| `POST` | `/transcribe` | Transcribe Speech | Audio → text (Amazon Transcribe fallback) |
| `GET` | `/weather/{location}` | Weather Lookup | Real-time weather + 5-day forecast |
| `GET` | `/schemes` | Govt Schemes | Government scheme directory |
| `GET/PUT/DELETE` | `/profile/{farmerId}` | Farmer Profile | Farmer profile CRUD |
| `POST` | `/otp/send` | Farmer Profile | Generate OTP (displayed on-screen for prototype) |
| `POST` | `/otp/verify` | Farmer Profile | Verify OTP |
| `POST` | `/pin/reset` | Farmer Profile | Reset farmer PIN |
| `GET` | `/health` | Health Check | Stack health check |

**CORS:** Origin restricted to `https://d80ytlzsrax1n.cloudfront.net` · Methods: GET, POST, OPTIONS · Headers: Content-Type, X-Amz-Date, Authorization, X-Api-Key

---

## 6. Request Flow — Chat (Detailed)

```
1. Farmer sends message (text or voice transcript) + language code
      │
      ▼
2. API Gateway → Agent Orchestrator Lambda
      │
      ▼
3. GUARDRAILS (pre-processing)
   ├── Input validation (max 2000 chars, control char removal)
   ├── PII detection & masking (Aadhaar, phone, PAN, email, IFSC)
   ├── Prompt injection detection (20+ regex patterns)
   ├── Toxicity detection (harm, sabotage, banned pesticides, self-harm)
   └── Rate limiting check (15/min, 120/hr, 500/day via DynamoDB)
      │
      ▼ (if all pass)
4. LANGUAGE PROCESSING
   ├── Amazon Translate: auto-detect farmer's language
   └── Translate message to English for Bedrock
      │
      ▼
5. BEDROCK REASONING (Amazon Nova Pro via Converse API)
   ├── System prompt: Indian agriculture expert with 35+ crops, rules, MSP data
   ├── Tool definitions: 5 tools (weather, crop, pest, schemes, profile)
   ├── Model decides: respond directly OR invoke tools
   └── If tools needed → parallel invoke child Lambdas (25s timeout each)
      │
      ▼
6. TOOL EXECUTION (parallel, thread-safe)
   ├── get_weather      → Weather Lambda → OpenWeatherMap API
   ├── get_crop_advisory → Crop Advisory Lambda → Bedrock Knowledge Base (RAG)
   ├── get_pest_alert    → Crop Advisory Lambda → KB retrieval + reasoning
   ├── search_schemes    → Govt Schemes Lambda → curated scheme data
   └── get_farmer_profile → DynamoDB direct read
      │
      ▼
7. POST-PROCESSING
   ├── Bedrock synthesises final advisory from tool results
   ├── Output guardrails: fact-check against tool data, PII removal, HTML stripping
   ├── Amazon Translate: translate response back to farmer's language
   ├── TTS generation: Polly (Hindi/English) or gTTS (11 other languages)
   └── Upload audio to S3, generate pre-signed URL
      │
      ▼
8. PERSIST & RESPOND
   ├── Save messages to DynamoDB (chat_sessions, 30-day TTL)
   └── Return JSON: { reply, reply_en, audio_url, tools_used, session_id, detected_language }
```

---

## 7. Request Flow — Image Diagnosis

```
1. Farmer uploads crop/leaf photo (JPEG/PNG/WebP/GIF, max 4 MB)
   + selects crop name, state, language
      │
      ▼
2. API Gateway → Image Analysis Lambda (512 MB, 60s timeout)
      │
      ▼
3. INPUT VALIDATION
   ├── Image size check (max 4 MB)
   ├── Format detection via magic bytes (JPEG, PNG, GIF, WebP)
   ├── Crop name / state sanitisation (max 100 chars, injection patterns)
   └── Base64 decode
      │
      ▼
4. AMAZON NOVA PRO VISION (temperature: 0.3)
   ├── System prompt: "Expert Indian agricultural scientist, 20 years experience"
   ├── Confidence rules: never guess on blurry/unclear images
   ├── Output format: disease name, severity, organic/chemical treatment, prevention, urgency
   └── Retry: up to 2 attempts with exponential backoff
      │
      ▼
5. POST-PROCESSING
   ├── PII sanitisation (Aadhaar, PAN, email removal from AI output)
   ├── HTML/script tag stripping
   └── Amazon Translate → farmer's language
      │
      ▼
6. Return structured diagnosis to frontend
```

---

## 8. Request Flow — Voice Input

### Path A: Chrome/Edge (Web Speech API — Zero Latency)

```
User clicks 🎤 → Browser Web Speech API (streaming)
  → Real-time partial transcripts shown in UI
  → Final transcript → POST /chat with text + language
```

### Path B: Firefox/Safari (Amazon Transcribe — Fallback)

```
User clicks 🎤 → MediaRecorder API records audio
  → Audio base64-encoded → POST /transcribe
  → Lambda uploads to S3 → starts Transcribe job
  → Frontend polls every 2s → transcript returned
  → POST /chat with transcript + language
```

---

## 9. Bedrock AI Architecture

### Foundation Models

| Model | ID | Role | When Used |
|-------|-----|------|-----------|
| **Amazon Nova Pro** | `apac.amazon.nova-pro-v1:0` | Primary reasoning, tool-calling, image diagnosis | Default for all requests |
| **Amazon Nova 2 Lite** | `global.amazon.nova-2-lite-v1:0` | Lightweight tasks + bidirectional fallback | Used directly for simpler operations (text localization, advisory formatting). Bidirectional fallback — Nova Pro falls back to Nova 2 Lite and vice versa on throttle/timeout, ensuring the farmer always gets a response |

### Tool-Use (Function Calling)

The orchestrator passes 5 tool schemas to Bedrock. Nova Pro autonomously decides which tools to call based on the farmer's query:

| Tool | Parameters | Data Source |
|------|-----------|-------------|
| `get_weather` | location, days (1–7) | OpenWeatherMap API via Weather Lambda |
| `get_crop_advisory` | location, crop, season, soil_type, query_type | Bedrock KB (RAG) via Crop Advisory Lambda |
| `get_pest_alert` | query, crop, symptoms, location, season | Bedrock KB + reasoning |
| `search_schemes` | query, state, category | Curated scheme data via Govt Schemes Lambda |
| `get_farmer_profile` | farmer_id | DynamoDB direct |

### Knowledge Base (RAG)

- **Corpus:** Curated Indian agricultural documents — crop calendars, soil maps, pest guides, scheme explainers
- **Retrieval config:** Top-K = 8 initial results, max 5 selected chunks, min score threshold = 0.35
- **Quality gate:** If < 2 chunks score above threshold → automatic query rewrite → retry
- **Freshness check:** Flags content older than 1 year for time-sensitive queries (MSP, prices, deadlines)
- **Injection protection:** Regex patterns block SQL injection, prompt injection, and command injection in KB queries

### Bedrock Guardrails (Optional Layer)

- **Topic gating:** Blocks non-agricultural queries
- **Grounding checks:** Ensures responses are supported by retrieved data
- **Content filtering:** Prevents harmful or irrelevant content generation

---

## 10. Security Architecture

### Defence in Depth — 7 Layers

| Layer | Mechanism | Detail |
|-------|-----------|--------|
| **1. Input Validation** | Length + format checks | Max 2000 chars, control char removal, image size ≤ 4 MB |
| **2. PII Detection & Masking** | Regex pattern matching | Aadhaar (12-digit), phone (10-digit), PAN, bank account, email, IFSC — masked in logs and responses |
| **3. Injection Prevention** | 20+ regex patterns | Prompt injection, SQL injection, command injection, role hijack, prompt extraction, data exfiltration |
| **4. Toxicity Detection** | Keyword + pattern matching | Harm to people, crop sabotage, banned pesticides (endosulfan, monocrotophos, etc.), self-harm (→ crisis helpline), hate speech |
| **5. Rate Limiting** | DynamoDB sliding-window counters | 15 req/min, 120 req/hr, 500 req/day per farmer — atomic increments, TTL auto-cleanup |
| **6. Output Guardrails** | Post-response validation | Fact-check AI response against tool data, PII removal from output, HTML/script stripping, max 8000 chars |
| **7. Bedrock Guardrails** | AWS-native safeguards | Optional topic gating, grounding checks, content filtering |

### IAM — Least-Privilege

Every Lambda function has a dedicated IAM role with only the permissions it needs. No function has wildcard access to any service. Cross-function invocation is restricted to the `smart-rural-ai-*` naming prefix.

### CORS — Strict Origin

All API Gateway responses restrict `Access-Control-Allow-Origin` to the production CloudFront domain only.

---

## 11. Reliability & Performance

| Feature | Implementation |
|---------|---------------|
| **Model Fallback** | Nova Pro ↔ Nova 2 Lite — bidirectional: each model automatically falls back to the other on throttle or timeout, ensuring 100% model availability |
| **Tool Timeouts** | 25s per tool execution, 29s API Gateway hard limit, 5s buffer |
| **KB Retry** | Exponential backoff on throttle — 1s → 2s → 4s, max 3 attempts |
| **TTS Failover** | Amazon Polly → gTTS fallback; exponential backoff on gTTS errors |
| **Connection Pooling** | Max 25 concurrent connections for tool invocations |
| **Session Persistence** | DynamoDB chat_sessions with 30-day TTL + localStorage caching |
| **Fast Path** | Pre-structured queries (crop-recommend, soil-analysis, farm-calendar) bypass full Bedrock converse for lower latency |
| **Async TTS** | If response time > 18s, TTS is skipped to stay within API Gateway timeout |

---

## 12. Frontend Architecture

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Framework** | React 18 + Vite | SPA with fast HMR, tree-shaking, code-splitting |
| **Routing** | React Router v6 | 11 pages, lazy-loaded |
| **State** | React Context (LanguageContext, FarmerContext) | Global language + farmer profile state |
| **Maps** | Leaflet + React-Leaflet | Interactive weather map with city quick-select |
| **Markdown** | Marked.js + DOMPurify | Render KB content securely (XSS-safe) |
| **Auth** | amazon-cognito-identity-js | Phone + PIN login via Cognito (OTP shown on-screen for prototype) |
| **Voice** | Web Speech API + Amazon Transcribe hook | Dual-path speech recognition |
| **i18n** | Custom translations.js | 500+ keys across 13 languages |
| **API Client** | Custom apiFetch.js | CORS headers, JWT auth, error handling, retries |

### Pages (11)

Dashboard · AI Chat · Weather (with Leaflet map) · Crop Doctor (image upload) · Govt Schemes · Farmer Profile · Login (OTP) · Crop Recommend · Farm Calendar · Soil Analysis · Market Prices

---

## 13. Deployment

### Infrastructure as Code

- **Template:** `infrastructure/template.yaml` (AWS SAM / CloudFormation)
- **Config:** `infrastructure/samconfig.toml` (stack: `smart-rural-ai`, region: `ap-south-1`)
- **Deploy scripts:** `deploy.sh` (Linux/Mac), `deploy_cfn.ps1` (Windows)
- **CI/CD:** `buildspec.yml` (AWS CodeBuild)

### Deploy Commands

```bash
# Linux/Mac
export OPENWEATHER_API_KEY_SECRET_ARN='arn:aws:secretsmanager:ap-south-1:...'
export BEDROCK_KB_ID='...'
bash infrastructure/deploy.sh

# Windows (PowerShell)
$env:OPENWEATHER_API_KEY_SECRET_ARN = 'arn:aws:secretsmanager:ap-south-1:...'
.\infrastructure\deploy_cfn.ps1 -BedrockKBId '...'
```

### Frontend Deployment

```bash
cd frontend && npm run build    # Builds to dist/
# Upload dist/ to S3 → served via CloudFront
```

---

## 14. Repository Structure

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

## 15. Design Tradeoffs & Rationale

Every production system involves tradeoffs. We document ours transparently to show deliberate engineering decisions, not shortcuts.

### Authentication: On-Screen OTP vs SMS/WhatsApp OTP

| Option | Why We Didn't Use It |
|--------|---------------------|
| **SMS OTP via Amazon SNS** | AWS SNS requires an **originating number** or **Sender ID** registration in India (TRAI DLT regulations). Registering a Sender ID requires a registered business entity, DLT portal approval, and template registration — a process that takes **2–4 weeks minimum**. Infeasible within hackathon timelines. Additionally, SNS SMS to India costs ~₹0.20/message with no free tier for transactional SMS. |
| **WhatsApp OTP** | Requires a **WhatsApp Business API** account, which needs Meta business verification, a dedicated phone number, and BSP (Business Solution Provider) onboarding — another **multi-week process** with commercial agreements. |
| **Our approach: On-Screen Demo OTP** | OTP is generated server-side (cryptographically random, 6-digit, 5-minute TTL, stored in DynamoDB) and returned in the API response. The frontend displays it for the user to enter — proving the full verification flow works end-to-end. Cognito still handles actual authentication (phone + PIN → JWT tokens). |

**Production path:** When deployed for real farmers, the OTP delivery switches from `demo_otp` in the response body to SNS SMS delivery — a single environment variable change (`ENABLE_DEMO_OTP=false`). The backend already has the SNS integration code path; it's gated behind a feature flag.

### TTS: gTTS vs Amazon Polly

| Decision | Rationale |
|----------|----------|
| **Polly for Hindi + English only** | Amazon Polly supports only 2 Indian languages with neural voices. We use Kajal — a bilingual neural voice covering both Hindi and Indian English. |
| **gTTS for all 13 languages** | Google Translate TTS covers all 13 Indian languages for free. In production, this would be replaced by Amazon Polly as it adds more Indian language support, or by a dedicated Indic TTS service. |
| **Dual fallback** | If gTTS fails (rate limit, network), the system falls back to Polly (Hindi/English) or returns text-only — never blocks the response. |

### Voice Input: Web Speech API vs Amazon Transcribe

| Decision | Rationale |
|----------|----------|
| **Web Speech API as primary** | Zero latency (streaming, client-side), works on Chrome/Edge (80%+ of Indian mobile users). No AWS cost. |
| **Amazon Transcribe as fallback** | Firefox/Safari don't support Web Speech API. Transcribe covers 12 Indian languages but adds 3–5s latency (upload → job → poll). |
| **Tradeoff accepted** | Slight UX inconsistency between browsers in exchange for universal voice support. |

### Model: Nova Pro vs Fine-Tuned Model

| Decision | Rationale |
|----------|----------|
| **Nova Pro (general-purpose) + RAG** | Fine-tuning requires curated training datasets, compute budget, and iteration cycles. RAG with Bedrock Knowledge Base achieves grounded, domain-specific responses without fine-tuning overhead. |
| **Nova 2 Lite for lightweight tasks + bidirectional fallback** | Nova 2 Lite is used directly for simpler operations (text localization, advisory formatting) to save cost. The two models serve as bidirectional fallbacks — Nova Pro falls back to Nova 2 Lite on throttle/timeout, and Nova 2 Lite falls back to Nova Pro. Either model can cover for the other, so the farmer always gets an answer. |

### Frontend: SPA vs Native App

| Decision | Rationale |
|----------|----------|
| **Web app (React SPA)** | No app store submission, no installation barrier, works on any smartphone browser. Indian farmers often have limited device storage — a web app avoids competing for space. |
| **Tradeoff** | No offline support, no push notifications. Acceptable for a prototype; PWA conversion is a clear production path. |

### Rate Limiting: DynamoDB vs API Gateway Throttling

| Decision | Rationale |
|----------|----------|
| **DynamoDB sliding-window counters** | Per-farmer rate limiting (not per-IP). Farmers may share devices or use the same IP via carrier NAT. DynamoDB counters track by `farmer_id`, ensuring fair usage per individual. |
| **API Gateway throttling as complement** | API Gateway throttling is per-API-key or per-stage — too coarse for per-farmer limits. We use both: API Gateway for global protection, DynamoDB for per-farmer fairness. |

---

## 16. Best Practices & Strengths

### Architectural Excellence

| Practice | Implementation |
|----------|---------------|
| **Serverless-first** | Every component is serverless (Lambda, API Gateway, DynamoDB, S3, CloudFront). Zero server management, auto-scaling, pay-per-use. Scales to zero when not in use — critical for a prototype that may see bursty traffic. |
| **Single-responsibility Lambdas** | Each Lambda has one job: orchestration, weather, crop advisory, schemes, profile, image analysis, transcription. Easy to test, deploy, and debug independently. |
| **Orchestrator pattern with tool-calling** | The Agent Orchestrator doesn't hard-code routing logic. It passes tool schemas to Bedrock, and the model decides which tools to invoke based on farmer intent. Adding a new capability = adding a tool schema — no code changes. |
| **Infrastructure as Code** | 100% of AWS resources defined in `infrastructure/template.yaml` (SAM/CloudFormation). Conditional resources and custom outputs ensure correct deployments. No manual console changes. |
| **29+ feature flags** | TTS engine, guardrail strictness, cache TTL, audit verbosity, model IDs — all environment variables. Demo → production = env var flip, not code change. |
| **Single-table DynamoDB design** | Sessions, messages, and cache entries share optimised table layouts with composite partition/sort keys and TTL-based auto-expiry. Minimises table count and provisioning overhead. |
| **Cascade session delete** | Deleting a chat session atomically removes all child messages, cache entries, and audit records. Zero orphaned data. |
| **Startup environment validation** | Lambda cold starts validate all required environment variables are present before processing any request. Missing config fails fast with a descriptive error. |

### Security & Safety (7-Layer Defence in Depth)

| Practice | Implementation |
|----------|---------------|
| **Layered security pipeline** | Input validation → PII masking → injection prevention → toxicity detection → rate limiting → output guardrails → Bedrock Guardrails. No single point of failure for security. |
| **Least-privilege IAM** | Each Lambda has a dedicated IAM role scoped to only the resources it needs. The Weather Lambda can only read from Secrets Manager; it cannot access DynamoDB or Bedrock. |
| **ReDoS protection** | Regex input lengths are capped to prevent denial-of-service via pathological regex patterns. Guards against crafted inputs that could cause exponential backtracking. |
| **Crisis helpline redirect** | Self-harm and distress detection triggers immediate display of 3 Indian helpline numbers (iCall, Vandrevala Foundation, AASRA) instead of any AI-generated response. |
| **Banned pesticide detection** | 8 specific hazardous chemicals (endosulfan, monocrotophos, etc.) are detected in queries and responses, with safer alternatives suggested automatically. |
| **System prompt leak prevention** | 15 marker patterns in AI output are checked to prevent the model from exposing internal system instructions to the user. |
| **PII never reaches logs** | All PII (Aadhaar, phone, PAN, email, bank account, IFSC) is detected and masked before CloudWatch logging. Even if logs are compromised, no farmer data is exposed. |
| **Injection prevention at every entry point** | 20+ regex patterns block prompt injection, SQL injection, and command injection — applied at the orchestrator, crop advisory, and image analysis layers independently. |
| **CORS strict origin** | API Gateway only accepts requests from the production CloudFront domain. No wildcard origins, no localhost in production. |
| **Secrets in Secrets Manager** | API keys (OpenWeather) stored in AWS Secrets Manager — never in environment variables, code, or config files. |
| **Output sanitisation** | AI responses are sanitised for HTML/script tags, PII leakage, and prompt leak patterns before delivery to the farmer. |
| **Custom DOMPurify allowlist** | All markdown/HTML rendering uses DOMPurify with a curated tag/attribute whitelist to prevent XSS — even if the AI model generates unexpected HTML. |
| **Chat title sanitisation** | User-provided session titles are sanitised to prevent stored XSS attacks. |
| **Chat idempotency** | Duplicate message submissions within a short window are detected and deduplicated to prevent double-processing. |

### AI/ML Intelligence

| Practice | Implementation |
|----------|---------------|
| **RAG over fine-tuning** | Bedrock Knowledge Base provides grounded responses from verified agricultural data. No training data curation, no compute cost, instantly updatable by adding documents to S3. |
| **3-layer hallucination prevention** | (1) RAG grounds responses in real data, (2) code-level fact-checking validates AI output against tool results, (3) Bedrock Guardrails provide grounding checks. |
| **21-rule system prompt** | Inline MSP/NPK reference data, tool-first routing policy, cautious diagnosis mandate, and multilingual output rules — all in one structured prompt. |
| **200-term AgriPolicy keyword set** | Domain gating ensures only agriculture-relevant queries reach Bedrock tools; off-topic queries are politely deflected without wasting model invocations. |
| **Greeting shortcut** | Simple greetings ("hi", "vanakkam", "namaste") skip Bedrock entirely, saving cost and latency. |
| **Multilingual intent classification** | Tamil, Hindi, and Telugu agricultural keywords detected natively without a translation round-trip, reducing latency for non-English users. |
| **Tool-first routing** | System prompt instructs the model to prefer tool invocations over generating answers from memory, ensuring all responses are grounded in live data. |
| **Tool result enrichment** | Raw tool data is post-processed with state filtering, cross-state scheme detection, and advisory augmentation before being passed to the model for synthesis. |
| **Strict soil evidence guard** | Soil recommendations require actual soil data from the farmer's profile or tool results; the model cannot fabricate soil parameters. |
| **Cautious pest diagnosis** | The system never hard-asserts a single disease from symptoms alone. It lists probable causes with confidence levels and always recommends visiting a KVK for confirmation. |
| **Quality gates on retrieval** | KB retrieval requires minimum score (0.35) and minimum good chunks (2). Low-quality retrievals trigger automatic query rewrite, not hallucinated responses. |
| **Freshness detection** | Time-sensitive queries (MSP prices, scheme deadlines) are flagged if retrieved KB content is older than 1 year. An explicit caveat is included. |

### Translation & Localization Intelligence

| Practice | Implementation |
|----------|---------------|
| **3-attempt translation strategy** | Bedrock Lite → Amazon Translate → graceful English fallback, with garbled output detection between each attempt. Maximises quality; minimises cost. |
| **Token-based markdown protection** | Markdown syntax (headers, bold, links) is replaced with placeholder tokens before translation and restored after — prevents Amazon Translate from corrupting formatting. |
| **700+ district name translations** | Pre-computed translations in 7 Indian scripts (Devanagari, Tamil, Telugu, Kannada, Malayalam, Bengali, Gujarati) for instant, accurate location rendering without API calls. |
| **Per-language Latin-script thresholds** | Detects when a translation returned too much Latin script (e.g., Tamil output still containing English words) and auto-retries with a different engine. |
| **Tamil-specific post-processing** | Handles unique Tamil Unicode rendering quirks and agricultural term translation artifacts that other languages don't encounter. |
| **Indic output normalisation** | Corrects numbered list renumbering, agricultural term translation artifacts, and script-specific rendering issues across all 13 languages. |
| **Chunked translation** | Long responses are split into chunks respecting sentence boundaries to stay within Translate API limits without breaking context. |

### System Design & Resilience

| Practice | Implementation |
|----------|---------------|
| **Graceful degradation** | Model fallback (Nova Pro ↔ Nova 2 Lite — bidirectional, each falls back to the other), TTS fallback (Polly → gTTS → text-only), voice fallback (Web Speech → Transcribe). The system always returns something useful, even when a service is degraded. |
| **Category-aware response caching** | SHA-256 hashed cache keys with domain-specific TTLs (weather = 1 h, schemes = 12 h) eliminate redundant Bedrock calls and significantly reduce cost. |
| **Parallel tool execution** | `ThreadPoolExecutor` runs up to 5 tool invocations concurrently per chat turn, reducing multi-tool query latency. |
| **Context window management** | Sliding window (500 chars × 40 messages) keeps conversations efficient without token overflow. Older messages are transparently truncated. |
| **Timeout budgeting** | API Gateway hard limit: 29s. The orchestrator allocates time budgets: 25s for tools, 18s TTS cutoff, 5s buffer. If time runs out, TTS is skipped but text response is still delivered. |
| **Dual chat persistence** | localStorage provides instant page loads; DynamoDB provides cross-device sync and durability. Both sources are reconciled on load. |
| **Session eviction** | Max 20 sessions per user; oldest auto-archived to prevent unbounded storage growth. |
| **Early user message save** | User messages are persisted to DynamoDB *before* Bedrock processing — data is never lost even if the AI call fails or times out. |
| **In-memory profile cache** | 120-second TTL cache avoids redundant DynamoDB reads for profile data within an active session. |
| **Idempotent operations** | DynamoDB atomic updates for rate limiting (`SET hit_count = if_not_exists(hit_count, 0) + 1`) prevent race conditions under concurrent requests. |
| **TTL-based cleanup** | Chat sessions (30 days), OTP codes (5 minutes), rate-limit counters (minutes/hours/days) all use DynamoDB TTL for automatic expiry. No cron jobs, no manual cleanup. |
| **Connection pooling** | The orchestrator reuses HTTP connections (max 25) for child Lambda invocations, reducing cold-start overhead on concurrent tool calls. |
| **gTTS exponential backoff + jitter** | TTS failures retry with exponential delay and random jitter to avoid thundering herd on rate-limited gTTS endpoints. |

### Frontend Engineering

| Practice | Implementation |
|----------|---------------|
| **`requestIdleCallback` prefetching** | Preloads chat history and profile data during browser idle time; zero perceived latency on page transitions. |
| **PageErrorBoundary** | Each route wrapped in an error boundary; a single component crash doesn't take down the app. Users see a friendly error message with retry. |
| **Cognito session restore** | 3-second timeout race: if Cognito token refresh hangs, the app loads anyway with cached state. Prevents auth issues from blocking the entire app. |
| **Orphan Cognito user cleanup** | Detects users who signed up but never completed profile creation and offers cleanup — prevents abandoned accounts. |
| **15+ responsive breakpoints** | Mobile-first CSS optimised for budget Android phones and small Indian-market screens (320px–1440px+). |
| **Staggered skeleton loaders** | Shimmer animations prevent layout shift while data loads. Different components animate with staggered delays for a polished feel. |
| **Auto-refresh presigned URLs** | Expired S3 audio presigned URLs are silently refreshed in the background — past audio playback never fails with 403 errors. |
| **6-field timestamp normalisation** | Handles multiple timestamp formats from DynamoDB and API to ensure consistent chronological display in chat and session lists. |
| **ResizeObserver scroll pill** | Auto-shows "scroll to bottom" indicator when new messages arrive below the viewport. No missed messages. |
| **ARIA attributes** | Chat messages, voice buttons, and navigation elements include accessibility roles and labels for screen reader support. |

### Observability & Audit

| Practice | Implementation |
|----------|---------------|
| **Structured JSON audit trail** | 7 event categories and 13 action types; every guardrail block, PII detection, tool invocation, and policy decision is logged with structured metadata for querying. |
| **PII-safe logging** | Audit logs capture event metadata (action type, category, timestamp) without exposing farmer personal data. Safe to ship to any log aggregator. |
| **CloudWatch custom metrics** | Tool execution latency, cache hit rates, and guardrail trigger counts tracked as custom metrics for operational dashboards. |
| **Bedrock guardrail audit** | Every guardrail intervention (topic gate, toxicity block, grounding failure) logged with the triggering input pattern for continuous improvement. |

---

## 17. Production Roadmap — From Prototype to Scale

Our prototype is designed to be **production-upgradeable by configuration, not rewrite**. Every tradeoff has a planned resolution. Given the modular architecture, feature flags, and IaC foundation, we can pull all production features within **~1–2 months** of focused development:

### Phase 1 — Week 1: Core Production Hardening

| Area | Upgrade | How | Impact |
|------|---------|-----|--------|
| **OTP Delivery** | SMS OTP via Amazon SNS | Complete TRAI DLT Sender ID registration, register SMS templates, flip `ENABLE_DEMO_OTP=false` | Real phone verification — zero code changes, one env var |
| **Custom Domain** | Route 53 + ACM certificate | Map a branded domain (e.g., `kisanai.in`) to CloudFront | Professional URL instead of CloudFront default domain |
| **CI/CD Pipeline** | AWS CodePipeline + CodeBuild | Connect GitHub → automatic build → SAM deploy → smoke tests | Automated deployments on every push to `main` |
| **Monitoring & Alerting** | CloudWatch Alarms + SNS notifications | Alarm on Lambda errors > 5%, latency > 10s, 4xx/5xx spikes | Proactive incident response instead of log-checking |
| **Error Tracking** | Structured error responses + dead-letter queues | SQS DLQ for failed Lambda invocations, retry policies | No silent failures — every error is captured and retryable |

### Phase 2 — Week 2: Channels, TTS & Offline

| Area | Upgrade | How | Impact |
|------|---------|-----|--------|
| **WhatsApp Channel** | WhatsApp Business API integration | Register via Meta Business Suite, BSP onboarding, build webhook handler Lambda | Reach farmers who don't use browsers — WhatsApp has 500M+ Indian users |
| **TTS — Full Indic Voices** | Replace gTTS with Amazon Polly (as voices release) or dedicated Indic TTS (AI4Bharat Vakyansh / IISc TTS) | Swap TTS provider in orchestrator config, add new voice IDs | Higher-quality, lower-latency voice output in all 13 languages |
| **Offline-First PWA** | Service Worker + IndexedDB cache | Add `manifest.json`, service worker for static assets + last 10 chat sessions | Farmers in low-connectivity areas can access cached advice offline |
| **Push Notifications** | Web Push API + SNS | Weather alerts, pest outbreak warnings, scheme deadlines pushed proactively | Shift from reactive (farmer asks) to proactive (system alerts) |
| **Multi-Region DR** | Active-passive in ap-southeast-1 (Singapore) | Route 53 failover routing, DynamoDB Global Tables, S3 cross-region replication | High availability — if Mumbai region has issues, Singapore takes over |

### Phase 3 — Weeks 3–4: KB Auto-Update, Mobile App, Analytics & Personalisation

| Area | Upgrade | How | Impact |
|------|---------|-----|--------|
| **KB Auto-Update Pipeline** | Automated Knowledge Base refresh mechanism | EventBridge scheduled rule → Lambda scrapes ICAR/KVK/state agriculture portals → validates & uploads to S3 → triggers Bedrock KB re-sync. Version-controlled with rollback capability. | KB stays current with latest MSP prices, scheme deadlines, pest alerts — no manual uploads |
| **KB Expansion** | Add 500+ verified documents | ICAR bulletins, KVK advisories, state agriculture dept circulars, MSP updates | Broader, deeper agricultural knowledge coverage |
| **Native Mobile App (Android)** | Build dedicated Android app using React Native / Capacitor | Same backend APIs, native push notifications, camera integration for Crop Doctor, GPS for auto-location, Play Store listing | App store discoverability, better UX, device features (camera, GPS, offline), reach users who prefer apps |
| **iOS App** | Extend mobile app to iOS | React Native cross-platform build → App Store listing | Complete mobile coverage for both Android and iOS users |
| **Fine-Tuned Model** | Fine-tune Nova Pro on Indian agriculture corpus | Curate 10K+ training samples from KB + expert-annotated Q&A pairs, use Bedrock fine-tuning | Better domain accuracy, reduced hallucination, lower token usage |
| **Per-Farmer Personalisation** | ML-based recommendation engine | Track query history, crop patterns, region → personalised advisories, proactive alerts | "Your wheat in Madhya Pradesh needs irrigation this week" — without the farmer asking |
| **Rate Limiting v2** | Redis (ElastiCache) + API Gateway WAF | Sub-millisecond enforcement, bot detection, abuse prevention | Production-grade traffic management at scale |
| **Analytics Dashboard** | Amazon QuickSight + Athena | Query CloudWatch logs via Athena, visualise in QuickSight | Usage patterns, popular crops, regional demand, scheme engagement metrics |

### Future Enhancements (Post-Launch)

| Area | Upgrade | How | Impact |
|------|---------|-----|--------|
| **IoT Sensor Integration** | AWS IoT Core + soil/weather sensors | Farmers install low-cost sensors → real-time soil moisture, pH, temperature feed into AI | Hyper-personalised: "Your field's soil moisture is 15% — irrigate today" |
| **Marketplace Integration** | Mandi price APIs + e-commerce links | Real-time market prices, direct buyer-seller connections, input purchase links | Complete farming lifecycle: advise → diagnose → sell → buy inputs |
| **Government API Integration** | Aadhaar e-KYC + DigiLocker + PM-KISAN API | Auto-verify identity, pull land records, check scheme eligibility automatically | One-click scheme enrolment instead of manual form-filling |
| **IVR / USSD Channel** | Toll-free number with Amazon Connect | Build voice-first IVR flow: dial → speak query → AI responds via TTS | Reach farmers with feature phones (no smartphone/internet required) |
| **Regional Language Fine-Tuning** | Multilingual fine-tuned model | Train on Hindi, Tamil, Telugu, Kannada agricultural corpus directly | Native language understanding without translation round-trip — lower latency, better accuracy |
| **Scale to 10M+ Farmers** | Multi-AZ, auto-scaling groups, CDN optimisation, database sharding | Lambda concurrency reserves, DynamoDB on-demand scaling, CloudFront price class All | Handle national-scale traffic during Kharif/Rabi season peaks |

### Knowledge Base Update Mechanism (Planned)

Keeping agricultural knowledge current is critical — MSP prices change annually, scheme deadlines shift, and new pest outbreaks emerge. Our planned KB auto-update pipeline:

```
┌──────────────────────────────────────────────────────────────────┐
│  KB Auto-Update Pipeline (EventBridge + Lambda + S3 + Bedrock)   │
│                                                                  │
│  1. EventBridge Scheduled Rule (daily/weekly cron)               │
│     │                                                            │
│     ▼                                                            │
│  2. KB Ingestion Lambda                                          │
│     ├── Scrape ICAR, KVK, state agriculture dept portals         │
│     ├── Pull latest MSP prices from govt APIs                    │
│     ├── Fetch new scheme circulars and pest advisories           │
│     └── Download updated crop calendars                          │
│     │                                                            │
│     ▼                                                            │
│  3. Validation & Deduplication                                   │
│     ├── Hash-based dedup (skip unchanged documents)              │
│     ├── Format validation (structure, language, completeness)    │
│     └── Version tagging (date, source, region)                   │
│     │                                                            │
│     ▼                                                            │
│  4. Upload to S3 (KB source bucket)                              │
│     ├── Versioned objects with metadata tags                     │
│     └── Rollback capability (restore previous version)           │
│     │                                                            │
│     ▼                                                            │
│  5. Trigger Bedrock KB Re-Sync                                   │
│     ├── StartIngestionJob API call                               │
│     └── CloudWatch alarm on ingestion failure                    │
│     │                                                            │
│     ▼                                                            │
│  6. Notification                                                 │
│     ├── SNS alert on success: "KB updated — 12 new docs"         │
│     └── SNS alert on failure: "KB ingestion failed — rollback"   │
└──────────────────────────────────────────────────────────────────┘
```

This ensures farmers always get advice based on the **latest** government data, prices, and agricultural research — without any manual intervention.

### Infrastructure Evolution Map

```
PROTOTYPE (Today)                    PRODUCTION (Weeks 1–2)                SCALE (Weeks 3–4 + Post-Launch)
─────────────────                    ──────────────────────                ──────────────────────────────
On-screen OTP          ──────►       SNS SMS OTP              ──────►     Aadhaar e-KYC
gTTS (13 languages)    ──────►       Polly + Indic TTS        ──────►     Regional fine-tuned TTS
Web Speech + Transcribe ─────►       Unified Transcribe       ──────►     On-device ASR
React SPA              ──────►       PWA (offline)            ──────►     Native Android + iOS App
Nova Pro + RAG         ──────►       Fine-tuned Nova Pro      ──────►     Multilingual fine-tuned model
CloudWatch logs        ──────►       Alarms + DLQ + dashboards ─────►     QuickSight analytics
Single region (Mumbai) ──────►       Multi-region DR          ──────►     Global CDN + edge compute
Manual KB updates      ──────►       Automated KB pipeline    ──────►     Auto-ingest from govt APIs
DynamoDB rate limits   ──────►       Redis + WAF              ──────►     ML-based abuse detection
Browser-only           ──────►       + WhatsApp channel       ──────►     + IVR + USSD + mobile apps
```

> **Key insight:** Our architecture is built for this evolution. Feature flags, environment-driven config, single-responsibility Lambdas, and Infrastructure-as-Code mean each phase is an *incremental addition*, never a rewrite. The same `template.yaml` that runs the prototype will grow to run the production system.
