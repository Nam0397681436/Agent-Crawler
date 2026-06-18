import os
import urllib.request
import zipfile
import io
import logging

logger = logging.getLogger(__name__)

def download_and_extract_extension(extension_id: str, output_dir: str) -> str:
    """
    Downloads a Chrome extension by ID from the Chrome Web Store,
    strips the CRX header, and extracts it to output_dir.
    """
    if os.path.exists(output_dir) and os.path.exists(os.path.join(output_dir, "manifest.json")):
        logger.info(f"[+] Extension {extension_id} đã được cài đặt tại: {output_dir}")
        return output_dir

    os.makedirs(output_dir, exist_ok=True)
    
    # URL download CRX chính thức từ Chrome Web Store
    url = f"https://clients2.google.com/service/update2/crx?response=redirect&prodversion=110.0&acceptformat=crx2,crx3&x=id%3D{extension_id}%26installsource%3Dondemand%26uc"
    
    logger.info(f"[*] Đang tải extension {extension_id} từ Chrome Web Store...")
    
    # Thiết lập User-Agent giả lập trình duyệt để tránh bị chặn
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36"}
    )
    
    try:
        with urllib.request.urlopen(req) as response:
            crx_data = response.read()
    except Exception as e:
        logger.error(f"[-] Không thể tải extension: {e}")
        raise e
        
    # Tìm signature bắt đầu của file ZIP (PK\x03\x04) để loại bỏ header của CRX (CRX2/CRX3)
    zip_start = crx_data.find(b"PK\x03\x04")
    if zip_start == -1:
        raise ValueError("Không tìm thấy ZIP header trong file CRX tải về.")
        
    zip_data = crx_data[zip_start:]
    
    logger.info(f"[*] Đang giải nén extension vào: {output_dir}...")
    with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
        zf.extractall(output_dir)
        
    logger.info(f"[+] Giải nén thành công extension: {extension_id}")
    return output_dir

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # Thử chạy tải Nopecha
    NOPECHA_ID = "dknlfmjaanfblgfdfebhijalfmhmjjjo"
    target_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "extensions", "nopecha")
    download_and_extract_extension(NOPECHA_ID, target_path)
