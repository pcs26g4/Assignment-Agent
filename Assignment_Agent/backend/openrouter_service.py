import os
from typing import Dict, List, Optional
import requests
from dotenv import load_dotenv

load_dotenv()


class OpenRouterService:
    def __init__(self):
        self.base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
        self.api_key = os.getenv("OPENROUTER_API_KEY", "")
        self.model = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")
        self.timeout = int(os.getenv("OPENROUTER_TIMEOUT", "300"))
        self.max_retries = int(os.getenv("OPENROUTER_MAX_RETRIES", "3"))
        self.backoff_base = float(os.getenv("OPENROUTER_BACKOFF_BASE", "0.75"))
        self.stream = False
        self.referer = os.getenv("OPENROUTER_HTTP_REFERER", "http://localhost:8000")
        self.title = os.getenv("OPENROUTER_TITLE", "Grading App")

    def _headers(self) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        if self.referer:
            headers["HTTP-Referer"] = self.referer
        if self.title:
            headers["X-Title"] = self.title
        return headers

    def generate(self, prompt: str, model: Optional[str] = None, system_message: Optional[str] = None) -> Dict:
        if not prompt or not prompt.strip():
            return {"success": False, "error": "Empty prompt sent to model", "response": ""}

        model = model or self.model
        # Default system message for grading (file uploads)
        default_system_message = "You are a strict grader that returns JSON only."
        system_msg = system_message if system_message is not None else default_system_message
        
        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_msg},
                {"role": "user", "content": prompt},
            ],
            "stream": self.stream,
        }

        attempt = 0
        last_err = None
        while attempt <= self.max_retries:
            try:
                resp = requests.post(url, json=payload, headers=self._headers(), timeout=self.timeout)
                if resp.status_code == 401:
                    return {"success": False, "error": "Unauthorized. Set OPENROUTER_API_KEY.", "response": ""}
                # Retry on 429 and 5xx
                if resp.status_code in (429, 500, 502, 503, 504):
                    raise requests.exceptions.RequestException(f"HTTP {resp.status_code}: transient error")
                resp.raise_for_status()
                data = resp.json()
                content = ""
                try:
                    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                except Exception:
                    content = ""
                return {"success": True, "response": content, "model": model, "done": True}
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError, requests.exceptions.RequestException) as e:
                last_err = str(e)
                if attempt == self.max_retries:
                    break
                # simple exponential backoff
                import time
                sleep_s = self.backoff_base * (2 ** attempt)
                try:
                    time.sleep(sleep_s)
                except Exception:
                    pass
                attempt += 1
                continue
            except Exception as e:
                return {"success": False, "error": f"OpenRouter error: {str(e)}", "response": ""}

        return {"success": False, "error": f"OpenRouter transient error after retries: {last_err}", "response": ""}

    def list_models(self) -> List[str]:
        try:
            url = f"{self.base_url}/models"
            resp = requests.get(url, headers=self._headers(), timeout=10)
            if resp.status_code != 200:
                return []
            data = resp.json()
            models = data.get("data", [])
            return [m.get("id", "") for m in models if isinstance(m, dict)]
        except Exception:
            return []

    def generate_with_images(self, messages: List[Dict], model: Optional[str] = None, system_message: Optional[str] = None) -> Dict:
        """
        Generate response with images (vision model support)
        messages: List of message dicts with content that can include images
        """
        model = model or self.model
        # Default system message for design evaluation
        default_system_message = "You are an expert presentation design evaluator. Return ONLY valid JSON, no other text."
        system_msg = system_message if system_message is not None else default_system_message
        
        # Build messages list with system message
        full_messages = [
            {"role": "system", "content": system_msg}
        ] + messages
        
        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": model,
            "messages": full_messages,
            "stream": self.stream,
        }

        attempt = 0
        last_err = None
        while attempt <= self.max_retries:
            try:
                resp = requests.post(url, json=payload, headers=self._headers(), timeout=self.timeout)
                if resp.status_code == 401:
                    return {"success": False, "error": "Unauthorized. Set OPENROUTER_API_KEY.", "response": ""}
                # Retry on 429 and 5xx
                if resp.status_code in (429, 500, 502, 503, 504):
                    raise requests.exceptions.RequestException(f"HTTP {resp.status_code}: transient error")
                resp.raise_for_status()
                data = resp.json()
                content = ""
                try:
                    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                except Exception:
                    content = ""
                return {"success": True, "response": content, "model": model, "done": True}
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError, requests.exceptions.RequestException) as e:
                last_err = str(e)
                if attempt == self.max_retries:
                    break
                # simple exponential backoff
                import time
                sleep_s = self.backoff_base * (2 ** attempt)
                try:
                    time.sleep(sleep_s)
                except Exception:
                    pass
                attempt += 1
                continue
            except Exception as e:
                return {"success": False, "error": f"OpenRouter error: {str(e)}", "response": ""}

        return {"success": False, "error": f"OpenRouter transient error after retries: {last_err}", "response": ""}

    def check_connection(self) -> bool:
        try:
            url = f"{self.base_url}/models"
            resp = requests.get(url, headers=self._headers(), timeout=5)
            return resp.status_code == 200
        except Exception:
            return False
