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
    
    # [방어 로직] 첫 번째 열에 기온 숫자가 들어오는 현상 방지
    # 문자열 데이터가 가장 많이 들어있는 열을 주(Province) 이름 열로 동적 선택
    prov_col = None
    for col in df_temp.columns:
        # 해당 열의 값 중 텍스트(숫자가 아닌 것)의 비율이 높은 열을 찾음
        non_numeric_ratio = df_temp[col].astype(str).str.contains(r'[a-zA-Z가-힣]', regex=True).mean()
        if non_numeric_ratio > 0.5:
            prov_col = col
            break
            
    if prov_col is None:
        df['Province'] = df_temp.iloc[:, 0].astype(str).str.strip()  # 기본값
    else:
        df['Province'] = df_temp[prov_col].astype(str).str.strip()
    
    # 기온 변화량 열 선택: 열 이름에 'change', '변화', '%'가 들어간 열 탐색
    change_col = None
    for col in df_temp.columns:
        col_lower = str(col).lower()
        if 'change' in col_lower or '변화' in col_lower or '%' in col_lower:
            change_col = col
            break
            
    if change_col is None:
        # 못 찾으면 마지막 열 사용
        df['Temp_Change'] = pd.to_numeric(df_temp.iloc[:, -1], errors='coerce')
    else:
        df['Temp_Change'] = pd.to_numeric(df_temp[change_col], errors='coerce')

    # 2. 변수 데이터 로드 (variables.xlsx)
    try:
        xls_vars = pd.ExcelFile("variables.xlsx")
        df_vars = pd.read_excel(xls_vars, sheet_name=xls_vars.sheet_names[0])
        
        # variables에서도 문자열이 포함된 주 이름 열 찾기
        v_prov_col = None
        for col in df_vars.columns:
            non_numeric_ratio = df_vars[col].astype(str).str.contains(r'[a-zA-Z가-힣]', regex=True).mean()
            if non_numeric_ratio > 0.5:
                v_prov_col = col
                break
                
        if v_prov_col is None:
            df_vars['Clean_Prov'] = df_vars.iloc[:, 0].astype(str).str.strip()
        else:
            df_vars['Clean_Prov'] = df_vars[v_prov_col].astype(str).str.strip()
        
        # 매칭용 조인 키 (소문자 및 모든 공백 제거)
        df_vars['Join_Key'] = df_vars['Clean_Prov'].str.replace(r'\s+', '', regex=True).str.lower()
        df['Join_Key'] = df['Province'].str.replace(r'\s+', '', regex=True).str.lower()
        
        # GDP 및 Poverty 컬럼 인덱스로 정밀 추적
        g2007_col, g2025_col, p2007_col, p2025_col = None, None, None, None
        for col in df_vars.columns:
            c_low = str(col).lower().replace(" ", "")
            if "gdp" in c_low and "2007" in c_low: g2007_col = col
            elif "gdp" in c_low and "2025" in c_low: g2025_col = col
            elif ("poverty" in c_low or "po" in c_low) and "2007" in c_low: p2007_col = col
            elif ("poverty" in c_low or "po" in c_low) and "2025" in c_low: p2025_col = col
            elif "07" in c_low and "gdp" not in c_low: p2007_col = col
            elif "25" in c_low and "gdp" not in c_low: p2025_col = col

        # 매칭 실패 시 기본 인덱스로 할당
        g2007 = pd.to_numeric(df_vars[g2007_col] if g2007_col else df_vars.iloc[:, 1], errors='coerce')
        g2025 = pd.to_numeric(df_vars[g2025_col] if g2025_col else df_vars.iloc[:, 2], errors='coerce')
        p2007 = pd.to_numeric(df_vars[p2007_col] if p2007_col else df_vars.iloc[:, 3], errors='coerce')
        p2025 = pd.to_numeric(df_vars[p2025_col] if p2025_col else df_vars.iloc[:, 4], errors='coerce')
        
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

    # 불필요한 행 필터링
    df = df[df['Province'].notna() & (df['Province'] != '')]
    df = df[~df['Province'].str.contains("행레이블|행 레이블|Total|합계|None|nan|Province|province", case=False, na=False)]
    
    # 정규화 연산 전 결측치 제거/대체
    df['GDP_val'] = df['GDP_val'].fillna(0)
    df['Pov_val'] = df['Pov_val'].fillna(0)
    df['Temp_Change'] = df['Temp_Change'].fillna(0.1)
    
    # 정규화 (Min-Max Scaling)
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

# BCPI 및 ETI 수식 계산
df['BCPI'] = (alpha * df['GDP_norm']) - (gamma * df['Poverty_norm'])
df['ETI'] = df['BCPI'] / (df['Temp_Change'].abs() + 1e-5)
df['순위'] = df['ETI'].rank(ascending=False, method='min').astype(int)

# 지도 매칭용 텍스트 가공
df['Geo_Province'] = df['Province'].astype(str).str.title().str.strip()

# 화면 레이아웃
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
