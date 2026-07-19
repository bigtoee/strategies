# -*- coding: utf-8 -*-
"""
LLM 客户端：支持 Kimi（Moonshot）/ Ollama / 仅返回上下文（无 LLM）
"""
import os


class BaseLLM:
    def chat(self, system_prompt: str, user_prompt: str) -> str:
        raise NotImplementedError


class KimiLLM(BaseLLM):
    """Moonshot Kimi（Kimi 智能助手），API 兼容 OpenAI 格式。"""

    def __init__(self, api_key: str = None, model: str = "moonshot-v1-8k", base_url: str = "https://api.moonshot.cn/v1", temperature: float = 0.3):
        import openai
        self.api_key = api_key
        if not self.api_key:
            raise ValueError("使用 Kimi 需要提供 api_key")
        self.model = model
        self.base_url = base_url
        self.temperature = temperature
        self.client = openai.OpenAI(api_key=self.api_key, base_url=self.base_url)

    def chat(self, system_prompt: str, user_prompt: str) -> str:
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=self.temperature,
        )
        return resp.choices[0].message.content


class OpenAILLM(BaseLLM):
    def __init__(self, api_key: str = None, model: str = "gpt-3.5-turbo", base_url: str = None, temperature: float = 0.3):
        import openai
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("使用 OpenAI 需要提供 api_key 或设置 OPENAI_API_KEY 环境变量")
        self.model = model
        self.base_url = base_url or os.getenv("OPENAI_BASE_URL")
        self.temperature = temperature
        self.client = openai.OpenAI(api_key=self.api_key, base_url=self.base_url)

    def chat(self, system_prompt: str, user_prompt: str) -> str:
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=self.temperature,
        )
        return resp.choices[0].message.content


class OllamaLLM(BaseLLM):
    def __init__(self, model: str = "llama3", base_url: str = "http://localhost:11434", temperature: float = 0.3):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.temperature = temperature

    def chat(self, system_prompt: str, user_prompt: str) -> str:
        import json
        import urllib.request
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "options": {"temperature": self.temperature},
        }
        req = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["message"]["content"]


class NoopLLM(BaseLLM):
    """不调用大模型，仅将检索结果拼接返回。"""

    def chat(self, system_prompt: str, user_prompt: str) -> str:
        return ""


def get_llm(provider: str = "auto", **kwargs) -> BaseLLM:
    """
    provider: auto | kimi | openai | ollama | noop
    """
    provider = provider.lower().strip()

    if provider == "kimi":
        return KimiLLM(**kwargs)
    if provider == "openai":
        return OpenAILLM(**kwargs)
    if provider == "ollama":
        return OllamaLLM(**kwargs)
    if provider == "noop":
        return NoopLLM()

    if provider == "auto":
        # 1. 优先 Kimi（如果传入了 kimi_api_key 或设置了 KIMI_API_KEY）
        kimi_key = kwargs.get("kimi_api_key") or os.getenv("KIMI_API_KEY")
        if kimi_key:
            try:
                return KimiLLM(api_key=kimi_key, model=kwargs.get("kimi_model", "moonshot-v1-8k"))
            except Exception:
                pass
        # 2. OpenAI（如果配置了 key）
        if kwargs.get("api_key") or os.getenv("OPENAI_API_KEY"):
            try:
                import openai
                return OpenAILLM(**kwargs)
            except Exception:
                pass
        # 3. 尝试 Ollama（检测本地服务是否可用）
        try:
            import urllib.request
            urllib.request.urlopen("http://localhost:11434", timeout=2)
            return OllamaLLM(**kwargs)
        except Exception:
            pass
        # 兜底：仅检索
        return NoopLLM()

    raise ValueError(f"未知的 LLM provider: {provider}")
