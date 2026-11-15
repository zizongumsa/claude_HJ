"""주식 도구 모음 — 실행: streamlit run app.py"""
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent


def _forget_project_modules() -> None:
    """GitHub에서 새 코드를 받아도 Streamlit Cloud는 이미 불러온 보조 모듈(backtest.py 등)을 예전 것 그대로 쓴다.
    그러면 새 화면 코드가 예전 모듈에서 새 함수를 찾다가 ImportError가 난다.
    이 프로젝트의 모듈은 작으므로(다시 읽는 데 수십 ms) 실행할 때마다 메모리에서 지워 항상 최신 파일을 읽게 한다."""
    me = Path(__file__).resolve()
    for name, mod in list(sys.modules.items()):
        f = getattr(mod, "__file__", None)
        if f and ROOT in Path(f).resolve().parents and Path(f).resolve() != me:
            del sys.modules[name]


_forget_project_modules()

st.set_page_config(page_title="주식 도구", page_icon="📈", layout="wide")

pages = [
    st.Page("views/recommend.py", title="종목 추천", icon="🎯", default=True),
    st.Page("views/calculator.py", title="수익 계산기 & 추세", icon="📈"),
]
st.navigation(pages).run()
