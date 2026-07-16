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
def load_perfect_data():
    # 1. 기온 데이터 로드 (data.xlsx)
    df_temp = pd.read_excel("data.xlsx")
    # 열 이름의 모든 줄바꿈(\n, \r)과 불필요한 공백 제거
    df_temp.columns = df_temp.columns.astype(str).str.replace(r'[\r\n\s]+', '', regex=True)
    
    df = pd.DataFrame()
    
    # 'Province' 열 매핑
    p_col = [c for c in df_temp.columns if 'province' in c.lower()]
    if p_col:
        df['Province'] = df_temp[p_col[0]].astype(str).str.strip()
    else:
        df['Province'] = df_temp.iloc[:, 0].astype(str).str.strip()
        
    # 'Change'가 포함된 열 자동 탐색 (공백 제거 상태이므로 'Change(2025-2007)' 등에서 'change' 검색)
    change_cols = [c for c in df_temp.columns if 'change' in c.lower() or '기온' in c or '변화' in c]
    if change_cols:
        df['Temp_Change'] = pd.to_numeric(df_temp[change_cols[0]], errors='coerce')
    else:
        df['Temp_Change'] = pd.to_numeric(df_temp.iloc[:, 3], errors='coerce')

    # 2. 변수 데이터 로드 및 병합 (variables.xlsx)
    try:
        df_vars = pd.read_excel("variables.xlsx")
        # 열 이름의 줄바꿈(\n)과 공백을 완전히 붙여버림 (예: 'Poverty_20\n25' -> 'Poverty_2025')
        df_vars.columns = df_vars.columns.astype(str).str.replace(r'[\r\n\s]+', '', regex=True)
        
        # 병합을 위한 조인 키 설정
        vars_p_col = [c for c in df_vars.columns if 'province' in c.lower()]
        vars_prov_name = vars_p_col[0] if vars_p_col else df_vars.columns[0]
        
        df_vars['Join_Key'] = df_vars[vars_prov_name].astype(str).str.replace(r'\s+', '', regex=True).str.lower()
        df['Join_Key'] = df['Province'].str.replace(r'\s+', '', regex=True).str.lower()
        
        # 정확히 줄바꿈이 제거된 'GDP2025' 또는 'Poverty2025' 패턴 검색
        gdp_cols = [c for c in df_vars.columns if 'gdp' in c.lower() and '2025' in c]
        pov_cols = [c for c in df_vars.columns if ('pove' in c.lower() or '빈곤' in c) and '2025' in c]
        
        # 만약 해당 패턴이 없으면 기존 방식대로 검색
        target_gdp_col = gdp_cols[0] if gdp_cols else [c for c in df_vars.columns if 'gdp' in c.lower()][-1]
        target_pov_col = pov_cols[0] if pov_cols else [c for c in df_vars.columns if 'pove' in c.lower() or '빈곤' in c][-1]
        
        var_subset = pd.DataFrame({
            'Join_Key': df_vars['Join_Key'],
            'GDP_val': pd.to_numeric(df_vars[target_gdp_col], errors='coerce'),
            'Pov_val': pd.to_numeric(df_vars[target_pov_col], errors='coerce')
        })
        
        df = pd.merge(df, var_subset, on='Join_Key', how='left')
    except Exception as e:
        df['GDP_val'] = np.nan
        df['Pov_val'] = np.nan

    # 데이터 최종 필터링 (행 레이블, None 등 찌꺼기 완벽하게 제거)
    df = df[df['Province'].notna() & (df['Province'] != '')]
    df = df[~df['Province'].astype(str).str.contains("행 레이블|Total|합계|None|nan|mean|temp", case=False, na=False)]
    
    # Province에 들어오는 잘못된 숫자 필터링
    def is_float(val):
        try:
            float(val)
            return True
        except ValueError:
            return False
    df = df[~df['Province'].apply(is_float)]
    
    # 결측값 방어 대책
    df['GDP_val'] = df['GDP_val'].fillna(5000)
    df['Pov_val'] = df['Pov_val'].fillna(10)
    df['Temp_Change'] = df['Temp_Change'].fillna(0.5)
    
    # 0~1 Min-Max 정규화
    gdp_min, gdp_max = df['GDP_val'].min(), df['GDP_val'].max()
    pov_min, pov_max = df['Pov_val'].min(), df['Pov_val'].max()
    
    df['GDP_norm'] = (df['GDP_val'] - gdp_min) / (gdp_max - gdp_min + 1e-5) if gdp_max != gdp_min else 0.5
    df['Poverty_norm'] = (df['Pov_val'] - pov_min) / (pov_max - pov_min + 1e-5) if pov_max != pov_min else 0.5
    
    return df

try:
    df = load_perfect_data()
    geojson_path = "indonesia.geojson"
    if not os.path.exists(geojson_path) and os.path.exists("indonesia.geojson.json"):
        geojson_path = "indonesia.geojson.json"
        
    with open(geojson_path, "r", encoding="utf-8") as f:
        geo_data = json.load(f)
except Exception as e:
    st.error(f"데이터 파일 에러 발생: {e}")
    st.stop()

# 사이드바 설정창
st.sidebar.header("⚙️ 가중치 설정")
alpha = st.sidebar.slider("1인당 GDP 가중치 (a)", 0.0, 1.0, 0.6, 0.1)
gamma = st.sidebar.slider("빈곤율 제약 가중치 (c)", 0.0, 1.0, 0.4, 0.1)

# ETI 공식 연산
df['BCPI'] = (alpha * df['GDP_norm']) - (gamma * df['Poverty_norm'])
df['ETI'] = df['BCPI'] / (df['Temp_Change'].abs() + 1e-5)
df['순위'] = df['ETI'].rank(ascending=False, method='min').astype(int)

# 화면 레이아웃 구성
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
    
    # 지도 컬러 스케일 자동 세팅
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
