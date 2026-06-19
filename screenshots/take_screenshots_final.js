const { chromium } = require('/opt/node22/lib/node_modules/playwright');
const http = require('http');

const BASE    = 'http://localhost:5173';
const API     = 'http://localhost:8765';
const OUT     = '/home/user/boardfarm/screenshots';
const DEVICE_ID = 'c5f0e828-6f54-46b8-b2a1-07167ef723c6'; // Demo Board with version_script set

async function go(page, path) {
  await page.goto(`${BASE}${path}`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(800);
}

async function shot(page, name) {
  await page.screenshot({ path: `${OUT}/${name}` });
  console.log(`  saved ${name}`);
}

// Find and click a button whose text matches regex
async function clickBtn(page, re, timeout = 3000) {
  const btns = await page.locator('button').all();
  for (const btn of btns) {
    const txt = await btn.textContent().catch(() => '');
    if (re.test(txt)) {
      await btn.click();
      return true;
    }
  }
  return false;
}

// Find a label by text and click its checkbox
async function toggleCheckbox(page, re, desiredState) {
  const labels = await page.locator('label').all();
  for (const label of labels) {
    const txt = await label.textContent().catch(() => '');
    if (re.test(txt)) {
      const cb = label.locator('input[type="checkbox"]');
      const checked = await cb.isChecked().catch(() => null);
      if (checked === null) continue;
      if (desiredState === true  && !checked) await cb.click();
      if (desiredState === false && checked)  await cb.click();
      console.log(`  "${txt.trim()}" checkbox → ${desiredState}`);
      return true;
    }
  }
  // Fallback: look for span/div siblings near checkboxes
  const checkboxes = await page.locator('input[type="checkbox"]').all();
  for (const cb of checkboxes) {
    const parentText = await cb.evaluate(el => {
      let p = el.parentElement;
      for (let i = 0; i < 4; i++) {
        if (p) { const t = p.textContent || ''; if (re.test(t)) return t; p = p.parentElement; }
      }
      return '';
    });
    if (parentText) {
      const checked = await cb.isChecked().catch(() => null);
      if (checked === null) continue;
      if (desiredState === true  && !checked) await cb.click();
      if (desiredState === false && checked)  await cb.click();
      console.log(`  "${parentText.trim().slice(0,40)}" checkbox → ${desiredState}`);
      return true;
    }
  }
  console.log(`  WARNING: checkbox matching /${re.source}/ not found`);
  return false;
}

(async () => {
  const browser = await chromium.launch({
    executablePath: '/opt/pw-browsers/chromium-1194/chrome-linux/chrome',
    args: ['--no-sandbox', '--disable-setuid-sandbox'],
  });
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();

  // Set localStorage credentials
  await page.goto(BASE, { waitUntil: 'domcontentloaded' });
  await page.evaluate(() => {
    localStorage.setItem('bf_server_url', 'http://localhost:8765');
    localStorage.setItem('bf_username', 'testuser');
  });

  // ── 1. Inventory ──────────────────────────────────────────────────────────
  console.log('[1/8] inventory.png');
  await go(page, '/devices');
  await shot(page, 'inventory.png');

  // ── 2. Setups ─────────────────────────────────────────────────────────────
  console.log('[2/8] setups.png');
  await go(page, '/setups');
  await shot(page, 'setups.png');

  // ── 3. Device detail (pending… badge + Redeploy) ──────────────────────────
  console.log('[3/8] device-detail.png');
  await go(page, `/devices/${DEVICE_ID}`);
  await page.waitForTimeout(600);
  await shot(page, 'device-detail.png');

  // ── 4. History ────────────────────────────────────────────────────────────
  console.log('[4/8] history.png');
  await go(page, '/history');
  await shot(page, 'history.png');

  // ── 5. Settings modal ─────────────────────────────────────────────────────
  console.log('[5/8] settings-modal.png');
  await go(page, '/devices');
  await page.waitForTimeout(400);

  // Dump all button texts to find the right one
  const allBtns = await page.locator('button').all();
  for (const btn of allBtns) {
    const txt = (await btn.textContent().catch(() => '')).trim();
    const aria = await btn.getAttribute('aria-label').catch(() => '');
    const title = await btn.getAttribute('title').catch(() => '');
    if (txt || aria || title) console.log(`  btn: "${txt}" aria="${aria}" title="${title}"`);
  }

  // Try clicking settings button
  const clicked = await clickBtn(page, /settings|gear|config/i);
  if (!clicked) {
    // Try the nav/header area for any clickable that opens a modal
    const navBtns = await page.locator('nav button, header button, [role="banner"] button').all();
    for (const btn of navBtns) {
      await btn.click().catch(() => {});
      const modal = await page.locator('[role="dialog"]').first().isVisible().catch(() => false);
      if (modal) { console.log('  opened modal via nav button'); break; }
    }
  }
  await page.waitForTimeout(600);
  await shot(page, 'settings-modal.png');

  // Close modal if open
  await page.keyboard.press('Escape');
  await page.waitForTimeout(300);

  // ── 6. Add setup modal ────────────────────────────────────────────────────
  console.log('[6/8] add-setup-modal.png');
  await go(page, '/setups');
  await page.waitForTimeout(400);

  // List buttons on setups page
  const setupBtns = await page.locator('button').all();
  for (const btn of setupBtns) {
    const txt = (await btn.textContent().catch(() => '')).trim();
    if (txt) console.log(`  setup page btn: "${txt}"`);
  }

  await clickBtn(page, /add.?setup|new.?setup|create.?setup|\+|add/i);
  await page.waitForTimeout(600);
  await shot(page, 'add-setup-modal.png');

  await page.keyboard.press('Escape');
  await page.waitForTimeout(300);

  // ── 7. Book setup modal ───────────────────────────────────────────────────
  console.log('[7/8] book-setup-modal.png');
  await go(page, '/setups');
  await page.waitForTimeout(400);

  await clickBtn(page, /book/i);
  await page.waitForTimeout(600);
  await shot(page, 'book-setup-modal.png');

  await page.keyboard.press('Escape');
  await page.waitForTimeout(300);

  // ── 8. Add device modal with all sections open ───────────────────────────
  console.log('[8/8] add-device-modal-agent.png');
  await go(page, '/devices');
  await page.waitForTimeout(400);

  // Open Add Device modal
  await clickBtn(page, /add.?device|new.?device|\+|add/i);
  await page.waitForTimeout(600);

  // Verify modal opened
  const modalOpen = await page.locator('[role="dialog"]').first().isVisible().catch(() => false);
  console.log(`  modal open: ${modalOpen}`);

  // Check Ethernet
  await toggleCheckbox(page, /ethernet/i, true);
  await page.waitForTimeout(300);

  // Check Hardware Agent
  await toggleCheckbox(page, /hardware.?agent|agent/i, true);
  await page.waitForTimeout(300);

  // Uncheck Self hosted (to show agent IP field)
  await toggleCheckbox(page, /self.?hosted/i, false);
  await page.waitForTimeout(300);

  // Check Version Control (to show version fields)
  await toggleCheckbox(page, /version.?control/i, true);
  await page.waitForTimeout(300);

  // Scroll modal to bottom to show version control fields
  await page.evaluate(() => {
    const selectors = ['[role="dialog"]', '.modal', 'form', '[class*="modal"]', '[class*="dialog"]'];
    for (const s of selectors) {
      const el = document.querySelector(s);
      if (el) { el.scrollTop = el.scrollHeight; return; }
    }
    window.scrollTo(0, document.body.scrollHeight);
  });
  await page.waitForTimeout(400);

  await shot(page, 'add-device-modal-agent.png');

  await browser.close();
  console.log('\nAll screenshots saved to', OUT);
})();
