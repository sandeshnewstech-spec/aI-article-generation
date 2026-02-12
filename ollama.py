import sys
import os
import json
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# =========================
# CONFIG
# =========================

PROVIDER = os.getenv("AI_PROVIDER", "ollama").lower()

# ---- Ollama ----
OLLAMA_URL = "http://localhost:11434/api/chat"
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1")

# ---- Gemini SDK ----
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3-flash-preview")


# =========================
# PROMPT BUILDER
# =========================

def build_prompt(source_text: str) -> str:
    return f"""
You are an expert Gujarati journalist.
You fully understand Gujarati, Hindi, and English.
You MUST write output strictly and only in Gujarati.

Rewrite the following article into a completely original Gujarati article.

Rules:
- Output ONLY Gujarati
- Preserve facts and meaning
- Do NOT summarize
- Do NOT quote or reference the original text
- Produce a natural, publication-ready article

ARTICLE:
\"\"\"
{source_text}
\"\"\"
"""


# =========================
# OLLAMA IMPLEMENTATION
# =========================

def rewrite_with_ollama(source_text: str) -> str:
    prompt = build_prompt(source_text)

    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "stream": True,
        "temperature": 0.7,
        "top_p": 0.9
    }

    try:
        response = requests.post(
            OLLAMA_URL,
            json=payload,
            stream=True,
            timeout=600
        )
        response.raise_for_status()
    except requests.RequestException as e:
        raise RuntimeError(f"Ollama request failed: {e}")

    output_chunks = []

    for line in response.iter_lines():
        if not line:
            continue

        try:
            decoded = line.decode("utf-8").strip()
            data = json.loads(decoded)

            if "message" in data and "content" in data["message"]:
                output_chunks.append(data["message"]["content"])
        except Exception:
            continue

    return "".join(output_chunks).strip()


# =========================
# GEMINI SDK IMPLEMENTATION
# =========================

def rewrite_with_gemini(source_text: str) -> str:
    try:
        from google import genai
    except ImportError:
        raise RuntimeError("google-genai package not installed. Run: pip install google-genai")

    try:
        client = genai.Client()  # Reads GEMINI_API_KEY from environment
    except Exception as e:
        raise RuntimeError(f"Failed to initialize Gemini client: {e}")

    prompt = build_prompt(source_text)

    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt
        )
        return response.text.strip()
    except Exception as e:
        raise RuntimeError(f"Gemini generation failed: {e}")


# =========================
# PROVIDER SWITCH
# =========================

def rewrite_article_to_gujarati(source_text: str) -> str:
    if PROVIDER == "ollama":
        print(f"Using Ollama model: {OLLAMA_MODEL}")
        return rewrite_with_ollama(source_text)

    elif PROVIDER == "gemini":
        print(f"Using Gemini model: {GEMINI_MODEL}")
        return rewrite_with_gemini(source_text)

    else:
        raise ValueError("Invalid AI_PROVIDER. Use 'ollama' or 'gemini'.")


# =========================
# ENTRY POINT
# =========================

if __name__ == "__main__":
    if not sys.stdin.isatty():
        source_article = sys.stdin.read()
    elif len(sys.argv) > 1:
        with open(sys.argv[1], "r", encoding="utf-8") as f:
            source_article = f.read()
    else:
        print("Provide article text via stdin or a file path.")
        sys.exit(1)

    try:
        rewritten_article = rewrite_article_to_gujarati(source_article)

        print("\n=== GUJARATI REWRITTEN ARTICLE ===\n")
        print(rewritten_article)

    except Exception as e:
        print("Error:", e)
        sys.exit(1)
