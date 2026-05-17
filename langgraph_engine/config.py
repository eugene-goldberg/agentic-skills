"""Load LLM configuration from a .env file.

Supports four providers via `LLM_PROVIDER`:

- `azure_openai` (default): reads AZURE_OPENAI_* variables
- `anthropic`: reads ANTHROPIC_API_KEY and optional ANTHROPIC_MODEL
- `huggingface`: reads HF_TOKEN, HF_MODEL, optional HF_BASE_URL (OpenAI-compatible router)
- `openai`: reads OPENAI_API_KEY, OPENAI_MODEL, optional OPENAI_BASE_URL

`AzureOpenAIConfig` is kept as an alias for `LLMConfig` so existing node
imports continue to work.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


@dataclass(frozen=True)
class LLMConfig:
    provider: str  # "azure_openai" | "anthropic"
    api_key: str
    model: str  # deployment name (Azure) or model id (Anthropic)
    endpoint: Optional[str] = None  # Azure only
    api_version: Optional[str] = None  # Azure only

    @property
    def deployment(self) -> str:
        # Backward-compat accessor for code that reads cfg.deployment.
        return self.model

    @classmethod
    def from_env(cls, env_path: Path | None = None) -> "LLMConfig":
        if env_path is not None:
            load_dotenv(env_path, override=True)
        else:
            load_dotenv(override=False)

        provider = (os.getenv("LLM_PROVIDER") or "azure_openai").strip().lower()

        if provider == "anthropic":
            api_key = os.getenv("ANTHROPIC_API_KEY")
            model = os.getenv("ANTHROPIC_MODEL", "claude-opus-4-7")
            if not api_key:
                raise RuntimeError("Missing ANTHROPIC_API_KEY in env")
            return cls(provider="anthropic", api_key=api_key, model=model)

        if provider == "openai":
            api_key = os.getenv("OPENAI_API_KEY")
            model = os.getenv("OPENAI_MODEL")
            base_url = os.getenv("OPENAI_BASE_URL")  # optional
            if not api_key:
                raise RuntimeError("Missing OPENAI_API_KEY in env")
            if not model:
                raise RuntimeError("Missing OPENAI_MODEL in env (e.g., gpt-5.1, gpt-4o)")
            return cls(
                provider="openai",
                api_key=api_key,
                model=model,
                endpoint=base_url,
            )

        if provider == "huggingface":
            api_key = os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_API_KEY")
            model = os.getenv("HF_MODEL")
            base_url = os.getenv("HF_BASE_URL", "https://router.huggingface.co/v1")
            if not api_key:
                raise RuntimeError("Missing HF_TOKEN in env")
            if not model:
                raise RuntimeError("Missing HF_MODEL in env (e.g., Qwen/Qwen3-32B:together)")
            return cls(
                provider="huggingface",
                api_key=api_key,
                model=model,
                endpoint=base_url,
            )

        if provider == "azure_openai":
            required = {
                "AZURE_OPENAI_API_KEY": os.getenv("AZURE_OPENAI_API_KEY"),
                "AZURE_OPENAI_ENDPOINT": os.getenv("AZURE_OPENAI_ENDPOINT"),
                "AZURE_OPENAI_API_VERSION": os.getenv("AZURE_OPENAI_API_VERSION"),
                "AZURE_OPENAI_DEPLOYMENT_NAME": os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME"),
            }
            missing = [k for k, v in required.items() if not v]
            if missing:
                raise RuntimeError(
                    f"Missing Azure OpenAI configuration in .env: {', '.join(missing)}"
                )
            return cls(
                provider="azure_openai",
                api_key=required["AZURE_OPENAI_API_KEY"],
                model=required["AZURE_OPENAI_DEPLOYMENT_NAME"],
                endpoint=required["AZURE_OPENAI_ENDPOINT"],
                api_version=required["AZURE_OPENAI_API_VERSION"],
            )

        raise RuntimeError(f"Unknown LLM_PROVIDER: {provider!r}")


# Backward-compat alias — node modules import AzureOpenAIConfig.
AzureOpenAIConfig = LLMConfig
