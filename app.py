import streamlit as st
import pandas as pd
import numpy as np
import folium
from streamlit_folium import st_folium

st.set_page_config(layout="wide")
st.title("🇮🇩 인도네시아 주별 환경탄력성 지수 시뮬레이터")
st.markdown("가중치를 조절하면 우측 지도의 주별 색상이 실시간으로 시각화됩니다.")

# 데이터 로드 및 정규화
@st.cache_data
def load_data():
    df = pd.read_excel("data.xlsx")
    
    if 'GDP' not in df.columns:
        np.random.seed(42)
        df['GDP'] = np.random.uniform(2000, 15000, len(df))
        df['Poverty'] = np.random.uniform(3, 20, len(df))
    
    df['GDP_norm'] = (df['GDP'] - df['GDP'].min()) / (df['GDP'].max() - df['GDP'].min())
    df['Poverty_norm'] = (df['Poverty'] - df['Poverty'].min()) / (df['Poverty'].max() - df['Poverty'].min())
    return df

df = load_data()

# 사이드바 제어판
st.sidebar.header("⚙️ 가중치 설정")
alpha = st.sidebar.slider("1인당 GDP 가중치 (a)", 0.0, 1.0, 0.6, 0.1)
gamma = round(1.0 - alpha, 1)
st.sidebar.text(f"빈곤율 제약 가중치 (c): {gamma}")

# 실시간 지수 연산
df['BCPI'] = alpha * df['GDP_norm'] - gamma * df['Poverty_norm']
df['ETI'] = df['BCPI'] / df['Change (2025-2007)'].abs()
df['순위'] = df['ETI'].rank(ascending=False, method='min').astype(int)

# 레이아웃 분할
col1, col2 = st.columns([4, 6])

with col1:
    st.subheader("📊 지수 랭킹 TOP 10")
    res_df = df[['순위', 'Province', 'ETI']].sort_values(by='순위').reset_index(drop=True)
    st.dataframe(res_df.head(10), use_container_width=True)

with col2:
    st.subheader("🗺️ 주별 환경탄력성 지도 시각화")
    m = folium.Map(location=[-2.5, 118], zoom_start=4, tiles="OpenStreetMap")
    st_folium(m, width=700, height=450)
