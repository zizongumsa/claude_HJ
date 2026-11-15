"""주식 도구 모음 — 실행: streamlit run app.py"""
import streamlit as st

st.set_page_config(page_title="주식 도구", page_icon="📈", layout="wide")

pages = [
    st.Page("views/recommend.py", title="종목 추천", icon="🎯", default=True),
    st.Page("views/calculator.py", title="수익 계산기 & 추세", icon="📈"),
]
st.navigation(pages).run()
