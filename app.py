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
        # 특정 시트 이름 대신, 파일 내의 첫 번째 시트를 자동으로 안전하게 로드
        xls_temp = pd.ExcelFile("data.xlsx")
        df_temp = pd.read_excel(xls_temp, sheet_name=xls_temp.sheet_names[0])
        
        # 컬럼명 줄바꿈 및 불필요한 공백 제거 표준화
        df_temp.columns = [str(c).replace('\r', '').replace('\n', ' ').strip() for c in df_temp.columns]
    except Exception as e:
        st.error(f"data.xlsx 로드 실패: {e}")
        st.stop()
    
    df = pd.DataFrame()
    
    # Province 열 추출
    prov_col = None
    for c in df_temp.columns:
        if 'province' in c.lower() or '주' in c:
            prov_col = c
            break
    if not prov_col:
        prov_col = df_temp.columns[0]
        
    df['Province'] = df_temp[prov_col].astype(str).str.strip()
    
    # 기온 변화량 열 추출 (Change (2025-2007) 또는 기온 변화율(%))
    change_col = None
    for c in df_temp.columns:
        if 'change' in c.lower() or '기온' in c or '변화' in c:
            change_col = c
            break
    if not change_col:
        change_col = df_temp.columns[-1]
        
    df['Temp_Change'] = pd.to_numeric(df_temp[change_col], errors='coerce')

    # 2. 변수 데이터 로드 (variables.xlsx)
    try:
        # Sheet 1 등 공백이 있는 시트 이름도 첫 번째 시트 자동 탐색으로 안전하게 우회
        xls_vars = pd.ExcelFile("variables.xlsx")
        df_vars = pd.read_excel(xls_vars, sheet_name=xls_vars.sheet_names[0])
        
        df_vars.columns = [str(c).replace('\r', '').replace('\n', ' ').strip() for c in df_vars.columns]
        
        # variables의 Province 열 탐색
        v_prov_col = None
        for c in df_vars.columns:
            if 'province' in c.lower() or '주' in c:
                v_prov_col = c
                break
        if not v_prov_col:
            v_prov_col = df_vars.columns[0]
            
        # 조인 키 정렬 (소문자화 및 모든 공백 제거)
        df_vars['Join_Key'] = df_vars[v_prov_col].astype(str).str.replace(r'\s+', '', regex=True).str.lower()
        df['Join_Key'] = df['Province'].astype(str).str.replace(r'\s+', '', regex=True).str.lower()
        
        # GDP 및 Poverty 컬럼 정확히 가져오기
        g2007_col = [c for c in df_vars.columns if 'gdp' in c.lower() and '2007' in c][0]
        g2025_col = [c for c in df_vars.columns if 'gdp' in c.lower() and '2025' in c][0]
        p2007_col = [c for c in df_vars.columns if 'poverty' in c.lower() and '2007' in c or 'po' in c.lower() and '07' in c][0]
        p2025_col = [c for c in df_vars.columns if 'poverty' in c.lower() and '2025' in c or 'po' in c.lower() and '25' in c][0]
        
        g2007 = pd.to_numeric(df_vars[g2007_col], errors='coerce')
        g2025 = pd.to_numeric(df_vars[g2025_col], errors='coerce')
        p2007 = pd.to_numeric(df_vars[p2007_col], errors='coerce')
        p2025 = pd.to_numeric(df_vars[p2025_col], errors='coerce')
        
        # 변화량 직접 계산
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

    # 요약 행이나 빈 데이터 필터링
    df = df[df['Province'].notna() & (df['Province'] != '')]
    df = df[~df['Province'].astype(str).str.contains("행레이블|행 레이블|Total|합계|None|nan|Province|province", case=False, na=False)]
    
    # 결측치 방어 코드
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

# 사이드바 설정창
st.sidebar.header("⚙️ 가중치 설정")
alpha = st.sidebar.slider("1인당 GDP 가중치 (a)", 0.0, 1.0, 0.6, 0.1)
gamma = st.sidebar.slider("빈곤율 제약 가중치 (c)", 0.0, 1.0, 0.4, 0.1)

# BCPI 및 ETI 수식 적용
df['BCPI'] = (alpha * df['GDP_norm']) - (gamma * df['Poverty_norm'])
df['ETI'] = df['BCPI'] / (df['Temp_Change'].abs() + 1e-5)
df['순위'] = df['ETI'].rank(ascending=False, method='min').astype(int)

# 지도의 주 이름 매칭용 데이터 가공
df['Geo_Province'] = df['Province'].astype(str).str.title().str.strip()

# 화면 레이아웃 구성
col1, col2 = st.columns([4, 6])

with col1:
    st.subheader("📊 시뮬레이션 결과 랭킹")
    # 열 꼬임 방지를 위해 딕셔너리로 명확히 데이터프레임 재정의
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
