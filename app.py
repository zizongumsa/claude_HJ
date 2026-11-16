"""주식 도구 모음 — 실행: streamlit run app.py"""
import sys
import threading
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent
_STATE_KEY = "_stock_app_code_state"  # 프로세스 전체에서 공유하는 기록 (sys 모듈에 보관, 새로 읽어도 사라지지 않음)


def _code_version() -> tuple:
    """프로젝트 .py 파일들의 (경로, 수정 시각) 목록. 파일이 바뀌면 값이 달라진다."""
    files = [ROOT / "app.py", *ROOT.glob("*.py"), *ROOT.glob("strategies/*.py"), *ROOT.glob("views/*.py")]
    out = []
    for f in sorted(set(files)):
        try:
            out.append((str(f), f.stat().st_mtime_ns))
        except OSError:
            pass
    return tuple(out)


def _reload_if_code_changed() -> None:
    """GitHub에서 새 코드를 받아도 Streamlit Cloud는 이미 불러온 보조 모듈(backtest.py 등)을 예전 것 그대로 써서,
    새 화면이 새 함수를 못 찾는 ImportError가 난다. 코드 파일이 바뀐 경우에만 한 번 보조 모듈을 메모리에서 지워
    최신 파일을 읽게 한다. 여러 화면 실행이 동시에 와도 한 번만 처리되도록 잠금을 건다."""
    state = getattr(sys, _STATE_KEY, None)
    if state is None:
        state = {"lock": threading.Lock(), "version": None}
        state = sys.__dict__.setdefault(_STATE_KEY, state)  # 동시에 만들어도 하나만 남는다
    version = _code_version()
    if state["version"] == version:
        return
    with state["lock"]:
        if state["version"] == version:  # 다른 실행이 방금 처리함
            return
        me = Path(__file__).resolve()
        for name, mod in list(sys.modules.items()):
            f = getattr(mod, "__file__", None)
            if f and ROOT in Path(f).resolve().parents and Path(f).resolve() != me:
                sys.modules.pop(name, None)
        state["version"] = version


_reload_if_code_changed()

st.set_page_config(page_title="주식 도구", page_icon="📈", layout="wide")

pages = [
    st.Page("views/recommend.py", title="종목 추천", icon="🎯", default=True),
    st.Page("views/calculator.py", title="수익 계산기 & 추세", icon="📈"),
]
st.navigation(pages).run()
