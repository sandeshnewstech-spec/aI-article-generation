import os
from pydantic import BaseConfig
from dotenv import load_dotenv

load_dotenv()

class Settings:
    PROJECT_NAME: str = "News Generator"
    AI_PROVIDER: str = os.getenv("AI_PROVIDER", "ollama").lower()
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3.1")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")

settings = Settings()
