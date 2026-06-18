import asyncio
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.browser import BrowserManager
from core.tool_registry import ToolRegistry
from Kafka.kafka import KafkaConsumer
from router_message import router_message


async def main():
    # Khởi tạo BrowserManager 1 lần duy nhất để dùng chung cho các message
    browser_manager = BrowserManager()
    await browser_manager.init_browser()

    # Thực hiện đăng nhập Facebook 1 lần duy nhất khi khởi động
    print("[*] Đang tiến hành đăng nhập Facebook...")
    login_success = await browser_manager.login_fb("https://www.facebook.com")
    if not login_success:
        print("[-] Đăng nhập Facebook thất bại khi khởi động worker!")
        return

    # Xử lý các popup trên trang chủ sau khi đăng nhập thành công
    from services.check_page import dismiss_popups
    if browser_manager.page:
        await dismiss_popups(browser_manager.page)
    print("[+] Đăng nhập và cấu hình môi trường Facebook thành công!")

    consumer = KafkaConsumer()
    topic_crawl = os.getenv("TOPIC_TASK_CRAWL", "task_queue_crawl")

    for message in consumer.consumer_with_task(topic_crawl, offset=6):
        print(message)
        await router_message(message, browser_manager)


if __name__ == "__main__":
    asyncio.run(main())
