# common · 기초 복습 (C-00 ~ C-07)

두 연구실 모두에 필요한 수학, 회로, 소자, 신호, 디지털 기초예요.
손 유도 사진과 1쪽 정리는 [`notes/`](../notes/)에 같은 번호로 저장해요 (예: `notes/c01_smallsignal.jpg`).

| 번호 | 주차 | 과제 | 파일 | 상태 |
| --- | --- | --- | --- | --- |
| C-00 | W1–2 (11/23–12/6) | 수학·회로이론 워밍업 | `c00_math_warmup.ipynb` · `notes/c00_diagnosis.md` | ⬜ |
| C-01 | W2 (11/30–12/6) | MOSFET 소신호 모델과 단일단 증폭기 | `c01_amplifiers.md` · `notes/c01_smallsignal.jpg` | ⬜ |
| C-02 | W2–3 (11/30–12/13) | 차동쌍, 전류 미러, 주파수 응답 | `c02_diffpair.asc` · `c02_bode.png` · `c02_diffpair.md` | ⬜ |
| C-03 | W3 (12/7–12/13) | 반도체 소자: 단채널 효과와 FinFET·FDSOI | `notes/c03_short_channel.md` | ⬜ |
| C-04 | W3 (12/7–12/13) | DFT를 직접 구현하고 FFT와 비교 | `c04_dft_vs_fft.ipynb` | ⬜ |
| C-05 | W4 (12/14–12/20) | 잡음, SNR, 검출 확률 | `c05_noise_detection.ipynb` | ⬜ |
| C-06 | W4 (12/14–12/20) | 디지털 회로: FSM과 타이밍 | `c06_timing.md` · `aisic/rtl/sync_2ff.v` | ⬜ |
| C-07 | W5 (12/21–12/27) | 영어 논문 읽기 연습 (3-pass) | `notes/c07_paper_summary.md` | ⬜ |

상태: ⬜ 시작 전 · 🟨 진행 중 · ✅ 완료 (증거 링크를 보드에 남긴 뒤)

## 파일 이름 규칙

- `c<두 자리 번호>_<짧은 영어 주제>.<확장자>` — 예: `c04_dft_vs_fft.ipynb`
- C-06의 2단 플립플롭 동기화기는 A-01에서 다시 쓰므로 `aisic/rtl/`에 둬요.
