from __future__ import annotations

import os
import re
import urllib.parse
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv

from modules.blog_generator import generate_blog_post, split_generated_post
from modules.post_exporter import create_blog_upload_package, parse_body_segments, select_image_path, select_video_path
from modules.crawler import crawl_many
from modules.formatter import dict_to_markdown, style_profile_to_markdown
from modules.media_analyzer import (
    analyze_image_file,
    analyze_video_file,
    plan_image_processing,
    plan_video_caption,
    process_image_for_blog,
)
from modules.storage import (
    BASE_DIR,
    OUTPUT_DIR,
    PROCESSED_IMAGE_DIR,
    UPLOAD_IMAGE_DIR,
    UPLOAD_VIDEO_DIR,
    load_json,
    save_json,
    save_text,
    save_uploaded_file,
    to_relative_path,
    resolve_path,
)
from modules.style_analyzer import analyze_style
from modules.llm_client import validate_openai_settings
from modules.web_research import analyze_business_research, research_business
from modules.analysis_gate import business_analysis_warning
from modules.project_manager import (
    list_projects,
    save_project_snapshot,
    load_project_snapshot,
    delete_project,
    rename_project,
    duplicate_project,
)

load_dotenv()

st.set_page_config(
    page_title="네이버 블로그 글 자동작성 v0.5.5",
    page_icon="✍️",
    layout="wide",
)

st.title("✍️ 네이버 블로그 글 자동작성 v0.5.5")
st.caption(
    "fact_guard 패턴, 업체 동일성 검증, 테스트 커버리지, 실행 검증 안내를 보강했습니다."
)


def _notify_and_refresh(message: str, level: str = "success") -> None:
    """Refresh so the top step status updates immediately after a step finishes."""
    st.session_state["last_action_message"] = message
    st.session_state["last_action_level"] = level
    st.rerun()


def _is_business_analysis_complete(analysis: dict | None, research: dict | None = None) -> bool:
    """STEP 2 is complete only when reliable search material exists."""
    if not isinstance(analysis, dict) or not analysis:
        return False

    research = research or {}
    valid_result_count = int(research.get("valid_result_count") or 0)
    avg_quality = float(research.get("average_quality_score") or 0)
    source_results = analysis.get("source_results") or []

    verified = analysis.get("verified_facts") or []
    profile = analysis.get("business_profile") or {}
    review = analysis.get("review_insights") or []
    keywords = analysis.get("seo_keywords") or []

    has_profile_value = isinstance(profile, dict) and any(str(v).strip() for v in profile.values() if not isinstance(v, list))
    has_list_value = bool(verified or review or keywords)
    has_web_sources = len(source_results) >= 2
    has_quality_local_sources = valid_result_count >= 2 and avg_quality >= 25
    insufficient_text = "검색 결과가 충분하지 않습니다" in str(analysis.get("summary", ""))

    return not insufficient_text and (has_web_sources or has_quality_local_sources) and (has_profile_value or has_list_value)


def _has_any_business_analysis(analysis: dict | None) -> bool:
    return isinstance(analysis, dict) and bool(analysis)


def _title_candidates(title_block: str) -> list[str]:
    candidates: list[str] = []
    for line in (title_block or "").splitlines():
        cleaned = re.sub(r"^\s*\d+[\.\)]\s*", "", line).strip()
        cleaned = cleaned.strip("-• ")
        if cleaned:
            candidates.append(cleaned)
    return candidates or [title_block.strip() or "제목을 입력하세요"]


def _text_area_height(text: str, min_height: int = 100, max_height: int = 360) -> int:
    line_count = max(3, len((text or "").splitlines()))
    return max(min_height, min(max_height, line_count * 28 + 40))


def _business_map_query(business_info: dict | None, analysis: dict | None = None) -> str:
    business_info = business_info or {}
    analysis = analysis or {}
    profile = analysis.get("business_profile") if isinstance(analysis, dict) else {}
    if not isinstance(profile, dict):
        profile = {}

    name = (
        business_info.get("업체명")
        or profile.get("official_name")
        or analysis.get("business_name", "")
        or ""
    )
    address = (
        business_info.get("주소/위치")
        or profile.get("address")
        or ""
    )
    return " ".join(str(x).strip() for x in [name, address] if str(x).strip())


