import asyncio
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.browser import BrowserManager
from core.tool_registry import ToolRegistry
from Kafka.kafka import KafkaConsumer
from router_message import router_message


async def main():
    browser = BrowserManager()
    await browser.start()

    # Đăng nhập Facebook 1 lần duy nhất khi khởi động
    print("[*] Đang tiến hành đăng nhập Facebook...")
    page = await browser.new_page()
    login_ok = await browser.ensure_login(page, "https://www.facebook.com")
    if not login_ok:
        print("[-] Đăng nhập thất bại. Thoát.")
        await browser.stop(save_data_path=None)
        return

    from services.check_page import dismiss_popups
    await dismiss_popups(page)
    print("[+] Đăng nhập và cấu hình môi trường thành công!")

    consumer = KafkaConsumer()
    topic_crawl = os.getenv("TOPIC_TASK_CRAWL", "task_queue_crawl")

    try:
        for message in consumer.consumer_with_task(topic_crawl, offset=6):
            print(message)
            await router_message(message, browser)
    finally:
        await browser.stop()


if __name__ == "__main__":
    asyncio.run(main())
