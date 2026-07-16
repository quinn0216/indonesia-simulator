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
    
    # [인덱스 강제 지정]
    # 기온 데이터의 A열(0번째)을 무조건 주 이름으로 사용하고,
    # B열(1번째)부터 E열까지 중 기온 변화율이 있는 '마지막 열'을 기온 변화량으로 지정합니다.
    df['Province'] = df_temp.iloc[:, 0].astype(str).str.strip()
    df['Temp_Change'] = pd.to_numeric(df_temp.iloc[:, -1], errors='coerce') # 엑셀의 맨 오른쪽 열 가져오기

    # 2. 변수 데이터 로드 (variables.xlsx)
    try:
        xls_vars = pd.ExcelFile("variables.xlsx")
        df_vars = pd.read_excel(xls_vars, sheet_name=xls_vars.sheet_names[0])
        
        # [인덱스 강제 지정]
        # variables.xlsx의 A열(0번째)을 무조건 주 이름으로 사용
        df_vars['Clean_Prov'] = df_vars.iloc[:, 0].astype(str).str.strip()
        
        # 조인 키 생성 (공백 제거 및 소문자화)
        df_vars['Join_Key'] = df_vars['Clean_Prov'].str.replace(r'\s+', '', regex=True).str.lower()
        df['Join_Key'] = df['Province'].str.replace(r'\s+', '', regex=True).str.lower()
        
        # [열 순서 강제 지정]
        # B열(1번째): 2007 GDP, C열(2번째): 2025 GDP
        # D열(3번째): 2007 Poverty, E열(4번째): 2025 Poverty
        g2007 = pd.to_numeric(df_vars.iloc[:, 1], errors='coerce')
        g2025 = pd.to_numeric(df_vars.iloc[:, 2], errors='coerce')
        p2007 = pd.to_numeric(df_vars.iloc[:, 3], errors='coerce')
        p2025 = pd.to_numeric(df_vars.iloc[:, 4], errors='coerce')
        
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

    # 쓰레기 데이터 행 필터링 (헤더 등 제외)
    df = df[df['Province'].notna() & (df['Province'] != '')]
    df = df[~df['Province'].str.contains("행레이블|행 레이블|Total|합계|None|nan|Province|province|2007|2025", case=False, na=False)]
    
    # 수치형 변환 재확인 및 결측값 제거
    df['GDP_val'] = pd.to_numeric(df['GDP_val'], errors='coerce').fillna(0)
    df['Pov_val'] = pd.to_numeric(df['Pov_val'], errors='coerce').fillna(0)
    df['Temp_Change'] = pd.to_numeric(df['Temp_Change'], errors='coerce').fillna(0.1)
    
    # 정규화 연산 (0~1로 맞춤)
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
    st.error(f"데이터 파일 및 지도 파일 로드 실패: {e}")
    st.stop()

# 사이드바 가중치 설정
st.sidebar.header("⚙️ 가중치 설정")
alpha = st.sidebar.slider("1인당 GDP 가중치 (a)", 0.0, 1.0, 0.7, 0.1)
gamma = st.sidebar.slider("빈곤율 제약 가중치 (c)", 0.0, 1.0, 0.3, 0.1)

# BCPI 및 ETI 공식 계산
df['BCPI'] = (alpha * df['GDP_norm']) - (gamma * df['Poverty_norm'])
df['ETI'] = df['BCPI'] / (df['Temp_Change'].abs() + 1e-5)
df['순위'] = df['ETI'].rank(ascending=False, method='min').astype(int)

# 지도시각화 매칭용 텍스트 표준 가공 (ex: Aceh, Bali 등)
df['Geo_Province'] = df['Province'].astype(str).str.title().str.strip()

# 화면 분할 출력
col1, col2 = st.columns([4, 6])

with col1:
    st.subheader("📊 시뮬레이션 결과 랭킹")
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
    
    # 값의 편차가 존재하므로 quantile 범위 사용
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
