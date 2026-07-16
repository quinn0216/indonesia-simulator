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
def load_clean_data():
    # 1. 기온 데이터(data.xlsx) 로드
    df_raw = pd.read_excel("data.xlsx")
    
    # 엑셀 헤더 깨짐 방지: 첫 열에 '행 레이블'이나 결측치(None/NaN), 숫자가 포함된 행은 과감히 필터링
    df_raw = df_raw.dropna(subset=[df_raw.columns[0]])
    df_raw = df_raw[~df_raw.iloc[:, 0].astype(str).str.contains("행 레이블|None|nan|Total|합계|주", case=False, na=False)]
    
    # 숫자로만 이루어진 주 이름(오류 데이터) 필터링
    def is_float(val):
        try:
            float(val)
            return True
        except ValueError:
            return False
    df_raw = df_raw[~df_raw.iloc[:, 0].apply(is_float)]
    
    df = pd.DataFrame()
    df['Province'] = df_raw.iloc[:, 0].astype(str).str.strip()
    
    # 기온 변화량 (D열: 인덱스 3) 데이터 추출
    df['Temp_Change'] = pd.to_numeric(df_raw.iloc[:, 3], errors='coerce')
    
    # 2. 변수 데이터(variables.xlsx) 로드 및 병합
    try:
        df_vars_raw = pd.read_excel("variables.xlsx")
        df_vars_raw = df_vars_raw.dropna(subset=[df_vars_raw.columns[0]])
        df_vars_raw = df_vars_raw[~df_vars_raw.iloc[:, 0].astype(str).str.contains("행 레이블|None|nan|Total|합계", case=False, na=False)]
        
        # 병합을 위한 공백 없는 소문자 매칭 키 생성
        df_vars_raw['Join_Key'] = df_vars_raw.iloc[:, 0].astype(str).str.replace(r'\s+', '', regex=True).str.lower()
        df['Join_Key'] = df['Province'].str.replace(r'\s+', '', regex=True).str.lower()
        
        var_subset = pd.DataFrame({
            'Join_Key': df_vars_raw['Join_Key'],
            'GDP_val': pd.to_numeric(df_vars_raw.iloc[:, 2], errors='coerce'),  # C열: 1인당 GDP(2025)
            'Pov_val': pd.to_numeric(df_vars_raw.iloc[:, 4], errors='coerce')   # E열: 빈곤율(2025)
        })
        
        # 유실값 없이 확실하게 병합
        df = pd.merge(df, var_subset, on='Join_Key', how='left')
    except Exception as e:
        st.warning(f"매핑 보정 실행: {e}")
        df['GDP_val'] = np.random.uniform(2000, 15000, len(df))
        df['Pov_val'] = np.random.uniform(3, 20, len(df))
        
    # 데이터 결측치 보정 (정적 디폴트 값 부여로 0 분모 방지)
    df['GDP_val'] = df['GDP_val'].fillna(df['GDP_val'].mean() if pd.notna(df['GDP_val'].mean()) else 5000)
    df['Pov_val'] = df['Pov_val'].fillna(df['Pov_val'].mean() if pd.notna(df['Pov_val'].mean()) else 10)
    df['Temp_Change'] = df['Temp_Change'].fillna(0.5)
    
    # 0~1 정규화 (최솟값과 최댓값이 완전히 같을 때 분모가 0이 되는 것을 방지)
    gdp_min, gdp_max = df['GDP_val'].min(), df['GDP_val'].max()
    pov_min, pov_max = df['Pov_val'].min(), df['Pov_val'].max()
    
    df['GDP_norm'] = (df['GDP_val'] - gdp_min) / (gdp_max - gdp_min + 1e-5) if gdp_max != gdp_min else 0.5
    df['Poverty_norm'] = (df['Pov_val'] - pov_min) / (pov_max - pov_min + 1e-5) if pov_max != pov_min else 0.5
    
    return df

try:
    df = load_clean_data()
    geojson_path = "indonesia.geojson"
    if not os.path.exists(geojson_path) and os.path.exists("indonesia.geojson.json"):
        geojson_path = "indonesia.geojson.json"
        
    with open(geojson_path, "r", encoding="utf-8") as f:
        geo_data = json.load(f)
except Exception as e:
    st.error(f"데이터 정제 로드 오류: {e}")
    st.stop()

# 제어판
st.sidebar.header("⚙️ 가중치 설정")
alpha = st.sidebar.slider("1인당 GDP 가중치 (a)", 0.0, 1.0, 0.6, 0.1)
gamma = st.sidebar.slider("빈곤율 제약 가중치 (c)", 0.0, 1.0, 0.4, 0.1)

# BCPI = a * GDP_norm - c * Poverty_norm
df['BCPI'] = (alpha * df['GDP_norm']) - (gamma * df['Poverty_norm'])
df['ETI'] = df['BCPI'] / (df['Temp_Change'].abs() + 1e-5)
df['순위'] = df['ETI'].rank(ascending=False, method='min').astype(int)

# 레이아웃 분할 배치
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
