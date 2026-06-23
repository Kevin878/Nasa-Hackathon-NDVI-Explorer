import requests
import time
import datetime
import random

API_BASE_URL = "https://ndvi-api-wtsg.onrender.com"

# 經緯度參數列表 (使用多個座標，避免每次都訪問完全相同的 Earth Engine 區域)
PING_LOCATIONS = [
    {"lat": 30.0, "lon": 120.0, "buffer_val": 1, "buffer_unit": "K"}, # 華東
    {"lat": 40.0, "lon": -100.0, "buffer_val": 1, "buffer_unit": "K"}, # 美國中部
    {"lat": -20.0, "lon": 140.0, "buffer_val": 1, "buffer_unit": "K"}, # 澳洲
]
# 請求間隔時間（秒）。10 分鐘 = 600 秒。
INTERVAL_SECONDS = 600

# 最大重試次數
MAX_RETRIES = 3
# --- 配置區塊結束 ---


def send_ping_request():
    """
    對 API 端點發送一個 Ping 請求，確保服務保持活躍。
    """
    # 隨機選擇一個位置參數
    params = random.choice(PING_LOCATIONS)

    url = API_BASE_URL + "/ndvi_heatmap"

    print(f"\n[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 正在發送請求...")
    print(f"URL: {url}, 參數: {params}")

    for attempt in range(MAX_RETRIES):
        try:
            # 設定超時，防止請求卡住
            response = requests.get(url, params=params, timeout=30) 
            
            # 檢查回應狀態碼
            if response.status_code == 200:
                print(f"🟢 請求成功！狀態碼: {response.status_code}")
                # print(f"回應摘要: {response.json().get('mean_ndvi', 'N/A')}")
                return True
            else:
                # 如果是 GEE 錯誤 (404/500) 或其他非 200 錯誤
                print(f"🟡 請求失敗 (非 200 狀態碼)。嘗試 {attempt + 1}/{MAX_RETRIES}")
                print(f"狀態碼: {response.status_code}, 錯誤訊息: {response.text[:150]}...")
                
        except requests.exceptions.RequestException as e:
            # 處理連線錯誤、超時、DNS 錯誤等
            print(f"🔴 發生連線錯誤或超時。嘗試 {attempt + 1}/{MAX_RETRIES}")
            print(f"錯誤詳情: {e}")

        # 如果不是最後一次嘗試，則等待一段時間後重試
        if attempt < MAX_RETRIES - 1:
            wait_time = (2 ** attempt) + random.uniform(1, 3) # 指數退避策略
            print(f"等待 {wait_time:.2f} 秒後重試...")
            time.sleep(wait_time)
        
    print("❌ 所有重試嘗試失敗。")
    return False

def main():
    """
    主循環：每隔指定時間發送一次請求。
    """
    print("--- Render Keep-Alive 服務啟動 ---")
    print(f"目標 API: {API_BASE_URL}")
    print(f"請求間隔: {INTERVAL_SECONDS / 60} 分鐘")
    
    while True:
        send_ping_request()
        print(f"\n等待 {INTERVAL_SECONDS} 秒進行下一次請求...")
        time.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nKeep-Alive 服務已停止。")
    except Exception as e:
        print(f"發生未預期的主要錯誤: {e}")
