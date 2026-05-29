"""
app_streamlit.py  —  스마트 관수 앱 (Streamlit 웹 앱)
======================================================
실행: streamlit run app_streamlit.py
접속: http://localhost:8501  (스마트폰도 같은 WiFi면 IP:8501)
배포: streamlit.io 에서 GitHub 연결 후 1클릭 → 무료 공개 URL
"""

import os, datetime, math, random, statistics
import streamlit as st

# ── 페이지 기본 설정 (가장 먼저 호출해야 함) ─────────────
st.set_page_config(
    page_title="🌾 스마트 관수 시스템",
    page_icon="🌾",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── backend_logic 임포트 ────────────────────────────────
try:
    from backend_logic import (
        CROP_THRESHOLDS, CROP_KC, SEASON_PARAMS,
        collect_weather, generate_soil, preprocess,
        train_and_validate, make_decision, get_advice,
        load_history, add_history_record, calc_stats,
        export_data,
    )
    BACKEND_OK = True
except ImportError:
    BACKEND_OK = False


# ══════════════════════════════════════════════════════
#  CSS — 모바일 친화적 스타일
# ══════════════════════════════════════════════════════

st.markdown("""
<style>
/* 전체 폰트 및 배경 */
.main { padding: 0.5rem 1rem; }

/* 상태 카드 */
.status-card {
    padding: 1.2rem 1.5rem;
    border-radius: 14px;
    margin: 0.5rem 0 1rem;
    font-size: 1.15rem;
    font-weight: 600;
    text-align: center;
    letter-spacing: 0.02em;
}
.status-즉시관수 { background:#ffe0e0; color:#c0392b; border:2px solid #e74c3c; }
.status-관수권장 { background:#fff3cd; color:#856404; border:2px solid #ffc107; }
.status-적정상태 { background:#d4edda; color:#155724; border:2px solid #28a745; }
.status-과습주의 { background:#cce5ff; color:#004085; border:2px solid #0d6efd; }

/* 지표 박스 */
.metric-row {
    display: flex; flex-wrap: wrap; gap: 0.6rem; margin: 0.5rem 0;
}
.metric-box {
    flex: 1 1 120px;
    background: var(--secondary-background-color);
    border-radius: 10px;
    padding: 0.7rem 1rem;
    text-align: center;
    border: 1px solid rgba(128,128,128,0.2);
}
.metric-label { font-size: 0.75rem; color: #888; margin-bottom: 0.2rem; }
.metric-value { font-size: 1.3rem; font-weight: 700; }

/* 게이지 바 */
.gauge-wrap { position: relative; height: 28px; border-radius: 8px;
              background: linear-gradient(to right, #e74c3c 0%, #e74c3c 40%,
              #f39c12 40%, #f39c12 55%, #27ae60 55%, #27ae60 80%,
              #2980b9 80%, #2980b9 100%);
              margin: 0.4rem 0; }
.gauge-arrow { position: absolute; top: 0; width: 4px; height: 28px;
               background: white; border-radius: 2px;
               box-shadow: 0 0 4px rgba(0,0,0,0.5); }
.gauge-labels { display: flex; justify-content: space-between;
                font-size: 0.7rem; color: #888; margin-top: 2px; }

/* 권고문 박스 */
.advice-box {
    background: var(--secondary-background-color);
    border-left: 4px solid #27ae60;
    border-radius: 0 10px 10px 0;
    padding: 1rem 1.2rem;
    margin: 0.5rem 0;
    line-height: 1.7;
    font-size: 0.95rem;
}

/* 모바일 대응 */
@media (max-width: 600px) {
    .metric-value { font-size: 1.1rem; }
    .status-card { font-size: 1rem; }
}
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════
#  세션 상태 초기화
# ══════════════════════════════════════════════════════

def _init_session():
    defaults = {
        "history":      load_history() if BACKEND_OK else [],
        "weather_list": [],
        "soil_list":    [],
        "decision":     None,
        "advice":       None,
        "model_result": None,
        "ran_once":     False,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init_session()


# ══════════════════════════════════════════════════════
#  사이드바 — 설정 입력 (Input)
# ══════════════════════════════════════════════════════

with st.sidebar:
    st.title("⚙️ 설정")
    st.caption("분석 조건을 선택하세요")

    st.subheader("🌾 작물 · 환경")
    Crop_Type = st.selectbox(
        "작물 선택",
        list(CROP_THRESHOLDS.keys()) if BACKEND_OK else ["상추/채소"],
        index=6,
    )
    Season = st.selectbox(
        "계절",
        ["봄", "여름", "가을", "겨울"],
        index=1,
    )
    Area_m2 = st.number_input("재배 면적 (m²)", min_value=10.0, max_value=100000.0, value=1000.0, step=100.0)
    Init_Moisture = st.slider("현재 토양 수분 추정 (%)", 10, 100, 65)
    Days = st.slider("데이터 수집 기간 (일)", 5, 60, 30)

    st.divider()
    st.subheader("🔑 API 키 설정")

    KMA_Key = st.text_input(
        "기상청 API 키 (선택)",
        value=os.environ.get("KMA_API_KEY", ""),
        type="password",
        help="data.go.kr → 기상청 단기예보 활용신청 후 발급"
    )
    Claude_Key = st.text_input(
        "Claude AI 키 (선택)",
        value=os.environ.get("ANTHROPIC_API_KEY", ""),
        type="password",
        help="console.anthropic.com 에서 발급"
    )
    if KMA_Key:    os.environ["KMA_API_KEY"]         = KMA_Key
    if Claude_Key: os.environ["ANTHROPIC_API_KEY"]   = Claude_Key

    st.divider()
    Run_Btn = st.button("🚀 분석 실행", use_container_width=True, type="primary")

    if KMA_Key:
        st.success("✅ 기상청 API 연동됨 — 실제 데이터 사용")
    else:
        st.info("ℹ️ API 키 없음 → 시뮬레이션 데이터 사용")


# ══════════════════════════════════════════════════════
#  헤더
# ══════════════════════════════════════════════════════

st.title("🌾 스마트 관수 시스템")
st.caption(f"기상 · 토양 데이터 기반 농업 용수 관리 | {datetime.date.today()}")

if not BACKEND_OK:
    st.error("❌ backend_logic.py 파일이 없습니다. 같은 폴더에 있는지 확인하세요.")
    st.stop()


# ══════════════════════════════════════════════════════
#  분석 실행
# ══════════════════════════════════════════════════════

if Run_Btn:
    with st.spinner("📡 데이터 수집 중..."):
        CW = collect_weather(Days, Season, KMA_Key or None, "data/raw")
        W_Raw = CW["data"]

    col_prog = st.empty()
    with col_prog.container():
        prog = st.progress(0, text="데이터 전처리 중...")

    with st.spinner("🔧 데이터 전처리 · 품질 관리 중..."):
        QR = preprocess(W_Raw, "data/processed")
        W_List = QR["data"]
        prog.progress(30, text="토양 데이터 생성 중...")

    with st.spinner("🌱 토양 데이터 생성 중..."):
        GS = generate_soil(W_List, Crop_Type, Init_Moisture, "data/raw")
        SQR = preprocess(GS["data"], "data/processed")
        S_List = SQR["data"]
        prog.progress(55, text="모델 학습 · 검증 중...")

    with st.spinner("🧠 모델 학습 · K-Fold 검증 중..."):
        MR = train_and_validate(W_List, S_List, Crop_Type, "data/model")
        prog.progress(80, text="관수 의사결정 중...")

    with st.spinner("💡 관수 판단 · AI 권고문 생성 중..."):
        Dec = make_decision(
            MR["model"], MR["norm_min"], MR["norm_max"],
            W_List[-1], S_List[-1], W_List, Crop_Type, Area_m2
        )
        Adv = get_advice(Dec, W_List[-1], S_List[-1], Crop_Type, Claude_Key or None)
        prog.progress(100, text="완료!")

    st.session_state.update({
        "weather_list": W_List,
        "soil_list":    S_List,
        "decision":     Dec,
        "advice":       Adv,
        "model_result": MR,
        "quality":      QR,
        "ran_once":     True,
        "source":       CW["source"],
    })
    col_prog.empty()
    st.success(f"✅ 분석 완료! 데이터 출처: **{CW['source']}** | 품질 등급: **{QR['quality_grade']}** ({QR['quality_score']:.0f}점)")


# ══════════════════════════════════════════════════════
#  결과 출력 (Output)
# ══════════════════════════════════════════════════════

if st.session_state["ran_once"] and st.session_state["decision"]:
    Dec    = st.session_state["decision"]
    Adv    = st.session_state["advice"]
    MR     = st.session_state["model_result"]
    W_List = st.session_state["weather_list"]
    S_List = st.session_state["soil_list"]
    W_Today = W_List[-1]
    S_Today = S_List[-1]

    # ── 탭 구성 ──────────────────────────────────────
    Tab1, Tab2, Tab3, Tab4, Tab5 = st.tabs([
        "📊 오늘 분석", "📈 주간 차트", "🔬 모델 검증", "📋 이력", "💾 내보내기"
    ])

    # ════════════ 탭1: 오늘 분석 ════════════
    with Tab1:

        # 관수 상태 카드
        Status = Dec["status"]
        Icon_Map = {"즉시관수": "🚨", "관수권장": "⚠️", "적정상태": "✅", "과습주의": "💧"}
        Icon = Icon_Map.get(Status, "✅")
        st.markdown(
            f'<div class="status-card status-{Status}">'
            f'{Icon} {Status} {Icon}<br>'
            f'<span style="font-size:0.85rem;font-weight:400">{Dec["reason"]}</span>'
            f'</div>',
            unsafe_allow_html=True
        )

        # 긴급도
        Stars = "★" * Dec["urgency"] + "☆" * (5 - Dec["urgency"])
        st.caption(f"긴급도: {Stars}")

        col1, col2 = st.columns(2)

        # ── 왼쪽: 기상 데이터 ──
        with col1:
            st.subheader("🌡 오늘의 기상")
            c1, c2 = st.columns(2)
            c1.metric("평균 온도",  f"{W_Today['평균온도_C']}°C",
                      delta="고온주의" if W_Today['평균온도_C'] > 33 else None,
                      delta_color="inverse")
            c2.metric("상대 습도",  f"{W_Today['상대습도_Pct']}%")
            c1.metric("강수량",     f"{W_Today['강수량_mm']}mm")
            c2.metric("증발산(ET₀)", f"{W_Today['증발산량ET0_mm']}mm")
            c1.metric("풍속",       f"{W_Today['풍속_ms']}m/s")
            c2.metric("일사량",     f"{W_Today['일사량_MJ']}MJ/m²")
            st.caption(f"📡 데이터 출처: {W_Today.get('출처','시뮬레이션')}")

        # ── 오른쪽: 토양 + 게이지 ──
        with col2:
            st.subheader("🌱 토양 수분 상태")
            Mois = Dec["soil_moisture"]
            Mn   = Dec["threshold_min"]
            Op   = Dec["threshold_opt"]
            Mx   = Dec["threshold_max"]
            Arrow_Pct = min(Mois, 100)

            # 프로그레스 바 + 마커
            # Streamlit 내장 progress는 색 지정 불가라 HTML 사용
            st.markdown(f"""
<div class="gauge-wrap">
  <div class="gauge-arrow" style="left: calc({Arrow_Pct}% - 2px)"></div>
</div>
<div class="gauge-labels">
  <span>0%</span>
  <span style="color:#e74c3c">▲최소 {Mn}%</span>
  <span style="color:#27ae60">▲최적 {Op}%</span>
  <span style="color:#2980b9">▲최대 {Mx}%</span>
  <span>100%</span>
</div>
""", unsafe_allow_html=True)

            c3, c4 = st.columns(2)
            c3.metric("토양 수분",   f"{Mois}%",
                      delta=f"{'부족' if Mois < Mn else '과습' if Mois > Mx else '적정'}",
                      delta_color="inverse" if Mois < Mn or Mois > Mx else "off")
            c4.metric("토양 온도",   f"{S_Today['토양온도_C']}°C")
            c3.metric("pH",          f"{S_Today['pH']}")
            c4.metric("EC",          f"{S_Today['전기전도도_dSm']} dS/m")

        st.divider()

        # ── 관수 권고량 ──
        if Status in ("즉시관수", "관수권장"):
            st.subheader("🚿 권장 관수량")
            cc1, cc2, cc3 = st.columns(3)
            cc1.metric("수분 부족량",  f"{Dec['deficit_mm']:.2f} mm")
            cc2.metric("권장 관수량",  f"{Dec['volume_l']:.0f} L",
                       help=f"재배 면적 {Area_m2:.0f}m² 기준")
            cc3.metric("최근 3일 강수", f"{Dec['recent_rain_mm']} mm")
            st.info("⏰ 권장 시간: 이른 아침(06~08시) 또는 저녁(18~20시) | 💡 방식: 점적관수 권장")

        st.divider()

        # ── AI 권고문 ──
        st.subheader("🤖 관수 권고문")
        Src_Label = "Claude AI 생성" if Adv["source"] == "claude_ai" else "규칙 기반 생성"
        st.caption(f"출처: {Src_Label}")
        for Line in Adv["advice"].split("\n"):
            if Line.strip():
                st.markdown(
                    f'<div class="advice-box">{Line}</div>',
                    unsafe_allow_html=True
                )

        # ── 관수 실시 기록 ──
        st.divider()
        st.subheader("📝 오늘 관수 기록")
        with st.form("irrigation_form"):
            Did_Irrigate = st.radio(
                "오늘 관수를 실시하셨나요?",
                ["미실시", "실시"],
                horizontal=True,
            )
            Actual_Vol = st.number_input(
                f"실제 관수량 (L, 권장: {Dec['volume_l']:.0f}L)",
                min_value=0.0, max_value=100000.0,
                value=float(Dec["volume_l"]) if Did_Irrigate == "실시" else 0.0,
                step=10.0,
                disabled=(Did_Irrigate == "미실시"),
            )
            Save_Btn = st.form_submit_button("💾 기록 저장", use_container_width=True)
            if Save_Btn:
                Updated = add_history_record(
                    st.session_state["history"],
                    W_Today["날짜"], Crop_Type, Dec,
                    Did_Irrigate == "실시", Actual_Vol
                )
                st.session_state["history"] = Updated
                st.success("✅ 기록이 저장되었습니다.")

    # ════════════ 탭2: 주간 차트 ════════════
    with Tab2:
        st.subheader("📈 최근 7일 기상 · 토양 수분")

        Last7_W = W_List[-7:]
        Last7_S = S_List[-7:]
        Dates   = [W["날짜"][5:] for W in Last7_W]  # MM-DD

        c_l, c_r = st.columns(2)

        with c_l:
            st.markdown("**기온 변화 (°C)**")
            Temps = [W["평균온도_C"] for W in Last7_W]
            st.line_chart(dict(zip(Dates, Temps)))

            st.markdown("**강수량 (mm)**")
            Rains = [W["강수량_mm"] for W in Last7_W]
            st.bar_chart(dict(zip(Dates, Rains)))

        with c_r:
            st.markdown("**토양 수분 변화 (%)**")
            Moiss = [S["토양수분_Pct"] for S in Last7_S]
            st.line_chart(dict(zip(Dates, Moiss)))

            st.markdown("**ET₀ 증발산량 (mm)**")
            ETs = [W["증발산량ET0_mm"] for W in Last7_W]
            st.bar_chart(dict(zip(Dates, ETs)))

        # 상세 표
        st.markdown("**주간 상세 데이터표**")
        import pandas as pd
        Table_Data = []
        for W, S in zip(Last7_W, Last7_S):
            Mois_V = S["토양수분_Pct"]
            Grade  = "🔴부족" if Mois_V < 40 else "🟡주의" if Mois_V < 55 else "🟢적정" if Mois_V <= 85 else "🔵과습"
            Table_Data.append({
                "날짜":        W["날짜"][5:],
                "평균온도(°C)": W["평균온도_C"],
                "강수량(mm)":   W["강수량_mm"],
                "ET₀(mm)":     W["증발산량ET0_mm"],
                "토양수분(%)":  Mois_V,
                "상태":         Grade,
                "출처":         W.get("출처","시뮬레이션"),
            })
        st.dataframe(pd.DataFrame(Table_Data), use_container_width=True, hide_index=True)

    # ════════════ 탭3: 모델 검증 ════════════
    with Tab3:
        st.subheader("🔬 모델 개발 · 검증 결과")
        CV   = MR["cv_result"]
        FM   = MR["final_metrics"]
        Hist = MR["train_history"]
        Dist = MR["label_dist"]

        col_a, col_b, col_c = st.columns(3)
        col_a.metric("평균 정확도",    f"{CV['mean_accuracy']:.1%}")
        col_b.metric("평균 F1-Score",  f"{CV['mean_f1']:.3f}")
        col_c.metric("정확도 편차",    f"{CV['std_accuracy']:.3f}",
                     help="낮을수록 안정적인 모델")

        st.caption(f"검증 방법: {CV['method']}")

        c_left, c_right = st.columns(2)

        with c_left:
            st.markdown("**학습 곡선 (에포크별 정확도 %)**")
            if Hist:
                st.line_chart({f"Epoch {I+1}": V for I, V in enumerate(Hist)})

            st.markdown("**레이블 분포**")
            if Dist:
                st.bar_chart(Dist)

        with c_right:
            st.markdown("**클래스별 성능**")
            Cm_Data = FM.get("class_metrics", {})
            if Cm_Data:
                import pandas as pd
                Rows = []
                for Lbl, M in Cm_Data.items():
                    Rows.append({"클래스": Lbl, "정밀도": M["Precision"],
                                 "재현율": M["Recall"], "F1": M["F1"],
                                 "샘플수": M["Support"]})
                st.dataframe(pd.DataFrame(Rows), use_container_width=True, hide_index=True)

            st.markdown("**혼동 행렬**")
            CM = FM.get("confusion_matrix", [])
            if CM:
                import pandas as pd
                Labels = ["즉시관수", "관수권장", "적정상태", "과습주의"]
                DF_CM  = pd.DataFrame(CM, index=Labels, columns=Labels)
                st.dataframe(DF_CM, use_container_width=True)
                st.caption("행=실제 / 열=예측")

        F1_Val = CV.get("mean_f1", 0)
        if F1_Val >= 0.7:
            st.success("✅ 모델 품질 양호 (F1 ≥ 0.7) — 실사용 가능")
        elif F1_Val >= 0.5:
            st.warning("⚠️ 모델 개선 필요 — 더 많은 데이터 수집 권장")
        else:
            st.error("❌ 모델 품질 불량 — 재학습 필요")

    # ════════════ 탭4: 이력 ════════════
    with Tab4:
        st.subheader("📋 관수 이력")
        History = st.session_state["history"]

        if not History:
            st.info("아직 기록된 이력이 없습니다. 분석 후 탭1에서 관수 여부를 기록하세요.")
        else:
            import pandas as pd
            Stats = calc_stats(History)

            s1, s2, s3, s4 = st.columns(4)
            s1.metric("총 기록",    f"{Stats['total']}건")
            s2.metric("관수 횟수",  f"{Stats['irrigated']}회")
            s3.metric("총 관수량",  f"{Stats['total_vol_L']:,.0f}L")
            s4.metric("절약 추정",  f"{Stats['saved_vol_L']:,.0f}L")

            st.markdown("**상태별 분포**")
            if Stats["status_dist"]:
                st.bar_chart(Stats["status_dist"])

            st.markdown("**상세 이력**")
            DF_H = pd.DataFrame(History[-20:])
            st.dataframe(DF_H, use_container_width=True, hide_index=True)

    # ════════════ 탭5: 내보내기 ════════════
    with Tab5:
        st.subheader("💾 데이터 내보내기")

        st.info("""
**CSV** → Claude(LLM) 분석에 최적화 — 텍스트 기반으로 AI가 읽기 쉬움
**Excel** → 수치 직접 수정, 셀 서식 · 차트 활용 시 편리
        """)

        if st.button("📥 파일 생성", use_container_width=True, type="primary"):
            ER = export_data(
                W_List, S_List,
                st.session_state["history"],
                "smart_irrigation_export"
            )
            st.success(ER["log"])
            for P in ER.get("csv_paths", []):
                st.code(f"CSV:   {P}")
            for P in ER.get("xlsx_paths", []):
                st.code(f"Excel: {P}")

        st.divider()
        st.subheader("📖 데이터 출처 (보고서 기재용)")
        st.markdown("""
| 출처 | 설명 | URL |
|------|------|-----|
| 기상청 기상자료개방포털 | ASOS 자동기상관측 일별 데이터 | https://data.kma.go.kr |
| 공공데이터포털 | 기상청 단기예보 조회서비스 | https://data.go.kr |
| WAMIS 한국수자원공사 | 강수량·기온·습도 일별 자료 | https://wamis.go.kr |
| 시뮬레이션 (Fallback) | 계절별 통계 파라미터 기반 생성 | — |
        """)

else:
    # 첫 실행 전 안내 화면
    st.markdown("---")
    col_guide1, col_guide2 = st.columns(2)

    with col_guide1:
        st.markdown("### 🚀 시작하는 방법")
        st.markdown("""
1. **왼쪽 사이드바**에서 작물·계절 선택
2. (선택) 기상청 API 키 입력
3. **분석 실행** 버튼 클릭
4. 결과를 탭별로 확인
        """)

    with col_guide2:
        st.markdown("### 📱 스마트폰 접속 방법")
        st.markdown("""
**PC와 같은 WiFi일 때:**
```
http://[PC의 IP 주소]:8501
```
예) `http://192.168.1.5:8501`

**어디서나 접속하려면:**
→ streamlit.io 에 GitHub로 배포
→ 공개 URL로 스마트폰에서 바로 접속
        """)

    st.markdown("---")
    st.markdown("### 🌾 프로그램 구조")
    st.markdown("""
```
FRONTEND (ui 화면)        BACKEND (연산·저장)
app_streamlit.py    ←→   backend_logic.py
  - 사이드바 입력              - 기상청 API 수집
  - 결과 시각화               - 데이터 전처리
  - 탭 구성                  - 모델 학습·검증
  - 차트·표                  - 관수 의사결정
```
    """)
