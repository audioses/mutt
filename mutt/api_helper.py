import openai
import google.generativeai as genai
import requests
from local_model_manager import LocalModelManager

class APIHelper:
    @staticmethod
    def get_openai_models(api_key):
        if not api_key: return []
        try:
            client = openai.OpenAI(api_key=api_key)
            return sorted([m.id for m in client.models.list() if "gpt" in m.id])
        except Exception as e:
            print(f"OpenAI Model Fetch Error: {e}"); return []
    @staticmethod
    def get_google_models(api_key):
        if not api_key: return []
        try:
            genai.configure(api_key=api_key)
            return sorted([m.name.replace("models/","") for m in genai.list_models() if 'generateContent' in m.supported_generation_methods])
        except Exception as e:
            print(f"Google Model Fetch Error: {e}"); return []
    @staticmethod
    def get_openrouter_models(api_key):
        try:
            response = requests.get("https://openrouter.ai/api/v1/models")
            response.raise_for_status()
            return sorted([m['id'] for m in response.json().get('data', [])])
        except Exception as e:
            print(f"OpenRouter Model Fetch Error: {e}"); return []
    @staticmethod
    def get_local_models(api_key=None):
        try:
            return [model["id"] for model in LocalModelManager().get_installed_models()]
        except Exception as e:
            print(f"Local Models Fetch Error: {e}"); return []

    @staticmethod
    def get_custom_openai_models(api_key, base_url):
        """Fetch models from any OpenAI-compatible endpoint.

        Works for OpenRouter, Groq, Together, vLLM, Ollama, LM Studio, llama.cpp,
        or any other server exposing GET {base_url}/models in the OpenAI spec.
        """
        if not base_url:
            return []
        try:
            client = openai.OpenAI(base_url=base_url.strip(), api_key=api_key or "not-needed")
            return sorted([m.id for m in client.models.list()])
        except Exception as e:
            print(f"Custom endpoint Model Fetch Error ({base_url}): {e}")
            return []
