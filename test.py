import asyncio
import sys
from pathlib import Path
from playwright.async_api import async_playwright

# Đảm bảo hiển thị tiếng Việt không bị lỗi Unicode trên Windows Command Prompt/PowerShell
sys.stdout.reconfigure(encoding='utf-8')

async def main():
    try:
        async with async_playwright() as p:
            # 1. Định nghĩa một thư mục để làm Profile thực
            user_data_dir = Path(__file__).parent / "chrome_test_profile"
            
            print(f"[*] Khởi tạo Profile tại: {user_data_dir}")

            # 2. Khởi động Chrome không tải Extension bên ngoài
            context = await p.chromium.launch_persistent_context(
                user_data_dir=str(user_data_dir),
                headless=False
            )

            # 3. Mở một trang mới hiển thị quản lý extension
            page = await context.new_page()
            await page.goto("chrome://extensions/")
            print("[+] Chrome đã mở thành công (không nạp Extension ngoài)!")
            
            # Chờ 3 giây trước khi kiểm tra facebook
            await asyncio.sleep(3)
            
            # 5. Tự động tìm tab facebook.com hoặc mở một tab mới
            fb_page = None
            for p_tab in context.pages:
                if "facebook.com" in p_tab.url:
                    fb_page = p_tab
                    await fb_page.bring_to_front()
                    print("[+] Đã phát hiện và chuyển sang tab facebook.com có sẵn.")
                    break
            
            if not fb_page:
                print("[*] Không tìm thấy tab facebook.com sẵn có. Đang mở tab mới và truy cập facebook.com...")
                fb_page = await context.new_page()
                await fb_page.goto("https://www.facebook.com")
                print("[+] Đã mở thành công facebook.com.")

            # 6. Giữ trình duyệt mở vô hạn cho đến khi người dùng nhấn Ctrl+C
            print("[*] Đã chuẩn bị xong. Trình duyệt sẽ được giữ mở vô hạn.")
            print("[*] Nhấn Ctrl+C tại Terminal để đóng trình duyệt.")
            
            stop_event = asyncio.Event()
            await stop_event.wait()

    except Exception as e:
        print(f"[-] Đã xảy ra lỗi hệ thống: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # Chạy vòng lặp bất đồng bộ (asyncio)
    asyncio.run(main())