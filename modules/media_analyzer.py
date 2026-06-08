from __future__ import annotations

import base64
import json
import mimetypes
import re
from pathlib import Path
from typing import Any

from .llm_client import ask_ai, ask_ai_multimodal, edit_image_with_ai
from .storage import PROCESSED_IMAGE_DIR, resolve_path, to_relative_path


def _extract_json(text: str) -> dict[str, Any]:
    try:
        return json.loads(text)
    except Exception:
        pass
    match = re.search(r"\{.*\}", text, flags=re.S)
    if not match:
        raise ValueError("AI 응답에서 JSON을 찾지 못했습니다.")
    return json.loads(match.group(0))


def file_to_data_url(path: Path) -> str:
    mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def analyze_image_file(path: Path, manual_description: str = "", model: str | None = None) -> dict[str, Any]:
    data_url = file_to_data_url(path)
    prompt = f"""
너는 네이버 블로그 글 작성을 위한 사진 분석가다.
첨부 이미지를 보고 블로그 본문에 사용할 수 있는 설명만 정리해라.

규칙:
- 이미지에 보이는 것만 설명한다.
- 상호/가격/효능/위치처럼 이미지에서 확실하지 않은 것은 단정하지 않는다.
- 사용자가 적은 설명이 있으면 참고하되, 이미지와 모순되면 '확인 필요'로 분리한다.
- 결과는 반드시 JSON만 출력한다.

사용자 입력 설명: {manual_description}

출력 JSON 스키마:
{{
  "file_name": "{path.name}",
  "image_type": "외관/내부/제품/메뉴/작업현장/인물/기타 중 하나",
  "visible_elements": ["보이는 요소"],
  "blog_caption": "블로그에 넣기 좋은 자연스러운 사진 설명 1~2문장",
  "recommended_position": "도입부/중간/상세설명/마무리 중 추천 위치",
  "cautions": ["단정하면 안 되는 내용"]
}}
""".strip()
    return _extract_json(ask_ai_multimodal(prompt, [data_url], model=model, temperature=0.2))


def _extract_video_frame_data_urls(path: Path, max_frames: int = 4) -> tuple[list[str], dict[str, Any]]:
    try:
        import cv2  # type: ignore
    except Exception:
        return [], {"video_analysis_available": False, "reason": "opencv-python-headless 설치가 필요합니다."}

    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        return [], {"video_analysis_available": False, "reason": "영상 파일을 열 수 없습니다."}

    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0)
    duration_sec = round(frame_count / fps, 2) if frame_count > 0 and fps > 0 else None

    if frame_count <= 0:
        cap.release()
        return [], {"video_analysis_available": False, "reason": "영상 프레임 수를 확인할 수 없습니다."}

    if max_frames <= 1:
        positions = [frame_count // 2]
    else:
        positions = sorted(set(int(frame_count * ratio) for ratio in [0.05, 0.33, 0.66, 0.9]))[:max_frames]

    data_urls: list[str] = []
    for pos in positions:
        cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, min(frame_count - 1, pos)))
        ok, frame = cap.read()
        if not ok:
            continue
        ok, buffer = cv2.imencode(".jpg", frame)
        if not ok:
            continue
        encoded = base64.b64encode(buffer.tobytes()).decode("ascii")
        data_urls.append(f"data:image/jpeg;base64,{encoded}")
    cap.release()

    return data_urls, {
        "video_analysis_available": bool(data_urls),
        "frame_count": frame_count,
        "fps": fps,
        "duration_sec": duration_sec,
        "sampled_frames": len(data_urls),
    }


def analyze_video_file(path: Path, manual_description: str = "", model: str | None = None) -> dict[str, Any]:
    frame_urls, meta = _extract_video_frame_data_urls(path)
    if not frame_urls:
        return {
            "file_name": path.name,
            "manual_description": manual_description,
            "video_summary": manual_description or "영상 분석을 실행하지 못했습니다. 영상 설명을 직접 입력해 주세요.",
            "blog_use_points": [manual_description] if manual_description else [],
            "recommended_position": "중간",
            "cautions": [meta.get("reason", "영상 프레임 추출 실패")],
            "metadata": meta,
        }

    prompt = f"""
너는 네이버 블로그 글 작성을 위한 영상 분석가다.
첨부된 이미지는 영상에서 추출한 대표 프레임이다. 프레임을 보고 블로그 본문에 사용할 수 있는 영상 설명을 정리해라.

규칙:
- 프레임에 보이는 것과 사용자가 입력한 설명만 기반으로 작성한다.
- 영상 전체 내용을 과도하게 단정하지 않는다.
- 결과는 반드시 JSON만 출력한다.

파일명: {path.name}
사용자 입력 설명: {manual_description}
영상 메타데이터: {json.dumps(meta, ensure_ascii=False)}

출력 JSON 스키마:
{{
  "file_name": "{path.name}",
  "video_summary": "영상에 대한 블로그용 자연스러운 설명 2~3문장",
  "visible_elements": ["대표 프레임에서 보이는 요소"],
  "blog_use_points": ["본문에 녹일 포인트"],
  "recommended_position": "도입부/중간/상세설명/마무리 중 추천 위치",
  "cautions": ["단정하면 안 되는 내용"],
  "metadata": {json.dumps(meta, ensure_ascii=False)}
}}
""".strip()
    return _extract_json(ask_ai_multimodal(prompt, frame_urls, model=model, temperature=0.2))


