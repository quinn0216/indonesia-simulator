import streamlit as st
import pandas as pd
import numpy as np
import folium
import json
import os
from streamlit_folium import st_folium

st.set_page_config(layout="wide")
st.title("🇮🇩 인도네시아 주별 환경탄력성 지수 시뮬레이터")
st.markdown("가중치를 조절하면 우측 지도의 주별 색상과 좌측 랭킹이 실시간으로 시각화됩니다.")

@st.cache_data
def load_safe_data():
    # 1. 기온 데이터 로드 (A열: 주 이름, D열: 기온 변화량)
    df_temp = pd.read_excel("data.xlsx")
    
    # 임시 df 생성 (열 이름을 번호로 접근하기 위해 복사)
    df = pd.DataFrame()
    df['Province'] = df_temp.iloc[:, 0].astype(str).str.strip()  # A열: 주 이름
    df['Temp_Change'] = pd.to_numeric(df_temp.iloc[:, 3], errors='coerce')  # D열: Change (2025-2007)
    
    # 2. 변수 데이터 로드 (A열: 주 이름, C열: GDP 2025, E열: 빈곤율 2025)
    try:
        df_vars = pd.read_excel("variables.xlsx")
        df_vars['Join_Key'] = df_vars.iloc[:, 0].astype(str).str.replace(r'\s+', '', regex=True).str.lower()
        df['Join_Key'] = df['Province'].str.replace(r'\s+', '', regex=True).str.lower()
        
        # 필요한 열만 추출 (A열 Key, C열 GDP 2025, E열 빈곤율 2025)
        var_subset = pd.DataFrame({
            'Join_Key': df_vars['Join_Key'],
            'GDP_val': pd.to_numeric(df_vars.iloc[:, 2], errors='coerce'),  # C열: 1인당 GDP(2025)
            'Pov_val': pd.to_numeric(df_vars.iloc[:, 4], errors='coerce')   # E열: 빈곤율(2025)
        })
        
        # 주 이름을 기준으로 결합
        df = pd.merge(df, var_subset, on='Join_Key', how='left')
    except Exception as e:
        st.error(f"variables.xlsx 매핑 실패: {e}")
        df['GDP_val'] = np.random.uniform(2000, 15000, len(df))
        df['Pov_val'] = np.random.uniform(3, 20, len(df))
        
    # 결측치 보정
    df['GDP_val'] = df['GDP_val'].fillna(df['GDP_val'].mean() if df['GDP_val'].mean() > 0 else 5000)
    df['Pov_val'] = df['Pov_val'].fillna(df['Pov_val'].mean() if df['Pov_val'].mean() > 0 else 10)
    df['Temp_Change'] = df['Temp_Change'].fillna(0.5)
    
    # 0~1 정규화
    df['GDP_norm'] = (df['GDP_val'] - df['GDP_val'].min()) / (df['GDP_val'].max() - df['GDP_val'].min() + 1e-5)
    df['Poverty_norm'] = (df['Pov_val'] - df['Pov_val'].min()) / (df['Pov_val'].max() - df['Pov_val'].min() + 1e-5)
    return df

try:
    df = load_safe_data()
    geojson_path = "indonesia.geojson"
    if not os.path.exists(geojson_path) and os.path.exists("indonesia.geojson.json"):
        geojson_path = "indonesia.geojson.json"
        
    with open(geojson_path, "r", encoding="utf-8") as f:
        geo_data = json.load(f)
except Exception as e:
    st.error(f"초기 파일 로딩 실패: {e}")
    st.stop()

# 사이드바 설정창
st.sidebar.header("⚙️ 가중치 설정")
alpha = st.sidebar.slider("1인당 GDP 가중치 (a)", 0.0, 1.0, 0.6, 0.1)
gamma = st.sidebar.slider("빈곤율 제약 가중치 (c)", 0.0, 1.0, 0.4, 0.1)

# BCPI = a * GDP - c * Poverty
df['BCPI'] = (alpha * df['GDP_norm']) - (gamma * df['Poverty_norm'])
# ETI = BCPI / |기온변화값|
df['ETI'] = df['BCPI'] / (df['Temp_Change'].abs() + 1e-5)
df['순위'] = df['ETI'].rank(ascending=False, method='min').astype(int)

# 뷰 포트 레이아웃 분할
col1, col2 = st.columns([4, 6])

with col1:
    st.subheader("📊 시뮬레이션 결과 랭킹")
    res_df = df[['순위', 'Province', 'BCPI', 'Temp_Change', 'ETI']].copy()
    res_df = res_df.sort_values(by='순위').reset_index(drop=True)
    res_df.columns = ['순위', '주(Province)', 'BCPI', '기온 변화량', '환경탄력성(ETI)']
    st.dataframe(res_df, use_container_width=True, height=500)

with col2:
    st.subheader("🗺️ 인도네시아 주별 환경탄력성 지도")
    m = folium.Map(location=[-2.5, 118], zoom_start=4, tiles="OpenStreetMap")
    
    # 수치 범위에 맞춘 동적 컬러 레벨 생성 (색상이 탁하게 뭉치는 현상 방지)
    threshold_scale = list(df['ETI'].quantile([0, 0.25, 0.5, 0.75, 1]))
    if len(set(threshold_scale)) < 5:
        threshold_scale = np.linspace(df['ETI'].min(), df['ETI'].max(), 5).tolist()

    folium.Choropleth(
        geo_data=geo_data,
        name="환경탄력성지수(ETI)",
        data=df,
        columns=["Province", "ETI"],
        key_on="feature.properties.NAME_1",
        fill_color="YlOrRd",
        fill_opacity=0.7,
        line_opacity=0.4,
        threshold_scale=threshold_scale,
        legend_name="환경탄력성지수 (ETI)",
    ).add_to(m)
    
    st_folium(m, width="100%", height=500)
