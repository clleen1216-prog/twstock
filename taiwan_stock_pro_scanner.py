import datetime
import pandas as pd
import requests
import twstock

# 台灣 50 (0050) 全成分股代號清單
WATCH_LIST = [
    '1101',
    '1216',
    '1301',
    '1303',
    '1326',
    '1402',
    '1504',
    '2002',
    '2207',
    '2301',
    '2303',
    '2308',
    '2317',
    '2327',
    '2330',
    '2357',
    '2379',
    '2382',
    '2395',
    '2408',
    '2412',
    '2454',
    '2603',
    '2609',
    '2615',
    '2801',
    '2880',
    '2881',
    '2882',
    '2884',
    '2885',
    '2886',
    '2887',
    '2891',
    '2892',
    '2912',
    '3008',
    '3034',
    '3037',
    '3045',
    '3231',
    '3661',
    '3711',
    '4904',
    '5871',
    '5880',
    '6505',
    '6669',
    '9910',
]


def check_market_settlement_risk():
  """動態偵測台股選擇權結算日風控閘門"""
  today = datetime.datetime.now()
  return today.weekday() == 2  # 週三為結算日


def get_institutional_data():
  """取得證交所三大法人最新買賣超資料"""
  url = 'https://www.twse.com.tw/rwd/zh/fund/T86?response=json'
  headers = {'User-Agent': 'Mozilla/5.0'}
  institutional_dict = {}
  try:
    response = requests.get(url, headers=headers, timeout=10)
    data = response.json()
    if data.get('stat') == 'OK':
      rows = data.get('data', [])
      for row in rows:
        ticker = row[0].strip()
        if ticker in WATCH_LIST:
          foreign_net = int(row[2].replace(',', ''))
          trust_net = int(row[4].replace(',', ''))
          institutional_dict[ticker] = {'foreign': foreign_net, 'trust': trust_net}
  except Exception as e:
    print(f'取得法人買賣超資料發生錯誤: {e}')
  return institutional_dict


def run_master_scanner():
  now = datetime.datetime.now()
  current_time_str = now.strftime('%Y-%m-%d %H:%M')
  is_settlement_day = check_market_settlement_risk()

  print(
      f'=== 【台灣50波段 SOP 旗艦風控掃描】 執行時間: {current_time_str} ==='
  )
  if is_settlement_day:
    print(
        '⚠️ 【風控警報】今天是週三選擇權結算日！權值股尾盤易受造市商對沖影響'
        '，突破追價請提高警覺。'
    )
  print(f'本次掃描目標：台灣50（0050）共 {len(WATCH_LIST)} 檔核心權值與產業龍頭')
  print('-' * 70)

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
          'Volume': [d.capacity for d in stock.data],
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

      ma5, ma10, ma20, ma60 = (
          float(latest['MA5']),
          float(latest['MA10']),
          float(latest['MA20']),
          float(latest['MA60']),
      )
      vol = float(latest['Volume'])
      vol_ma20 = float(latest['Vol_MA20'])

      # 1. 均線糾結度檢核 (< 5%)
      ma_values = [ma5, ma10, ma20, ma60]
      spread_pct = (max(ma_values) - min(ma_values)) / close
      if spread_pct >= 0.05:
        continue

      # 2. 進階假突破與 K 棒型態檢核
      vol_ratio = round(vol / vol_ma20, 2) if vol_ma20 > 0 else 0
      total_length = high_p - low_p
      upper_shadow = high_p - max(close, open_p)
      is_upper_shadow_trap = (
          total_length > 0 and (upper_shadow / total_length) > 0.4
      )
      is_bearish_candle = close < open_p

      # 3. 智慧評分與風控模型
      score = 70  # 基礎分

      if spread_pct < 0.025:
        score += 10  # 糾結度極度緊密加分

      status = '👀 【盤整中】均線糾結觀察區'
      if vol_ratio >= 1.5 and close > ma20:
        if is_upper_shadow_trap or is_bearish_candle:
          status = '⚠️ 【高度警戒】爆量假突破/上影線出貨'
          score -= 30
        else:
          status = '🔥 【強勢發動】扎實突破 + 爆量'
          score += 20
      elif vol_ratio < 0.8:
        status = '⏳ 【等待中】均線糾結 + 量縮沉澱'
        score += 5

      # 4. 籌碼背書 (外資 + 投信)
      foreign_net = inst_data.get(ticker, {}).get('foreign', 0)
      trust_net = inst_data.get(ticker, {}).get('trust', 0)

      chip_status = '中立'
      if foreign_net > 0 and trust_net > 0:
        chip_status = '🟢 雙法人同步買超 (強勢背書)'
        score += 15
      elif foreign_net > 0 or trust_net > 0:
        chip_status = '🟡 單法人買超'
        score += 5
      elif foreign_net < 0 and trust_net < 0:
        chip_status = '🔴 雙法人調節賣超'
        score -= 15

      if is_settlement_day and '強勢發動' in status:
        score -= 10
        status += ' (⚠️ 結算日追價風險)'

      results.append({
          '股票代號': ticker,
          '收盤/現價': close,
          '糾結度(%)': round(spread_pct * 100, 2),
          '量能倍數': vol_ratio,
          '綜合評分': score,
          '籌碼背書': chip_status,
          '狀態': status,
      })
    except Exception as ex:
      continue

  df_result = pd.DataFrame(results)
  if not df_result.empty:
    df_result = df_result.sort_values(by='綜合評分', ascending=False)
    print(df_result.to_string(index=False))
  else:
    print('今日無符合均線糾結條件的標的。')


if __name__ == '__main__':
  run_master_scanner()
