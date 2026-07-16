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
    # 1. 기온 데이터 로드
    try:
        df_temp = pd.read_excel("data.xlsx")
        # 모든 열 이름을 무조건 문자열로 변환한 후 공백/줄바꿈 제거
        df_temp.columns = [str(c).replace('\r', '').replace('\n', '').replace(' ', '') for c in df_temp.columns]
    except Exception as e:
        st.error(f"data.xlsx 로드 실패: {e}")
        st.stop()
    
    df = pd.DataFrame()
    
    # 숫자가 아닌 문자열이 가장 많이 들어있는 열을 주 이름(Province) 열로 자동 지정
    prov_col = None
    for col in df_temp.columns:
        # 무조건 문자열로 변환한 값들의 패턴 검사
        non_numeric_ratio = df_temp[col].astype(str).apply(lambda x: not x.replace('.','',1).isdigit()).mean()
        if non_numeric_ratio > 0.7:
            prov_col = col
            break
            
    if prov_col is not None:
        df['Province'] = df_temp[prov_col].astype(str).str.strip()
    else:
        df['Province'] = df_temp.iloc[:, 0].astype(str).str.strip()
        
    # 기온 변화량 열 자동 탐색
    change_cols = [c for c in df_temp.columns if 'change' in str(c).lower() or '기온' in str(c) or '변화' in str(c)]
    if change_cols:
        df['Temp_Change'] = pd.to_numeric(df_temp[change_cols[0]], errors='coerce')
    else:
        numeric_cols = [c for c in df_temp.columns if c != prov_col]
        df['Temp_Change'] = pd.to_numeric(df_temp[numeric_cols[-1]], errors='coerce')

    # 2. 변수 데이터 로드 및 병합
    var_file = "variables.xlsx"
    if not os.path.exists(var_file) and os.path.exists("Variables.xlsx"):
        var_file = "Variables.xlsx"

    try:
        df_vars = pd.read_excel(var_file)
        # 모든 열 이름을 문자열화시킨 후 가공하여 타입 에러('float' has no replace) 완벽 방어!
        df_vars.columns = [str(c).replace('\r', '').replace('\n', '').replace(' ', '') for c in df_vars.columns]
        
        # 주 이름 컬럼 찾기
        var_prov_col = None
        for col in df_vars.columns:
            non_numeric_ratio = df_vars[col].astype(str).apply(lambda x: not x.replace('.','',1).isdigit()).mean()
            if non_numeric_ratio > 0.7:
                var_prov_col = col
                break
        
        vars_prov_name = var_prov_col if var_prov_col else df_vars.columns[0]
        
        df_vars['Join_Key'] = df_vars[vars_prov_name].astype(str).str.replace(r'\s+', '', regex=True).str.lower()
        df['Join_Key'] = df['Province'].astype(str).str.replace(r'\s+', '', regex=True).str.lower()
        
        gdp_cols = [c for c in df_vars.columns if 'gdp' in str(c).lower()]
        pov_cols = [c for c in df_vars.columns if 'pove' in str(c).lower() or '빈곤' in str(c)]
        
        target_gdp_col = gdp_cols[-1] if gdp_cols else df_vars.columns[-1]
        target_pov_col = pov_cols[-1] if pov_cols else df_vars.columns[-1]
        
        var_subset = pd.DataFrame({
            'Join_Key': df_vars['Join_Key'],
            'GDP_val': pd.to_numeric(df_vars[target_gdp_col], errors='coerce'),
            'Pov_val': pd.to_numeric(df_vars[target_pov_col], errors='coerce')
        })
        
        df = pd.merge(df, var_subset, on='Join_Key', how='left')
    except Exception as e:
        df['GDP_val'] = np.nan
        df['Pov_val'] = np.nan

    # 데이터 최종 필터링 및 찌꺼기 행 완벽 제거
    df = df[df['Province'].notna() & (df['Province'] != '')]
    df = df[~df['Province'].astype(str).str.contains("행레이블|행 레이블|Total|합계|None|nan|Province|province", case=False, na=False)]
    
    # Province 자리에 들어간 완전한 실수형 숫자 행 제거
    def is_float(val):
        try:
            float(val)
            return True
        except ValueError:
            return False
    df = df[~df['Province'].apply(is_float)]
    
    # 결측치 수치 보정
    df['GDP_val'] = df['GDP_val'].fillna(5000)
    df['Pov_val'] = df['Pov_val'].fillna(10)
    df['Temp_Change'] = df['Temp_Change'].fillna(0.5)
    
    # Min-Max 정규화
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

# 공식 연산
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
    
    # 동적 스케일 부여
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
    
    st_folium(m, width="100%", height=500
