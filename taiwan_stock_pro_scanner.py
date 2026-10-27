import datetime
import pandas as pd
import requests
import twstock

# 核心監控清單 (半導體與 AI 供應鏈)
WATCH_LIST = [
    '2330',  # 台積電
    '2317',  # 鴻海
    '2454',  # 聯發科
    '2382',  # 廣達
    '2308',  # 台達電
    '3711',  # 日月光投控
    '3034',  # 聯詠
    '2379',  # 瑞昱
    '3231',  # 緯創
    '6669',  # 緯穎
    '3661',  # 世芯-KY
    '3443',  # 創意
    '3017',  # 奇鋐
    '8210',  # 勤誠
    '3260',  # 威剛
    '2408',  # 南亞科
]


def check_market_settlement_risk():
  """動態偵測台股選擇權結算日風控閘門

  台股每週三為週選擇權結算日，尾盤容易受造市商避險買賣盤影響出現虛假波動。
  """
  today = datetime.datetime.now()
  is_wednesday = today.weekday() == 2  # 0=週一, 2=週三
  return is_wednesday


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

  print(f'=== 【短線波段 SOP 頂級風控智慧掃描】 執行時間: {current_time_str} ===')
  if is_settlement_day:
    print(
        '⚠️ 【風控警報】今天是週三選擇權結算日！尾盤現貨權值股易受造市商對沖影響'
        '，突破訊號請提高警覺。'
    )
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
      score = 70  # 基礎分（符合均線糾結）

      # 糾結度越緊密加分越多
      if spread_pct < 0.025:
        score += 10

      # 量價狀態與陷阱防護
      status = '👀 【盤整中】均線糾結觀察區'
      if vol_ratio >= 1.5 and close > ma20:
        if is_upper_shadow_trap or is_bearish_candle:
          status = '⚠️ 【高度警戒】爆量假突破/上影線出貨'
          score -= 30  # 嚴重扣分
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

      # 若逢週三結算日，對突破型態進行風控懲罰
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
