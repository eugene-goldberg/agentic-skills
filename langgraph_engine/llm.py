"""LLM client factory.

Dispatches on `cfg.provider`:
- `azure_openai` -> langchain_openai.AzureChatOpenAI
- `anthropic`    -> langchain_anthropic.ChatAnthropic
- `huggingface`  -> langchain_openai.ChatOpenAI pointed at the HF router

Tools are attached per-node via `.bind_tools(...)`.
"""

from __future__ import annotations

import json
import os

from .config import LLMConfig


def build_llm(cfg: LLMConfig, *, temperature: float = 0.2):
    override = os.getenv("LLM_TEMPERATURE")
    if override is not None and override.strip() != "":
        try:
            temperature = float(override)
        except ValueError:
            pass

    extra_body = None
    raw_extra = os.getenv("OPENAI_EXTRA_BODY")
    if raw_extra:
        try:
            extra_body = json.loads(raw_extra)
        except ValueError:
            pass

    if cfg.provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        # Newer Claude models (opus-4.7) reject the `temperature` parameter.
        return ChatAnthropic(
            api_key=cfg.api_key,
            model=cfg.model,
            timeout=300,
            max_tokens=8192,
        )

    if cfg.provider == "huggingface":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            api_key=cfg.api_key,
            model=cfg.model,
            base_url=cfg.endpoint,
            temperature=temperature,
            timeout=300,
        )

    if cfg.provider == "openai":
        from langchain_openai import ChatOpenAI

        kwargs = {
            "api_key": cfg.api_key,
            "model": cfg.model,
            "temperature": temperature,
            "timeout": 600,
            "max_retries": 2,
        }
        if cfg.endpoint:
            kwargs["base_url"] = cfg.endpoint
        if extra_body:
            kwargs["extra_body"] = extra_body
        return ChatOpenAI(**kwargs)

    from langchain_openai import AzureChatOpenAI

    return AzureChatOpenAI(
        azure_endpoint=cfg.endpoint,
        api_key=cfg.api_key,
        api_version=cfg.api_version,
        azure_deployment=cfg.model,
        temperature=temperature,
        timeout=300,
    )
