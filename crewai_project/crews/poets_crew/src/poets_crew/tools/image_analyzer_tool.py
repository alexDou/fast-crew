"""Custom image analysis tool using OpenRouter vision models directly."""
import base64
from pathlib import Path

from crewai.tools import BaseTool
from openai import OpenAI
from pydantic import BaseModel, Field, field_validator


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
    model: str = Field(default="openrouter/google/gemma-3-27b-it:free", description="Vision model to use")
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
                                "text": "Analyse in detail what you see in this image. Output only concise excerpt of essentials. Summerize to no more than 10 sentences."
                            },
                            {
                                "type": "image_url",
                                "image_url": {"url": image_data_url},
                            },
                        ],
                    }
                ],
            )

            return completion.choices[0].message.content

        except Exception as e:
            return f"Error analyzing image: {e!s}"
