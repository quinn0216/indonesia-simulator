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

def load_perfect_data():
    # 1. 기온 데이터 로드 (data.xlsx)
    try:
        xls_temp = pd.ExcelFile("data.xlsx")
        df_temp = pd.read_excel(xls_temp, sheet_name=xls_temp.sheet_names[0])
    except Exception as e:
        st.error(f"data.xlsx 로드 실패: {e}")
        st.stop()
    
    df = pd.DataFrame()
    
    # [무조건 첫 번째 열(A열)을 주 이름으로 강제 지정]
    df['Province'] = df_temp.iloc[:, 0].astype(str).str.strip()
    
    # [기온 변화량 가져오기] 기온 변화율(%) 또는 Change 열 검색
    change_col_idx = -1
    for i, col in enumerate(df_temp.columns):
        col_str = str(col).lower().replace(" ", "")
        if "change" in col_str or "기온" in col_str or "변화" in col_str:
            change_col_idx = i
            break
    
    df['Temp_Change'] = pd.to_numeric(df_temp.iloc[:, change_col_idx], errors='coerce')

    # 2. 변수 데이터 로드 (variables.xlsx)
    try:
        xls_vars = pd.ExcelFile("variables.xlsx")
        df_vars = pd.read_excel(xls_vars, sheet_name=xls_vars.sheet_names[0])
        
        # variables의 첫 번째 열(A열)도 주 이름으로 강제 지정
        df_vars['Clean_Prov'] = df_vars.iloc[:, 0].astype(str).str.strip()
        
        # 조인용 키 생성 (띄어쓰기 완전 제거 + 소문자화하여 매칭률 100% 보장)
        df_vars['Join_Key'] = df_vars['Clean_Prov'].str.replace(r'\s+', '', regex=True).str.lower()
        df['Join_Key'] = df['Province'].str.replace(r'\s+', '', regex=True).str.lower()
        
        # GDP 및 Poverty 컬럼 인덱스로 직접 찾아오기 (B, C, D, E열)
        g2007_idx, g2025_idx, p2007_idx, p2025_idx = 1, 2, 3, 4
        for i, col in enumerate(df_vars.columns):
            col_str = str(col).lower().replace(" ", "")
            if "gdp" in col_str and "2007" in col_str: g2007_idx = i
            elif "gdp" in col_str and "2025" in col_str: g2025_idx = i
            elif "poverty" in col_str and "2007" in col_str: p2007_idx = i
            elif "poverty" in col_str and "2025" in col_str: p2025_idx = i
            elif "po" in col_str and "07" in col_str: p2007_idx = i
            elif "po" in col_str and "25" in col_str: p2025_idx = i
            
        g2007 = pd.to_numeric(df_vars.iloc[:, g2007_idx], errors='coerce')
        g2025 = pd.to_numeric(df_vars.iloc[:, g2025_idx], errors='coerce')
        p2007 = pd.to_numeric(df_vars.iloc[:, p2007_idx], errors='coerce')
        p2025 = pd.to_numeric(df_vars.iloc[:, p2025_idx], errors='coerce')
        
        # 변화량 연산
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

    # 쓰레기 행(헤더 반복 등) 필터링
    df = df[df['Province'].notna() & (df['Province'] != '')]
    df = df[~df['Province'].str.contains("행레이블|행 레이블|Total|합계|None|nan|Province|province", case=False, na=False)]
    
    # 데이터 매칭 실패로 생긴 NaN 값 보정
    df['GDP_val'] = df['GDP_val'].fillna(0)
    df['Pov_val'] = df['Pov_val'].fillna(0)
    df['Temp_Change'] = df['Temp_Change'].fillna(0.1)
    
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

# 사이드바 가중치 설정
st.sidebar.header("⚙️ 가중치 설정")
alpha = st.sidebar.slider("1인당 GDP 가중치 (a)", 0.0, 1.0, 0.7, 0.1)
gamma = st.sidebar.slider("빈곤율 제약 가중치 (c)", 0.0, 1.0, 0.3, 0.1)

# BCPI 및 ETI 수식 적용
df['BCPI'] = (alpha * df['GDP_norm']) - (gamma * df['Poverty_norm'])
df['ETI'] = df['BCPI'] / (df['Temp_Change'].abs() + 1e-5)
df['순위'] = df['ETI'].rank(ascending=False, method='min').astype(int)

# GeoJSON의 NAME_1과 맞추기 위해 타이틀 케이스로 변경
df['Geo_Province'] = df['Province'].astype(str).str.title().str.strip()

# 화면 레이아웃
col1, col2 = st.columns([4, 6])

with col1:
    st.subheader("📊 시뮬레이션 결과 랭킹")
    # 딕셔너리로 안전하게 데이터 매핑 지정
    res_df = pd.DataFrame({
        '순위': df['순위'],
        '주(Province)': df['Province'],
        'BCPI': df['BCPI'].round(4),
        '기온 변화량': df['Temp_Change'].round(4),
        '환경탄력성(ETI)': df['ETI'].round(4)
    })
    res_df = res_df.sort_values(by='순위').reset_index(drop=True)
    st.dataframe(res_df, use_container_width=True, height=500)

with col2:
    st.subheader("🗺️ 인도네시아 주별 환경탄력성 지도")
    m = folium.Map(location=[-2.5, 118], zoom_start=4, tiles="OpenStreetMap")
    
    # 분위수 기반 범주 색상 정의
    threshold_scale = list(df['ETI'].quantile([0, 0.25, 0.5, 0.75, 1]))
    if len(set(threshold_scale)) < 5:
        threshold_scale = np.linspace(df['ETI'].min(), df['ETI'].max(), 5).tolist()

    folium.Choropleth(
        geo_data=geo_data,
        name="환경탄력성지수(ETI)",
        data=df,
        columns=["Geo_Province", "ETI"],
        key_on="feature.properties.NAME_1",
        fill_color="YlOrRd",
        fill_opacity=0.7,
        line_opacity=0.4,
        threshold_scale=threshold_scale,
        legend_name="환경탄력성지수 (ETI)",
    ).add_to(m)
    
    st_folium(m, width="100%", height=500)