def plan_image_processing(
    image_analysis: dict[str, Any],
    style_profile: dict[str, Any],
    business_analysis: dict[str, Any],
    overlay_caption: bool = True,
    overlay_style: str = "정보형",
    model: str | None = None,
) -> dict[str, Any]:
    prompt = f"""
너는 블로그용 이미지 가공 기획자다.
사용자의 블로그 문체/분위기와 업체 분석, 그리고 현재 이미지 분석 결과를 바탕으로
'블로그에 넣기 좋은 가공 이미지'를 만들기 위한 편집 계획을 JSON으로 작성하라.

중요 규칙:
- 이미지에 없는 사실을 새로 추가하라고 하면 안 된다.
- 실제 사진의 핵심 피사체는 유지한다.
- 색감, 밝기, 선명도, 정리, 구도 보정 위주로 제안한다.
- overlay_caption이 true이면 이미지 안에 넣을 짧은 자막/라벨 문구를 1개 제안한다.
- 과장 광고 문구는 피하고, 블로그 글에 어울리는 자연스러운 표현을 사용한다.
- 결과는 반드시 JSON만 출력한다.

입력:
style_profile={json.dumps(style_profile, ensure_ascii=False)}
business_analysis={json.dumps(business_analysis, ensure_ascii=False)}
image_analysis={json.dumps(image_analysis, ensure_ascii=False)}
overlay_caption={str(overlay_caption).lower()}
overlay_style={overlay_style}

출력 JSON 스키마:
{{
  "editing_goal": "",
  "suggested_crop": "",
  "color_tone": "",
  "overlay_caption": "",
  "overlay_position": "상단/하단/좌측상단/우측상단/없음",
  "overlay_style_note": "",
  "edit_prompt": "OpenAI 이미지 편집 API에 넣을 구체적인 한국어 프롬프트"
}}
""".strip()
    return _extract_json(ask_ai(prompt, model=model, temperature=0.2))


def process_image_for_blog(
    source_image_path: str | Path,
    processing_plan: dict[str, Any],
    image_model: str | None = None,
) -> dict[str, Any]:
    source_image_path = resolve_path(source_image_path)
    output_name = source_image_path.stem + "_processed.png"
    output_path = PROCESSED_IMAGE_DIR / output_name
    edit_prompt = processing_plan.get("edit_prompt", "")
    if not edit_prompt:
        raise RuntimeError("이미지 편집 프롬프트가 비어 있습니다.")
    edited_path = edit_image_with_ai(source_image_path, edit_prompt, output_path, image_model=image_model)
    return {
        "source_image": to_relative_path(source_image_path),
        "processed_image": to_relative_path(edited_path),
        "processing_plan": processing_plan,
        "overlay_caption": processing_plan.get("overlay_caption", ""),
    }


def plan_video_caption(
    video_analysis: dict[str, Any],
    style_profile: dict[str, Any],
    business_analysis: dict[str, Any],
    model: str | None = None,
) -> dict[str, Any]:
    prompt = f"""
너는 블로그/쇼츠용 자막 기획자다.
아래 영상 분석 결과를 바탕으로, 블로그 본문에 녹일 설명과 영상 자막 초안을 JSON으로 작성하라.
직접 보이스 인식한 자막이 아니라, 블로그/쇼츠에 넣기 좋은 짧은 자막 문구 초안이라고 생각하면 된다.

입력:
style_profile={json.dumps(style_profile, ensure_ascii=False)}
business_analysis={json.dumps(business_analysis, ensure_ascii=False)}
video_analysis={json.dumps(video_analysis, ensure_ascii=False)}

출력 JSON 스키마:
{{
  "video_hook": "",
  "subtitle_lines": ["짧은 자막 1", "짧은 자막 2", "짧은 자막 3"],
  "blog_integration_note": "블로그 본문에 어떤 문장으로 녹이면 좋은지",
  "thumbnail_text": "썸네일/대표이미지용 짧은 문구"
}}
""".strip()
    return _extract_json(ask_ai(prompt, model=model, temperature=0.25))
