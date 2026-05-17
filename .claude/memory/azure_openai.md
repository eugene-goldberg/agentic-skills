---
name: azure-openai
description: "User's Azure OpenAI resource — name, RG, deployments, env file routing"
metadata: 
  node_type: memory
  type: reference
  originSessionId: 2b184b19-1809-4a2e-bad8-ec19ea9ee94c
---

User has Azure OpenAI through their employer.

**Resource:** `AIF-EUS2-INTPLATFORMSVC-DEV-001` in resource group `RG-EUS-INTPLATFORMSVC-DEV-002`, region `eastus2`.

**Endpoint:** `https://aif-eus2-intplatformsvc-dev-001.cognitiveservices.azure.com/`

**Deployments confirmed working (as of 2026-05-17):**
- `gpt-5.4` (chat, GlobalStandard 1000 capacity)
- `gpt-5.4-mini`, `gpt-5.4-nano` (variants)
- `gpt-5.2-chat`
- `text-embedding-ada-002` (legacy 1536-dim)
- `text-embedding-3-large` (3072-dim, deployed via `az cognitiveservices account deployment create` on 2026-05-17)
- Cohere rerank, Llama-4-Maverick, DeepSeek-V4-Flash, gpt-4o

**Env files in the repo (gitignored):**
- `.env.gpt54`  — chat=Azure gpt-5.4, embeddings=Azure text-embedding-3-large
- `.env.kimi`   — chat=kimi-k2.6 (Moonshot), embeddings=Azure text-embedding-3-large
- `.env.openai` — direct OpenAI fallback (less preferred)

**The webapp auto-loads the first .env it finds:** `webapp/.env` → `.env.kimi` → `.env.gpt54`. See `webapp/backend/app/main.py:_autoload_env`.

**Azure CLI is logged in** — `az account show` works. User can deploy new models via CLI if needed.

**How to apply:** when retrieval or scoring requires embeddings, route via Azure text-embedding-3-large (3072 dim). When chat is the focus, gpt-5.4 is the default; kimi-k2.6 is an alternate via Moonshot's OpenAI-compatible endpoint. Never use the raw `text-embedding-ada-002` deployment unless explicitly requested.
