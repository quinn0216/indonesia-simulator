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
    try:
        df_temp = pd.read_excel("data.xlsx")
        df_temp.columns = df_temp.columns.astype(str).str.replace(r'[\r\n\s]+', '', regex=True)
    except Exception as e:
        st.error(f"data.xlsx 파일을 찾을 수 없거나 읽을 수 없습니다: {e}")
        st.stop()
    
    df = pd.DataFrame()
    
    # 'Province' 또는 '주'가 포함된 첫 번째 열 자동 탐색
    p_cols = [c for c in df_temp.columns if 'prov' in c.lower() or '주' in c or 'name' in c.lower()]
    if p_cols:
        df['Province'] = df_temp[p_cols[0]].astype(str).str.strip()
    else:
        # 찾지 못하면 첫 번째 열 강제 지정
        df['Province'] = df_temp[df_temp.columns[0]].astype(str).str.strip()
        
    # 'Change'가 포함된 기온 변화량 열 자동 탐색
    change_cols = [c for c in df_temp.columns if 'change' in c.lower() or '기온' in c or '변화' in c]
    if change_cols:
        df['Temp_Change'] = pd.to_numeric(df_temp[change_cols[0]], errors='coerce')
    else:
        # 찾지 못하면 마지막 열이라도 유연하게 지정
        df['Temp_Change'] = pd.to_numeric(df_temp[df_temp.columns[-1]], errors='coerce')

    # 2. 변수 데이터 로드 및 병합 (variables.xlsx)
    # 대소문자 다른 파일명 대비 (variables.xlsx / Variables.xlsx 등)
    var_file = "variables.xlsx"
    if not os.path.exists(var_file) and os.path.exists("Variables.xlsx"):
        var_file = "Variables.xlsx"

    try:
        df_vars = pd.read_excel(var_file)
        df_vars.columns = df_vars.columns.astype(str).str.replace(r'[\r\n\s]+', '', regex=True)
        
        # variables 내 'Province' 열 찾기
        vars_p_cols = [c for c in df_vars.columns if 'prov' in c.lower() or '주' in c or 'name' in c.lower()]
        vars_prov_name = vars_p_cols[0] if vars_p_cols else df_vars.columns[0]
        
        df_vars['Join_Key'] = df_vars[vars_prov_name].astype(str).str.replace(r'\s+', '', regex=True).str.lower()
        df['Join_Key'] = df['Province'].str.replace(r'\s+', '', regex=True).str.lower()
        
        # GDP 및 빈곤율(Poverty) 2025 타겟 자동 탐색
        gdp_cols = [c for c in df_vars.columns if 'gdp' in c.lower() and '2025' in c]
        if not gdp_cols:
            gdp_cols = [c for c in df_vars.columns if 'gdp' in c.lower() or '소득' in c]
            
        pov_cols = [c for c in df_vars.columns if ('pove' in c.lower() or '빈곤' in c) and '2025' in c]
        if not pov_cols:
            pov_cols = [c for c in df_vars.columns if 'pove' in c.lower() or '빈곤' in c]
            
        target_gdp_col = gdp_cols[0] if gdp_cols else df_vars.columns[-1]
        target_pov_col = pov_cols[0] if pov_cols else df_vars.columns[-1]
        
        var_subset = pd.DataFrame({
            'Join_Key': df_vars['Join_Key'],
            'GDP_val': pd.to_numeric(df_vars[target_gdp_col], errors='coerce'),
            'Pov_val': pd.to_numeric(df_vars[target_pov_col], errors='coerce')
        })
        
        df = pd.merge(df, var_subset, on='Join_Key', how='left')
    except Exception as e:
        df['GDP_val'] = np.nan
        df['Pov_val'] = np.nan

    # 데이터 최종 필터링 (행 레이블, 합계, None 등 정제)
    df = df[df['Province'].notna() & (df['Province'] != '')]
    df = df[~df['Province'].astype(str).str.contains("행 레이블|Total|합계|None|nan|mean|temp", case=False, na=False)]
    
    # Province에 들어오는 잘못된 행 정제
    def is_float(val):
        try:
            float(val)
            return True
        except ValueError:
            return False
    df = df[~df['Province'].apply(is_float)]
    
    # 결측값 방어 수치 채우기
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
    df = load_perfect_data()
    geojson_path = "indonesia.geojson"
    if not os.path.exists(geojson_path) and os.path.exists("indonesia.geojson.json"):
        geojson_path = "indonesia.geojson.json"
        
    with open(geojson_path, "r", encoding="utf-8") as f:
        geo_data = json.load(f)
except Exception as e:
    st.error(f"데이터 파일 처리 중 치명적 오류 발생: {e}")
    st.stop()

# 사이드바 설정창
st.sidebar.header("⚙️ 가중치 설정")
alpha = st.sidebar.slider("1인당 GDP 가중치 (a)", 0.0, 1.0, 0.6, 0.1)
gamma = st.sidebar.slider("빈곤율 제약 가중치 (c)", 0.0, 1.0, 0.4, 0.1)

# 공식 연산
df['BCPI'] = (alpha * df['GDP_norm']) - (gamma * df['Poverty_norm'])
df['ETI'] = df['BCPI'] / (df['Temp_Change'].abs() + 1e-5)
df['순위'] = df['ETI'].rank(ascending=False, method='min').astype(int)

# 레이아웃 구성
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
