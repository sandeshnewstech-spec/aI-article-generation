import requests
from typing import List, Dict
from app.core.config import settings
from app.models.data import ScrapedArticle
from app.services.ai_rules_loader import inject_system_prompt


class AIService:

    def __init__(self):
        self.provider = settings.AI_PROVIDER

    def build_style_prompt(
        self, articles: List[ScrapedArticle], topic: str, style: str
    ) -> str:
        combined_text = "\n\n".join(
            [
                f"SOURCE: {a.source}\nTITLE: {a.title}\nCONTENT: {a.body}"
                for a in articles
            ]
        )

        style_instructions = {
            "formal": """
Write in a FORMAL, PROFESSIONAL journalistic style:
- Use formal language and third-person perspective
- Maintain objective, neutral tone
- Structure with clear sections and formal transitions
- Suitable for traditional news publications
""",
            "conversational": """
Write in a CONVERSATIONAL, ENGAGING style:
- Use accessible, everyday language
- Include rhetorical questions where appropriate
- Make it feel like a friendly explanation
- Suitable for social media or blog posts
""",
            "analytical": """
Write in an ANALYTICAL, IN-DEPTH style:
- Provide detailed analysis and context
- Explore implications and connections
- Use data and facts to support points
- Suitable for feature articles or investigative pieces
""",
        }

        task_prompt = f"""
You are an expert Gujarati journalist.
You fully understand Gujarati, Hindi, and English.

TOPIC: {topic}

TASK: Write a comprehensive news report in GUJARATI synthesizing information from multiple sources.

STYLE: {style_instructions.get(style, style_instructions["formal"])}

RULES:
1. Output ONLY in Gujarati.
2. Synthesize viewpoints from all verified sources.
3. If sources conflict, state the different reports neutrally.
4. Create a well-structured article with a compelling headline and clear paragraphs.
5. Focus ONLY on information RELEVANT TO THE TOPIC. Ignore unrelated content.
6. Start with a compelling headline in Gujarati.
7. Do NOT list sources explicitly unless necessary for attribution.

SOURCES AND CONTENT:
{combined_text}
"""
        # Inject the SANDESH editorial framework as system context
        return inject_system_prompt(task_prompt)

    async def generate_content(self, prompt: str) -> str:
        import asyncio

        result = ""
        if self.provider == "gemini":
            result = await asyncio.to_thread(self._generate_gemini, prompt)
        elif self.provider == "openrouter":
            result = await asyncio.to_thread(self._generate_openrouter, prompt)
        else:
            result = await asyncio.to_thread(self._generate_ollama, prompt)
        
        print(f"--- AI RESPONSE ({self.provider}) ---\n{result[:1000]}{'...' if len(result) > 1000 else ''}\n--- END RESPONSE ---")
        return result

    def _generate_ollama(self, prompt: str) -> str:
        payload = {
            "model": settings.OLLAMA_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "temperature": 0.7,
        }
        try:
            resp = requests.post(
                "http://localhost:11434/api/chat", json=payload, timeout=120
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("message", {}).get("content", "")
        except Exception as e:
            print(f"Ollama Error: {e}")
            return "Error generating content with Ollama."

    def _generate_gemini(self, prompt: str) -> str:
        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=settings.GEMINI_API_KEY)
            response = client.models.generate_content(
                model=settings.GEMINI_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.7,
                ),
            )
            return response.text.strip()
        except Exception as e:
            print(f"Gemini Error: {e}")
            return f"Error generating content with Gemini: {str(e)}"

    def _generate_openrouter(self, prompt: str) -> str:
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost:8000", # Optional but good practice
            "X-Title": "AI Newsroom Pro" # Optional
        }
        payload = {
            "model": settings.OPENROUTER_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7
        }
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=120)
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"].strip()
        except Exception as e:
            print(f"OpenRouter Error: {e}")
            return f"Error generating content with OpenRouter: {str(e)}"
