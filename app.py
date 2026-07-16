import streamlit as st
import pandas as pd
import numpy as np
import folium
import json
import os
from streamlit_folium import st_folium

st.set_page_config(layout="wide")
st.title("🇮🇩 인도네시아 주별 환경탄력성 지수 시뮬레이터")

# 디버깅 정보 출력 공간
st.subheader("🔍 시스템 로그 (디버깅)")

# 1. 파일 존재 여부 검사
st.write("📂 파일 체크:")
st.write(f"- data.xlsx 존재 여부: {os.path.exists('data.xlsx')}")
st.write(f"- variables.xlsx 존재 여부: {os.path.exists('variables.xlsx')}")
st.write(f"- indonesia.geojson 존재 여부: {os.path.exists('indonesia.geojson')}")

@st.cache_data
def load_perfect_data():
    # 1. 기온 데이터 로드
    try:
        df_temp = pd.read_excel("data.xlsx")
        st.write("✅ data.xlsx 로드 완료! 컬럼 목록:", list(df_temp.columns))
    except Exception as e:
        st.error(f"❌ data.xlsx 로드 실패: {e}")
        return None
    
    df = pd.DataFrame()
    
    # 안전하게 주 이름 컬럼 가져오기
    p_cols = [c for c in df_temp.columns if 'prov' in str(c).lower() or '주' in str(c) or 'name' in str(c).lower()]
    if p_cols:
        df['Province'] = df_temp[p_cols[0]].astype(str).str.strip()
    else:
        first_col = list(df_temp.columns)[0]
        df['Province'] = df_temp[first_col].astype(str).str.strip()
        
    # 안전하게 기온 변화량 가져오기
    change_cols = [c for c in df_temp.columns if 'change' in str(c).lower() or '기온' in str(c) or '변화' in str(c)]
    if change_cols:
        df['Temp_Change'] = pd.to_numeric(df_temp[change_cols[0]], errors='coerce')
    else:
        last_col = list(df_temp.columns)[-1]
        df['Temp_Change'] = pd.to_numeric(df_temp[last_col], errors='coerce')

    # 2. 변수 데이터 로드 및 병합
    try:
        df_vars = pd.read_excel("variables.xlsx")
        st.write("✅ variables.xlsx 로드 완료! 컬럼 목록:", list(df_vars.columns))
        
        df_vars.columns = df_vars.columns.astype(str).str.replace(r'[\r\n\s]+', '', regex=True)
        
        vars_p_cols = [c for c in df_vars.columns if 'prov' in str(c).lower() or '주' in str(c) or 'name' in str(c).lower()]
        vars_prov_name = vars_p_cols[0] if vars_p_cols else list(df_vars.columns)[0]
        
        df_vars['Join_Key'] = df_vars[vars_prov_name].astype(str).str.replace(r'\s+', '', regex=True).str.lower()
        df['Join_Key'] = df['Province'].str.replace(r'\s+', '', regex=True).str.lower()
        
        gdp_cols = [c for c in df_vars.columns if 'gdp' in str(c).lower()]
        pov_cols = [c for c in df_vars.columns if 'pove' in str(c).lower() or '빈곤' in str(c)]
        
        target_gdp_col = gdp_cols[-1] if gdp_cols else list(df_vars.columns)[-1]
        target_pov_col = pov_cols[-1] if pov_cols else list(df_vars.columns)[-1]
        
        var_subset = pd.DataFrame({
            'Join_Key': df_vars['Join_Key'],
            'GDP_val': pd.to_numeric(df_vars[target_gdp_col], errors='coerce'),
            'Pov_val': pd.to_numeric(df_vars[target_pov_col], errors='coerce')
        })
        
        df = pd.merge(df, var_subset, on='Join_Key', how='left')
    except Exception as e:
        st.warning(f"⚠️ variables.xlsx 병합 실패 (기본값 대체): {e}")
        df['GDP_val'] = 5000
        df['Pov_val'] = 10

    # 데이터 최종 필터링 및 결측 보정
    df = df[df['Province'].notna() & (df['Province'] != '')]
    df['GDP_val'] = df['GDP_val'].fillna(5000)
    df['Pov_val'] = df['Pov_val'].fillna(10)
    df['Temp_Change'] = df['Temp_Change'].fillna(0.5)
    
    # 정규화
    gdp_min, gdp_max = df['GDP_val'].min(), df['GDP_val'].max()
    pov_min, pov_max = df['Pov_val'].min(), df['Pov_val'].max()
    
    df['GDP_norm'] = (df['GDP_val'] - gdp_min) / (gdp_max - gdp_min + 1e-5) if gdp_max != gdp_min else 0.5
    df['Poverty_norm'] = (df['Pov_val'] - pov_min) / (pov_max - pov_min + 1e-5) if pov_max != pov_min else 0.5
    
    return df

df = load_perfect_data()

if df is not None:
    st.write("📊 정제 완료된 데이터 프레임 샘플:")
    st.dataframe(df.head())
    
    # 지도용 데이터 로드
    geojson_path = "indonesia.geojson"
    if not os.path.exists(geojson_path) and os.path.exists("indonesia.geojson.json"):
        geojson_path = "indonesia.geojson.json"
        
    try:
        with open(geojson_path, "r", encoding="utf-8") as f:
            geo_data = json.load(f)
        st.write("✅ GeoJSON 파일 로드 성공!")
    except Exception as e:
        st.error(f"❌ GeoJSON 로드 실패: {e}")
        st.stop()

    # 사이드바 설정창
    st.sidebar.header("⚙️ 가중치 설정")
    alpha = st.sidebar.slider("1인당 GDP 가중치 (a)", 0.0, 1.0, 0.6, 0.1)
    gamma = st.sidebar.slider("빈곤율 제약 가중치 (c)", 0.0, 1.0, 0.4, 0.1)

    # 공식 연산
    df['BCPI'] = (alpha * df['GDP_norm']) - (gamma * df['Poverty_norm'])
    df['ETI'] = df['BCPI'] / (df['Temp_Change'].abs() + 1e-5)
    df['순위'] = df['ETI'].rank(ascending=False, method='min').astype(int)

    # 화면 배치
    col1, col2 = st.columns([4, 6])

    with col1:
        st.subheader("📊 시뮬레이션 결과 랭킹")
        res_df = df[['순위', 'Province', 'BCPI', 'Temp_Change', 'ETI']].copy()
        res_df = res_df.sort_values(by='순위').reset_index(drop=True)
        res_df.columns = ['순위', '주(Province)', 'BCPI', '기온 변화량', '환경탄력성(ETI)']
        st.dataframe(res_df, use_container_width=True, height=400)

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
        
        st_folium(m, width="100%", height=400)
else:
    st.error("데이터 로드 실패로 앱을 정상 작동할 수 없습니다.")
