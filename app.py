"""
app.py  —  스마트 관수 시스템 (Streamlit Cloud 전용)
=====================================================
📁 저장 위치: backend.py 와 같은 폴더
▶  로컬 실행:  streamlit run app.py
🌐 배포 URL:   https://smart-irrigation-app.streamlit.app

[Streamlit Cloud 핵심 규칙]
- API 키는 반드시 st.secrets["키이름"] 으로 읽기
- os.environ 은 Streamlit Cloud 에서 작동 안 함
- 분석 실행 버튼 클릭 시점에 키를 읽어야 캐시 문제 없음
"""

import os
import datetime
import streamlit as st

# ── 페이지 설정 ──────────────────────────────────────
st.set_page_config(
    page_title="🌾 스마트 관수 시스템",
    page_icon="🌾",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Backend 임포트 ────────────────────────────────────
try:
    from backend import (
        CROP_THRESHOLDS, collect_weather, generate_soil,
        preprocess, train_and_validate, make_decision,
        get_advice, load_history, add_history_record,
        calc_stats, export_data,
    )
    BACKEND_OK = True
except ImportError as E:
    BACKEND_OK = False
    st.error(f"❌ backend.py 를 찾을 수 없습니다: {E}")
    st.stop()


# ══════════════════════════════════════════════════════
#  핵심 함수: Secrets 에서 키 읽기
#  Streamlit Cloud → 로컬 환경변수 순서로 읽음
# ══════════════════════════════════════════════════════

def get_secret(Key_Name: str) -> str:
    """
    [워크플로우]
    ◇ Streamlit Secrets에 키 있음?
      Yes → 키 반환
      No  ◇ 환경변수에 키 있음?
              Yes → 키 반환
              No  → 빈 문자열 반환
    """
    try:
        Value = st.secrets[Key_Name]
        if Value:
            return Value
    except Exception:
        pass
    return os.environ.get(Key_Name, "")


# ══════════════════════════════════════════════════════
#  CSS 스타일
# ══════════════════════════════════════════════════════

st.markdown("""
<style>
.status-card {
    padding: 1.2rem 1.5rem; border-radius: 14px;
    margin: 0.5rem 0 1rem; font-size: 1.15rem;
    font-weight: 600; text-align: center;
}
.status-즉시관수 { background:#ffe0e0; color:#c0392b; border:2px solid #e74c3c; }
.status-관수권장 { background:#fff3cd; color:#856404; border:2px solid #ffc107; }
.status-적정상태 { background:#d4edda; color:#155724; border:2px solid #28a745; }
.status-과습주의 { background:#cce5ff; color:#004085; border:2px solid #0d6efd; }
.advice-box {
    background: var(--secondary-background-color);
    border-left: 4px solid #27ae60;
    border-radius: 0 10px 10px 0;
    padding: 1rem 1.2rem; margin: 0.5rem 0;
    line-height: 1.7; font-size: 0.95rem;
}
.gauge-wrap {
    position: relative; height: 28px; border-radius: 8px;
    background: linear-gradient(to right,
        #e74c3c 0%, #e74c3c 40%,
        #f39c12 40%, #f39c12 55%,
        #27ae60 55%, #27ae60 80%,
        #2980b9 80%, #2980b9 100%);
    margin: 0.4rem 0;
}
.gauge-arrow {
    position: absolute; top: 0; width: 4px; height: 28px;
    background: white; border-radius: 2px;
    box-shadow: 0 0 4px rgba(0,0,0,0.5);
}
@media (max-width: 600px) { .status-card { font-size: 1rem; } }
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════
#  세션 상태 초기화
# ══════════════════════════════════════════════════════

if "history" not in st.session_state:
    st.session_state["history"] = load_history()
if "results" not in st.session_state:
    st.session_state["results"] = None


# ══════════════════════════════════════════════════════
#  사이드바 (Input)
# ══════════════════════════════════════════════════════

with st.sidebar:
    st.title("⚙️ 설정")

    st.subheader("🌾 작물 · 환경")
    Crop_Type = st.selectbox("작물 선택", list(CROP_THRESHOLDS.keys()), index=6)
    Season    = st.selectbox("계절", ["봄", "여름", "가을", "겨울"], index=1)
    Area_m2   = st.number_input("재배 면적 (m²)", min_value=10.0, value=1000.0, step=100.0)
    Init_Mois = st.slider("현재 토양 수분 추정 (%)", 10, 100, 65)
    Days      = st.slider("데이터 수집 기간 (일)", 5, 60, 30)

    st.divider()
    st.subheader("🔑 API 키 설정")
    st.caption("Streamlit Cloud Secrets 에 저장된 키가 자동으로 사용됩니다.")

    # 사이드바에는 표시만 (실제 사용은 버튼 클릭 시점에 읽음)
    KMA_Display    = "●●●●● (Secrets 등록됨)" if get_secret("KMA_API_KEY")    else ""
    Claude_Display = "●●●●● (Secrets 등록됨)" if get_secret("ANTHROPIC_API_KEY") else ""

    KMA_Input = st.text_input(
        "기상청 API 키 (직접 입력 시)",
        value=KMA_Display,
        type="password",
        help="비워두면 Secrets 에서 자동으로 읽음"
    )
    Claude_Input = st.text_input(
        "Claude AI 키 (직접 입력 시)",
        value=Claude_Display,
        type="password",
        help="비워두면 Secrets 에서 자동으로 읽음"
    )

    st.divider()
    Run_Btn = st.button("🚀 분석 실행", use_container_width=True, type="primary")

    # 연동 상태 표시
    KMA_OK = bool(get_secret("KMA_API_KEY") or (KMA_Input and "●" not in KMA_Input))
    if KMA_OK:
        st.success("✅ 기상청 API 연동됨")
    else:
        st.info("ℹ️ 시뮬레이션 데이터 사용")


# ══════════════════════════════════════════════════════
#  헤더
# ══════════════════════════════════════════════════════

st.title("🌾 스마트 관수 시스템")
st.caption(f"기상 · 토양 데이터 기반 농업 용수 관리 | {datetime.date.today()}")


# ══════════════════════════════════════════════════════
#  분석 실행 (버튼 클릭 시점에 Secrets 읽기)
# ══════════════════════════════════════════════════════

if Run_Btn:
    # ◇ Secrets / 직접입력 키 결정
    # Secrets 우선 → 직접 입력 → None
    KMA_Key    = get_secret("KMA_API_KEY")
    Claude_Key = get_secret("ANTHROPIC_API_KEY")

    # 직접 입력한 경우 (●이 없는 실제 키값)
    if KMA_Input and "●" not in KMA_Input and KMA_Input.strip():
        KMA_Key = KMA_Input.strip()
    if Claude_Input and "●" not in Claude_Input and Claude_Input.strip():
        Claude_Key = Claude_Input.strip()

    KMA_Key    = KMA_Key    or None
    Claude_Key = Claude_Key or None

    # ── 진행 바 ──────────────────────────────────────
    Progress = st.progress(0, text="1단계: 데이터 수집 중...")

    # ── 1단계: 데이터 수집 ───────────────────────────
    with st.spinner("📡 기상 데이터 수집 중..."):
        CW     = collect_weather(Days, Season, KMA_Key, "data/raw")
        W_Raw  = CW["data"]
        Source = CW["source"]
    Progress.progress(20, text="2단계: 데이터 전처리 중...")

    # ── 2단계: 전처리 ────────────────────────────────
    with st.spinner("🔧 데이터 전처리 · 품질 관리 중..."):
        QR     = preprocess(W_Raw, "data/processed")
        W_List = QR["data"]
        GS     = generate_soil(W_List, Crop_Type, Init_Mois, "data/raw")
        SQR    = preprocess(GS["data"], "data/processed")
        S_List = SQR["data"]
    Progress.progress(50, text="3단계: 모델 학습 · 검증 중...")

    # ── 3~4단계: 모델 ────────────────────────────────
    with st.spinner("🧠 모델 학습 · K-Fold 검증 중..."):
        MR = train_and_validate(W_List, S_List, Crop_Type, "data/model")
    Progress.progress(75, text="5단계: 관수 의사결정 중...")

    # ── 5단계: 의사결정 ──────────────────────────────
    with st.spinner("💡 관수 판단 · 권고문 생성 중..."):
        Dec = make_decision(
            MR["model"], MR["norm_min"], MR["norm_max"],
            W_List[-1], S_List[-1], W_List, Crop_Type, Area_m2
        )
        Adv = get_advice(Dec, W_List[-1], S_List[-1], Crop_Type, Claude_Key)
    Progress.progress(100, text="✅ 분석 완료!")

    # 결과 저장
    st.session_state["results"] = {
        "W_List": W_List, "S_List": S_List,
        "Dec": Dec, "Adv": Adv, "MR": MR,
        "Source": Source, "Grade": QR["quality_grade"],
        "Score": QR["quality_score"],
    }

    st.success(
        f"✅ 분석 완료! "
        f"데이터 출처: **{Source}** | "
        f"품질 등급: **{QR['quality_grade']}** ({QR['quality_score']:.0f}점)"
    )


# ══════════════════════════════════════════════════════
#  결과 출력 (Output)
# ══════════════════════════════════════════════════════

if st.session_state["results"]:
    R      = st.session_state["results"]
    Dec    = R["Dec"]
    Adv    = R["Adv"]
    MR     = R["MR"]
    W_List = R["W_List"]
    S_List = R["S_List"]
    W_Today = W_List[-1]
    S_Today = S_List[-1]

    Tab1, Tab2, Tab3, Tab4, Tab5 = st.tabs([
        "📊 오늘 분석", "📈 주간 차트", "🔬 모델 검증", "📋 이력", "💾 내보내기"
    ])

    # ════ 탭1: 오늘 분석 ════
    with Tab1:
        Status   = Dec["status"]
        Icon_Map = {"즉시관수": "🚨", "관수권장": "⚠️", "적정상태": "✅", "과습주의": "💧"}
        Icon     = Icon_Map.get(Status, "✅")

        st.markdown(
            f'<div class="status-card status-{Status}">'
            f'{Icon} {Status} {Icon}<br>'
            f'<span style="font-size:0.85rem;font-weight:400">{Dec["reason"]}</span>'
            f'</div>', unsafe_allow_html=True
        )
        Stars = "★" * Dec["urgency"] + "☆" * (5 - Dec["urgency"])
        st.caption(f"긴급도: {Stars}")

        Col1, Col2 = st.columns(2)

        with Col1:
            st.subheader("🌡 오늘의 기상")
            C1, C2 = st.columns(2)
            C1.metric("평균 온도",  f"{W_Today['평균온도_C']}°C",
                      delta="고온주의" if W_Today['평균온도_C'] > 33 else None,
                      delta_color="inverse")
            C2.metric("상대 습도",  f"{W_Today['상대습도_Pct']}%")
            C1.metric("강수량",     f"{W_Today['강수량_mm']}mm")
            C2.metric("증발산(ET₀)", f"{W_Today['증발산량ET0_mm']}mm")
            C1.metric("풍속",       f"{W_Today['풍속_ms']}m/s")
            C2.metric("일사량",     f"{W_Today['일사량_MJ']}MJ/m²")
            st.caption(f"📡 데이터 출처: {W_Today.get('출처','시뮬레이션')}")

        with Col2:
            st.subheader("🌱 토양 수분 상태")
            Mois = Dec["soil_moisture"]
            st.markdown(
                f'<div class="gauge-wrap">'
                f'<div class="gauge-arrow" style="left:calc({min(Mois,100)}% - 2px)"></div>'
                f'</div>'
                f'<div style="display:flex;justify-content:space-between;font-size:0.7rem;color:#888">'
                f'<span>0%</span>'
                f'<span style="color:#e74c3c">▲최소 {Dec["threshold_min"]}%</span>'
                f'<span style="color:#27ae60">▲최적 {Dec["threshold_opt"]}%</span>'
                f'<span style="color:#2980b9">▲최대 {Dec["threshold_max"]}%</span>'
                f'<span>100%</span></div>',
                unsafe_allow_html=True
            )
            C3, C4 = st.columns(2)
            Mois_Delta = "부족" if Mois < Dec["threshold_min"] else "과습" if Mois > Dec["threshold_max"] else "적정"
            C3.metric("토양 수분", f"{Mois}%", delta=Mois_Delta,
                      delta_color="inverse" if Mois_Delta != "적정" else "off")
            C4.metric("토양 온도", f"{S_Today['토양온도_C']}°C")
            C3.metric("pH",        f"{S_Today['pH']}")
            C4.metric("EC",        f"{S_Today['전기전도도_dSm']} dS/m")

        st.divider()

        if Status in ("즉시관수", "관수권장"):
            st.subheader("🚿 권장 관수량")
            CC1, CC2, CC3 = st.columns(3)
            CC1.metric("수분 부족량",   f"{Dec['deficit_mm']:.2f} mm")
            CC2.metric("권장 관수량",   f"{Dec['volume_l']:.0f} L")
            CC3.metric("최근 3일 강수", f"{Dec['recent_rain_mm']} mm")
            st.info("⏰ 권장 시간: 이른 아침(06~08시) 또는 저녁(18~20시) | 💡 방식: 점적관수")

        st.divider()
        st.subheader("🤖 관수 권고문")
        Src = "Claude AI 생성" if Adv["source"] == "claude_ai" else "규칙 기반 생성"
        st.caption(f"출처: {Src}")
        for Line in Adv["advice"].split("\n"):
            if Line.strip():
                st.markdown(f'<div class="advice-box">{Line}</div>', unsafe_allow_html=True)

        st.divider()
        st.subheader("📝 오늘 관수 기록")
        with st.form("form_record"):
            Did = st.radio("오늘 관수를 실시하셨나요?", ["미실시", "실시"], horizontal=True)
            Vol = st.number_input(
                f"실제 관수량 (L, 권장: {Dec['volume_l']:.0f}L)",
                min_value=0.0, value=float(Dec["volume_l"]) if Did == "실시" else 0.0,
                step=10.0, disabled=(Did == "미실시")
            )
            if st.form_submit_button("💾 기록 저장", use_container_width=True):
                st.session_state["history"] = add_history_record(
                    st.session_state["history"],
                    W_Today["날짜"], Crop_Type, Dec,
                    Did == "실시", Vol
                )
                st.success("✅ 기록 저장 완료!")

    # ════ 탭2: 주간 차트 ════
    with Tab2:
        st.subheader("📈 최근 7일 기상 · 토양 수분")
        Last7W = W_List[-7:]
        Last7S = S_List[-7:]
        Dates  = [W["날짜"][5:] for W in Last7W]
        CL, CR = st.columns(2)
        with CL:
            st.markdown("**기온 변화 (°C)**")
            st.line_chart({D: T for D, T in zip(Dates, [W["평균온도_C"] for W in Last7W])})
            st.markdown("**강수량 (mm)**")
            st.bar_chart({D: T for D, T in zip(Dates, [W["강수량_mm"] for W in Last7W])})
        with CR:
            st.markdown("**토양 수분 (%)**")
            st.line_chart({D: T for D, T in zip(Dates, [S["토양수분_Pct"] for S in Last7S])})
            st.markdown("**ET₀ 증발산량 (mm)**")
            st.bar_chart({D: T for D, T in zip(Dates, [W["증발산량ET0_mm"] for W in Last7W])})

        import pandas as pd
        Table = []
        for W, S in zip(Last7W, Last7S):
            M = S["토양수분_Pct"]
            G = "🔴부족" if M < 40 else "🟡주의" if M < 55 else "🟢적정" if M <= 85 else "🔵과습"
            Table.append({"날짜": W["날짜"][5:], "평균온도(°C)": W["평균온도_C"],
                          "강수량(mm)": W["강수량_mm"], "ET₀(mm)": W["증발산량ET0_mm"],
                          "토양수분(%)": M, "상태": G, "출처": W.get("출처","시뮬레이션")})
        st.dataframe(pd.DataFrame(Table), use_container_width=True, hide_index=True)

    # ════ 탭3: 모델 검증 ════
    with Tab3:
        st.subheader("🔬 모델 개발 · 검증 결과")
        CV = MR["cv_result"]
        FM = MR["final_metrics"]
        MA, MB, MC = st.columns(3)
        MA.metric("평균 정확도",   f"{CV['mean_accuracy']:.1%}")
        MB.metric("평균 F1-Score", f"{CV['mean_f1']:.3f}")
        MC.metric("정확도 편차",   f"{CV['std_accuracy']:.3f}")
        st.caption(f"검증 방법: {CV['method']}")

        CLA, CRA = st.columns(2)
        with CLA:
            st.markdown("**학습 곡선**")
            if MR["train_history"]:
                st.line_chart({"정확도(%)": MR["train_history"]})
            st.markdown("**레이블 분포**")
            if MR["label_dist"]:
                st.bar_chart(MR["label_dist"])
        with CRA:
            st.markdown("**클래스별 성능**")
            if FM.get("class_metrics"):
                import pandas as pd
                Rows = [{"클래스": L, "정밀도": M["Precision"],
                         "재현율": M["Recall"], "F1": M["F1"], "샘플수": M["Support"]}
                        for L, M in FM["class_metrics"].items()]
                st.dataframe(pd.DataFrame(Rows), use_container_width=True, hide_index=True)
            st.markdown("**혼동 행렬**")
            CM = FM.get("confusion_matrix", [])
            if CM:
                import pandas as pd
                Labels = ["즉시관수", "관수권장", "적정상태", "과습주의"]
                st.dataframe(pd.DataFrame(CM, index=Labels, columns=Labels), use_container_width=True)

        F1 = CV.get("mean_f1", 0)
        if F1 >= 0.7:   st.success("✅ 모델 품질 양호 (F1 ≥ 0.7)")
        elif F1 >= 0.5: st.warning("⚠️ 모델 개선 필요")
        else:           st.error("❌ 모델 품질 불량")

    # ════ 탭4: 이력 ════
    with Tab4:
        st.subheader("📋 관수 이력")
        History = st.session_state["history"]
        if not History:
            st.info("아직 기록이 없습니다. 탭1에서 관수 여부를 기록하세요.")
        else:
            import pandas as pd
            Stats = calc_stats(History)
            S1, S2, S3, S4 = st.columns(4)
            S1.metric("총 기록",   f"{Stats['total']}건")
            S2.metric("관수 횟수", f"{Stats['irrigated']}회")
            S3.metric("총 관수량", f"{Stats['total_vol_L']:,.0f}L")
            S4.metric("절약 추정", f"{Stats['saved_vol_L']:,.0f}L")
            if Stats["status_dist"]:
                st.bar_chart(Stats["status_dist"])
            st.dataframe(pd.DataFrame(History[-20:]), use_container_width=True, hide_index=True)

    # ════ 탭5: 내보내기 ════
    with Tab5:
        st.subheader("💾 데이터 내보내기")
        st.info("CSV → LLM(Claude) 분석용 | Excel → 수치 조정용")
        if st.button("📥 파일 생성", use_container_width=True, type="primary"):
            ER = export_data(W_List, S_List, st.session_state["history"], "export")
            st.success(ER["log"])
            for P in ER.get("csv_paths", []):  st.code(f"CSV:   {P}")
            for P in ER.get("xlsx_paths", []): st.code(f"Excel: {P}")

        st.divider()
        st.subheader("📖 데이터 출처")
        st.markdown("""
| 출처 | URL |
|---|---|
| 기상청 기상자료개방포털 | https://data.kma.go.kr |
| 공공데이터포털 | https://data.go.kr |
| WAMIS 한국수자원공사 | https://wamis.go.kr |
        """)

else:
    # 첫 실행 전 안내
    st.markdown("---")
    C1, C2 = st.columns(2)
    with C1:
        st.markdown("### 🚀 시작하는 방법")
        st.markdown("""
1. 왼쪽 사이드바에서 작물·계절 선택
2. 🚀 **분석 실행** 버튼 클릭
3. 결과를 탭별로 확인
        """)
    with C2:
        st.markdown("### 📱 스마트폰 접속")
        st.markdown("""
이 앱의 URL을 폰 브라우저에 입력하면
PC 없이도 언제든 접속 가능합니다.

```
https://smart-irrigation-app.streamlit.app
```
        """)
