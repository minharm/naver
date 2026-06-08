from __future__ import annotations

import sys
from pathlib import Path

# pytest 실행 위치나 VS Code 테스트 수집 방식에 따라 프로젝트 루트가
# sys.path에 자동으로 들어가지 않는 경우가 있습니다.
# modules/, package_release.py를 항상 import할 수 있도록 루트를 명시적으로 추가합니다.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
project_root_str = str(PROJECT_ROOT)
if project_root_str not in sys.path:
    sys.path.insert(0, project_root_str)
