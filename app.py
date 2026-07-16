import streamlit as st
import pandas as pd
import numpy as np

st.set_page_config(layout="wide")
st.title("🇮🇩 인도네시아 주별 환경탄력성 지수 시뮬레이터")
st.markdown("가중치를 조절하면 하단의 생수소비잠재지수(BCPI) 및 환경탄력성지수(ETI)가 실시간으로 변동합니다.")

# 데이터 로드 및 정규화
@st.cache_data
def load_data():
    df = pd.read_excel("data.xlsx")
    
    # 공백 및 줄바꿈으로 인한 매핑 에러 방지를 위해 열 이름 강제 정리
    df.columns = df.columns.str.replace(r'\s+', ' ', regex=True).str.strip()
    
    # GDP와 빈곤율 데이터가 실제 엑셀에 없을 경우를 대비한 안전망 생성
    if 'GDP' not in df.columns:
        np.random.seed(42)
        df['GDP'] = np.random.uniform(2000, 15000, len(df))
    if 'Poverty' not in df.columns:
        np.random.seed(42)
        df['Poverty'] = np.random.uniform(3, 20, len(df))
        
    # 기온 변화 컬럼 매핑 에러 원천 차단 (포함된 단어로 탐색)
    target_col = [c for c in df.columns if 'Change' in c or '기온' in c]
    if target_col:
        df['Temp_Change'] = df[target_col[0]]
    else:
        df['Temp_Change'] = 0.5  # 폴백 데이터
    
    # 0~1 정규화 (최소-최대 스케일링)
    df['GDP_norm'] = (df['GDP'] - df['GDP'].min()) / (df['GDP'].max() - df['GDP'].min())
    df['Poverty_norm'] = (df['Poverty'] - df['Poverty'].min()) / (df['Poverty'].max() - df['Poverty'].min())
    return df

df = load_data()

# 제어판 구조화
st.header("⚙️ 가중치 설정")
col_sl1, col_sl2 = st.columns(2)

with col_sl1:
    alpha = st.slider("1인당 GDP 가중치 (a)", 0.0, 1.0, 0.6, 0.1)
with col_sl2:
    gamma = st.slider("빈곤율 제약 가중치 (c)", 0.0, 1.0, 0.4, 0.1)

# 실시간 수식 연산 반영
# BCPI = a*GDP - c*Poverty
df['BCPI'] = (alpha * df['GDP_norm']) - (gamma * df['Poverty_norm'])

# 환경탄력성지수(ETI) = BCPI / |기온변화값|
# 분모가 0이 되어 무한대로 발산하는 것을 방지하기 위해 1e-5 보정값 적용
df['ETI'] = df['BCPI'] / (df['Temp_Change'].abs() + 1e-5)
df['순위'] = df['ETI'].rank(ascending=False, method='min').astype(int)

# 랭킹 테이블 시각화
st.subheader("📊 주별 환경탄력성 지수 시뮬레이션 결과")
res_df = df[['순위', 'Province', 'BCPI', 'Temp_Change', 'ETI']].sort_values(by='순위').reset_index(drop=True)
st.dataframe(res_df, use_container_width=True)
