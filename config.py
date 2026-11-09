"""Central configuration for NyayaSetu.

All optional integrations are controlled through environment variables.
Nothing secret is ever hard-coded. The default configuration is DEMO MODE,
which needs no API key and no paid service.
"""
from __future__ import annotations

import os
from datetime import date, datetime
from pathlib import Path

try:  # optional: load a local .env file if python-dotenv is installed
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent / ".env")
except Exception:  # pragma: no cover - dotenv is optional
    pass

APP_NAME = "NyayaSetu"
APP_TAGLINE = "From Consumer Problem to Legal Action."
APP_VERSION = "1.0.0"

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
ASSETS_DIR = BASE_DIR / "assets"
FONTS_DIR = ASSETS_DIR / "fonts"
OUTPUTS_DIR = BASE_DIR / "outputs"
RAW_OUTPUTS_DIR = OUTPUTS_DIR / "raw_outputs"
COMPLAINTS_DIR = OUTPUTS_DIR / "generated_complaints"
LEGAL_SOURCES_PATH = DATA_DIR / "legal_sources.json"

# ---------------------------------------------------------------- LLM settings
# demo | anthropic | openai_compatible
LLM_PROVIDER = os.getenv("NYAYASETU_LLM_PROVIDER", "demo").strip().lower()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
ANTHROPIC_MODEL = os.getenv("NYAYASETU_ANTHROPIC_MODEL", "claude-sonnet-5-5").strip()

# Any OpenAI-compatible chat-completions endpoint (OpenAI, Groq, Together,
# a local Ollama server, Gemini's OpenAI-compatible endpoint, etc.)
OPENAI_BASE_URL = os.getenv("NYAYASETU_OPENAI_BASE_URL", "https://api.openai.com/v1").strip()
OPENAI_API_KEY = os.getenv("NYAYASETU_OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("NYAYASETU_OPENAI_MODEL", "").strip()

# Anthropic: current models run adaptive thinking by default and max_tokens covers thinking + text,
# so a minimum budget is enforced. Effort ("low" keeps short structured calls fast and cheap) is sent as
# output_config.effort; set NYAYASETU_ANTHROPIC_EFFORT= (empty) to omit it for models that do not support it.
def _number(name: str, default, cast):
    """Read a numeric setting; an empty or malformed value falls back to the default instead of crashing the app."""
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return cast(raw)
    except ValueError:
        return default


ANTHROPIC_EFFORT = os.getenv("NYAYASETU_ANTHROPIC_EFFORT", "low").strip().lower()
ANTHROPIC_MIN_MAX_TOKENS = _number("NYAYASETU_ANTHROPIC_MIN_MAX_TOKENS", 4096, int)

# Only sent to OpenAI-compatible endpoints when explicitly set (some models reject sampling parameters).
OPENAI_TEMPERATURE = _number("NYAYASETU_OPENAI_TEMPERATURE", None, float)

LLM_TIMEOUT_SECONDS = _number("NYAYASETU_LLM_TIMEOUT", 60.0, float)

# ------------------------------------------------------------- Reproducibility
# Relative dates such as "three weeks ago" are resolved against this date.
# Leave unset in normal use (today's date is used). Tests pin it.
_REF = os.getenv("NYAYASETU_REFERENCE_DATE", "").strip()


def reference_date() -> date:
    if _REF:
        try:
            return datetime.strptime(_REF, "%Y-%m-%d").date()
        except ValueError:
            pass
    return date.today()


# ------------------------------------------------------------------- Privacy
# Case data lives only in the user's Streamlit session. Nothing is written to
# disk by the app itself; downloads are generated in memory.
PERSIST_CASES_TO_DISK = False

DISCLAIMER_EN = (
    "NyayaSetu is an AI-assisted legal information and document-preparation tool. "
    "It does not replace a qualified advocate or constitute a lawyer-client relationship. "
    "Legal outcomes depend on facts and applicable law. Verify important legal decisions "
    "with a qualified professional."
)
DISCLAIMER_HI = (
    "NyayaSetu एक AI-सहायित कानूनी जानकारी और दस्तावेज़-तैयारी उपकरण है। यह किसी योग्य "
    "अधिवक्ता का विकल्प नहीं है और इससे वकील-मुवक्किल संबंध नहीं बनता। कानूनी परिणाम तथ्यों "
    "और लागू कानून पर निर्भर करते हैं। महत्वपूर्ण कानूनी निर्णयों की पुष्टि किसी योग्य पेशेवर से करें।"
)
