# 네이버 블로그 글 자동작성 v0.5.2

## v0.5.2 수정 사항

### 저장된 스타일 프로필 불러오기 후 STEP 2 이동

v0.5.1에서는 직접 스타일 분석을 완료하면 STEP 2로 이동했지만, 사이드바의 `저장된 스타일 프로필 불러오기`는 여전히 STEP 1에 머무르는 문제가 있었습니다.

v0.5.2에서는 다음을 수정했습니다.

- `저장된 스타일 프로필 불러오기` 클릭 후 STEP 2 업체 조사로 자동 이동
- 프로젝트 불러오기 시 저장된 진행 상태에 따라 다음 작업 단계로 이동
  - 생성글 있음 → STEP 4
  - 이미지/영상 분석 있음 → STEP 4
  - 업체 분석 있음 → STEP 3
  - 스타일 프로필만 있음 → STEP 2

## v0.5.1 수정 사항

### 1단계 완료 후 2단계 이동 보완

v0.5.0에서 스타일 분석은 완료되지만 화면이 1단계에 남아 있어 2단계로 넘어가지 않는 것처럼 보일 수 있었습니다.

v0.5.1에서는 다음을 수정했습니다.

- 스타일 분석 완료 후 자동으로 STEP 2 업체 조사로 이동
- STEP 1 하단에 `다음 단계로 이동: STEP 2 업체 조사` 버튼 추가

## v0.5.0 핵심 변경 사항

이번 버전은 평가에서 지적된 보안/검색품질/사실성/프로젝트 관리 문제를 우선 수정한 버전입니다.

## 1. 배포 ZIP 보안 정리

외부 공유용 ZIP에는 아래 항목이 포함되지 않도록 정리했습니다.

- `.venv/`
- `__pycache__/`
- `.env`
- `output/`
- `uploads/`
- `data/*.json`
- `projects/`
- `output/naver_playwright_profile/`
- 브라우저 쿠키, 로그인 데이터, 히스토리, 로컬스토리지, 세션스토리지
- 기존 작업 결과물과 개인 업로드 원본

추가 파일:

- `.gitignore`
- `package_release.py`

배포용 ZIP을 다시 만들 때는 아래 명령을 사용하세요.

```powershell
python package_release.py
```

생성되는 ZIP은 소스 코드 중심의 clean release입니다.

## 2. 업체 검색 품질 필터 강화

`web_research.py`에 검색 결과 품질 점수를 추가했습니다.

주요 기준:

- 네이버 플레이스/지도: 가산점
- 네이버 블로그 실제 글: 가산점
- 다이닝코드/망고플레이트 등 로컬 리뷰: 가산점
- 업체명 포함: 가산점
- 주소 핵심 단어 포함: 가산점
- NAVER 메인/쇼핑/사전/검색탭/고객센터 등 잡링크: 강한 감점 또는 제외
- 본문 excerpt 없음: 낮은 점수

STEP 2 완료 판단도 단순 결과 개수가 아니라 `valid_result_count`, `average_quality_score`, OpenAI 웹 검색 출처 수를 함께 봅니다.

## 3. 생성 글 사실 제한 강화

생성 프롬프트에 아래 제한을 추가했습니다.

- 사용자가 직접 경험 메모에 적지 않은 내용은 실제 방문 후기처럼 쓰지 않음
- `다녀왔다`, `먹어봤다`, `주문했다`, `아이들이 잘 먹었다` 같은 표현 제한
- 사진만 보고 맛, 친절도, 가성비, 주차 편의, 대표 메뉴를 단정하지 않음
- verified_facts에 없는 전화번호/영업시간/주차/예약/배달 정보는 단정하지 않음
- 확인 필요 정보는 방문 전 확인 안내 수준으로만 작성

STEP 4에 `직접 경험 메모/방문 메모` 입력칸을 추가했습니다.

## 4. 프로젝트 관리 기능 추가

사이드바에 프로젝트 관리 기능을 추가했습니다.

- 현재 작업 프로젝트로 저장
- 최근 프로젝트 목록
- 프로젝트 불러오기
- 프로젝트 삭제
- 프로젝트 복제
- 프로젝트 이름 변경

프로젝트는 `projects/프로젝트명/project.json` 구조로 저장됩니다.

주의: `projects/`는 개인 작업 데이터이므로 배포 ZIP에는 포함하지 않습니다.

## 5. 모델 선택 UI 숨김

사이드바의 모델명 입력칸을 제거했습니다.

모델은 `.env`에서만 설정합니다.

```env
OPENAI_MODEL=gpt-4.1-mini
OPENAI_IMAGE_MODEL=gpt-image-1
```

## 6. 경로 저장 방식 개선

업로드 이미지/영상, 가공 이미지 경로는 가능한 경우 프로젝트 기준 상대경로로 저장합니다.

예:

```text
uploads/images/sample.jpg
output/processed_images/sample_processed.png
```

절대경로가 저장되어 다른 PC에서 깨지는 문제를 줄였습니다.

## 7. 테스트 코드 추가

기본 테스트 파일을 추가했습니다.

```text
tests/test_parsers_and_quality.py
```

실행:

```powershell
pytest
```

## 기존 폴더를 정리해야 할 때

이전 버전 폴더에 `.venv`, `output`, `uploads`, `projects` 등이 남아 있으면 `cleanup_sensitive_files.bat`를 실행해 정리할 수 있습니다.

주의: 개인 작업 결과와 업로드 원본도 삭제되므로 필요한 파일은 먼저 백업하세요.

## 실행 방법

```powershell
pip install -r requirements.txt
streamlit run app.py
```

또는:

```powershell
run_localhost_5173.bat
```

접속 주소:

```text
http://localhost:5173/
```

## 포함 파일

외부 공유용 ZIP에 포함되는 주요 파일:

```text
app.py
modules/
tests/
requirements.txt
README.md
.env.example
.gitignore
package_release.py
run_localhost_5173.bat
cleanup_sensitive_files.bat
.streamlit/config.toml
```

