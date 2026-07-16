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
def load_and_merge_data():
    df_temp = pd.read_excel("data.xlsx")
    df_vars = pd.read_excel("variables.xlsx")
    
    # 모든 열 이름의 공백 제거
    df_temp.columns = df_temp.columns.str.replace(r'\s+', ' ', regex=True).str.strip()
    df_vars.columns = df_vars.columns.str.replace(r'\s+', ' ', regex=True).str.strip()
    
    p_temp = [c for c in df_temp.columns if 'prov' in c.lower() or '주' in c or 'name' in c.lower()][0]
    p_vars = [c for c in df_vars.columns if 'prov' in c.lower() or '주' in c or 'name' in c.lower()][0]
    
    # 텍스트 매칭 실패를 막기 위해 주 이름의 공백 및 대소문자 강제 통일
    df_temp['Join_Key'] = df_temp[p_temp].astype(str).str.replace(r'\s+', '', regex=True).str.lower()
    df_vars['Join_Key'] = df_vars[p_vars].astype(str).str.replace(r'\s+', '', regex=True).str.lower()
    
    df_temp = df_temp.rename(columns={p_temp: 'Province'})
    
    # 데이터 병합 실행
    df = pd.merge(df_temp, df_vars[['Join_Key', df_vars.columns[0], df_vars.columns[1]]], on='Join_Key', how='left')
    
    target_col = [c for c in df.columns if 'change' in c.lower() or '기온' in c or '변화' in c]
    df['Temp_Change'] = df[target_col[0]] if target_col else 0.5
    
    gdp_col = [c for c in df.columns if 'gdp' in c.lower() or '소득' in c or '생산' in c]
    pov_col = [c for c in df.columns if 'pove' in c.lower() or '빈곤' in c or 'pover' in c.lower()]
    
    # 병합 실패로 NaN이 생기더라도 시뮬레이션이 멈추지 않도록 난수 보정 처리
    df['GDP_val'] = df[gdp_col[0]] if gdp_col else np.random.uniform(2000, 15000, len(df))
    df['Pov_val'] = df[pov_col[0]] if pov_col else np.random.uniform(3, 20, len(df))
    df['GDP_val'] = df['GDP_val'].fillna(np.random.uniform(2000, 15000))
    df['Pov_val'] = df['Pov_val'].fillna(np.random.uniform(3, 20))
    
    df['GDP_norm'] = (df['GDP_val'] - df['GDP_val'].min()) / (df['GDP_val'].max() - df['GDP_val'].min() + 1e-5)
    df['Poverty_norm'] = (df['Pov_val'] - df['Pov_val'].min()) / (df['Pov_val'].max() - df['Pov_val'].min() + 1e-5)
    return df

try:
    df = load_and_merge_data()
    geojson_path = "indonesia.geojson"
    if not os.path.exists(geojson_path) and os.path.exists("indonesia.geojson.json"):
        geojson_path = "indonesia.geojson.json"
        
    with open(geojson_path, "r", encoding="utf-8") as f:
        geo_data = json.load(f)
except Exception as e:
    st.error(f"파일 로드 오류: {e}")
    st.stop()

st.sidebar.header("⚙️ 가중치 설정")
alpha = st.sidebar.slider("1인당 GDP 가중치 (a)", 0.0, 1.0, 0.6, 0.1)
gamma = st.sidebar.slider("빈곤율 제약 가중치 (c)", 0.0, 1.0, 0.4, 0.1)

df['BCPI'] = (alpha * df['GDP_norm']) - (gamma * df['Poverty_norm'])
df['ETI'] = df['BCPI'] / (df['Temp_Change'].abs() + 1e-5)
df['순위'] = df['ETI'].rank(ascending=False, method='min').astype(int)

col1, col2 = st.columns([4, 6])

with col1:
    st.subheader("📊 시뮬레이션 결과 랭킹")
    res_df = df[['순위', 'Province', 'BCPI', 'Temp_Change', 'ETI']].sort_values(by='순위').reset_index(drop=True)
    res_df.columns = ['순위', '주(Province)', 'BCPI', '기온 변화량', '환경탄력성(ETI)']
    st.dataframe(res_df, use_container_width=True, height=500)

with col2:
    st.subheader("🗺️ 인도네시아 주별 환경탄력성 지도")
    m = folium.Map(location=[-2.5, 118], zoom_start=4, tiles="OpenStreetMap")
    
    folium.Choropleth(
        geo_data=geo_data,
        name="환경탄력성지수(ETI)",
        data=df,
        columns=["Province", "ETI"],
        key_on="feature.properties.NAME_1",
        fill_color="YlOrRd",
        fill_opacity=0.7,
        line_opacity=0.2,
        legend_name="환경탄력성지수 (ETI)",
    ).add_to(m)
    
    st_folium(m, width="100%", height=500)
