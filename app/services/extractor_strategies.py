"""Extractor strategy implementations for LLM backends."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel


class BaseExtractor(ABC):
    """Strategy interface for extraction backends."""

    @abstractmethod
    def extract(
        self,
        *,
        messages: list[dict[str, str]],
        response_model: type[BaseModel],
        model: str,
        temperature: float,
    ) -> BaseModel:
        """Run extraction and return an instance of response_model."""


class OllamaInstructorExtractor(BaseExtractor):
    """Ollama extractor using instructor constrained decoding."""

    def __init__(self, *, base_url: str, api_key: str) -> None:
        self.base_url = base_url
        self.api_key = api_key

    def extract(
        self,
        *,
        messages: list[dict[str, str]],
        response_model: type[BaseModel],
        model: str,
        temperature: float,
    ) -> BaseModel:
        import instructor
        from openai import OpenAI

        base_url = self.base_url.rstrip("/")
        if not base_url.endswith("/v1"):
            base_url = f"{base_url}/v1"

        client = instructor.from_openai(
            OpenAI(base_url=base_url, api_key=self.api_key),
            mode=instructor.Mode.JSON,
        )

        result = client.chat.completions.create(
            model=model,
            temperature=temperature,
            response_model=response_model,
            max_retries=0,
            messages=messages,
        )

        if isinstance(result, response_model):
            return result
        return response_model.model_validate(result)


class OpenAIExtractor(BaseExtractor):
    """OpenAI extractor using JSON schema response format."""

    def __init__(self, *, api_key: str, base_url: str | None = None) -> None:
        self.api_key = api_key
        self.base_url = base_url

    def extract(
        self,
        *,
        messages: list[dict[str, str]],
        response_model: type[BaseModel],
        model: str,
        temperature: float,
    ) -> BaseModel:
        from openai import OpenAI

        client_kwargs: dict[str, Any] = {"api_key": self.api_key}
        if self.base_url:
            client_kwargs["base_url"] = self.base_url

        client = OpenAI(**client_kwargs)
        schema = response_model.model_json_schema()

        response = client.chat.completions.create(
            model=model,
            temperature=temperature,
            messages=messages,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": response_model.__name__,
                    "schema": schema,
                    "strict": True,
                },
            },
        )

        content = response.choices[0].message.content or "{}"
        return response_model.model_validate(json.loads(content))


class GeminiExtractor(BaseExtractor):
    """Gemini extractor using JSON-schema constrained response."""

    def __init__(self, *, api_key: str) -> None:
        self.api_key = api_key

    def extract(
        self,
        *,
        messages: list[dict[str, str]],
        response_model: type[BaseModel],
        model: str,
        temperature: float,
    ) -> BaseModel:
        from google import genai
        from google.genai import types

        user_content = "\n\n".join(m["content"] for m in messages if m.get("role") == "user")
        system_content = "\n\n".join(m["content"] for m in messages if m.get("role") == "system")

        client = genai.Client(api_key=self.api_key)
        response = client.models.generate_content(
            model=model,
            contents=[user_content],
            config=types.GenerateContentConfig(
                system_instruction=system_content,
                temperature=temperature,
                response_mime_type="application/json",
            ),
        )

        text = (response.text or "{}").strip()
        if text.startswith("```"):
            lines = text.splitlines()
            lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines)

        return response_model.model_validate(json.loads(text))
