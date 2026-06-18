#!/usr/bin/env python3
"""Take screenshots of the boardfarm version feature."""
import asyncio
import aiohttp
from playwright.async_api import async_playwright

DEVICE_ID = "7c6cdcb2-4a57-4e60-8e0b-3b1bec4cf5bc"
BASE_URL = "http://localhost:5173"
API_URL = "http://localhost:8765"
SCREENSHOTS_DIR = "/home/user/boardfarm/screenshots"

DIRTY_VERSION = (
    "f9e8d7c6:dirty:a1b2c3d4\n"
    "--- /opt/sca/ref-version.txt\n"
    "+++ /tmp/current_version.txt\n"
    "@@ -1,5 +1,5 @@\n"
    " kernel 6.6.30\n"
    " glibc 2.38\n"
    "-openssl 3.2.1\n"
    "+openssl 3.3.0\n"
    " busybox 1.36.1\n"
    "-python3 3.11.8\n"
    "+python3 3.12.2"
)

async def set_version(session, version):
    async with session.patch(
        f"{API_URL}/devices/{DEVICE_ID}/version",
        json={"version": version},
        headers={"Content-Type": "application/json"}
    ) as resp:
        text = await resp.text()
        print(f"Set version response: {resp.status} {text[:100]}")

async def main():
    async with aiohttp.ClientSession() as http_session:
        async with async_playwright() as p:
            browser = await p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
            context = await browser.new_context(viewport={"width": 1280, "height": 800})
            page = await context.new_page()

            # Set localStorage on the root page first
            print("Setting up localStorage...")
            await page.goto(BASE_URL)
            await page.evaluate(f"""() => {{
                localStorage.setItem('bf_server_url', '{API_URL}');
                localStorage.setItem('bf_username', 'testuser');
            }}""")
            print("localStorage set")

            # ── Screenshot 1 & 2: CLEAN version ──────────────────────────────────
            print(f"Navigating to device detail: {BASE_URL}/devices/{DEVICE_ID}")
            await page.goto(f"{BASE_URL}/devices/{DEVICE_ID}")

            # Wait for the green clean badge to appear
            print("Waiting for clean badge (a1b2c3d4)...")
            try:
                await page.wait_for_selector("button:has-text('a1b2c3d4')", timeout=15000)
                print("Found clean badge by text")
            except Exception:
                # Fallback: look for any version badge
                print("Trying fallback selectors for clean badge...")
                await page.wait_for_selector("[class*='version'], [class*='badge'], [class*='chip']", timeout=10000)

            await page.wait_for_timeout(1000)

            print("Taking version-clean-badge screenshot...")
            await page.screenshot(path=f"{SCREENSHOTS_DIR}/version-clean-badge.png", full_page=False)
            print("Saved version-clean-badge.png")

            # Click the green badge to open the modal
            print("Clicking the clean badge...")
            try:
                await page.click("button:has-text('a1b2c3d4')")
            except Exception:
                # Try other selectors
                await page.click("[class*='version'], [class*='badge']")

            # Wait for modal to appear
            print("Waiting for modal...")
            await page.wait_for_selector(
                "[role='dialog'], .modal, [class*='modal'], [class*='Modal'], [class*='dialog'], [class*='Dialog']",
                timeout=10000
            )
            await page.wait_for_timeout(800)

            print("Taking version-clean-modal screenshot...")
            await page.screenshot(path=f"{SCREENSHOTS_DIR}/version-clean-modal.png", full_page=False)
            print("Saved version-clean-modal.png")

            # ── Set dirty version via API ─────────────────────────────────────────
            print("Setting dirty version via API...")
            await set_version(http_session, DIRTY_VERSION)
            await page.wait_for_timeout(500)

            # Close any open modal (press Escape)
            await page.keyboard.press("Escape")
            await page.wait_for_timeout(500)

            # ── Screenshot 3 & 4: DIRTY version ──────────────────────────────────
            print("Reloading for dirty version...")
            await page.reload()

            # Wait for the red dirty badge
            print("Waiting for dirty badge (f9e8d7c6)...")
            try:
                await page.wait_for_selector("button:has-text('f9e8d7c6')", timeout=15000)
                print("Found dirty badge by text")
            except Exception:
                print("Trying fallback selectors for dirty badge...")
                await page.wait_for_selector("[class*='version'], [class*='badge']", timeout=10000)

            await page.wait_for_timeout(1000)

            print("Taking version-dirty-badge screenshot...")
            await page.screenshot(path=f"{SCREENSHOTS_DIR}/version-dirty-badge.png", full_page=False)
            print("Saved version-dirty-badge.png")

            # Click the red badge
            print("Clicking the dirty badge...")
            try:
                await page.click("button:has-text('f9e8d7c6')")
            except Exception:
                await page.click("[class*='version'], [class*='badge']")

            # Wait for modal with diff view
            print("Waiting for diff modal...")
            await page.wait_for_selector(
                "[role='dialog'], .modal, [class*='modal'], [class*='Modal'], [class*='dialog'], [class*='Dialog']",
                timeout=10000
            )
            await page.wait_for_timeout(800)

            print("Taking version-dirty-modal screenshot...")
            await page.screenshot(path=f"{SCREENSHOTS_DIR}/version-dirty-modal.png", full_page=False)
            print("Saved version-dirty-modal.png")

            await browser.close()
            print("All 4 screenshots taken successfully!")

asyncio.run(main())
