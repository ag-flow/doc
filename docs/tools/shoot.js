/* Driver de screenshots pour la doc utilisateur docflow.
 * Chromium browserless distant (test1:3000), app de démo sur test1:18086.
 * Usage : node shoot.js <job> [args...]
 */
const puppeteer = require('puppeteer-core')
const fs = require('fs')

const BROWSER_WS = 'ws://192.168.10.197:3000'
const BASE = 'http://192.168.10.197:18086'
const OUT = process.env.SHOT_DIR || './shots'
const ADMIN = { email: 'claire@exemple.fr', password: 'Docflow-Demo-2026!' }

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

async function connect() {
  const browser = await puppeteer.connect({ browserWSEndpoint: BROWSER_WS })
  const page = await browser.newPage()
  await page.setViewport({ width: 1440, height: 900, deviceScaleFactor: 1.5 })
  return { browser, page }
}

async function shot(page, name) {
  fs.mkdirSync(OUT, { recursive: true })
  await page.screenshot({ path: `${OUT}/${name}.png` })
  console.log(`✓ ${name}.png`)
}

async function apiLogin() {
  const res = await fetch(`${BASE}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(ADMIN),
  })
  if (!res.ok) throw new Error(`login API ${res.status}`)
  return (await res.json()).access_token
}

async function authedPage(page) {
  const token = await apiLogin()
  await page.goto(`${BASE}/login`, { waitUntil: 'networkidle0' })
  await page.evaluate((t) => localStorage.setItem('docflow_token', t), token)
  return token
}

async function gotoAndShot(page, path, name, { wait = 800, selector = null } = {}) {
  await page.goto(`${BASE}${path}`, { waitUntil: 'networkidle0' })
  if (selector) await page.waitForSelector(selector, { timeout: 15000 })
  await sleep(wait)
  await shot(page, name)
}

const jobs = {
  /* Écran de premier démarrage (AVANT création de l'admin), formulaire rempli. */
  async setup(page) {
    await page.goto(`${BASE}/login`, { waitUntil: 'networkidle0' })
    await sleep(500)
    const inputs = await page.$$('input')
    if (inputs.length >= 4) {
      await inputs[0].type('claire')
      await inputs[1].type('claire@exemple.fr')
      await inputs[2].type('Docflow-Demo-2026!')
      await inputs[3].type('Docflow-Demo-2026!')
    }
    await sleep(300)
    await shot(page, '01-premier-demarrage')
  },

  /* Page de connexion (l'admin existe), champs remplis. */
  async login(page) {
    await page.goto(`${BASE}/login`, { waitUntil: 'networkidle0' })
    await page.waitForSelector('[data-testid="email-input"]', { timeout: 15000 })
    await page.type('[data-testid="email-input"]', ADMIN.email)
    await page.type('[data-testid="password-input"]', ADMIN.password)
    await sleep(300)
    await shot(page, '02-connexion')
  },

  /* Rend un schéma d'architecture en HTML et le capture → image de démo. */
  async diagram(page) {
    const html = `<!doctype html><meta charset="utf-8">
    <style>
      body{margin:0;font-family:system-ui,sans-serif;background:#fff}
      .wrap{width:860px;padding:30px;display:flex;flex-direction:column;gap:26px;align-items:center}
      .row{display:flex;gap:40px;align-items:center}
      .box{border:2px solid #334155;border-radius:10px;padding:16px 26px;text-align:center;
           font-size:15px;font-weight:600;color:#0f172a;background:#f8fafc;min-width:150px}
      .box small{display:block;font-weight:400;color:#64748b;margin-top:4px;font-size:12px}
      .accent{background:#eff6ff;border-color:#2563eb}
      .db{background:#f0fdf4;border-color:#16a34a}
      .arrow{font-size:22px;color:#64748b}
    </style>
    <div class="wrap" id="diagram">
      <div class="row">
        <div class="box">Navigateur<small>React + BlockNote</small></div>
        <div class="arrow">⟶</div>
        <div class="box accent">docflow<small>API FastAPI · serveur MCP</small></div>
        <div class="arrow">⟶</div>
        <div class="box db">PostgreSQL<small>documents · types · artefacts</small></div>
      </div>
      <div class="row">
        <div class="box">Agent IA<small>client MCP</small></div>
        <div class="arrow">⟶</div>
        <div class="box accent">docflow<small>mêmes droits que l'API</small></div>
      </div>
    </div>`
    await page.setContent(html, { waitUntil: 'networkidle0' })
    const el = await page.$('#diagram')
    fs.mkdirSync(OUT, { recursive: true })
    await el.screenshot({ path: `${OUT}/architecture-demo.png` })
    console.log('✓ architecture-demo.png')
  },

  /* Toutes les vues authentifiées. Arguments injectés par le seed via env. */
  async app(page) {
    const WS = process.env.DEMO_WS || 'produit-alpha'
    const FEATURE_DOC = process.env.DEMO_FEATURE_DOC // uuid feature "Connexion via Keycloak"
    const ARCHI_DOC = process.env.DEMO_ARCHI_DOC // uuid page wiki "Architecture"
    await authedPage(page)

    await gotoAndShot(page, '/workspaces', '03-espaces-de-travail')
    await gotoAndShot(page, `/ws/${WS}/types`, '04-types-et-statuts', { wait: 1200 })
    await gotoAndShot(page, `/ws/${WS}/blocs`, '05-blocs')
    await gotoAndShot(page, `/ws/${WS}/blocs/roadmap/documents`, '06-arbre-documents', {
      wait: 1500,
    })
    if (FEATURE_DOC)
      await gotoAndShot(
        page,
        `/ws/${WS}/blocs/roadmap/documents/${FEATURE_DOC}`,
        '07-edition-document',
        { wait: 2500 },
      )
    if (ARCHI_DOC)
      await gotoAndShot(page, `/ws/${WS}/blocs/wiki/documents/${ARCHI_DOC}`, '08-image-dans-page', {
        wait: 3000,
      })
    await gotoAndShot(page, '/api-keys', '10-cles-api')
    await gotoAndShot(page, '/admin/remote', '11-sauvegardes', { wait: 1200 })
    await gotoAndShot(page, '/templates', '12-templates', { wait: 1200 })
  },

  /* Page types avec le type "feature" déplié (propriétés + statuts visibles). */
  async types(page) {
    const WS = process.env.DEMO_WS || 'produit-alpha'
    await authedPage(page)
    await page.goto(`${BASE}/ws/${WS}/types`, { waitUntil: 'networkidle0' })
    await sleep(800)
    // Déplie la ligne du type "feature"
    await page.click('[data-testid="type-row-feature"]')
    await sleep(1500)
    await shot(page, '04-types-et-statuts')
  },

  /* Onglet Sauvegarde de la page Connexions & Sauvegarde. */
  async backup(page) {
    await authedPage(page)
    await page.goto(`${BASE}/admin/remote`, { waitUntil: 'networkidle0' })
    await sleep(800)
    await page.evaluate(() => {
      const btn = [...document.querySelectorAll('button')].find((b) =>
        b.textContent.includes('Sauvegarde'),
      )
      if (btn) btn.click()
    })
    await sleep(1500)
    await shot(page, '11-sauvegardes')
  },

  /* Capture une seule vue authentifiée : node shoot.js one <path> <name> */
  async one(page) {
    const [, , , path, name] = process.argv
    await authedPage(page)
    await gotoAndShot(page, path, name, { wait: 1500 })
  },

  /* Page publique (sans authentification). */
  async pub(page) {
    const PUB_DOC = process.env.DEMO_PUB_DOC
    if (!PUB_DOC) throw new Error('DEMO_PUB_DOC manquant')
    await gotoAndShot(page, `/pub/${PUB_DOC}`, '09-page-publique', { wait: 2000 })
  },
}

;(async () => {
  const job = process.argv[2]
  if (!jobs[job]) {
    console.error(`job inconnu : ${job} (dispo : ${Object.keys(jobs).join(', ')})`)
    process.exit(1)
  }
  const { browser, page } = await connect()
  try {
    await jobs[job](page)
  } finally {
    await page.close().catch(() => {})
    browser.disconnect()
  }
})().catch((e) => {
  console.error(e)
  process.exit(1)
})