def _remove_map_placeholder(text: str) -> str:
    """Remove map placeholder text from generated body.

    Naver place/map must be attached with the SmartEditor '장소' button,
    so we do not keep [네이버 지도 첨부] as body text.
    """
    text = text or ""
    text = re.sub(r"\n?\s*\[\s*네이버\s*지도\s*첨부\s*\]\s*\n?", "\n\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _naver_map_url(query: str) -> str:
    query = (query or "").strip()
    if not query:
        return "https://map.naver.com/"
    return "https://map.naver.com/p/search/" + urllib.parse.quote(query)


def _render_visible_map_preview(map_query: str, height: int = 430) -> None:
    """Render a visible map preview in the app.

    실제 네이버 블로그 발행 글에는 네이버 에디터의 '장소' 버튼으로 첨부해야
    사용자가 보여준 실제 지도 카드가 들어갑니다. 이 함수는 업로드 전에
    위치정보를 눈으로 확인하는 미리보기입니다.
    """
    map_query = (map_query or "").strip()
    map_url = _naver_map_url(map_query)
    st.markdown("##### 위치정보")
    try:
        components.iframe(map_url, height=height, scrolling=True)
    except Exception:
        # iframe이 차단될 때도 최소한 지도 카드 형태로 보이게 한다.
        place_name = map_query.split()[0] if map_query else "업체명"
        st.markdown(
            f"""
            <div class="mobile-map-box">
              <div style="height:260px;background:#edf4ed;border:1px solid #d7e8d7;border-radius:8px;
                          display:flex;align-items:center;justify-content:center;color:#03c75a;font-weight:800;font-size:22px;">
                NAVER MAP
              </div>
              <div style="padding-top:12px;">
                <b>{place_name}</b><br>
                <span style="color:#667085;">{map_query}</span>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )



def _step_after_loading_project(data: dict) -> str:
    """Move to the next actionable step after loading saved data."""
    if data.get("generated_post"):
        return "STEP 4. 블로그 글 생성"
    if data.get("image_analysis") or data.get("video_analysis"):
        return "STEP 4. 블로그 글 생성"
    if data.get("business_analysis"):
        return "STEP 3. 이미지/영상"
    if data.get("style_profile"):
        return "STEP 2. 업체 조사"
    return "STEP 1. 블로그 학습"


# Session defaults are initialized before sidebar actions so project save/load buttons can use them.
for _key, _default in {
    "samples": [],
    "style_profile": None,
    "business_info": {},
    "business_research": {},
    "business_analysis": {},
    "image_analysis": [],
    "video_analysis": [],
    "generated_post": "",
    "generated_package_zip": "",
    "generated_package_dir": "",
    "user_experience_note": "",
}.items():
    st.session_state.setdefault(_key, _default)


with st.sidebar:
    st.header("설정")
    model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
    image_model = os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-1")
    ok, api_msg = validate_openai_settings()
    if ok:
        st.success("API 키 설정 확인됨")
    else:
        st.error(api_msg)
    with st.expander("모델 설정 확인", expanded=False):
        st.caption(f"텍스트/멀티모달 모델: {model}")
        st.caption(f"이미지 편집 모델: {image_model}")
        st.caption("모델은 .env에서만 수정합니다. 일반 화면에서는 선택하지 않습니다.")
    st.caption(".env의 OPENAI_API_KEY가 필요합니다.")
    st.caption("이미지 가공은 OPENAI_IMAGE_MODEL 사용 가능 계정/모델이어야 합니다.")

    st.divider()
    st.header("프로젝트 관리")
    existing_projects = list_projects()
    default_project_name = st.session_state.get("current_project_name") or (
        f"{st.session_state.get('business_info', {}).get('업체명', '')}".strip()
    )
    project_name_input = st.text_input("저장/이름변경할 프로젝트명", value=default_project_name or "")
    if st.button("현재 작업 프로젝트로 저장", use_container_width=True):
        try:
            saved_path = save_project_snapshot(project_name_input, st.session_state)
            st.session_state["current_project_name"] = saved_path.parent.name
            _notify_and_refresh(f"프로젝트 저장 완료: {saved_path.parent.name}")
        except Exception as exc:  # noqa: BLE001
            st.error(f"프로젝트 저장 실패: {exc}")

    selected_project = st.selectbox("최근 프로젝트", [""] + existing_projects, index=0)
    pc1, pc2 = st.columns(2)
    with pc1:
        if st.button("불러오기", use_container_width=True, disabled=not bool(selected_project)):
            try:
                data = load_project_snapshot(selected_project)
                for key in [
                    "samples", "style_profile", "business_info", "business_research",
                    "business_analysis", "image_analysis", "video_analysis",
                    "generated_post", "generated_package_zip", "generated_package_dir",
                    "user_experience_note",
                ]:
                    if key in data:
                        st.session_state[key] = data.get(key)
                st.session_state["current_project_name"] = selected_project
                st.session_state["current_step"] = _step_after_loading_project(data)
                _notify_and_refresh(f"프로젝트 불러오기 완료: {selected_project} - {st.session_state['current_step']}로 이동합니다.")
            except Exception as exc:  # noqa: BLE001
                st.error(f"프로젝트 불러오기 실패: {exc}")
    with pc2:
        if st.button("삭제", use_container_width=True, disabled=not bool(selected_project)):
            try:
                delete_project(selected_project)
                _notify_and_refresh(f"프로젝트 삭제 완료: {selected_project}", level="warning")
            except Exception as exc:  # noqa: BLE001
                st.error(f"프로젝트 삭제 실패: {exc}")

    pc3, pc4 = st.columns(2)
    with pc3:
        if st.button("복제", use_container_width=True, disabled=not bool(selected_project)):
            try:
                new_name = duplicate_project(selected_project)
                _notify_and_refresh(f"프로젝트 복제 완료: {new_name}")
            except Exception as exc:  # noqa: BLE001
                st.error(f"프로젝트 복제 실패: {exc}")
    with pc4:
        if st.button("이름 변경", use_container_width=True, disabled=not bool(selected_project) or not bool(project_name_input.strip())):
            try:
                new_name = rename_project(selected_project, project_name_input)
                _notify_and_refresh(f"프로젝트 이름 변경 완료: {new_name}")
            except Exception as exc:  # noqa: BLE001
                st.error(f"프로젝트 이름 변경 실패: {exc}")

    st.divider()

    if st.button("저장된 스타일 프로필 불러오기"):
        profile = load_json("style_profile.json", default=None)
        if profile:
            st.session_state["style_profile"] = profile
            st.session_state["current_step"] = "STEP 2. 업체 조사"
            _notify_and_refresh("저장된 스타일 프로필을 불러왔습니다. STEP 2 업체 조사로 이동합니다.")
        else:
            st.warning("저장된 style_profile.json이 없습니다.")

    if st.button("저장된 업체 분석 불러오기"):
        analysis = load_json("business_analysis.json", default=None)
        research = load_json("business_research.json", default=None)
        info = load_json("business_info.json", default={})
        if analysis:
            st.session_state["business_analysis"] = analysis
            st.session_state["business_research"] = research or {}
            st.session_state["business_info"] = info or {}
            st.session_state["current_step"] = "STEP 3. 이미지/영상"
            _notify_and_refresh("저장된 업체 분석을 불러왔습니다. STEP 3으로 이동합니다.")
        else:
            st.warning("저장된 business_analysis.json이 없습니다.")

    if st.button("저장된 미디어 분석 불러오기"):
        images = load_json("image_analysis.json", default=[])
        videos = load_json("video_analysis.json", default=[])
        if images or videos:
            st.session_state["image_analysis"] = images or []
            st.session_state["video_analysis"] = videos or []
            st.session_state["current_step"] = "STEP 4. 블로그 글 생성"
            _notify_and_refresh("저장된 이미지/영상 분석을 불러왔습니다. STEP 4로 이동합니다.")
        else:
            st.warning("저장된 image_analysis.json / video_analysis.json이 없습니다.")

    if st.button("저장된 생성글 불러오기"):
        output_path = OUTPUT_DIR / "generated_post.txt"
        if output_path.exists():
            st.session_state["generated_post"] = output_path.read_text(encoding="utf-8")
            st.session_state["current_step"] = "STEP 4. 블로그 글 생성"
            _notify_and_refresh("저장된 생성글을 불러왔습니다.")
        else:
            st.warning("저장된 generated_post.txt가 없습니다.")

    if st.button("새 작업 시작 / 현재 화면 초기화"):
        for key in [
            "samples",
            "style_profile",
            "business_info",
            "business_research",
            "business_analysis",
            "image_analysis",
            "video_analysis",
            "generated_post",
            "generated_package_zip",
            "generated_package_dir",
            "user_experience_note",
        ]:
            st.session_state[key] = [] if key in ["samples", "image_analysis", "video_analysis"] else ({} if key in ["business_info", "business_research", "business_analysis"] else "")
        st.session_state["style_profile"] = None
        _notify_and_refresh("현재 화면을 새 작업 상태로 초기화했습니다. 저장 파일은 삭제하지 않았습니다.")

    st.divider()
    st.warning("본인이 작성했거나 사용 권한이 있는 글만 학습에 사용하세요. 검색 자료는 출처 확인 후 사용하세요.")

# Session defaults
# v0.3.2 변경:
# 저장된 json/txt가 있어도 새로 켜자마자 완료로 표시하지 않습니다.
# 필요한 저장 데이터는 왼쪽 사이드바의 "불러오기" 버튼으로 직접 불러옵니다.
st.session_state.setdefault("samples", [])
st.session_state.setdefault("style_profile", None)
st.session_state.setdefault("business_info", {})
st.session_state.setdefault("business_research", {})
st.session_state.setdefault("business_analysis", {})
st.session_state.setdefault("image_analysis", [])
st.session_state.setdefault("video_analysis", [])
st.session_state.setdefault("generated_post", "")
st.session_state.setdefault("generated_package_zip", "")
st.session_state.setdefault("generated_package_dir", "")
st.session_state.setdefault("user_experience_note", "")

# Progress summary
p1 = "✅ 완료" if st.session_state.get("style_profile") else "⬜ 대기"
business_analysis_state = st.session_state.get("business_analysis")
business_research_state = st.session_state.get("business_research")
if _is_business_analysis_complete(business_analysis_state, business_research_state):
    p2 = "✅ 완료"
elif _has_any_business_analysis(business_analysis_state):
    p2 = "⚠️ 검색부족"
else:
    p2 = "⬜ 대기"
p3 = "✅ 완료" if (st.session_state.get("image_analysis") or st.session_state.get("video_analysis")) else "⬜ 대기"
p4 = "✅ 완료" if st.session_state.get("generated_post") else "⬜ 대기"

c1, c2, c3, c4 = st.columns(4)
c1.info(f"1단계\n{p1}")
c2.info(f"2단계\n{p2}")
c3.info(f"3단계\n{p3}")
c4.info(f"4단계\n{p4}")

if st.session_state.get("last_action_message"):
    level = st.session_state.pop("last_action_level", "success")
    message = st.session_state.pop("last_action_message")
    if level == "warning":
        st.warning(message)
    elif level == "error":
        st.error(message)
    else:
        st.success(message)

step_options = [
    "STEP 1. 블로그 학습",
    "STEP 2. 업체 조사",
    "STEP 3. 이미지/영상",
    "STEP 4. 블로그 글 생성",
]

# Streamlit은 한 번 생성된 위젯 key 값을 같은 실행 흐름에서 직접 수정할 수 없습니다.
# 그래서 내부 상태(current_step)와 라디오 위젯 상태(current_step_radio)를 분리합니다.
st.session_state.setdefault("current_step", step_options[0])
if st.session_state.get("current_step") not in step_options:
    st.session_state["current_step"] = step_options[0]

if (
    "current_step_radio" not in st.session_state
    or st.session_state.get("current_step_radio") != st.session_state.get("current_step")
):
    # radio 위젯이 생성되기 전에만 위젯 key 값을 맞춥니다.
    st.session_state["current_step_radio"] = st.session_state["current_step"]

selected_step = st.radio(
    "진행 단계 선택",
    step_options,
    horizontal=True,
    key="current_step_radio",
    label_visibility="collapsed",
)
st.session_state["current_step"] = selected_step

if selected_step == step_options[0]:
    st.header("진행 1번. 내 블로그 학습")
    st.caption("내가 기존에 작성한 블로그 글 URL을 넣으면 제목, 본문, 태그, 사진/영상 흐름을 수집하고 내 글 스타일을 분석합니다.")

    url_text = st.text_area(
        "내가 쓴 블로그 글 URL을 한 줄에 하나씩 입력",
        height=150,
        placeholder="https://blog.naver.com/블로그ID/글번호\nhttps://blog.naver.com/블로그ID/글번호",
        key="step1_url_text",
    )

    s1c1, s1c2, s1c3 = st.columns([1, 1, 3])
    with s1c1:
        crawl_button = st.button("URL 수집", type="primary", use_container_width=True, key="step1_crawl")
    with s1c2:
        analyze_button = st.button("스타일 분석", type="primary", use_container_width=True, key="step1_analyze")
    with s1c3:
        st.caption("처음에는 5개 이상 권장. 글이 많을수록 문체 분석이 안정적입니다.")

    if crawl_button:
        urls = [line.strip() for line in url_text.splitlines() if line.strip()]
        if not urls:
            st.error("URL을 1개 이상 입력하세요.")
        else:
            with st.spinner("블로그 글을 수집하고 있습니다..."):
                samples, errors = crawl_many(urls)
                sample_dicts = [s.to_dict() for s in samples]
                st.session_state["samples"] = sample_dicts
                save_json("blog_samples.json", sample_dicts)
            st.session_state["current_step"] = step_options[0]
            _notify_and_refresh(f"URL 수집 완료: 성공 {len(samples)}개 / 실패 {len(errors)}개")
            if errors:
                st.error("수집 실패 URL")
                st.json(errors)

    if analyze_button:
        samples = st.session_state.get("samples", [])
        if not samples:
            st.error("먼저 블로그 URL을 수집하세요.")
        else:
            try:
                with st.spinner("AI가 기존 글 스타일을 분석하고 있습니다..."):
                    profile = analyze_style(samples, model=model)
                    st.session_state["style_profile"] = profile
                    save_json("style_profile.json", profile)
                st.session_state["current_step"] = step_options[1]
                _notify_and_refresh("스타일 분석 완료 - STEP 2 업체 조사로 이동합니다.")
            except Exception as exc:  # noqa: BLE001
                msg = str(exc)
                st.error(msg)
                if "JSON" in msg or "delimiter" in msg or "구분자" in msg or "형식" in msg:
                    st.info("이 오류는 .env/API 키 문제가 아니라 AI 분석 결과의 JSON 형식이 깨진 문제입니다. v0.3.5에서는 자동 복구를 1회 시도하도록 수정했습니다.")
                else:
                    st.info(".env 파일의 OPENAI_API_KEY와 OPENAI_MODEL 값을 먼저 확인하세요.")

    if st.session_state["samples"]:
        with st.expander("수집된 글 확인", expanded=False):
            for idx, sample in enumerate(st.session_state["samples"], start=1):
                st.subheader(f"{idx}. {sample.get('title', '제목 없음')}")
                st.caption(sample.get("url", ""))
                st.write(sample.get("body", "")[:700] + "...")
                st.write("태그:", " ".join(sample.get("tags", [])))

    if st.session_state.get("style_profile"):
        with st.expander("내 글 스타일 프로필", expanded=True):
            st.markdown(style_profile_to_markdown(st.session_state["style_profile"]))

        if st.button("다음 단계로 이동: STEP 2 업체 조사", type="primary", use_container_width=True):
            st.session_state["current_step"] = step_options[1]
            _notify_and_refresh("STEP 2 업체 조사로 이동합니다.")

if selected_step == step_options[1]:
    st.header("진행 2번. 업체명 + 주소만 입력하면 사실 기반 조사")
    st.caption("업체명과 주소만 입력하면 웹, 블로그, 플레이스, SNS, 유튜브 등 공개 자료를 최대한 모아서 AI가 사실 위주로 정리합니다.")

    saved_info = st.session_state.get("business_info", {}) or {}
    with st.form("research_form"):
        r1, r2 = st.columns(2)
        with r1:
            business_name = st.text_input("업체명 *", value=saved_info.get("업체명", ""))
        with r2:
            address = st.text_input("주소 *", value=saved_info.get("주소/위치", ""), placeholder="예: 경기 화성시 ...")

        fetch_excerpts = st.checkbox("검색 결과 페이지 본문 일부까지 읽기", value=True)
        submitted_research = st.form_submit_button("업체 조사 및 AI 분석", type="primary")

    if submitted_research:
        if not business_name.strip() or not address.strip():
            st.error("업체명과 주소를 모두 입력하세요.")
        else:
            st.session_state["business_info"] = {
                "업체명": business_name.strip(),
                "주소/위치": address.strip(),
            }
            save_json("business_info.json", st.session_state["business_info"])

            try:
                with st.spinner("웹/블로그/플레이스/SNS/유튜브에서 업체 정보를 검색하고 있습니다..."):
                    research = research_business(
                        business_name=business_name.strip(),
                        address=address.strip(),
                        max_results_per_group=4,
                        fetch_excerpts=fetch_excerpts,
                    )
                    st.session_state["business_research"] = research
                    save_json("business_research.json", research)

                with st.spinner("AI가 검색 결과를 사실 중심으로 분석하고 있습니다..."):
                    analysis = analyze_business_research(research, model=model)
                    st.session_state["business_analysis"] = analysis
                    save_json("business_analysis.json", analysis)
                if _is_business_analysis_complete(analysis, research):
                    _notify_and_refresh(f"업체 분석 완료: 검색 결과 {research.get('result_count', 0)}개 사용", "success")
                else:
                    _notify_and_refresh(
                        f"업체 검색 결과가 부족해서 완료 처리하지 않았습니다. 검색 결과: {research.get('result_count', 0)}개",
                        "warning",
                    )
            except Exception as exc:  # noqa: BLE001
                st.error(str(exc))
                st.info("일부 사이트는 검색 차단이 있을 수 있습니다. 업체명/주소를 더 정확히 입력해 다시 시도해 보세요.")

    if st.session_state.get("business_analysis"):
        with st.expander("업체 AI 분석 결과", expanded=True):
            analysis_data = st.session_state["business_analysis"]
            method = analysis_data.get("research_method", "")
            if method:
                st.caption(f"분석 방식: {method}")
            st.markdown(dict_to_markdown(analysis_data))

        source_results = st.session_state["business_analysis"].get("source_results") or []
        if source_results:
            with st.expander("OpenAI 웹 검색 출처 확인", expanded=False):
                for idx, item in enumerate(source_results, start=1):
                    title = item.get("title", "")
                    url = item.get("url", "")
                    source_type = item.get("source_type", "")
                    memo = item.get("memo", "")
                    st.markdown(f"**{idx}. {title}**")
                    st.caption(f"{source_type} | {url}")
                    if memo:
                        st.write(memo)

    if _is_business_analysis_complete(
        st.session_state.get("business_analysis"),
        st.session_state.get("business_research"),
    ):
        if st.button("다음 단계로 이동: STEP 3 이미지/영상", type="primary", use_container_width=True):
            st.session_state["current_step"] = "STEP 3. 이미지/영상"
            _notify_and_refresh("STEP 3으로 이동합니다.")

    if st.session_state.get("business_research"):
        rq = st.session_state.get("business_research", {})
        st.caption(
            f"검색 품질: 유효 {rq.get('valid_result_count', 0)}개 / 원본 {rq.get('raw_result_count', rq.get('result_count', 0))}개 "
            f"/ 평균점수 {rq.get('average_quality_score', 0)}"
        )

    if st.session_state.get("business_research", {}).get("results"):
        with st.expander("유효 검색 출처 확인", expanded=False):
            for idx, item in enumerate(st.session_state["business_research"]["results"], start=1):
                st.markdown(f"**{idx}. {item.get('title', '')}**")
                st.caption(f"{item.get('domain_type', '')} | {item.get('source', '')} | {item.get('url', '')}")
                if item.get("snippet"):
                    st.write(item.get("snippet"))
                if item.get("text_excerpt"):
                    st.text_area(f"본문 일부 {idx}", value=item.get("text_excerpt", ""), height=120, key=f"research_excerpt_{idx}")

if selected_step == step_options[2]:
    st.header("진행 3번. 업로드 이미지/영상 분석 + 내 스타일 기반 이미지 가공")
    st.caption("이미지는 AI가 직접 보고 블로그용 설명을 만들고, 원하면 GPT 이미지 편집으로 블로그용 가공본도 생성합니다. 영상은 프레임 분석 후 블로그 설명과 추천 자막 초안을 만듭니다.")

    with st.form("media_form"):
        st.subheader("이미지 업로드")
        image_files = st.file_uploader("사진 파일", type=["png", "jpg", "jpeg", "webp"], accept_multiple_files=True)
        image_desc = st.text_area("사진 설명", placeholder="사진 1: 외관\n사진 2: 내부\n사진 3: 메뉴판", height=100)

        st.subheader("영상 업로드")
        video_files = st.file_uploader("영상 파일", type=["mp4", "mov", "avi", "mkv"], accept_multiple_files=True)
        video_desc = st.text_area("영상 설명", placeholder="영상 1: 매장 내부 분위기\n영상 2: 제품 작동 장면", height=80)

        analyze_media_button = st.form_submit_button("이미지/영상 AI 분석", type="primary")

    if analyze_media_button:
        images_result = []
        videos_result = []
        image_desc_lines = [line.strip() for line in image_desc.splitlines() if line.strip()]
        video_desc_lines = [line.strip() for line in video_desc.splitlines() if line.strip()]

        if not image_files and not video_files:
            st.error("분석할 이미지나 영상을 1개 이상 업로드하세요.")
        else:
            try:
                if image_files:
                    with st.spinner("이미지를 AI로 분석하고 있습니다..."):
                        for idx, file in enumerate(image_files, start=1):
                            path = save_uploaded_file(file, UPLOAD_IMAGE_DIR)
                            desc = image_desc_lines[idx - 1] if idx - 1 < len(image_desc_lines) else ""
                            analysis = analyze_image_file(Path(path), manual_description=desc, model=model)
                            images_result.append({
                                "filename": path.name,
                                "saved_path": str(path),
                                "description": desc,
                                "analysis": analysis,
                                **analysis,
                            })

                if video_files:
                    with st.spinner("영상 대표 프레임을 추출해서 AI로 분석하고 있습니다..."):
                        for idx, file in enumerate(video_files, start=1):
                            path = save_uploaded_file(file, UPLOAD_VIDEO_DIR)
                            desc = video_desc_lines[idx - 1] if idx - 1 < len(video_desc_lines) else ""
                            analysis = analyze_video_file(Path(path), manual_description=desc, model=model)
                            videos_result.append({
                                "filename": path.name,
                                "saved_path": str(path),
                                "description": desc,
                                "analysis": analysis,
                                **analysis,
                            })

                st.session_state["image_analysis"] = images_result
                st.session_state["video_analysis"] = videos_result
                save_json("image_analysis.json", images_result)
                save_json("video_analysis.json", videos_result)
                st.session_state["current_step"] = step_options[2]
                _notify_and_refresh(f"미디어 분석 완료: 이미지 {len(images_result)}개 / 영상 {len(videos_result)}개")
            except Exception as exc:  # noqa: BLE001
                st.error(str(exc))
                st.info("이미지 분석이 안 되면 OPENAI_MODEL이 이미지 입력을 지원하는지 확인하세요. 영상 분석은 opencv-python-headless 설치가 필요합니다.")

    if st.session_state.get("image_analysis") or st.session_state.get("video_analysis"):
        with st.expander("이미지/영상 AI 분석 결과", expanded=True):
            if st.session_state.get("image_analysis"):
                st.subheader("이미지")
                for idx, item in enumerate(st.session_state["image_analysis"], start=1):
                    st.markdown(f"**사진 {idx}: {item.get('filename', '')}**")
                    st.json(item.get("analysis", item))
            if st.session_state.get("video_analysis"):
                st.subheader("영상")
                for idx, item in enumerate(st.session_state["video_analysis"], start=1):
                    st.markdown(f"**영상 {idx}: {item.get('filename', '')}**")
                    st.json(item.get("analysis", item))

    st.subheader("3-2. 내 스타일 기반 이미지 가공 / 영상 자막 기획")
    st.caption("이미지 가공은 선택 기능입니다. 실제 편집 실행 시 OpenAI 이미지 API 비용이 추가될 수 있습니다.")

    v1, v2, v3, v4 = st.columns(4)
    with v1:
        enable_overlay = st.checkbox("이미지 자막/라벨 넣기", value=False)
    with v2:
        enable_video_subtitle = st.checkbox("영상 자막 초안 만들기", value=False)
    with v3:
        overlay_style = st.selectbox("자막/라벨 톤", ["정보형", "감성형", "후기형", "깔끔한 라벨형"], index=0)
    with v4:
        enable_processing = st.checkbox("이미지 가공 실행", value=False)

    st.caption("자막/라벨은 선택입니다. 체크하지 않으면 사진·영상 분석 설명만 글에 반영하고, 자막 문구는 만들지 않습니다.")

    process_button = st.button("이미지 가공 계획 / 선택 자막 계획 만들기", type="primary", use_container_width=True)

    if process_button:
        if not st.session_state.get("style_profile"):
            st.error("먼저 STEP 1에서 스타일 분석을 완료하세요.")
        elif not st.session_state.get("business_analysis"):
            st.error("먼저 STEP 2에서 업체 분석을 완료하세요.")
        elif not st.session_state.get("image_analysis") and not st.session_state.get("video_analysis"):
            st.error("먼저 STEP 3에서 이미지/영상을 분석하세요.")
        else:
            try:
                updated_images = []
                updated_videos = []
                if st.session_state.get("image_analysis"):
                    with st.spinner("이미지 가공 계획을 만들고 있습니다..."):
                        for item in st.session_state["image_analysis"]:
                            plan = plan_image_processing(
                                image_analysis=item.get("analysis", item),
                                style_profile=st.session_state["style_profile"],
                                business_analysis=st.session_state.get("business_analysis", {}),
                                overlay_caption=enable_overlay,
                                overlay_style=overlay_style,
                                model=model,
                            )
                            item["processing_plan"] = plan
                            if enable_processing:
                                processed_info = process_image_for_blog(
                                    source_image_path=item.get("saved_path", ""),
                                    processing_plan=plan,
                                    image_model=image_model,
                                )
                                item["processed_info"] = processed_info
                            updated_images.append(item)

                if st.session_state.get("video_analysis"):
                    if enable_video_subtitle:
                        with st.spinner("영상 자막/설명 계획을 만들고 있습니다..."):
                            for item in st.session_state["video_analysis"]:
                                caption_plan = plan_video_caption(
                                    video_analysis=item.get("analysis", item),
                                    style_profile=st.session_state["style_profile"],
                                    business_analysis=st.session_state.get("business_analysis", {}),
                                    model=model,
                                )
                                item["caption_plan"] = caption_plan
                                updated_videos.append(item)
                    else:
                        for item in st.session_state["video_analysis"]:
                            item["caption_plan"] = {
                                "video_hook": "",
                                "subtitle_lines": [],
                                "blog_integration_note": "영상 자막 초안 생성 안 함",
                                "thumbnail_text": "",
                            }
                            updated_videos.append(item)

                if updated_images:
                    st.session_state["image_analysis"] = updated_images
                    save_json("image_analysis.json", updated_images)
                if updated_videos:
                    st.session_state["video_analysis"] = updated_videos
                    save_json("video_analysis.json", updated_videos)
                st.session_state["current_step"] = step_options[2]
                _notify_and_refresh("이미지 가공 계획 / 영상 자막 계획 생성 완료")
            except Exception as exc:  # noqa: BLE001
                st.error(str(exc))
                st.info("이미지 편집이 실패하면 '이미지 가공 실행'을 끄고 계획만 생성으로 먼저 테스트해 보세요.")

    if st.session_state.get("image_analysis"):
        with st.expander("가공 이미지 결과", expanded=False):
            for idx, item in enumerate(st.session_state["image_analysis"], start=1):
                st.markdown(f"**사진 {idx}: {item.get('filename', '')}**")
                if item.get("processing_plan"):
                    st.write("가공 계획")
                    st.json(item.get("processing_plan"))
                processed = item.get("processed_info", {}) or {}
                processed_path = processed.get("processed_image")
                if processed_path and Path(processed_path).exists():
                    st.image(processed_path, caption=f"가공 이미지 {idx}", use_container_width=True)
                    st.download_button(
                        f"가공 이미지 {idx} 다운로드",
                        data=Path(processed_path).read_bytes(),
                        file_name=Path(processed_path).name,
                        mime="image/png",
                        key=f"download_processed_{idx}",
                    )

    if st.session_state.get("video_analysis"):
        with st.expander("영상 자막/설명 계획", expanded=False):
            for idx, item in enumerate(st.session_state["video_analysis"], start=1):
                st.markdown(f"**영상 {idx}: {item.get('filename', '')}**")
                if item.get("caption_plan"):
                    st.json(item.get("caption_plan"))

    if st.session_state.get("image_analysis") or st.session_state.get("video_analysis"):
        st.divider()
        if st.button("다음 단계로 이동: STEP 4 블로그 글 생성", type="primary", use_container_width=True):
            st.session_state["current_step"] = "STEP 4. 블로그 글 생성"
            _notify_and_refresh("STEP 4로 이동합니다.")

if selected_step == step_options[3]:
    st.header("진행 4번. 내 스타일 + 업체 분석 + 이미지/영상 분석으로 블로그 글 작성")
    st.caption("생성된 글은 네이버 블로그에 바로 복사해서 붙여넣을 수 있는 형식으로 출력합니다.")

    current_info = st.session_state.get("business_info", {}) or {}
    source_warning = business_analysis_warning(
        st.session_state.get("business_analysis", {}),
        st.session_state.get("business_research", {}),
    )
    if source_warning:
        st.warning(source_warning)

    with st.form("generate_form"):
        g1, g2 = st.columns(2)
        with g1:
            final_business_name = st.text_input("업체명", value=current_info.get("업체명", ""))
            address_final = st.text_input("주소/위치", value=current_info.get("주소/위치", ""))
            purpose = st.text_input("글 목적", placeholder="방문 후기 / 업체 소개 / 서비스 홍보 등")
        with g2:
            target_keywords = st.text_input("추가 노출 희망 키워드", placeholder="예: 화성 맛집, 동탄 카페")
            caution = st.text_input("빼야 할 내용/주의사항")
            extra_memo = st.text_area("추가로 꼭 넣을 말", height=90)

        strengths = st.text_area("내가 직접 강조하고 싶은 장점/특징", height=90)
        user_experience_note = st.text_area(
            "직접 경험 메모/방문 메모",
            value=st.session_state.get("user_experience_note", ""),
            height=120,
            placeholder="직접 방문해서 먹어본 메뉴, 아이 반응, 친절도, 주차 체감 등 실제 경험한 내용만 적어주세요. 비워두면 실제 체험담처럼 쓰지 않습니다.",
        )

        generate_button = st.form_submit_button("최종 블로그 글 생성", type="primary")

    if generate_button:
        if not st.session_state.get("style_profile"):
            st.error("STEP 1에서 스타일 분석을 먼저 완료하세요.")
        elif not final_business_name.strip():
            st.error("업체명은 필수입니다.")
        else:
            business_info = {
                "업체명": final_business_name,
                "주소/위치": address_final,
                "글 목적": purpose,
                "추가 노출 희망 키워드": target_keywords,
                "내가 직접 강조하고 싶은 장점/특징": strengths,
                "추가 메모": extra_memo,
                "빼야 할 내용/주의사항": caution,
            }
            st.session_state["business_info"] = {**current_info, **business_info}
            st.session_state["user_experience_note"] = user_experience_note
            save_json("business_info.json", st.session_state["business_info"])

            try:
                with st.spinner("네이버 블로그 복사용 글을 생성하고 있습니다..."):
                    research = st.session_state.get("business_research", {}) or {}
                    post = generate_blog_post(
                        style_profile=st.session_state["style_profile"],
                        business_info=business_info,
                        images=st.session_state.get("image_analysis", []),
                        videos=st.session_state.get("video_analysis", []),
                        research_analysis=st.session_state.get("business_analysis", {}),
                        research_sources=research.get("results", []),
                        user_experience_note=st.session_state.get("user_experience_note", ""),
                        model=model,
                    )
                    st.session_state["generated_post"] = post
                    save_text("generated_post.txt", post)

                    title_block, body, tags = split_generated_post(post)
                    body = _remove_map_placeholder(body)
                    map_query = _business_map_query(business_info, st.session_state.get("business_analysis", {}))
                    package_info = create_blog_upload_package(
                        title_block=title_block,
                        body=body,
                        tags=tags,
                        full_post=post,
                        images=st.session_state.get("image_analysis", []),
                        videos=st.session_state.get("video_analysis", []),
                        map_query=map_query,
                        map_url=_naver_map_url(map_query),
                    )
                    st.session_state["generated_package_zip"] = package_info.get("zip_path", "")
                    st.session_state["generated_package_dir"] = package_info.get("package_dir", "")

                st.session_state["current_step"] = step_options[3]
                _notify_and_refresh("글 생성 완료 - 수동 업로드용 패키지를 함께 만들었습니다.")
            except Exception as exc:  # noqa: BLE001
                msg = str(exc)
                st.error(msg)
                if "JSON" in msg or "delimiter" in msg or "구분자" in msg or "형식" in msg:
                    st.info("이 오류는 .env/API 키 문제가 아니라 AI 분석 결과의 JSON 형식이 깨진 문제입니다. v0.3.5에서는 자동 복구를 1회 시도하도록 수정했습니다.")
                else:
                    st.info(".env 파일의 OPENAI_API_KEY와 OPENAI_MODEL 값을 먼저 확인하세요.")

    st.subheader("생성 결과")
    post = st.session_state.get("generated_post", "")
    if post:
        title_block, body, tags = split_generated_post(post)
        body = _remove_map_placeholder(body)
        package_zip_path = Path(st.session_state.get("generated_package_zip", "")) if st.session_state.get("generated_package_zip") else None
        package_dir_path = Path(st.session_state.get("generated_package_dir", "")) if st.session_state.get("generated_package_dir") else None
        segments = parse_body_segments(body)
        candidates = _title_candidates(title_block)
        selected_title = candidates[0]

        st.markdown(
            """
            <style>
            .naver-upload-card {
                border: 1px solid #dfe5ec;
                border-radius: 14px;
                padding: 18px 20px;
                margin: 14px 0;
                background: #ffffff;
                box-shadow: 0 1px 2px rgba(0,0,0,0.04);
            }
            .naver-step-title {
                font-size: 20px;
                font-weight: 800;
                color: #03c75a;
                margin-bottom: 8px;
            }
            .naver-small-guide {
                color: #5f6b7a;
                font-size: 14px;
                line-height: 1.6;
            }
            .naver-media-chip {
                display: inline-block;
                background: #eef8f1;
                color: #0b7f35;
                border: 1px solid #bfe6ca;
                border-radius: 999px;
                padding: 5px 10px;
                font-size: 13px;
                font-weight: 700;
                margin-bottom: 8px;
            }
            .mobile-preview-wrap {
                max-width: 430px;
                margin: 0 auto;
                padding: 18px 16px;
                border: 1px solid #e6e9ef;
                border-radius: 18px;
                background: #fff;
                box-shadow: 0 2px 10px rgba(0,0,0,0.05);
            }
            .mobile-preview-title {
                font-size: 22px;
                font-weight: 800;
                line-height: 1.38;
                margin-bottom: 18px;
                color: #1f2933;
            }
            .mobile-preview-text {
                font-size: 16px;
                line-height: 1.95;
                letter-spacing: -0.2px;
                color: #222;
                margin: 0 0 18px 0;
                white-space: pre-wrap;
            }
            .mobile-map-box {
                border: 1px solid #d9eadf;
                border-radius: 14px;
                background: #f4fbf6;
                padding: 14px;
                margin-top: 22px;
                font-size: 15px;
                line-height: 1.65;
            }
            </style>
            """,
            unsafe_allow_html=True,
        )

        upload_tab, preview_tab, package_tab, raw_tab = st.tabs(
            ["네이버 업로드용", "완성 미리보기", "파일/패키지", "원본 텍스트"]
        )

        with upload_tab:
            st.success("아래 순서대로 네이버 블로그 SmartEditor에 수동으로 넣으면 됩니다.")
            st.warning("참고: 완성 미리보기 화면을 통째로 복사하면 다른 사람에게 이미지가 보이지 않을 수 있습니다. 이미지는 반드시 아래 순서대로 네이버 에디터에 직접 업로드하세요. 사진 아래에 사진1/사진2 같은 번호 문구는 표시하지 않습니다.")
            st.markdown(
                """
                <div class="naver-upload-card">
                  <div class="naver-step-title">① 제목 넣기</div>
                  <div class="naver-small-guide">아래 제목 중 하나를 네이버 블로그 제목 칸에 복사해서 넣으세요.</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            selected_title = st.radio("제목 후보 선택", candidates, horizontal=False, key="naver_title_choice")
            st.text_input("네이버 제목 칸에 붙여넣기", value=selected_title, key="naver_title_copy")

            st.markdown(
                """
                <div class="naver-upload-card">
                  <div class="naver-step-title">② 본문 + 이미지/영상 순서대로 넣기</div>
                  <div class="naver-small-guide">
                    텍스트 블록은 복사해서 붙여넣고, 이미지/영상 블록이 나오면 바로 아래 표시된 파일을 네이버 에디터에 업로드하세요.
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            text_block_no = 1
            media_block_no = 1
            for seg in segments:
                if seg["type"] == "text":
                    st.markdown(f"#### 본문 텍스트 {text_block_no}")
                    st.text_area(
                        f"본문 텍스트 {text_block_no} 복사",
                        value=seg["content"],
                        height=_text_area_height(seg["content"]),
                        key=f"naver_text_block_{text_block_no}",
                    )
                    text_block_no += 1

                elif seg["type"] == "photo":
                    st.markdown(f'<span class="naver-media-chip">이미지 업로드 위치 {media_block_no}</span>', unsafe_allow_html=True)
                    st.caption(seg.get("placeholder", ""))
                    cols = st.columns(2)
                    col_i = 0
                    for idx in seg["indices"]:
                        with cols[col_i % 2]:
                            if 1 <= idx <= len(st.session_state.get("image_analysis", [])):
                                item = st.session_state["image_analysis"][idx - 1]
                                img_path = select_image_path(item)
                                caption = (item.get("analysis") or item).get("blog_caption", "")
                                if img_path and img_path.exists():
                                    st.image(str(img_path), use_container_width=True)
                                    st.download_button(
                                        f"이미지 파일 다운로드",
                                        data=img_path.read_bytes(),
                                        file_name=img_path.name,
                                        mime="image/jpeg",
                                        key=f"naver_download_img_{media_block_no}_{idx}",
                                    )
                                    if caption:
                                        st.text_area(
                                            f"이미지 설명 문장",
                                            value=caption,
                                            height=80,
                                            key=f"naver_caption_img_{media_block_no}_{idx}",
                                        )
                                else:
                                    st.warning(f"사진 {idx} 파일을 찾지 못했습니다.")
                            else:
                                st.warning(f"사진 {idx}는 업로드된 이미지 범위를 벗어났습니다.")
                        col_i += 1
                    media_block_no += 1

                elif seg["type"] == "video":
                    st.markdown(f'<span class="naver-media-chip">영상 업로드 위치 {media_block_no}</span>', unsafe_allow_html=True)
                    for idx in seg["indices"]:
                        if 1 <= idx <= len(st.session_state.get("video_analysis", [])):
                            item = st.session_state["video_analysis"][idx - 1]
                            video_path = select_video_path(item)
                            caption = (item.get("analysis") or item).get("video_summary", "")
                            if video_path and video_path.exists():
                                st.video(str(video_path))
                                st.download_button(
                                    f"영상 파일 다운로드",
                                    data=video_path.read_bytes(),
                                    file_name=video_path.name,
                                    mime="video/mp4",
                                    key=f"naver_download_video_{media_block_no}_{idx}",
                                )
                                if caption:
                                    st.text_area(
                                        f"영상 설명 문장",
                                        value=caption,
                                        height=90,
                                        key=f"naver_caption_video_{media_block_no}_{idx}",
                                    )
                            else:
                                st.warning(f"영상 {idx} 파일을 찾지 못했습니다.")
                        else:
                            st.warning(f"영상 {idx}는 업로드된 영상 범위를 벗어났습니다.")
                    media_block_no += 1

            st.markdown(
                """
                <div class="naver-upload-card">
                  <div class="naver-step-title">③ 태그 넣기</div>
                  <div class="naver-small-guide">아래 태그를 네이버 블로그 태그 영역 또는 본문 마지막에 활용하세요.</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.text_area("태그 복사", value=tags, height=150, key="naver_tags_copy")

            map_query = _business_map_query(st.session_state.get("business_info", {}), st.session_state.get("business_analysis", {}))
            st.markdown(
                """
                <div class="naver-upload-card">
                  <div class="naver-step-title">④ 맨 아래 지도 첨부하기</div>
                  <div class="naver-small-guide">
                    아래 위치정보처럼 보이도록, 네이버 블로그 에디터 상단의 <b>장소</b> 버튼을 눌러 실제 지도 카드를 첨부하세요.<br>
                    검색어를 복사해서 장소 검색창에 붙여넣고 해당 업체를 선택하면 사용자가 보여준 지도 카드 형태로 들어갑니다.
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.text_input("장소 버튼에서 검색할 문구", value=map_query, key="naver_place_query_copy")
            _render_visible_map_preview(map_query, height=430)

        with preview_tab:
            st.info("모바일 네이버 블로그에서 보이는 느낌에 가깝게 줄간격과 폭을 맞춘 확인용 미리보기입니다.")
            st.markdown(f'<div class="mobile-preview-wrap"><div class="mobile-preview-title">{selected_title}</div>', unsafe_allow_html=True)
            for seg in segments:
                if seg["type"] == "text":
                    paragraphs = [p.strip() for p in re.split(r"\n{2,}", seg["content"]) if p.strip()]
                    for p in paragraphs:
                        st.markdown(f'<div class="mobile-preview-text">{p}</div>', unsafe_allow_html=True)
                elif seg["type"] == "photo":
                    for idx in seg["indices"]:
                        if 1 <= idx <= len(st.session_state.get("image_analysis", [])):
                            item = st.session_state["image_analysis"][idx - 1]
                            img_path = select_image_path(item)
                            if img_path and img_path.exists():
                                caption = (item.get("analysis") or item).get("blog_caption", "")
                                st.image(str(img_path), use_container_width=True)
                            else:
                                st.warning(f"사진 {idx} 파일을 찾지 못했습니다.")
                        else:
                            st.warning(f"사진 {idx}는 업로드된 이미지 범위를 벗어났습니다.")
                elif seg["type"] == "video":
                    for idx in seg["indices"]:
                        if 1 <= idx <= len(st.session_state.get("video_analysis", [])):
                            item = st.session_state["video_analysis"][idx - 1]
                            video_path = select_video_path(item)
                            caption = (item.get("analysis") or item).get("video_summary", "")
                            if video_path and video_path.exists():
                                st.video(str(video_path))
                                if caption:
                                    st.caption(caption)
                            else:
                                st.warning(f"영상 {idx} 파일을 찾지 못했습니다.")
                        else:
                            st.warning(f"영상 {idx}는 업로드된 영상 범위를 벗어났습니다.")
            map_query = _business_map_query(st.session_state.get("business_info", {}), st.session_state.get("business_analysis", {}))
            _render_visible_map_preview(map_query, height=360)
            st.markdown("</div>", unsafe_allow_html=True)
            st.markdown("### 태그")
            st.write(tags)

        with package_tab:
            st.markdown("### 네이버 업로드 패키지")
            st.write("본문, 이미지/영상 파일, 업로드 순서 가이드, HTML 미리보기를 하나로 묶었습니다.")
            if package_zip_path and package_zip_path.exists():
                st.download_button(
                    "업로드 패키지 ZIP 다운로드",
                    data=package_zip_path.read_bytes(),
                    file_name=package_zip_path.name,
                    mime="application/zip",
                )
            else:
                st.warning("업로드 패키지가 아직 생성되지 않았습니다. 최종 블로그 글 생성을 다시 눌러주세요.")

            if package_dir_path and package_dir_path.exists():
                guide_path = package_dir_path / "upload_guide.txt"
                html_path = package_dir_path / "blog_post_with_media.html"
                if guide_path.exists():
                    st.text_area("업로드 가이드", value=guide_path.read_text(encoding="utf-8"), height=260)
                if html_path.exists():
                    st.caption(f"HTML 미리보기 파일: {html_path}")
                st.caption(f"패키지 폴더: {package_dir_path}")

        with raw_tab:
            raw1, raw2, raw3, raw4 = st.tabs(["전체 복사용", "제목", "본문", "태그"])
            with raw1:
                st.text_area("전체 복사용", value=post, height=650)
            with raw2:
                st.text_area("제목 후보", value=title_block, height=220)
            with raw3:
                st.text_area("본문", value=body, height=650)
            with raw4:
                st.text_area("태그", value=tags, height=200)

            output_path = OUTPUT_DIR / "generated_post.txt"
            if output_path.exists():
                st.download_button(
                    "TXT 파일 다운로드",
                    data=output_path.read_bytes(),
                    file_name="generated_post.txt",
                    mime="text/plain",
                )
    else:
        st.info("아직 생성된 글이 없습니다.")

    if PROCESSED_IMAGE_DIR.exists():
        generated_count = len(list(PROCESSED_IMAGE_DIR.glob("*.png"))) + len(list(PROCESSED_IMAGE_DIR.glob("*.jpg")))
        if generated_count:
            st.caption(f"가공 이미지 저장 폴더: {PROCESSED_IMAGE_DIR} / 현재 {generated_count}개")
