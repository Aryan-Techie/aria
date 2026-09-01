"""Thin wrapper over Agora's Conversational AI Engine REST API.

Base URL and auth confirmed against docs.agora.io this session:
- Base: https://api.agora.io/api/conversational-ai-agent/v2/projects/{app_id}
- Auth: HTTP Basic, base64("{customer_key}:{customer_secret}")
- POST /join, POST /agents/{agent_id}/leave, POST /agents/{agent_id}/interrupt
  were confirmed directly; /speak, /update, /agents (list), /agents/{id}/history
  were not individually re-verified but follow the same confirmed path pattern
  as leave/interrupt/query — re-check against docs.agora.io if they misbehave.
"""
import base64

import httpx


class AgoraRestClient:
    def __init__(self, app_id: str, customer_key: str, customer_secret: str):
        self._app_id = app_id
        self._base_url = f"https://api.agora.io/api/conversational-ai-agent/v2/projects/{app_id}"
        credentials = base64.b64encode(f"{customer_key}:{customer_secret}".encode()).decode()
        self._headers = {
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/json",
        }

    def join(self, payload: dict) -> dict:
        response = httpx.post(f"{self._base_url}/join", headers=self._headers, json=payload, timeout=15.0)
        response.raise_for_status()
        return response.json()

    def leave(self, agent_id: str) -> None:
        response = httpx.post(f"{self._base_url}/agents/{agent_id}/leave", headers=self._headers, timeout=15.0)
        response.raise_for_status()

    def interrupt(self, agent_id: str) -> None:
        response = httpx.post(f"{self._base_url}/agents/{agent_id}/interrupt", headers=self._headers, timeout=10.0)
        response.raise_for_status()

    def update(self, agent_id: str, properties: dict) -> None:
        """Change a running agent's configuration without restarting the call.

        Agora documents runtime TTS parameter updates specifically for the
        custom-LLM setup this backend is - the case where our own model
        decides the voice should change - so this is the supported path rather
        than a trick. It takes a partial `properties` object in the same shape
        /join takes, and only the keys present are touched.

        Used for two things here (app/voice/director.py): following the
        caller's language so an English sentence is not read in a Hindi voice,
        and giving the second-layer agents a voice of their own.

        Best-effort by construction. This sits beside a live conversation, and
        a voice that failed to change is a cosmetic disappointment where a
        raised exception mid-turn is a broken call.
        """
        response = httpx.post(
            f"{self._base_url}/agents/{agent_id}/update",
            headers=self._headers,
            json={"properties": properties},
            timeout=5.0,
        )
        response.raise_for_status()

    def query(self, agent_id: str) -> dict:
        response = httpx.get(f"{self._base_url}/agents/{agent_id}", headers=self._headers, timeout=10.0)
        response.raise_for_status()
        return response.json()

    def speak(self, agent_id: str, text: str, *, priority: str = "interrupt") -> None:
        response = httpx.post(
            f"{self._base_url}/agents/{agent_id}/speak",
            headers=self._headers,
            json={"text": text, "priority": priority},
            timeout=10.0,
        )
        response.raise_for_status()

    def list_agents(self) -> dict:
        response = httpx.get(f"{self._base_url}/agents", headers=self._headers, timeout=10.0)
        response.raise_for_status()
        return response.json()


def default_agora_client() -> AgoraRestClient:
    from app.config import get_settings

    settings = get_settings()
    return AgoraRestClient(settings.agora_app_id, settings.agora_customer_key, settings.agora_customer_secret)
