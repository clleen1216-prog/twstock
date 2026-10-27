import datetime
import pandas as pd
import requests
import twstock

# 您的核心監控清單 (台股代號)
WATCH_LIST = ['2330', '2317', '2454', '2382', '2308', '3008', '3260', '2408', '3481']

def get_institutional_data():
    """透過證交所 OpenAPI 或 FinMind 取得三大法人最新買賣超資料"""
    # 這裡串接證交所每日三大法人買賣超彙總表 API
    url = "https://www.twse.com.tw/rwd/zh/fund/T86?response=json"
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    institutional_dict = {}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        data = response.json()
        if data.get('stat') == 'OK':
            rows = data.get('data', [])
            for row in rows:
                # row[0] 是代號, row[2] 是外資買賣超, row[4] 是投信買賣超
                ticker = row[0].strip()
                if ticker in WATCH_LIST:
                    # 移除千分位逗號並轉為整數 (張數)
                    foreign_net = int(row[2].replace(',', ''))
                    trust_net = int(row[4].replace(',', ''))
                    institutional_dict[ticker] = {
                        'foreign': foreign_net,
                        'trust': trust_net
                    }
    except Exception as e:
        print(f"取得法人買賣超資料發生錯誤: {e}")
    
    return institutional_dict

def run_scanner():
    now = datetime.datetime.now()
    current_time_str = now.strftime('%Y-%m-%d %H:%M')
    print(f"=== 【台股波段 SOP 智慧掃描】 執行時間: {current_time_str} ===")
    
    current_year = now.year
    inst_data = get_institutional_data()
    
    results = []

    for ticker in WATCH_LIST:
        try:
            stock = twstock.Stock(ticker)
            stock.fetch_from(current_year - 1, 1)
            
            if not stock.data or len(stock.data) < 60:
                continue

            df = pd.DataFrame({
                'Date': [d.date for d in stock.data],
                'Open': [d.open for d in stock.data],
                'High': [d.high for d in stock.data],
                'Low': [d.low for d in stock.data],
                'Close': [d.close for d in stock.data],
                'Volume': [d.capacity for d in stock.data]
            })
            df.set_index('Date', inplace=True)

            # 計算技術指標
            df['MA5'] = df['Close'].rolling(window=5).mean()
            df['MA10'] = df['Close'].rolling(window=10).mean()
            df['MA20'] = df['Close'].rolling(window=20).mean()
            df['MA60'] = df['Close'].rolling(window=60).mean()
            df['Vol_MA20'] = df['Volume'].rolling(window=20).mean()

            latest = df.iloc[-1]
            close = float(latest['Close'])
            open_p = float(latest['Open'])
            high_p = float(latest['High'])
            low_p = float(latest['Low'])
            
            ma5, ma10, ma20, ma60 = float(latest['MA5']), float(latest['MA10']), float(latest['MA20']), float(latest['MA60'])
            vol = float(latest['Volume'])
            vol_ma20 = float(latest['Vol_MA20'])

            # 1. 均線糾結度 (5%, 2.5%)
            ma_values = [ma5, ma10, ma20, ma60]
            spread_pct = (max(ma_values) - min(ma_values)) / close
            is_converged = spread_pct < 0.05

            if not is_converged:
                continue

            # 2. 量價與突破檢核
            vol_ratio = round(vol / vol_ma20, 2) if vol_ma20 > 0 else 0
            k_body_ratio = (close - open_p) / (high_p - low_p) if (high_p - low_p) > 0 else 0
            
            status = "【👀 盤整中】均線糾結觀察區"
            if vol_ratio >= 1.5 and close > ma20 and k_body_ratio > 0.5:
                status = "【🔥 強勢發動】突破 + 爆量"

            # 3. 籌碼背書 (三大法人買賣超)
            foreign_net = inst_data.get(ticker, {}).get('foreign', 0)
            trust_net = inst_data.get(ticker, {}).get('trust', 0)
            
            chip_status = "中立"
            if foreign_net > 0 and trust_net > 0:
                chip_status = "🟢 雙法人同步買超 (強勢背書)"
            elif foreign_net > 0 or trust_net > 0:
                chip_status = "🟡 單法人買超"
            elif foreign_net < 0 and trust_net < 0:
                chip_status = "🔴 雙法人調節賣超"

            results.append({
                "股票代號": ticker,
                "收盤/現價": close,
                "糾結度(%)": round(spread_pct * 100, 2),
                "量能倍數": vol_ratio,
                "外資買賣超(張)": foreign_net,
                "投信買賣超(張)": trust_net,
                "籌碼背書": chip_status,
                "狀態": status
            })
        except Exception as ex:
            continue

    df_result = pd.DataFrame(results)
    if not df_result.empty:
        print("\n=== 台股 SOP 智慧掃描與法人籌碼報告 ===")
        print(df_result.to_string(index=False))
    else:
        print("\n今日無符合均線糾結條件的標的。")

if __name__ == "__main__":
    run_scanner()
