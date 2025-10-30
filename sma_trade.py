import yfinance as yf
import pandas as pd
import os
import smtplib
import ssl
from email.message import EmailMessage
from datetime import datetime

# --- 환경 변수 로드 (GitHub Secrets에서 가져옴) ---
EMAIL_SENDER = os.getenv("EMAIL_ADDRESS")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
EMAIL_RECEIVER = os.getenv("EMAIL_TO_1")

# --- 기본 설정 ---
Ticker = "QLD"
my_strategy = {
    # 정배열 (강세)
    "SMA5 > EMA20 > SMA180": .7,
    "EMA20 > SMA5 > SMA180": 1,
    # 혼조세 (180일선이 중간)
    "SMA5 > SMA180 > EMA20": 0.4,
    "EMA20 > SMA180 > SMA5": 0,
    # 역배열 (약세)
    "SMA180 > SMA5 > EMA20": 0.4,
    "SMA180 > EMA20 > SMA5": 0.1
}

# --- 헬퍼 함수 1: SMA 상태 계산 ---
def get_sma_state(row):
    if pd.isna(row['SMA5']) or pd.isna(row['EMA20']) or pd.isna(row['SMA180']):
        return None
    smas = {
        'SMA5': row['SMA5'],
        'EMA20': row['EMA20'],
        'SMA180': row['SMA180']
    }
    # 값(value)을 기준으로 정렬하되, 키(key)를 튜플로 반환
    sorted_state = tuple(k for k, v in sorted(smas.items(), key=lambda item: item[1], reverse=True))
    return sorted_state

# --- [신규] 헬퍼 함수 2: 현재 상태만 가져오기 ---
def get_current_recommendation(ticker, strategy_map_config):
    """
    최신 데이터를 다운로드하여 현재 SMA 상태와 권장 비중을 계산합니다.
    """
    print(f"[{ticker}] 최신 데이터 다운로드 중...")
    
    # SMA180 계산을 위해 최소 180일이 필요하므로, 1년(약 252 거래일) 데이터를 여유있게 가져옵니다.
    data = yf.download(ticker, period="1y", auto_adjust=True, progress=False)
    
    if data.empty:
        print("데이터 다운로드 실패")
        return "데이터 다운로드 실패", 0.0, datetime.now().strftime('%Y-%m-%d')

    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.droplevel(1)

    # SMA/EMA 계산
    data['SMA5'] = data['Close'].rolling(5).mean()
    data['EMA20'] = data['Close'].ewm(com=20, adjust=False).mean()
    data['SMA180'] = data['Close'].rolling(180).mean()

    # NaN 값을 제거한 마지막 유효한 데이터 행을 가져옵니다.
    last_valid_row = data.dropna().iloc[-1]
    last_date = last_valid_row.name.strftime('%Y-%m-%d')
    
    # 마지막 행을 기준으로 현재 상태 계산
    current_state = get_sma_state(last_valid_row)

    if current_state is None:
        print("SMA 계산 불가 (데이터 부족)")
        return "SMA 계산 불가 (데이터 부족)", 0.0, last_date

    # 전략 맵의 키를 문자열에서 튜플로 변환 (비교를 위해)
    strategy_map = {}
    for k_str, allocation in strategy_map_config.items():
        key_tuple = tuple(k_str.split(' > '))
        strategy_map[key_tuple] = allocation

    current_state_str = ' > '.join(current_state)
    # 현재 상태에 맞는 비중을 맵에서 찾습니다. 없으면 0.0 (현금)
    current_alloc = strategy_map.get(current_state, 0.0) 

    return current_state_str, current_alloc, last_date


# --- 헬퍼 함수 3: 이메일 전송 (기존과 동일) ---
def send_email(subject, body, sender, password, receiver):
    if not all([sender, password, receiver]):
        print("이메일 환경 변수가 설정되지 않았습니다. (EMAIL_ADDRESS, EMAIL_PASSWORD, EMAIL_TO_1)")
        return

    print(f"\n[이메일 전송] {receiver}(으)로 알림 발송 시도...")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = receiver
    msg.set_content(body) # 이메일 본문 설정

    context = ssl.create_default_context()
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
            server.login(sender, password)
            server.send_message(msg)
        print("[이메일 전송] 성공!")
    except Exception as e:
        print(f"[이메일 전송] 실패: {e}")


# --- [수정] 메인 로직: 현재 상태만 확인하고 이메일 발송 ---
if __name__ == "__main__":
    
    # 1. 현재 상태 및 비중 가져오기
    current_state_str, current_alloc, last_date = get_current_recommendation(Ticker, my_strategy)

    # 2. 이메일 제목 및 본문 생성
    email_subject = f"주간 {Ticker} 리밸런싱 알림 ({last_date})"
    
    email_body = f"""
안녕하세요,

{last_date} 기준 {Ticker}의 현재 상태 및 권장 비중입니다.

■ 현재 SMA 상태
-> {current_state_str}

■ 권장 비중 (전략 기준)
-> {current_alloc * 100:.0f}%

---
[참고: 전체 전략 맵]
"""
    # 이메일 본문에 전략 맵 전체를 참고용으로 추가
    for state_str, alloc in my_strategy.items():
        email_body += f"- {state_str:<25}: {alloc * 100:.0f}%\n"

    # (GitHub Actions 로그 확인을 위해 콘솔에도 출력)
    print("--- 이메일 발송 내용 ---")
    print(email_body.strip())
    print("-" * 25)

    # 3. 이메일 전송 실행
    send_email(
        subject=email_subject,
        body=email_body.strip(), # 앞뒤 공백 제거
        sender=EMAIL_SENDER,
        password=EMAIL_PASSWORD,
        receiver=EMAIL_RECEIVER
    )
