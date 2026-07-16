import streamlit as st
import pandas as pd
import numpy as np
import folium
import json
from streamlit_folium import st_folium

st.set_page_config(layout="wide")
st.title("🇮🇩 인도네시아 주별 환경탄력성 지수 시뮬레이터")
st.markdown("가중치를 조절하면 우측 지도의 주별 색상과 좌측 랭킹이 실시간으로 시각화됩니다.")

# 데이터 로드 및 결합, 정규화
@st.cache_data
def load_and_merge_data():
    # 1. 기온 데이터 로드
    df_temp = pd.read_excel("data.xlsx")
    df_temp.columns = df_temp.columns.str.replace(r'\s+', ' ', regex=True).str.strip()
    
    # 2. GDP, 빈곤율 변수 데이터 로드
    df_vars = pd.read_excel("variables.xlsx")
    df_vars.columns = df_vars.columns.str.replace(r'\s+', ' ', regex=True).str.strip()
    
    # 주(Province) 컬럼 매핑 자동 탐색
    p_temp = [c for c in df_temp.columns if 'prov' in c.lower() or '주' in c or 'name' in c.lower()][0]
    p_vars = [c for c in df_vars.columns if 'prov' in c.lower() or '주' in c or 'name' in c.lower()][0]
    
    df_temp = df_temp.rename(columns={p_temp: 'Province'})
    df_vars = df_vars.rename(columns={p_vars: 'Province'})
    
    # 두 엑셀 파일을 주 이름을 기준으로 병합
    df = pd.merge(df_temp, df_vars, on='Province', how='inner')
    
    # 기온 변화 컬럼 자동 찾기
    target_col = [c for c in df.columns if 'change' in c.lower() or '기온' in c or '변화' in c]
    df['Temp_Change'] = df[target_col[0]] if target_col else 0.5
    
    # GDP 및 빈곤율 컬럼 자동 찾기
    gdp_col = [c for c in df.columns if 'gdp' in c.lower() or '소득' in c or '생산' in c]
    pov_col = [c for c in df.columns if 'pove' in c.lower() or '빈곤' in c or 'pover' in c.lower()]
    
    df['GDP_val'] = df[gdp_col[0]] if gdp_col else np.random.uniform(2000, 15000, len(df))
    df['Pov_val'] = df[pov_col[0]] if pov_col else np.random.uniform(3, 20, len(df))
    
    # 0~1 정규화 (최소-최대 스케일링)
    df['GDP_norm'] = (df['GDP_val'] - df['GDP_val'].min()) / (df['GDP_val'].max() - df['GDP_val'].min() + 1e-5)
    df['Poverty_norm'] = (df['Pov_val'] - df['Pov_val'].min()) / (df['Pov_val'].max() - df['Pov_val'].min() + 1e-5)
    return df

try:
    df = load_and_merge_data()
    
    # GeoJSON 파일 로드
    with open("indonesia.geojson", "r", encoding="utf-8") as f:
        geo_data = json.load(f)
except Exception as e:
    st.error(f"파일을 읽는 중 오류가 발생했습니다. 모든 파일이 최상위 경로에 업로드 되었는지 확인하세요: {e}")
    st.stop()

# 레이아웃 구성: 사이드바 제어판
st.sidebar.header("⚙️ 가중치 설정")
alpha = st.sidebar.slider("1인당 GDP 가중치 (a)", 0.0, 1.0, 0.6, 0.1)
gamma = st.sidebar.slider("빈곤율 제약 가중치 (c)", 0.0, 1.0, 0.4, 0.1)

# 실시간 수식 연산
df['BCPI'] = (alpha * df['GDP_norm']) - (gamma * df['Poverty_norm'])
df['ETI'] = df['BCPI'] / (df['Temp_Change'].abs() + 1e-5)
df['순위'] = df['ETI'].rank(ascending=False, method='min').astype(int)

# 메인 화면 레이아웃 분할 (좌측 표 / 우측 지도)
col1, col2 = st.columns([4, 6])

with col1:
    st.subheader("📊 시뮬레이션 결과 랭킹")
    res_df = df[['순위', 'Province', 'BCPI', 'Temp_Change', 'ETI']].sort_values(by='순위').reset_index(drop=True)
    res_df.columns = ['순위', '주(Province)', 'BCPI', '기온 변화량', '환경탄력성(ETI)']
    st.dataframe(res_df, use_container_width=True, height=500)

with col2:
    st.subheader("🗺️ 인도네시아 주별 환경탄력성 지도")
    
    # 기본 지도 중심 설정 (인도네시아 중앙)
    m = folium.Map(location=[-2.5, 118], zoom_start=4, tiles="OpenStreetMap")
    
    # 계산된 ETI 값을 지도 경계면에 실시간 매핑 및 시각화
    folium.Choropleth(
        geo_data=geo_data,
        name="환경탄력성지수(ETI)",
        data=df,
        columns=["Province", "ETI"],
        key_on="feature.properties.NAME_1",  # GADM level 1 기준 주 이름 매핑 키
        fill_color="YlOrRd",
        fill_opacity=0.7,
        line_opacity=0.2,
        legend_name="환경탄력성지수 (ETI)",
    ).add_to(m)
    
    st_folium(m, width="100%", height=500)
