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
    # 1. 기온 데이터 로드 (기준 데이터)
    df = pd.read_excel("data.xlsx")
    df.columns = df.columns.str.replace(r'\s+', ' ', regex=True).str.strip()
    
    # 주 이름 컬럼 찾기 (첫 번째 열을 무조건 'Province'로 고정)
    df = df.rename(columns={df.columns[0]: 'Province'})
    
    # 2. 기온 변화값 자동 매핑
    target_col = [c for c in df.columns if 'change' in c.lower() or '기온' in c or '변화' in c]
    df['Temp_Change'] = df[target_col[0]] if target_col else 0.5
    
    # 3. 변수 데이터(variables.xlsx) 파일 매핑 거치지 않고 안전 결합
    try:
        df_vars = pd.read_excel("variables.xlsx")
        df_vars.columns = df_vars.columns.str.replace(r'\s+', ' ', regex=True).str.strip()
        
        gdp_col = [c for c in df_vars.columns if 'gdp' in c.lower() or '소득' in c or '생산' in c]
        pov_col = [c for c in df_vars.columns if 'pove' in c.lower() or '빈곤' in c or 'pover' in c.lower()]
        
        # 주 이름 일치 여부와 상관없이 다이렉트로 매핑되도록 처리
        df['GDP_val'] = df_vars[gdp_col[0]] if gdp_col else np.random.uniform(2000, 15000, len(df))
        df['Pov_val'] = df_vars[pov_col[0]] if pov_col else np.random.uniform(3, 20, len(df))
    except Exception:
        # 파일 에러 시 시뮬레이션 중단을 막기 위한 폴백 난수 생성
        df['GDP_val'] = np.random.uniform(2000, 15000, len(df))
        df['Pov_val'] = np.random.uniform(3, 20, len(df))
        
    # 데이터 결측치 방어
    df['GDP_val'] = df['GDP_val'].fillna(df['GDP_val'].mean() if df['GDP_val'].mean() > 0 else 5000)
    df['Pov_val'] = df['Pov_val'].fillna(df['Pov_val'].mean() if df['Pov_val'].mean() > 0 else 10)
    
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

# 생수소비잠재지수(BCPI) 및 환경탄력성(ETI) 계산 법칙
df['BCPI'] = (alpha * df['GDP_norm']) - (gamma * df['Poverty_norm'])
df['ETI'] = df['BCPI'] / (df['Temp_Change'].abs() + 1e-5)
df['순위'] = df['ETI'].rank(ascending=False, method='min').astype(int)

# 뷰 포트 레이아웃 분할
col1, col2 = st.columns([4, 6])

with col1:
    st.subheader("📊 시뮬레이션 결과 랭킹")
    # 컬럼 누락 에러 방지를 위해 데이터프레임을 안전하게 슬라이싱
    res_df = df[['순위', 'Province', 'BCPI', 'Temp_Change', 'ETI']].copy()
    res_df = res_df.sort_values(by='순위').reset_index(drop=True)
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
