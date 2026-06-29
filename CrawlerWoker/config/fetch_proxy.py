import requests

KEY_XOAY = "iLuwvXLfqbjSkKkQSocOak"
URL_FETCH_PROXY = f"https://proxyxoay.shop/api/get.php?key={KEY_XOAY}&&nhamang=random&&tinhthanh=0&whitelist=1"


def get_new_proxy():
    try:
        response = requests.get(URL_FETCH_PROXY)
        data = response.json()
        if data.get("status") == 100:
            # API trả về "42.117.243.215:10836::", Playwright cần "http://42.117.243.215:10836"
            raw_proxy = data.get("proxyhttp", "")
            clean_proxy = raw_proxy.rstrip(":")
            return f"http://{clean_proxy}" if clean_proxy else None
        else:
            print(f"Lỗi lấy proxy: {data.get('message')}")
            return None
    except Exception as e:
        print(f"Lỗi API proxy: {e}")
        return None
