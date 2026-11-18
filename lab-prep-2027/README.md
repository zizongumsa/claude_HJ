# lab-prep-2027

> 2027년 1학기 학부연구생 지원을 위한 14주 준비 기록
> (2026-11-23 ~ 2027-02-28 · RFst Lab / AISIC Lab)

<!-- X-03에서 이 첫 화면을 완성해요. 아래 [ ] 칸을 채우고, 대표 결과 그림을 넣으세요. -->

## 한 줄 소개

[ 예: FMCW 레이더 신호처리와 디지털 IC 설계를 Python·C·Verilog로 직접 구현하며 공부하고 있습니다. ]

## 주력 연구실

- [ ] RFst Lab (레이더·안테나·AI 신호처리)
- [ ] AISIC Lab (디지털 IC·하드웨어 보안)

결정한 이유 (6주차 체크포인트, K-01): [ 3줄 ]

## 대표 결과

| 결과 | 그림 | 한 줄 설명 | 과제 |
| --- | --- | --- | --- |
| [ 예: range-Doppler map ] | [ 그림 링크 ] | [ 두 표적을 (3 m, +3 m/s), (7 m, −5 m/s)에서 검출 ] | R-05 |
| [ ] | [ ] | [ ] | |
| [ ] | [ ] | [ ] | |

## 폴더 구조

```
lab-prep-2027/
├─ README.md      ← 이 문서 (포트폴리오 첫 화면)
├─ common/        ← C-00 ~ C-07 기초 복습
├─ rfst/          ← R-01 ~ R-11 레이더·안테나·신호처리
├─ aisic/         ← A-01 ~ A-09 디지털 IC·하드웨어 보안
│  ├─ rtl/        ← Verilog 설계
│  └─ tb/         ← testbench
└─ notes/         ← 손 유도 사진, 1쪽 정리 노트
```

과제별 파일 이름은 [`common/README.md`](common/README.md), [`rfst/README.md`](rfst/README.md)에 있어요.

## 개발 환경 확인 (P-03)

| 항목 | 내용 |
| --- | --- |
| OS | [ 예: Windows 11 + WSL2 Ubuntu 24.04 / macOS 15 ] |
| Python 환경 | [ 예: conda env `lab`, Python 3.11 ] |
| 파형 뷰어 | [ GTKWave / Surfer ] |
| 확인한 날짜 | [ YYYY-MM-DD ] |

아래 명령을 터미널에서 실행하고, 출력 결과를 각 칸에 그대로 붙여 넣어요. 네 명령이 모두 오류 없이 버전을 출력하면 완료예요.

**Icarus Verilog**

```bash
iverilog -V
```

```text
[ 출력 붙여 넣기 ]
```

**Yosys**

```bash
yosys -V
```

```text
[ 출력 붙여 넣기 ]
```

**ngspice**

```bash
ngspice -v
```

```text
[ 출력 붙여 넣기 ]
```

**Python 패키지** (`import skrf`만 하면 아무것도 출력되지 않아서 버전을 함께 찍어요)

```bash
python -c "import numpy, scipy, matplotlib, skrf; print(numpy.__version__, scipy.__version__, matplotlib.__version__, skrf.__version__)"
```

```text
[ 출력 붙여 넣기 ]
```

## 작업 규칙

- 노트북 한 개 = 과제 한 개. 순서는 **목표 → 파라미터 → 코드 → 그림 → 해석 3줄**.
- 그림에는 축 이름과 단위(m, m/s, dB)를 꼭 붙여요.
- 커밋 메시지는 과제 번호로 시작해요. 예: `R-05 range-Doppler map 추가`
- 시뮬레이션 출력(`.vcd`, `.raw` 등)은 `.gitignore`로 제외돼요. 결과는 그림(`.png`)으로 남겨요.
