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
    df_temp.columns = df_temp.columns.str.replace(r'\s+', ' ', regex=True).str.strip()
    
    # 주(Province) 이름 열 찾기
    p_col_temp = [c for c in df_temp.columns if 'prov' in c.lower() or '주' in c or 'name' in c.lower()]
    temp_prov_name = p_col_temp[0] if p_col_temp else df_temp.columns[0]
    
    df = pd.DataFrame()
    df['Province'] = df_temp[temp_prov_name].astype(str).str.strip()
    
    # 기온 변화값 열 찾기 (Change 또는 기온변화율 등 단어로 탐색)
    change_col = [c for c in df_temp.columns if 'change' in c.lower() or '기온' in c or '변화' in c]
    if change_col:
        df['Temp_Change'] = pd.to_numeric(df_temp[change_col[0]], errors='coerce')
    else:
        # 혹시 못 찾으면 마지막 열 사용
        df['Temp_Change'] = pd.to_numeric(df_temp.iloc[:, -1], errors='coerce')
        
    # 2. 변수 데이터(variables.xlsx) 로드
    try:
        df_vars = pd.read_excel("variables.xlsx")
        df_vars.columns = df_vars.columns.str.replace(r'\s+', ' ', regex=True).str.strip()
        
        # 주 이름 결합 키 생성
        p_col_vars = [c for c in df_vars.columns if 'prov' in c.lower() or '주' in c or 'name' in c.lower()]
        vars_prov_name = p_col_vars[0] if p_col_vars else df_vars.columns[0]
        
        df_vars['Join_Key'] = df_vars[vars_prov_name].astype(str).str.replace(r'\s+', '', regex=True).str.lower()
        df['Join_Key'] = df['Province'].str.replace(r'\s+', '', regex=True).str.lower()
        
        # GDP 및 빈곤율(Poverty) 열 이름 자동 검색
        gdp_col = [c for c in df_vars.columns if 'gdp' in c.lower() or '소득' in c or '생산' in c]
        pov_col = [c for c in df_vars.columns if 'pove' in c.lower() or '빈곤' in c or 'pover' in c.lower()]
        
        # 2025 시점 등 다중 열이 있을 경우 가장 마지막(최신) 컬럼 선택
        target_gdp = gdp_col[-1] if gdp_col else df_vars.columns[1]
        target_pov = pov_col[-1] if pov_col else df_vars.columns[-1]
        
        var_subset = pd.DataFrame({
            'Join_Key': df_vars['Join_Key'],
            'GDP_val': pd.to_numeric(df_vars[target_gdp], errors='coerce'),
            'Pov_val': pd.to_numeric(df_vars[target_pov], errors='coerce')
        })
        
        df = pd.merge(df, var_subset, on='Join_Key', how='left')
    except Exception as e:
        st.warning(f"데이터 매핑 보정 중: {e}")
        df['GDP_val'] = np.random.uniform(2000, 15000, len(df))
        df['Pov_val'] = np.random.uniform(3, 20, len(df))
        
    # 결측치 정제 및 예외 처리
    df['GDP_val'] = df['GDP_val'].fillna(df['GDP_val'].mean() if df['GDP_val'].mean() > 0 else 5000)
    df['Pov_val'] = df['Pov_val'].fillna(df['Pov_val'].mean() if df['Pov_val'].mean() > 0 else 10)
    df['Temp_Change'] = df['Temp_Change'].fillna(0.5)
    
    # 0~1 정규화 (Min-Max)
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
    st.error(f"데이터 파일 처리 실패: {e}")
    st.stop()

# 제어 사이드바
st.sidebar.header("⚙️ 가중치 설정")
alpha = st.sidebar.slider("1인당 GDP 가중치 (a)", 0.0, 1.0, 0.6, 0.1)
gamma = st.sidebar.slider("빈곤율 제약 가중치 (c)", 0.0, 1.0, 0.4, 0.1)

# ETI 수식 반영
df['BCPI'] = (alpha * df['GDP_norm']) - (gamma * df['Poverty_norm'])
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
