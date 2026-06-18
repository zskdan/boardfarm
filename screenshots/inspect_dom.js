#!/usr/bin/env node
/**
 * Inspect the DOM after clicking the version badge to find modal selectors.
 */
const { chromium } = require('/opt/node22/lib/node_modules/playwright');

const DEVICE_ID = "7c6cdcb2-4a57-4e60-8e0b-3b1bec4cf5bc";
const BASE_URL = "http://localhost:5173";
const API_URL = "http://localhost:8765";

async function main() {
    const browser = await chromium.launch({
        args: ['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu']
    });
    const context = await browser.newContext({ viewport: { width: 1280, height: 800 } });
    const page = await context.newPage();

    // Capture console messages
    page.on('console', msg => console.log('BROWSER:', msg.text()));

    await page.goto(BASE_URL);
    await page.evaluate(({ apiUrl }) => {
        localStorage.setItem('bf_server_url', apiUrl);
        localStorage.setItem('bf_username', 'testuser');
    }, { apiUrl: API_URL });

    await page.goto(`${BASE_URL}/devices/${DEVICE_ID}`);
    await page.waitForSelector("button:has-text('a1b2c3d4')", { timeout: 20000 });
    await page.waitForTimeout(1000);

    // Take a screenshot before clicking
    await page.screenshot({ path: '/tmp/before_click.png' });
    console.log('Screenshot taken before click');

    // Get the HTML of the area around the version badge
    const badgeHtml = await page.evaluate(() => {
        const badge = document.querySelector('button');
        // Find button with a1b2c3d4 text
        const buttons = Array.from(document.querySelectorAll('button'));
        const versionBtn = buttons.find(b => b.textContent.includes('a1b2c3d4'));
        if (versionBtn) {
            return versionBtn.outerHTML + '\n\nParent:\n' + versionBtn.parentElement.outerHTML.slice(0, 500);
        }
        return 'Button not found';
    });
    console.log('Badge HTML:', badgeHtml);

    // Click and wait to see what appears
    await page.click("button:has-text('a1b2c3d4')");
    await page.waitForTimeout(2000);

    // Get all visible elements after click
    const afterHtml = await page.evaluate(() => {
        return document.body.innerHTML.slice(0, 3000);
    });
    console.log('\nAfter click body (first 3000 chars):\n', afterHtml);

    // Take a screenshot after clicking
    await page.screenshot({ path: '/tmp/after_click.png' });
    console.log('Screenshot taken after click');

    await browser.close();
}

main().catch(err => {
    console.error('Error:', err);
    process.exit(1);
});
