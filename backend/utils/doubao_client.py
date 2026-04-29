"""豆包 API 客户端"""
import json
import re
import requests
from typing import Optional

from backend.utils.logger import logger

DOUBAO_URL = "https://ark.cn-beijing.volces.com/api/v3/chat/completions"
DOUBAO_DEFAULT_MODEL = "ep-20260329183523-7ns5h"


class DoubaoClient:
    def __init__(self, api_key: str, model: str = DOUBAO_DEFAULT_MODEL):
        self.api_key = api_key
        self.model = model
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    def chat(self, messages: list, system: Optional[str] = None,
             max_tokens: int = 4096, temperature: float = 0.2) -> str:
        full_messages = []
        if system:
            full_messages.append({"role": "system", "content": system})
        full_messages.extend(messages)

        payload = {
            "model": self.model,
            "messages": full_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        try:
            resp = requests.post(DOUBAO_URL, headers=self._headers, json=payload, timeout=60)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        except requests.HTTPError as e:
            logger.error(f"[doubao] HTTP错误 {resp.status_code}: {resp.text[:200]}")
            raise RuntimeError(f"豆包API HTTP错误 {resp.status_code}: {e}") from e
        except Exception as e:
            logger.error(f"[doubao] 请求失败: {e}")
            raise RuntimeError(f"豆包API调用失败: {e}") from e

    def chat_json(self, messages: list, system: Optional[str] = None,
                  max_tokens: int = 4096, temperature: float = 0.1) -> dict:
        raw = self.chat(messages, system=system, max_tokens=max_tokens, temperature=temperature)
        raw = raw.strip()
        if raw.startswith("```"):
            raw = re.sub(r"```(?:json)?", "", raw).strip().rstrip("```").strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError as e:
            logger.warning(f"[doubao] JSON解析失败: {raw[:200]}")
            raise ValueError(f"豆包API返回非法JSON: {e}") from e
