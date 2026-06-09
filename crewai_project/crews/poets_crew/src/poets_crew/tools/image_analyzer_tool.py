"""Custom image analysis tool using OpenRouter vision models directly."""

import base64
from pathlib import Path

from crewai.tools import BaseTool
from openai import OpenAI
from pydantic import BaseModel, Field, field_validator

INDISTINCT_CONTENT_MESSAGE = "indistinct content"

IMAGE_ANALYSIS_PROMPT = """
You are a strict image gatekeeper for poem generation.

ACCEPT ONLY images that clearly show story-bearing visual content, such as:
- people in scenes of life
- portraits with recognizable expression or context
- animals/pets in recognizable settings
- architecture or landmarks with clear structure
- distinctive nature scenes (mountains, sea, forests, storms, fields)
- meaningful actions or moments that suggest a narrative

REJECT images if they are not poetically useful due to being vague or non-narrative, including:
- abstract wallpapers or decorative patterns
- random color mixes/gradients/textures
- screenshots, UI captures, meme templates, or banners
- mostly text, logos, posters, or a single text line
- blurred, indistinct, very low-detail, or barely recognizable content

Output rules:
1) If REJECTED, respond with exactly: indistinct content
2) If ACCEPTED, provide a concise visual analysis in 4-8 sentences with concrete details only.
3) Never add preambles, labels, bullet points, or markdown.
""".strip()


class ImageAnalyzerInput(BaseModel):
    """Input schema for the image analyzer tool."""

    image_path: str = Field(..., description="The local file path to the image to analyze.")

    @field_validator("image_path")
    @classmethod
    def validate_image_path(cls, v: str) -> str:
        path = Path(v)
        if not path.exists():
            raise ValueError(f"Image file does not exist: {v}")
        valid_extensions = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
        if path.suffix.lower() not in valid_extensions:
            raise ValueError(f"Unsupported image format. Supported: {valid_extensions}")
        return v


class ImageAnalyzerTool(BaseTool):
    """Analyzes images using a vision model via OpenRouter."""

    name: str = "Image Analyzer Tool"
    description: str = "Analyzes an image and returns a detailed description of its contents."
    args_schema: type[BaseModel] = ImageAnalyzerInput

    api_key: str = Field(..., description="OpenRouter API key")
    model: str = Field(default="google/gemma-3-27b-it:free", description="Vision model to use")
    base_url: str = Field(default="https://openrouter.ai/api/v1", description="OpenRouter base URL")

    def _run(self, **kwargs) -> str:
        image_path = kwargs.get("image_path")
        if not image_path:
            return "Error: image_path is required."

        try:
            with open(image_path, "rb") as f:
                base64_image = base64.b64encode(f.read()).decode()

            image_data_url = f"data:image/jpeg;base64,{base64_image}"

            client = OpenAI(base_url=self.base_url, api_key=self.api_key)
            completion = client.chat.completions.create(
                extra_headers={
                    "HTTP-Referer": "PoetsCrew",
                    "X-Title": "PoetsCrew",
                },
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": IMAGE_ANALYSIS_PROMPT,
                            },
                            {
                                "type": "image_url",
                                "image_url": {"url": image_data_url},
                            },
                        ],
                    }
                ],
            )

            response_content = completion.choices[0].message.content or ""
            if isinstance(response_content, list):
                response_content = "".join(str(part) for part in response_content)

            normalized = str(response_content).strip().lower()
            first_line_normalized = normalized.split("\n", maxsplit=1)[0].strip()
            if first_line_normalized.startswith(INDISTINCT_CONTENT_MESSAGE):
                return INDISTINCT_CONTENT_MESSAGE

            return str(response_content).strip()

        except Exception as e:
            return f"Error analyzing image: {e!s}"
