import os
import asyncio
from playwright.async_api import async_playwright
from dotenv import load_dotenv

# Load env variables from the parent directory's .env file
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))


async def main():
    profile_path = os.getenv("PROFILE_PATH")
    if not profile_path:
        profile_path = os.path.join(os.getcwd(), "chrome_test_profile")

    print(f"Using profile path: {profile_path}")

    async with async_playwright() as p:
        # Launch Chromium persistent context
        context = await p.chromium.launch_persistent_context(
            user_data_dir=profile_path,
            headless=False,
            no_viewport=True,
            args=["--disable-blink-features=AutomationControlled", "--start-maximized"],
        )
        await context.clear_cookies()

        # Open a new page or get the default one
        page = context.pages[0] if context.pages else await context.new_page()

        # Navigate to Facebook
        print("Navigating to Facebook...")
        await page.goto("https://www.facebook.com")

        print("\nBrowser is open and running!")
        print("You can perform operations in the browser window.")
        print("Press Ctrl+C in the terminal or close the browser window to exit.")

        # Keep the script running until the browser context is closed
        stop_event = asyncio.Event()
        context.on("close", lambda _: stop_event.set())

        try:
            await stop_event.wait()
        except asyncio.CancelledError:
            pass
        finally:
            print("\nClosing browser...")
            await context.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nClosed by user.")
