from __future__ import annotations

import base64
import os
from pathlib import Path
from typing import Any

import requests
from openai import OpenAI


PLACEHOLDER_VALUES = {
    "sk-your-api-key-here",
    "your_openai_api_key_here",
    "your-api-key-here",
    "api_key_here",
    "",
}


def _has_non_ascii(value: str) -> bool:
    try:
        value.encode("ascii")
        return False
    except UnicodeEncodeError:
        return True


def validate_openai_settings() -> tuple[bool, str]:
    """Return (is_valid, message) for UI-friendly validation."""
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini").strip()

    if not api_key:
        return False, "OPENAI_API_KEY가 비어 있습니다. .env 파일에 실제 API 키를 입력하세요."

    if api_key.lower() in PLACEHOLDER_VALUES or "본인키" in api_key or "여기에" in api_key:
        return False, "OPENAI_API_KEY가 예시값으로 남아 있습니다. 실제 OpenAI API 키로 교체하세요."

    if _has_non_ascii(api_key):
        return False, "OPENAI_API_KEY에 한글/특수문자가 포함되어 있습니다. 실제 API 키만 입력하세요. 예: sk-..."

    if _has_non_ascii(model):
        return False, "OPENAI_MODEL 값에 한글이 포함되어 있습니다. 예: gpt-4.1-mini"

    return True, "OpenAI 설정이 확인되었습니다."


def get_openai_client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    ok, message = validate_openai_settings()
    if not ok:
        raise RuntimeError(message)
    return OpenAI(api_key=api_key)


def _selected_model(model: str | None = None) -> str:
    selected_model = (model or os.getenv("OPENAI_MODEL", "gpt-4.1-mini")).strip()
    if not selected_model:
        selected_model = "gpt-4.1-mini"
    if _has_non_ascii(selected_model):
        raise RuntimeError("모델명에 한글/특수문자가 포함되어 있습니다. 예: gpt-4.1-mini")
    return selected_model


def _selected_image_model(model: str | None = None) -> str:
    selected_model = (model or os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-1")).strip()
    if not selected_model:
        selected_model = "gpt-image-1"
    if _has_non_ascii(selected_model):
        raise RuntimeError("이미지 모델명에 한글/특수문자가 포함되어 있습니다. 예: gpt-image-1")
    return selected_model


def _extract_output_text(response: Any) -> str:
    if hasattr(response, "output_text") and response.output_text:
        return response.output_text.strip()

    chunks: list[str] = []
    for item in getattr(response, "output", []) or []:
        for content in getattr(item, "content", []) or []:
            text = getattr(content, "text", None)
            if text:
                chunks.append(text)
    return "\n".join(chunks).strip()


def _friendly_openai_error(exc: Exception, selected_model: str) -> RuntimeError:
    msg = str(exc)
    if "Incorrect API key" in msg or "invalid_api_key" in msg or "401" in msg:
        return RuntimeError("OpenAI API 키가 올바르지 않습니다. .env의 OPENAI_API_KEY를 다시 확인하세요.")
    if "model" in msg.lower() and ("not found" in msg.lower() or "does not exist" in msg.lower()):
        return RuntimeError(f"사용할 수 없는 모델명입니다: {selected_model}")
    if "image" in msg.lower() and "model" in msg.lower():
        return RuntimeError(
            f"이미지 처리를 지원하지 않는 모델일 수 있습니다: {selected_model}. OPENAI_IMAGE_MODEL을 확인하세요."
        )
    return RuntimeError(f"AI 호출 중 오류가 발생했습니다: {msg}")


def ask_ai(prompt: str, model: str | None = None, temperature: float = 0.7) -> str:
    """Text-only OpenAI Responses API wrapper."""
    client = get_openai_client()
    selected_model = _selected_model(model)

    try:
        response = client.responses.create(
            model=selected_model,
            input=prompt,
            temperature=temperature,
        )
    except Exception as exc:  # noqa: BLE001
        raise _friendly_openai_error(exc, selected_model) from exc

    return _extract_output_text(response)


def ask_ai_with_web_search(prompt: str, model: str | None = None, temperature: float = 0.2) -> str:
    """OpenAI Responses API wrapper with web search tool.

    This is used for STEP 2 business research. It is intentionally separate
    from normal scraping because Korean/Naver search pages are highly dynamic.
    """
    client = get_openai_client()
    selected_model = _selected_model(model)

    try:
        response = client.responses.create(
            model=selected_model,
            input=prompt,
            tools=[{"type": "web_search_preview"}],
            temperature=temperature,
        )
    except Exception as exc:  # noqa: BLE001
        msg = str(exc)
        if "web_search" in msg.lower() or "tool" in msg.lower():
            raise RuntimeError(
                "OpenAI 웹 검색 도구 호출에 실패했습니다. 현재 계정/모델에서 web_search_preview 도구를 사용할 수 없는 경우입니다. "
                "OPENAI_MODEL을 웹 검색 지원 모델로 바꾸거나, 네이버 검색 API 보조 설정을 사용하세요. 원문 오류: "
                + msg
            ) from exc
        raise _friendly_openai_error(exc, selected_model) from exc

    return _extract_output_text(response)


def ask_ai_multimodal(
    text: str,
    image_data_urls: list[str],
    model: str | None = None,
    temperature: float = 0.2,
) -> str:
    """Text + image wrapper for media analysis.

    image_data_urls must be data URLs such as data:image/jpeg;base64,...
    """
    client = get_openai_client()
    selected_model = _selected_model(model)

    content: list[dict[str, Any]] = [{"type": "input_text", "text": text}]
    for data_url in image_data_urls:
        content.append({"type": "input_image", "image_url": data_url})

    try:
        response = client.responses.create(
            model=selected_model,
            input=[{"role": "user", "content": content}],
            temperature=temperature,
        )
    except Exception as exc:  # noqa: BLE001
        raise _friendly_openai_error(exc, selected_model) from exc

    return _extract_output_text(response)


def _extract_image_bytes(image_response: Any) -> bytes:
    data_items = getattr(image_response, "data", None)
    if data_items is None and isinstance(image_response, dict):
        data_items = image_response.get("data")
    if not data_items:
        raise RuntimeError("이미지 응답 데이터가 비어 있습니다.")

    first = data_items[0]
    b64_value = getattr(first, "b64_json", None)
    if b64_value is None and isinstance(first, dict):
        b64_value = first.get("b64_json")
    if b64_value:
        return base64.b64decode(b64_value)

    url_value = getattr(first, "url", None)
    if url_value is None and isinstance(first, dict):
        url_value = first.get("url")
    if url_value:
        resp = requests.get(url_value, timeout=30)
        resp.raise_for_status()
        return resp.content

    raise RuntimeError("이미지 응답에서 결과 이미지를 추출하지 못했습니다.")


def edit_image_with_ai(
    input_path: str | Path,
    prompt: str,
    output_path: str | Path,
    image_model: str | None = None,
    size: str = "1024x1024",
) -> Path:
    """Edit a user image into a blog-ready image.

    This uses the OpenAI Images API. If the account/model does not support image editing,
    a user-friendly RuntimeError is raised.
    """
    client = get_openai_client()
    selected_model = _selected_image_model(image_model)
    input_path = Path(input_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with input_path.open("rb") as image_file:
            response = client.images.edit(
                model=selected_model,
                image=image_file,
                prompt=prompt,
                size=size,
            )
    except Exception as exc:  # noqa: BLE001
        raise _friendly_openai_error(exc, selected_model) from exc

    image_bytes = _extract_image_bytes(response)
    output_path.write_bytes(image_bytes)
    return output_path
