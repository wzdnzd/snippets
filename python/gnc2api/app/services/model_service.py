from datetime import datetime, timezone
from typing import Any, Dict, Optional

import requests

from app.core.config import settings
from app.core.logger import get_model_logger

logger = get_model_logger()


class ModelService:
    def __init__(self, search_models: list, image_models: list):
        self.search_models = search_models
        self.image_models = image_models
        self.filtered_models = settings.FILTERED_MODELS

    def get_gemini_models(self, provider: str) -> Optional[Dict[str, Any]]:
        models = {
            "models": [
                {
                    "name": "models/gemini-1.5-pro-latest",
                    "version": "001",
                    "displayName": "Gemini 1.5 Pro Latest",
                    "description": "Alias that points to the most recent production (non-experimental) release of Gemini 1.5 Pro, our mid-size multimodal model that supports up to 2 million tokens.",
                    "inputTokenLimit": 2000000,
                    "outputTokenLimit": 8192,
                    "supportedGenerationMethods": ["generateContent", "countTokens"],
                    "temperature": 1,
                    "topP": 0.95,
                    "topK": 40,
                    "maxTemperature": 2,
                },
                {
                    "name": "models/gemini-1.5-pro-001",
                    "version": "001",
                    "displayName": "Gemini 1.5 Pro 001",
                    "description": "Stable version of Gemini 1.5 Pro, our mid-size multimodal model that supports up to 2 million tokens, released in May of 2024.",
                    "inputTokenLimit": 2000000,
                    "outputTokenLimit": 8192,
                    "supportedGenerationMethods": ["generateContent", "countTokens", "createCachedContent"],
                    "temperature": 1,
                    "topP": 0.95,
                    "topK": 64,
                    "maxTemperature": 2,
                },
                {
                    "name": "models/gemini-1.5-pro-002",
                    "version": "002",
                    "displayName": "Gemini 1.5 Pro 002",
                    "description": "Stable version of Gemini 1.5 Pro, our mid-size multimodal model that supports up to 2 million tokens, released in September of 2024.",
                    "inputTokenLimit": 2000000,
                    "outputTokenLimit": 8192,
                    "supportedGenerationMethods": ["generateContent", "countTokens", "createCachedContent"],
                    "temperature": 1,
                    "topP": 0.95,
                    "topK": 40,
                    "maxTemperature": 2,
                },
                {
                    "name": "models/gemini-1.5-pro",
                    "version": "001",
                    "displayName": "Gemini 1.5 Pro",
                    "description": "Stable version of Gemini 1.5 Pro, our mid-size multimodal model that supports up to 2 million tokens, released in May of 2024.",
                    "inputTokenLimit": 2000000,
                    "outputTokenLimit": 8192,
                    "supportedGenerationMethods": ["generateContent", "countTokens"],
                    "temperature": 1,
                    "topP": 0.95,
                    "topK": 40,
                    "maxTemperature": 2,
                },
                {
                    "name": "models/gemini-1.5-flash-latest",
                    "version": "001",
                    "displayName": "Gemini 1.5 Flash Latest",
                    "description": "Alias that points to the most recent production (non-experimental) release of Gemini 1.5 Flash, our fast and versatile multimodal model for scaling across diverse tasks.",
                    "inputTokenLimit": 1000000,
                    "outputTokenLimit": 8192,
                    "supportedGenerationMethods": ["generateContent", "countTokens"],
                    "temperature": 1,
                    "topP": 0.95,
                    "topK": 40,
                    "maxTemperature": 2,
                },
                {
                    "name": "models/gemini-1.5-flash-001",
                    "version": "001",
                    "displayName": "Gemini 1.5 Flash 001",
                    "description": "Stable version of Gemini 1.5 Flash, our fast and versatile multimodal model for scaling across diverse tasks, released in May of 2024.",
                    "inputTokenLimit": 1000000,
                    "outputTokenLimit": 8192,
                    "supportedGenerationMethods": ["generateContent", "countTokens", "createCachedContent"],
                    "temperature": 1,
                    "topP": 0.95,
                    "topK": 64,
                    "maxTemperature": 2,
                },
                {
                    "name": "models/gemini-1.5-flash-001-tuning",
                    "version": "001",
                    "displayName": "Gemini 1.5 Flash 001 Tuning",
                    "description": "Version of Gemini 1.5 Flash that supports tuning, our fast and versatile multimodal model for scaling across diverse tasks, released in May of 2024.",
                    "inputTokenLimit": 16384,
                    "outputTokenLimit": 8192,
                    "supportedGenerationMethods": ["generateContent", "countTokens", "createTunedModel"],
                    "temperature": 1,
                    "topP": 0.95,
                    "topK": 64,
                    "maxTemperature": 2,
                },
                {
                    "name": "models/gemini-1.5-flash",
                    "version": "001",
                    "displayName": "Gemini 1.5 Flash",
                    "description": "Alias that points to the most recent stable version of Gemini 1.5 Flash, our fast and versatile multimodal model for scaling across diverse tasks.",
                    "inputTokenLimit": 1000000,
                    "outputTokenLimit": 8192,
                    "supportedGenerationMethods": ["generateContent", "countTokens"],
                    "temperature": 1,
                    "topP": 0.95,
                    "topK": 40,
                    "maxTemperature": 2,
                },
                {
                    "name": "models/gemini-1.5-flash-002",
                    "version": "002",
                    "displayName": "Gemini 1.5 Flash 002",
                    "description": "Stable version of Gemini 1.5 Flash, our fast and versatile multimodal model for scaling across diverse tasks, released in September of 2024.",
                    "inputTokenLimit": 1000000,
                    "outputTokenLimit": 8192,
                    "supportedGenerationMethods": ["generateContent", "countTokens", "createCachedContent"],
                    "temperature": 1,
                    "topP": 0.95,
                    "topK": 40,
                    "maxTemperature": 2,
                },
                {
                    "name": "models/gemini-1.5-flash-8b",
                    "version": "001",
                    "displayName": "Gemini 1.5 Flash-8B",
                    "description": "Stable version of Gemini 1.5 Flash-8B, our smallest and most cost effective Flash model, released in October of 2024.",
                    "inputTokenLimit": 1000000,
                    "outputTokenLimit": 8192,
                    "supportedGenerationMethods": ["createCachedContent", "generateContent", "countTokens"],
                    "temperature": 1,
                    "topP": 0.95,
                    "topK": 40,
                    "maxTemperature": 2,
                },
                {
                    "name": "models/gemini-1.5-flash-8b-001",
                    "version": "001",
                    "displayName": "Gemini 1.5 Flash-8B 001",
                    "description": "Stable version of Gemini 1.5 Flash-8B, our smallest and most cost effective Flash model, released in October of 2024.",
                    "inputTokenLimit": 1000000,
                    "outputTokenLimit": 8192,
                    "supportedGenerationMethods": ["createCachedContent", "generateContent", "countTokens"],
                    "temperature": 1,
                    "topP": 0.95,
                    "topK": 40,
                    "maxTemperature": 2,
                },
                {
                    "name": "models/gemini-1.5-flash-8b-latest",
                    "version": "001",
                    "displayName": "Gemini 1.5 Flash-8B Latest",
                    "description": "Alias that points to the most recent production (non-experimental) release of Gemini 1.5 Flash-8B, our smallest and most cost effective Flash model, released in October of 2024.",
                    "inputTokenLimit": 1000000,
                    "outputTokenLimit": 8192,
                    "supportedGenerationMethods": ["createCachedContent", "generateContent", "countTokens"],
                    "temperature": 1,
                    "topP": 0.95,
                    "topK": 40,
                    "maxTemperature": 2,
                },
                {
                    "name": "models/gemini-1.5-flash-8b-exp-0827",
                    "version": "001",
                    "displayName": "Gemini 1.5 Flash 8B Experimental 0827",
                    "description": "Experimental release (August 27th, 2024) of Gemini 1.5 Flash-8B, our smallest and most cost effective Flash model. Replaced by Gemini-1.5-flash-8b-001 (stable).",
                    "inputTokenLimit": 1000000,
                    "outputTokenLimit": 8192,
                    "supportedGenerationMethods": ["generateContent", "countTokens"],
                    "temperature": 1,
                    "topP": 0.95,
                    "topK": 40,
                    "maxTemperature": 2,
                },
                {
                    "name": "models/gemini-1.5-flash-8b-exp-0924",
                    "version": "001",
                    "displayName": "Gemini 1.5 Flash 8B Experimental 0924",
                    "description": "Experimental release (September 24th, 2024) of Gemini 1.5 Flash-8B, our smallest and most cost effective Flash model. Replaced by Gemini-1.5-flash-8b-001 (stable).",
                    "inputTokenLimit": 1000000,
                    "outputTokenLimit": 8192,
                    "supportedGenerationMethods": ["generateContent", "countTokens"],
                    "temperature": 1,
                    "topP": 0.95,
                    "topK": 40,
                    "maxTemperature": 2,
                },
                {
                    "name": "models/gemini-2.0-flash-exp",
                    "version": "2.0",
                    "displayName": "Gemini 2.0 Flash Experimental",
                    "description": "Gemini 2.0 Flash Experimental",
                    "inputTokenLimit": 1048576,
                    "outputTokenLimit": 8192,
                    "supportedGenerationMethods": ["generateContent", "countTokens", "bidiGenerateContent"],
                    "temperature": 1,
                    "topP": 0.95,
                    "topK": 40,
                    "maxTemperature": 2,
                },
                {
                    "name": "models/gemini-2.0-flash",
                    "version": "2.0",
                    "displayName": "Gemini 2.0 Flash",
                    "description": "Gemini 2.0 Flash",
                    "inputTokenLimit": 1048576,
                    "outputTokenLimit": 8192,
                    "supportedGenerationMethods": ["generateContent", "countTokens"],
                    "temperature": 1,
                    "topP": 0.95,
                    "topK": 40,
                    "maxTemperature": 2,
                },
                {
                    "name": "models/gemini-2.0-flash-001",
                    "version": "2.0",
                    "displayName": "Gemini 2.0 Flash 001",
                    "description": "Stable version of Gemini 2.0 Flash, our fast and versatile multimodal model for scaling across diverse tasks, released in January of 2025.",
                    "inputTokenLimit": 1048576,
                    "outputTokenLimit": 8192,
                    "supportedGenerationMethods": ["generateContent", "countTokens"],
                    "temperature": 1,
                    "topP": 0.95,
                    "topK": 40,
                    "maxTemperature": 2,
                },
                {
                    "name": "models/gemini-2.0-flash-exp-image-generation",
                    "version": "2.0",
                    "displayName": "Gemini 2.0 Flash (Image Generation) Experimental",
                    "description": "Gemini 2.0 Flash (Image Generation) Experimental",
                    "inputTokenLimit": 1048576,
                    "outputTokenLimit": 8192,
                    "supportedGenerationMethods": ["generateContent", "countTokens", "bidiGenerateContent"],
                    "temperature": 1,
                    "topP": 0.95,
                    "topK": 40,
                    "maxTemperature": 2,
                },
                {
                    "name": "models/gemini-2.0-flash-lite-001",
                    "version": "2.0",
                    "displayName": "Gemini 2.0 Flash-Lite 001",
                    "description": "Stable version of Gemini 2.0 Flash Lite",
                    "inputTokenLimit": 1048576,
                    "outputTokenLimit": 8192,
                    "supportedGenerationMethods": ["generateContent", "countTokens"],
                    "temperature": 1,
                    "topP": 0.95,
                    "topK": 40,
                    "maxTemperature": 2,
                },
                {
                    "name": "models/gemini-2.0-flash-lite",
                    "version": "2.0",
                    "displayName": "Gemini 2.0 Flash-Lite",
                    "description": "Gemini 2.0 Flash-Lite",
                    "inputTokenLimit": 1048576,
                    "outputTokenLimit": 8192,
                    "supportedGenerationMethods": ["generateContent", "countTokens"],
                    "temperature": 1,
                    "topP": 0.95,
                    "topK": 40,
                    "maxTemperature": 2,
                },
                {
                    "name": "models/gemini-2.0-flash-lite-preview-02-05",
                    "version": "preview-02-05",
                    "displayName": "Gemini 2.0 Flash-Lite Preview 02-05",
                    "description": "Preview release (February 5th, 2025) of Gemini 2.0 Flash Lite",
                    "inputTokenLimit": 1048576,
                    "outputTokenLimit": 8192,
                    "supportedGenerationMethods": ["generateContent", "countTokens"],
                    "temperature": 1,
                    "topP": 0.95,
                    "topK": 40,
                    "maxTemperature": 2,
                },
                {
                    "name": "models/gemini-2.0-flash-lite-preview",
                    "version": "preview-02-05",
                    "displayName": "Gemini 2.0 Flash-Lite Preview",
                    "description": "Preview release (February 5th, 2025) of Gemini 2.0 Flash Lite",
                    "inputTokenLimit": 1048576,
                    "outputTokenLimit": 8192,
                    "supportedGenerationMethods": ["generateContent", "countTokens"],
                    "temperature": 1,
                    "topP": 0.95,
                    "topK": 40,
                    "maxTemperature": 2,
                },
                {
                    "name": "models/gemini-2.0-pro-exp",
                    "version": "2.0",
                    "displayName": "Gemini 2.0 Pro Experimental",
                    "description": "Experimental release (February 5th, 2025) of Gemini 2.0 Pro",
                    "inputTokenLimit": 2097152,
                    "outputTokenLimit": 8192,
                    "supportedGenerationMethods": ["generateContent", "countTokens"],
                    "temperature": 1,
                    "topP": 0.95,
                    "topK": 64,
                    "maxTemperature": 2,
                },
                {
                    "name": "models/gemini-2.0-pro-exp-02-05",
                    "version": "2.0",
                    "displayName": "Gemini 2.0 Pro Experimental 02-05",
                    "description": "Experimental release (February 5th, 2025) of Gemini 2.0 Pro",
                    "inputTokenLimit": 2097152,
                    "outputTokenLimit": 8192,
                    "supportedGenerationMethods": ["generateContent", "countTokens"],
                    "temperature": 1,
                    "topP": 0.95,
                    "topK": 64,
                    "maxTemperature": 2,
                },
                {
                    "name": "models/gemini-exp-1206",
                    "version": "2.0",
                    "displayName": "Gemini Experimental 1206",
                    "description": "Experimental release (February 5th, 2025) of Gemini 2.0 Pro",
                    "inputTokenLimit": 2097152,
                    "outputTokenLimit": 8192,
                    "supportedGenerationMethods": ["generateContent", "countTokens"],
                    "temperature": 1,
                    "topP": 0.95,
                    "topK": 64,
                    "maxTemperature": 2,
                },
                {
                    "name": "models/gemini-2.0-flash-thinking-exp-01-21",
                    "version": "2.0-exp-01-21",
                    "displayName": "Gemini 2.0 Flash Thinking Experimental 01-21",
                    "description": "Experimental release (January 21st, 2025) of Gemini 2.0 Flash Thinking",
                    "inputTokenLimit": 1048576,
                    "outputTokenLimit": 65536,
                    "supportedGenerationMethods": ["generateContent", "countTokens"],
                    "temperature": 0.7,
                    "topP": 0.95,
                    "topK": 64,
                    "maxTemperature": 2,
                },
                {
                    "name": "models/gemini-2.0-flash-thinking-exp",
                    "version": "2.0-exp-01-21",
                    "displayName": "Gemini 2.0 Flash Thinking Experimental 01-21",
                    "description": "Experimental release (January 21st, 2025) of Gemini 2.0 Flash Thinking",
                    "inputTokenLimit": 1048576,
                    "outputTokenLimit": 65536,
                    "supportedGenerationMethods": ["generateContent", "countTokens"],
                    "temperature": 0.7,
                    "topP": 0.95,
                    "topK": 64,
                    "maxTemperature": 2,
                },
                {
                    "name": "models/gemini-2.0-flash-thinking-exp-1219",
                    "version": "2.0",
                    "displayName": "Gemini 2.0 Flash Thinking Experimental",
                    "description": "Gemini 2.0 Flash Thinking Experimental",
                    "inputTokenLimit": 1048576,
                    "outputTokenLimit": 65536,
                    "supportedGenerationMethods": ["generateContent", "countTokens"],
                    "temperature": 0.7,
                    "topP": 0.95,
                    "topK": 64,
                    "maxTemperature": 2,
                },
                {
                    "name": "models/learnlm-1.5-pro-experimental",
                    "version": "001",
                    "displayName": "LearnLM 1.5 Pro Experimental",
                    "description": "Alias that points to the most recent stable version of Gemini 1.5 Pro, our mid-size multimodal model that supports up to 2 million tokens.",
                    "inputTokenLimit": 32767,
                    "outputTokenLimit": 8192,
                    "supportedGenerationMethods": ["generateContent", "countTokens"],
                    "temperature": 1,
                    "topP": 0.95,
                    "topK": 64,
                    "maxTemperature": 2,
                },
                {
                    "name": "models/gemma-3-27b-it",
                    "version": "001",
                    "displayName": "Gemma 3 27B",
                    "inputTokenLimit": 131072,
                    "outputTokenLimit": 8192,
                    "supportedGenerationMethods": ["generateContent", "countTokens"],
                    "temperature": 1,
                    "topP": 0.95,
                    "topK": 64,
                },
                {
                    "name": "models/embedding-001",
                    "version": "001",
                    "displayName": "Embedding 001",
                    "description": "Obtain a distributed representation of a text.",
                    "inputTokenLimit": 2048,
                    "outputTokenLimit": 1,
                    "supportedGenerationMethods": ["embedContent"],
                },
                {
                    "name": "models/text-embedding-004",
                    "version": "004",
                    "displayName": "Text Embedding 004",
                    "description": "Obtain a distributed representation of a text.",
                    "inputTokenLimit": 2048,
                    "outputTokenLimit": 1,
                    "supportedGenerationMethods": ["embedContent"],
                },
                {
                    "name": "models/gemini-embedding-exp-03-07",
                    "version": "exp-03-07",
                    "displayName": "Gemini Embedding Experimental 03-07",
                    "description": "Obtain a distributed representation of a text.",
                    "inputTokenLimit": 8192,
                    "outputTokenLimit": 1,
                    "supportedGenerationMethods": ["embedContent"],
                },
                {
                    "name": "models/gemini-embedding-exp",
                    "version": "exp-03-07",
                    "displayName": "Gemini Embedding Experimental",
                    "description": "Obtain a distributed representation of a text.",
                    "inputTokenLimit": 8192,
                    "outputTokenLimit": 1,
                    "supportedGenerationMethods": ["embedContent"],
                },
                {
                    "name": "models/aqa",
                    "version": "001",
                    "displayName": "Model that performs Attributed Question Answering.",
                    "description": "Model trained to return answers to questions that are grounded in provided sources, along with estimating answerable probability.",
                    "inputTokenLimit": 7168,
                    "outputTokenLimit": 1024,
                    "supportedGenerationMethods": ["generateAnswer"],
                    "temperature": 0.2,
                    "topP": 1,
                    "topK": 40,
                },
                {
                    "name": "models/imagen-3.0-generate-002",
                    "version": "002",
                    "displayName": "Imagen 3.0 002 model",
                    "description": "Vertex served Imagen 3.0 002 model",
                    "inputTokenLimit": 480,
                    "outputTokenLimit": 8192,
                    "supportedGenerationMethods": ["predict"],
                },
                {
                    "name": "models/gemini-2.0-flash-exp-search",
                    "version": "2.0",
                    "displayName": "Gemini 2.0 Flash Experimental For Search",
                    "description": "Gemini 2.0 Flash Experimental For Search",
                    "inputTokenLimit": 1048576,
                    "outputTokenLimit": 8192,
                    "supportedGenerationMethods": ["generateContent", "countTokens", "bidiGenerateContent"],
                    "temperature": 1,
                    "topP": 0.95,
                    "topK": 40,
                    "maxTemperature": 2,
                },
                {
                    "name": "models/gemini-2.0-pro-exp-search",
                    "version": "2.0",
                    "displayName": "Gemini 2.0 Pro Experimental For Search",
                    "description": "Gemini 2.0 Pro Experimental For Search",
                    "inputTokenLimit": 2097152,
                    "outputTokenLimit": 8192,
                    "supportedGenerationMethods": ["generateContent", "countTokens"],
                    "temperature": 1,
                    "topP": 0.95,
                    "topK": 64,
                    "maxTemperature": 2,
                },
                {
                    "name": "models/gemini-2.0-flash-exp-image",
                    "version": "2.0",
                    "displayName": "Gemini 2.0 Flash Experimental For Image",
                    "description": "Gemini 2.0 Flash Experimental For Image",
                    "inputTokenLimit": 1048576,
                    "outputTokenLimit": 8192,
                    "supportedGenerationMethods": ["generateContent", "countTokens", "bidiGenerateContent"],
                    "temperature": 1,
                    "topP": 0.95,
                    "topK": 40,
                    "maxTemperature": 2,
                },
            ]
        }

        filtered_models = []
        for model in models.get("models", []):
            model_id = model["name"].split("/")[-1]
            if model_id not in self.filtered_models:
                filtered_models.append(model)
            else:
                logger.info(f"Filtered out model: {model_id}")

        models["models"] = filtered_models
        return models

    def get_gemini_openai_models(self, provider: str) -> Optional[Dict[str, Any]]:
        try:
            gemini_models = self.get_gemini_models(provider)
            return self.convert_to_openai_models_format(gemini_models)
        except requests.RequestException as e:
            logger.error(f"Request failed: {e}")
            return None

    def convert_to_openai_models_format(self, gemini_models: Dict[str, Any]) -> Dict[str, Any]:
        openai_format = {"object": "list", "data": [], "success": True}

        for model in gemini_models.get("models", []):
            model_id = model["name"].split("/")[-1]
            openai_model = {
                "id": model_id,
                "object": "model",
                "created": int(datetime.now(timezone.utc).timestamp()),
                "owned_by": "google",
                "permission": [],
                "root": model["name"],
                "parent": None,
            }
            openai_format["data"].append(openai_model)

            if model_id in self.search_models:
                search_model = openai_model.copy()
                search_model["id"] = f"{model_id}-search"
                openai_format["data"].append(search_model)

            if model_id in self.image_models:
                image_model = openai_model.copy()
                image_model["id"] = f"{model_id}-image"
                openai_format["data"].append(image_model)

        return openai_format

    def check_model_support(self, model: str) -> bool:
        if not model or not isinstance(model, str):
            return False

        model = model.strip()
        if model.endswith("-search"):
            model = model[:-7]
            return model in self.search_models
        if model.endswith("-image"):
            model = model[:-6]
            return model in self.image_models

        return model not in self.filtered_models
