import streamlit as st
import pandas as pd

# 1. 페이지 레이아웃 및 타이틀
st.set_page_config(layout="wide")
st.title("🇮🇩 인도네시아 주별 환경탄력성 지수 시뮬레이터")
st.markdown("가중치를 조절하며 주별 소비잠재력 및 최종 환경탄력성 지수의 변화를 모니터링하세요.")

# 2. 데이터 불러오기 (엑셀 파일명을 data.xlsx로 통일)
@st.cache_data
def load_data():
    df = pd.read_excel("data.xlsx")
    # 예시를 위해 GDP와 빈곤율 가상 데이터 매핑 (실제 데이터 확보 시 이 부분을 교체)
    # 실제 엑셀에 GDP, Poverty 열이 들어오면 pd.read_excel로 그냥 읽으면 됨
    if 'GDP' not in df.columns:
        import numpy as np
        np.random.seed(42)
        df['GDP'] = np.random.uniform(2000, 15000, len(df)) # 가상 1인당 GDP
        df['Poverty'] = np.random.uniform(3, 20, len(df))     # 가상 빈곤율(%)
    return df

df = load_data()

# 3. 사이드바 - 가중치 조절 슬라이더
st.sidebar.header("⚙️ 가중치 설정 (Weight Settings)")
alpha = st.sidebar.slider("1인당 GDP 가중치 (a)", 0.0, 1.0, 0.6, 0.05)
# 두 가중치의 합이 1이 되도록 자동 계산
gamma = round(1.0 - alpha, 2)
st.sidebar.text(f"빈곤율 제약 가중치 (c): {gamma}")

# 4. 데이터 연산 프로세스
# 데이터 정규화 (Min-Max Scaling) - 지수 산출을 위한 필수 과정
df['GDP_norm'] = (df['GDP'] - df['GDP'].min()) / (df['GDP'].max() - df['GDP'].min())
df['Poverty_norm'] = (df['Poverty'] - df['Poverty'].min()) / (df['Poverty'].max() - df['Poverty'].min())

# 소비잠재력지수(BCPI) 계산: a*GDP - c*Poverty
df['BCPI'] = alpha * df['GDP_norm'] - gamma * df['Poverty_norm']

# 환경탄력성 지수(ETI) 계산: BCPI / 기온 변화량
# 분모가 0이 되거나 마이너스 표시 서식 버그 방지를 위해 절대값 처리 혹은 조건 부여 가능
df['Environmental_Elasticity'] = df['BCPI'] / df['Change (2025-2007)'].abs()

# 순위 매기기
df['순위'] = df['Environmental_Elasticity'].rank(ascending=False, method='min').astype(int)

# 5. 결과 화면 시각화
col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("📊 가중치 반영 지수 데이터 TOP 10")
    display_df = df[['순위', 'Province', 'Environmental_Elasticity', 'BCPI', 'Change (2025-2007)']]
    st.dataframe(display_df.sort_values(by='순위').reset_index(drop=True).head(10), use_container_width=True)

with col2:
    st.subheader("📈 환경탄력성 지수 상위 노출 그래프")
    chart_data = df.sort_values(by='Environmental_Elasticity', ascending=False).head(15)
    st.bar_chart(data=chart_data, x='Province', y='Environmental_Elasticity', color="#2b5c8f")

st.info("💡 슬라이더를 움직이면 상위권 주의 순위와 그래프 뼈대가 실시간으로 리렌더링됩니다. (민감도 분석 기능)")