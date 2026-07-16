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

# 캐시 없이 깨끗하게 데이터 로드
def load_perfect_data():
    # 1. 기온 데이터 로드 (data.xlsx)
    try:
        df_temp = pd.read_excel("data.xlsx")
        # 모든 줄바꿈, 공백 제거하여 임시 컬럼명 생성
        original_cols = list(df_temp.columns)
        clean_cols = [str(c).replace('\r', '').replace('\n', '').replace(' ', '').replace('-', '').replace('(', '').replace(')', '') for c in original_cols]
        df_temp.columns = clean_cols
    except Exception as e:
        st.error(f"data.xlsx 로드 실패: {e}")
        st.stop()
    
    df = pd.DataFrame()
    
    # Province 열 추출
    if 'Province' in df_temp.columns:
        df['Province'] = df_temp['Province'].astype(str).str.strip()
    else:
        df['Province'] = df_temp[df_temp.columns[0]].astype(str).str.strip()
        
    # 'Change(2025-2007)' 컬럼 매핑
    if 'Change20252007' in df_temp.columns:
        df['Temp_Change'] = pd.to_numeric(df_temp['Change20252007'], errors='coerce')
    elif '기온변화율%' in df_temp.columns:
        df['Temp_Change'] = pd.to_numeric(df_temp['기온변화율%'], errors='coerce')
    else:
        df['Temp_Change'] = pd.to_numeric(df_temp[df_temp.columns[-1]], errors='coerce')

    # 2. 변수 데이터 로드 (variables.xlsx)
    try:
        df_vars = pd.read_excel("variables.xlsx")
        df_vars.columns = [str(c).replace('\r', '').replace('\n', '').replace(' ', '').replace('_', '') for c in df_vars.columns]
        
        # 조인용 키 (공백 제거 후 소문자 변환)
        df_vars['Join_Key'] = df_vars['Province'].astype(str).str.replace(r'\s+', '', regex=True).str.lower()
        df['Join_Key'] = df['Province'].astype(str).str.replace(r'\s+', '', regex=True).str.lower()
        
        g2007 = pd.to_numeric(df_vars['GDP2007'], errors='coerce')
        g2025 = pd.to_numeric(df_vars['GDP2025'], errors='coerce')
        p2007 = pd.to_numeric(df_vars['Poverty2007'], errors='coerce')
        p2025 = pd.to_numeric(df_vars['Poverty2025'], errors='coerce')
        
        df_vars['GDP_diff'] = g2025 - g2007
        df_vars['Poverty_diff'] = p2025 - p2007
        
        var_subset = pd.DataFrame({
            'Join_Key': df_vars['Join_Key'],
            'GDP_val': df_vars['GDP_diff'],
            'Pov_val': df_vars['Poverty_diff']
        })
        
        df = pd.merge(df, var_subset, on='Join_Key', how='left')
    except Exception as e:
        st.error(f"variables.xlsx 처리 실패: {e}")
        st.stop()

    # 행 레이블 및 요약 행 제거
    df = df[df['Province'].notna() & (df['Province'] != '')]
    df = df[~df['Province'].astype(str).str.contains("행레이블|행 레이블|Total|합계|None|nan|Province|province", case=False, na=False)]
    
    # 결측값 보정
    df['GDP_val'] = df['GDP_val'].fillna(0)
    df['Pov_val'] = df['Pov_val'].fillna(0)
    df['Temp_Change'] = df['Temp_Change'].fillna(0.5)
    
    # 정규화
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
    st.error(f"데이터 로드 치명적 에러: {e}")
    st.stop()

# 사이드바 설정창
st.sidebar.header("⚙️ 가중치 설정")
alpha = st.sidebar.slider("1인당 GDP 가중치 (a)", 0.0, 1.0, 0.6, 0.1)
gamma = st.sidebar.slider("빈곤율 제약 가중치 (c)", 0.0, 1.0, 0.4, 0.1)

# BCPI 및 ETI 계산
df['BCPI'] = (alpha * df['GDP_norm']) - (gamma * df['Poverty_norm'])
df['ETI'] = df['BCPI'] / (df['Temp_Change'].abs() + 1e-5)
df['순위'] = df['ETI'].rank(ascending=False, method='min').astype(int)

# GeoJSON의 NAME_1과 맞추기 위해 대소문자 가공한 지도용 컬럼 생성
# GeoJSON과 Excel의 주 이름 스펠링 불일치를 메우기 위한 보정
df['Geo_Province'] = df['Province'].astype(str).str.title().str.strip()

# 화면 레이아웃 구성
col1, col2 = st.columns([4, 6])

with col1:
    st.subheader("📊 시뮬레이션 결과 랭킹")
    # 열 순서가 꼬이지 않도록 순위와 주 이름 명시적으로 지정
    res_df = df[['순위', 'Province', 'BCPI', 'Temp_Change', 'ETI']].copy()
    res_df = res_df.sort_values(by='순위').reset_index(drop=True)
    res_df.columns = ['순위', '주(Province)', 'BCPI', '기온 변화량', '환경탄력성(ETI)']
    st.dataframe(res_df, use_container_width=True, height=500)

with col2:
    st.subheader("🗺️ 인도네시아 주별 환경탄력성 지도")
    m = folium.Map(location=[-2.5, 118], zoom_start=4, tiles="OpenStreetMap")
    
    # 동적 스케일 설정
    threshold_scale = list(df['ETI'].quantile([0, 0.25, 0.5, 0.75, 1]))
    if len(set(threshold_scale)) < 5:
        threshold_scale = np.linspace(df['ETI'].min(), df['ETI'].max(), 5).tolist()

    folium.Choropleth(
        geo_data=geo_data,
        name="환경탄력성지수(ETI)",
        data=df,
        columns=["Geo_Province", "ETI"], # 가공된 Geo_Province 컬럼 사용
        key_on="feature.properties.NAME_1",
        fill_color="YlOrRd",
        fill_opacity=0.7,
        line_opacity=0.4,
        threshold_scale=threshold_scale,
        legend_name="환경탄력성지수 (ETI)",
    ).add_to(m)
    
    st_folium(m, width="100%", height=500)
