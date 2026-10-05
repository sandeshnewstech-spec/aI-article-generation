import requests
from typing import List, Dict, Tuple
from app.core.config import settings
from app.models.data import ScrapedArticle
from app.services.ai_rules_loader import inject_system_prompt


class AIService:

    def __init__(self):
        self.provider = settings.AI_PROVIDER
        from openai import AsyncOpenAI
        self._async_client = None
        if settings.OPENROUTER_API_KEY:
            self._async_client = AsyncOpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=settings.OPENROUTER_API_KEY,
            )

    def build_style_prompt(
        self, articles: List[ScrapedArticle], topic: str, style: str
    ) -> Tuple[str, str]:
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

    async def generate_content(self, system_prompt: str, user_prompt: str) -> str:
        try:
            if not self._async_client:
                return "Error: OpenRouter API key not configured."
                
            response = await self._async_client.chat.completions.create(
                model="google/gemini-3.8-flash",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.2, # Based on the user configuration
            )
            result = response.choices[0].message.content.strip()
            print(f"--- AI RESPONSE (openrouter) ---\n{result[:1000]}{'...' if len(result) > 1000 else ''}\n--- END RESPONSE ---")
            return result
        except Exception as e:
            print(f"OpenRouter Error: {e}")
            return f"Error generating content with OpenRouter: {str(e)}"
