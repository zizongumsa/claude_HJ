# rfst · 레이더, 안테나, 신호처리 (R-01 ~ R-11)

RFst Lab 트랙이에요. 겨울에는 장비 없이 할 수 있는 이론, Python 시뮬레이션, C 구현에 집중해요.
손 설계 사진은 [`notes/`](../notes/)에 같은 번호로 저장해요 (예: `notes/r01_smith_1.jpg`).

| 번호 | 주차 | 과제 | 파일 | 표시 | 상태 |
| --- | --- | --- | --- | --- | --- |
| R-01 | W7 (1/4–1/10) | 전송선로, 반사계수, 스미스 차트 | `r01_matching.ipynb` · `notes/r01_smith_*.jpg` | 핵심 | ⬜ |
| R-02 | W7 (1/4–1/10) | S-파라미터와 VNA | `r02_sparams.ipynb` | | ⬜ |
| R-03 | W8 (1/11–1/17) | 안테나 기초와 배열 빔 조향 | `r03_array_factor.ipynb` | | ⬜ |
| R-04 | W4 (12/14–12/20) | 레이더 방정식과 FMCW 원리 | `r04_fmcw_params.ipynb` · `notes/r04_fmcw_formulas.md` | 맛보기 · 핵심 | ⬜ |
| R-05 | W5 (12/21–12/27) | FMCW 레이더 시뮬레이터 만들기 | `r05_fmcw_sim.ipynb` · `r05_rd_map.png` | 맛보기 · 핵심 | ⬜ |
| R-06 | W8 (1/11–1/17) | CFAR 검출 | `r06_cfar.ipynb` | | ⬜ |
| R-07 | W9 (1/18–1/24) | 비접촉 호흡·심박 추출 시뮬레이션 | `r07_vital_signs.ipynb` | | ⬜ |
| R-08 | W10 (1/25–1/31) | 칼만 필터로 표적 추적 | `r08_kalman.ipynb` | | ⬜ |
| R-09 | W11 (2/1–2/7) | openEMS로 패치 안테나 S11 시뮬레이션 | `r09_openems_patch.py` · `r09_s11.png` | 선택 | ⬜ |
| R-10 | W11 (2/1–2/7) | AI 레이더 신호처리 맛보기: range-Doppler 분류 | `r10_rd_classifier.ipynb` · `fmcw_sim.py` | | ⬜ |
| R-11 | W9 (1/18–1/24) | C로 radix-2 FFT 구현 | `r11_fft_c/` (`fft.c` · `Makefile` · `compare.ipynb`) | | ⬜ |

상태: ⬜ 시작 전 · 🟨 진행 중 · ✅ 완료 (증거 링크를 보드에 남긴 뒤)

## 파일 이름 규칙

- `r<두 자리 번호>_<짧은 영어 주제>.<확장자>` — 예: `r05_fmcw_sim.ipynb`
- `fmcw_sim.py`는 R-10에서 R-05 시뮬레이터를 함수로 옮긴 공용 모듈이에요. R-06, R-11도 이 모듈로 데이터를 만들 수 있어요.
- R-11은 C 파일이 여러 개라 폴더 하나로 묶어요. 빌드 결과(`*.o`, 실행 파일)는 커밋하지 않아요.
