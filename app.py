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
    # 1. 기온 데이터(data.xlsx) 로드
    df_temp = pd.read_excel("data.xlsx")
    df_temp.columns = df_temp.columns.astype(str).str.replace(r'\s+', ' ', regex=True).str.strip()
    
    # 첫 열을 무조건 주 이름으로 설정하고 불필요한 행(None, 행 레이블) 필터링
    df_temp = df_temp.dropna(subset=[df_temp.columns[0]])
    df_temp = df_temp[~df_temp.iloc[:, 0].astype(str).str.contains("행 레이블|None|nan|Total|합계|주", case=False, na=False)]
    
    df = pd.DataFrame()
    df['Province'] = df_temp.iloc[:, 0].astype(str).str.strip()
    
    # 기온 변화 컬럼을 이름 단어로 검색 (Change, 기온, 변화 등)
    change_cols = [c for c in df_temp.columns if 'change' in c.lower() or '기온' in c or '변화' in c]
    if change_cols:
        df['Temp_Change'] = pd.to_numeric(df_temp[change_cols[0]], errors='coerce')
    else:
        # 단어가 없으면 안전하게 0.5로 채움
        df['Temp_Change'] = 0.5
        
    # 2. 변수 데이터(variables.xlsx) 로드
    try:
        df_vars = pd.read_excel("variables.xlsx")
        df_vars.columns = df_vars.columns.astype(str).str.replace(r'\s+', ' ', regex=True).str.strip()
        df_vars = df_vars.dropna(subset=[df_vars.columns[0]])
        df_vars = df_vars[~df_vars.iloc[:, 0].astype(str).str.contains("행 레이블|None|nan|Total|합계", case=False, na=False)]
        
        # 병합을 위한 주 이름 조인 키 생성
        df_vars['Join_Key'] = df_vars.iloc[:, 0].astype(str).str.replace(r'\s+', '', regex=True).str.lower()
        df['Join_Key'] = df['Province'].str.replace(r'\s+', '', regex=True).str.lower()
        
        # GDP 및 빈곤율(Poverty) 열 이름 자동 검색
        gdp_cols = [c for c in df_vars.columns if 'gdp' in c.lower() or '소득' in c or '생산' in c]
        pov_cols = [c for c in df_vars.columns if 'pove' in c.lower() or '빈곤' in c or 'pover' in c.lower()]
        
        # 여러 시점이 있을 경우 가장 마지막(최신인 2025년) 컬럼 자동 선택
        target_gdp_col = gdp_cols[-1] if gdp_cols else None
        target_pov_col = pov_cols[-1] if pov_cols else None
        
        var_subset = pd.DataFrame({'Join_Key': df_vars['Join_Key']})
        
        if target_gdp_col:
            var_subset['GDP_val'] = pd.to_numeric(df_vars[target_gdp_col], errors='coerce')
        else:
            var_subset['GDP_val'] = np.nan
            
        if target_pov_col:
            var_subset['Pov_val'] = pd.to_numeric(df_vars[target_pov_col], errors='coerce')
        else:
            var_subset['Pov_val'] = np.nan
            
        df = pd.merge(df, var_subset, on='Join_Key', how='left')
    except Exception as e:
        df['GDP_val'] = np.nan
        df['Pov_val'] = np.nan
        
    # 결측치 보정 (정수 디폴트 부여)
    df['GDP_val'] = df['GDP_val'].fillna(5000)
    df['Pov_val'] = df['Pov_val'].fillna(10)
    df['Temp_Change'] = df['Temp_Change'].fillna(0.5)
    
    # 0~1 정규화 (Min-Max)
    gdp_min, gdp_max = df['GDP_val'].min(), df['GDP_val'].max()
    pov_min, pov_max = df['Pov_val'].min(), df['Pov_val'].max()
    
    df['GDP_norm'] = (df['GDP_val'] - gdp_min) / (gdp_max - gdp_min + 1e-5) if gdp_max != gdp_min else 0.5
    df['Poverty_norm'] = (df['Pov_val'] - pov_min) / (pov_max - pov_min + 1e-5) if pov_max != pov_min else 0.5
    return df

try:
    df = load_safe_data()
    geojson_path = "indonesia.geojson"
    if not os.path.exists(geojson_path) and os.path.exists("indonesia.geojson.json"):
        geojson_path = "indonesia.geojson.json"
        
    with open(geojson_path, "r", encoding="utf-8") as f:
        geo_data = json.load(f)
except Exception as e:
    st.error(f"데이터 정제 로드 오류: {e}")
    st.stop()

# 사이드바 제어판
st.sidebar.header("⚙️ 가중치 설정")
alpha = st.sidebar.slider("1인당 GDP 가중치 (a)", 0.0, 1.0, 0.6, 0.1)
gamma = st.sidebar.slider("빈곤율 제약 가중치 (c)", 0.0, 1.0, 0.4, 0.1)

# BCPI = a * GDP_norm - c * Poverty_norm
df['BCPI'] = (alpha * df['GDP_norm']) - (gamma * df['Poverty_norm'])
# ETI = BCPI / |Temp_Change|
df['ETI'] = df['BCPI'] / (df['Temp_Change'].abs() + 1e-5)
df['순위'] = df['ETI'].rank(ascending=False, method='min').astype(int)

# 레이아웃 배치
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
