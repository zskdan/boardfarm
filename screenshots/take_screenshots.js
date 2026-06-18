#!/usr/bin/env node
/**
 * Take screenshots of the boardfarm version feature using Node.js Playwright.
 */
const { chromium } = require('/opt/node22/lib/node_modules/playwright');
const http = require('http');

const DEVICE_ID = "7c6cdcb2-4a57-4e60-8e0b-3b1bec4cf5bc";
const BASE_URL = "http://localhost:5173";
const API_URL = "http://localhost:8765";
const SCREENSHOTS_DIR = "/home/user/boardfarm/screenshots";

const CLEAN_VERSION =
    "a1b2c3d4:clean\n" +
    "kernel 6.6.30\n" +
    "glibc 2.38\n" +
    "openssl 3.2.1\n" +
    "busybox 1.36.1\n" +
    "python3 3.11.8";

const DIRTY_VERSION =
    "f9e8d7c6:dirty:a1b2c3d4\n" +
    "--- /opt/sca/ref-version.txt\n" +
    "+++ /tmp/current_version.txt\n" +
    "@@ -1,5 +1,5 @@\n" +
    " kernel 6.6.30\n" +
    " glibc 2.38\n" +
    "-openssl 3.2.1\n" +
    "+openssl 3.3.0\n" +
    " busybox 1.36.1\n" +
    "-python3 3.11.8\n" +
    "+python3 3.12.2";

function patchVersion(version) {
    return new Promise((resolve, reject) => {
        const body = JSON.stringify({ version });
        const options = {
            hostname: 'localhost',
            port: 8765,
            path: `/devices/${DEVICE_ID}/version`,
            method: 'PATCH',
            headers: {
                'Content-Type': 'application/json',
                'Content-Length': Buffer.byteLength(body)
            }
        };
        const req = http.request(options, (res) => {
            let data = '';
            res.on('data', chunk => data += chunk);
            res.on('end', () => {
                console.log(`PATCH /version response: ${res.statusCode} ${data.slice(0, 80)}`);
                resolve(data);
            });
        });
        req.on('error', reject);
        req.write(body);
        req.end();
    });
}

async function main() {
    // First, reset to clean version via API
    console.log('Setting clean version via API...');
    await patchVersion(CLEAN_VERSION);

    console.log('Launching browser...');
    const browser = await chromium.launch({
        args: ['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu']
    });
    const context = await browser.newContext({ viewport: { width: 1280, height: 800 } });
    const page = await context.newPage();

    // Set localStorage on root page first
    console.log('Setting localStorage...');
    await page.goto(BASE_URL);
    await page.evaluate(({ apiUrl }) => {
        localStorage.setItem('bf_server_url', apiUrl);
        localStorage.setItem('bf_username', 'testuser');
    }, { apiUrl: API_URL });
    console.log('localStorage set');

    // ── Screenshot 1 & 2: CLEAN version ───────────────────────────────────
    console.log(`Navigating to device: ${BASE_URL}/devices/${DEVICE_ID}`);
    await page.goto(`${BASE_URL}/devices/${DEVICE_ID}`);

    console.log('Waiting for clean badge (a1b2c3d4)...');
    await page.waitForSelector("button[title='Click to view version details']", { timeout: 20000 });
    // Verify it's the clean (green) badge
    await page.waitForFunction(() => {
        const btn = document.querySelector("button[title='Click to view version details']");
        return btn && btn.textContent.includes('a1b2c3d4');
    }, { timeout: 15000 });
    await page.waitForTimeout(1000);

    console.log('Taking version-clean-badge screenshot...');
    await page.screenshot({ path: `${SCREENSHOTS_DIR}/version-clean-badge.png` });
    console.log('Saved version-clean-badge.png');

    // Click the badge to open modal
    console.log('Clicking clean badge...');
    await page.click("button[title='Click to view version details']");

    // Wait for the modal (fixed overlay with z-50)
    console.log('Waiting for version detail modal...');
    await page.waitForSelector("h2:text('Version details')", { timeout: 10000 });
    await page.waitForTimeout(800);

    console.log('Taking version-clean-modal screenshot...');
    await page.screenshot({ path: `${SCREENSHOTS_DIR}/version-clean-modal.png` });
    console.log('Saved version-clean-modal.png');

    // ── Set dirty version via API ──────────────────────────────────────────
    console.log('Setting dirty version via API...');
    await patchVersion(DIRTY_VERSION);

    // Close modal by clicking backdrop or X button
    await page.click("button:has(svg)", { position: { x: 0, y: 0 } }).catch(() => {});
    // Press Escape to close modal
    await page.keyboard.press('Escape');
    await page.waitForTimeout(300);

    // ── Screenshot 3 & 4: DIRTY version ───────────────────────────────────
    console.log('Reloading page for dirty version...');
    await page.reload();

    console.log('Waiting for dirty badge (f9e8d7c6)...');
    await page.waitForSelector("button[title='Click to view version details']", { timeout: 20000 });
    await page.waitForFunction(() => {
        const btn = document.querySelector("button[title='Click to view version details']");
        return btn && btn.textContent.includes('f9e8d7c6');
    }, { timeout: 15000 });
    await page.waitForTimeout(1000);

    console.log('Taking version-dirty-badge screenshot...');
    await page.screenshot({ path: `${SCREENSHOTS_DIR}/version-dirty-badge.png` });
    console.log('Saved version-dirty-badge.png');

    // Click the dirty badge
    console.log('Clicking dirty badge...');
    await page.click("button[title='Click to view version details']");

    // Wait for modal
    console.log('Waiting for version detail modal (dirty)...');
    await page.waitForSelector("h2:text('Version details')", { timeout: 10000 });
    await page.waitForTimeout(800);

    console.log('Taking version-dirty-modal screenshot...');
    await page.screenshot({ path: `${SCREENSHOTS_DIR}/version-dirty-modal.png` });
    console.log('Saved version-dirty-modal.png');

    await browser.close();
    console.log('\nAll 4 screenshots taken successfully!');
    console.log('  ' + SCREENSHOTS_DIR + '/version-clean-badge.png');
    console.log('  ' + SCREENSHOTS_DIR + '/version-clean-modal.png');
    console.log('  ' + SCREENSHOTS_DIR + '/version-dirty-badge.png');
    console.log('  ' + SCREENSHOTS_DIR + '/version-dirty-modal.png');
}

main().catch(err => {
    console.error('Error:', err.message);
    process.exit(1);
});
