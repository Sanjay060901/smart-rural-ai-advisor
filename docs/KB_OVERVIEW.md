# Knowledge Base Overview — Smart Rural AI Advisor

> Amazon Bedrock Knowledge Base powers the RAG (Retrieval-Augmented Generation) pipeline that grounds crop advisory responses in verified Indian agricultural data.

---

## 1. Purpose

Farmers ask questions that require domain-specific accuracy — "What fertiliser schedule should I follow for rice in clay soil during Kharif?" A general-purpose LLM may hallucinate outdated MSP values, incorrect pesticide dosages, or unsuitable crop recommendations. The Knowledge Base ensures every crop/pest/scheme advisory is grounded in curated, verified content — not model priors.

---

## 2. What the Knowledge Base Contains

| Content Category | Description | Examples |
|------------------|-------------|----------|
| **Crop Cultivation Guides** | Season-specific cultivation practices for 35+ Indian crops | Rice (Kharif, 120–150 days, 3.5–5.0 t/ha), Wheat (Rabi, 110–140 days), Cotton (black soil, 140–180 days), Sugarcane (300–450 days) |
| **Soil & Irrigation Data** | Soil type mapping, water requirements, irrigation scheduling | Clay soil — paddy, wheat; Sandy loam — groundnut, millets; Drip vs. flood irrigation per crop |
| **Pest & Disease Reference** | Symptoms, diagnosis, organic & chemical treatments | Blast (rice), Boll rot (cotton), Aphids, Caterpillars — with product names and dosages |
| **Government Scheme Explainers** | Eligibility, benefits, application steps for 10+ schemes | PM-KISAN (₹6,000/yr), PMFBY (crop insurance), KCC (credit card), Soil Health Card, PMKSY (irrigation), eNAM, PKVY |
| **Regional Best Practices** | State-specific advisories for major farming regions | Tamil Nadu — paddy double-cropping; AP/Telangana — cotton + chilli rotation; Karnataka — ragi + groundnut |
| **MSP & Market Data** | Minimum Support Prices for major crops | Rice ₹2,300/q, Wheat ₹2,275/q, Cotton ₹7,020/q, Sugarcane ₹3,150/q, Groundnut ₹6,377/q |
| **Seasonal Calendars** | Kharif/Rabi/Zaid planting and harvesting windows | Kharif (Jun–Oct): Rice, Cotton, Maize, Groundnut · Rabi (Nov–Mar): Wheat, Mustard, Gram · Zaid (Mar–Jun): Watermelon, Cucumber |

---

## 3. How the KB is Used in the System

### Retrieval Pipeline

```
1. Farmer asks crop/pest/advisory question
      │
      ▼
2. Agent Orchestrator detects tool-calling intent
   → invokes Crop Advisory Lambda with query parameters
      │
      ▼
3. Crop Advisory Lambda calls Bedrock KB
   ├── API: bedrock-agent-runtime → RetrieveAndGenerate
   ├── Top-K retrieval: 8 initial candidates
   ├── Score threshold: ≥ 0.35 confidence
   └── Max selected chunks: 5
      │
      ▼
4. QUALITY GATE
   ├── If ≥ 2 chunks score above threshold → proceed
   └── If < 2 chunks → automatic query rewrite → retry retrieval
      │
      ▼
5. Bedrock generates grounded response using retrieved chunks
      │
      ▼
6. Response returned to orchestrator for post-processing
   (fact-check, translate, TTS)
```

### Quality Gates & Safeguards

| Gate | Threshold | Action on Failure |
|------|-----------|-------------------|
| **Minimum score** | 0.35 | Chunk discarded |
| **Minimum good chunks** | 2 | Automatic query rewrite + retry |
| **Max retrieval attempts** | 3 | Flag `insufficient_evidence` — respond with caveats |
| **Freshness check** | 1 year | Warn if time-sensitive query (MSP, prices, deadlines) references stale data |
| **Injection protection** | Regex patterns | Block SQL injection, prompt injection, command injection in KB queries |

### Retry & Resilience

- **KB throttle handling:** Exponential backoff — 1s → 2s → 4s, max 3 attempts
- **Query rewrite:** On low-quality retrieval, the system rewrites the query to a broader recall form (e.g., `"rice irrigation schedule water requirement india best practices"`)
- **Scheme redirect:** If the query is about a government scheme, the system redirects to the dedicated Govt Schemes Lambda (curated data) instead of relying on KB alone

---

## 4. KB Configuration

| Parameter | Value | Description |
|-----------|-------|-------------|
| `BEDROCK_KB_ID` | *(configured at deploy time)* | Knowledge Base identifier |
| `KB_RETRIEVAL_TOP_K` | 8 | Number of initial candidates to retrieve |
| `KB_RETRIEVAL_MAX_CHUNKS` | 5 | Maximum chunks passed to generation |
| `KB_MIN_SCORE` | 0.35 | Minimum retrieval confidence score |
| `KB_MIN_GOOD_CHUNKS` | 2 | Minimum high-quality chunks before accepting |
| `KB_RETRY_MAX_ATTEMPTS` | 3 | Max retries on throttle |
| `KB_RETRY_BASE_DELAY` | 1.0 s | Base delay for exponential backoff |
| `ENABLE_KB_QUERY_REWRITE` | true | Auto-rewrite on low retrieval quality |
| `FRESHNESS_STALE_AFTER_YEARS` | 1 | Flag content older than 1 year |
| `MAX_QUERY_LENGTH` | 500 chars | Input query length limit |
| `MAX_FIELD_LENGTH` | 200 chars | Per-field input length limit |

---

## 5. Input Security

All KB queries pass through injection protection before retrieval:

| Threat | Examples Blocked |
|--------|-----------------|
| **Prompt injection** | "ignore previous instructions", "you are now", "act as" |
| **SQL injection** | "UNION SELECT", "DROP TABLE", "DELETE FROM" |
| **Command injection** | "&&", "||", "rm -rf", "wget http" |

Fields are sanitised (crop name, location, season, soil type) — max 200 characters each, with dangerous patterns stripped.

---

## 6. Why RAG (and Not Just Prompting)

| Approach | Problem | Our Solution |
|----------|---------|-------------|
| **Pure LLM** | May hallucinate MSP values, pesticide dosages, incorrect crop seasons | RAG grounds every advisory in verified Indian agricultural data |
| **Static FAQ** | Cannot personalise to farmer's soil, location, season | KB retrieval + Bedrock reasoning combines context for personalised answers |
| **Keyword search** | Returns raw documents, not actionable advice | Bedrock generates natural-language advisory from retrieved chunks |
| **Manual curation per language** | Infeasible for 13 languages × 35+ crops | KB stores data once (English); Amazon Translate handles all 13 languages at runtime |

---

## 7. Deployment Note

The KB is deployed and managed via the Amazon Bedrock console in `ap-south-1`. Source documents are stored in an S3 bucket (`smart-rural-ai-{ACCOUNT_ID}`). The KB identifier is passed to the stack as the `BedrockKBId` parameter in `infrastructure/template.yaml`.

For submission brevity, the full raw KB source documents are not included in the repository. The live prototype demonstrates the deployed KB-backed behaviour end-to-end.
