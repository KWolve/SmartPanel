#!/usr/bin/env node
/**
 * shoot_box.mjs — 把网页预览里「绿框内的画面」原样截出来（headless Edge/Chrome + 原生 CDP）
 *
 * 用途：验收「所见 = 所出」——绿框里显示什么，导出的那段就是什么。
 * 零三方依赖（Node 内置 WebSocket / fetch；浏览器用系统 Edge/Chrome）。
 *
 * 关键点（保证截图是**像素级 1:1**，不引入额外重采样）：
 *   1. 注入 CSS：把 #canvasBox 固定到页面 (0,0)、去掉 padding/border、隐藏右栏
 *      → 画布原点 = 页面原点（整数），clip 才不会落在半像素上；
 *   2. 用 VW.setViewWidth(W) 控制预览缩放 K = W / 源宽：
 *      取 W = 源宽 × (目标输出宽 / 裁剪宽) → 绿框区域在页面上正好是 目标输出宽×高 个 CSS 像素；
 *   3. Page.captureScreenshot(clip=绿框矩形, scale=1, deviceScaleFactor=1) → 1:1 拷像素。
 *   （脚本会打印 clip 与期望尺寸；非整数会告警。）
 *
 * 用法：
 *   node shoot_box.mjs --url "http://127.0.0.1:8798/?src=x.mp4&cols=2&crop=128,64,1024,512&overlay=0&bare=1&t=0" \
 *        --vieww 1200 --out preview_box.png [--expect 960x480] [--viewport 1400x900] [--wait 30000]
 *   node shoot_box.mjs --url "..." --vieww 1200 --selftest      # 交互自检（拖框/滚轮/钳制）
 *   node shoot_box.mjs --url "..." --uitest                     # 页面级 UI 自检
 *        （列表点选/时间轴/逐帧/快捷键/绿框开关/记忆/队列/组名）
 *   node shoot_box.mjs --url "..." --eval "window.VW.queue()"    # 就绪后跑一段页面 JS，结果写进末行 JSON
 *   node shoot_box.mjs --url "..." --page --viewport 1680x1180  # 截整个页面（看排版；不注入 CSS）
 * 输出：末行 JSON（{ok,clip,expect,K,crop,canvasRect,out}）
 */
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function arg(name, def) {
  const i = process.argv.indexOf('--' + name);
  return i >= 0 && process.argv[i + 1] ? process.argv[i + 1] : def;
}
const URL_ = arg('url');
const VIEWW = parseFloat(arg('vieww', '0'));
const OUT = arg('out', 'preview_box.png');
const EXPECT = arg('expect', '');
const VIEWPORT = arg('viewport', '1400x900').split('x').map(Number);
const WAIT = parseInt(arg('wait', '30000'), 10);
const SELFTEST = process.argv.includes('--selftest');
const FULLVIEW = process.argv.includes('--full');   // 截整幅画布（看 UI：绿框/压暗）
const FULLPAGE = process.argv.includes('--page');   // 截整个页面（看 UI 排版；不注入 CSS）
const UITEST = process.argv.includes('--uitest');   // 页面级 UI 自检（不注入 CSS，真点/真敲）
const EVALJS = arg('eval', '');                     // 就绪后执行一段 JS（awaitPromise），结果写进末行 JSON
if (!URL_) { console.error('缺少 --url'); process.exit(2); }

function findBrowser() {
  const cands = [
    process.env.CHROME_PATH, process.env.CSS2IMG_BROWSER,
    'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
    'C:/Program Files/Microsoft/Edge/Application/msedge.exe',
    'C:/Program Files/Google/Chrome/Application/chrome.exe',
    'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
    '/usr/bin/google-chrome', '/usr/bin/chromium', '/usr/bin/microsoft-edge',
  ].filter(Boolean);
  for (const c of cands) { try { if (fs.existsSync(c)) return c; } catch { /* noop */ } }
  throw new Error('未找到 Chrome/Edge（可用 CHROME_PATH 指定）');
}

function connectCDP(wsUrl) {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(wsUrl);
    const pending = new Map();
    let seq = 0;
    ws.addEventListener('open', () => resolve(api));
    ws.addEventListener('error', (e) => reject(new Error('CDP 连接失败: ' + (e.message || e.type))));
    ws.addEventListener('message', (ev) => {
      let m; try { m = JSON.parse(ev.data); } catch { return; }
      if (m.id === undefined) return;
      const p = pending.get(m.id); if (!p) return;
      pending.delete(m.id);
      m.error ? p.reject(new Error(m.error.message)) : p.resolve(m.result);
    });
    const api = {
      send(method, params = {}, sessionId) {
        const id = ++seq;
        const payload = sessionId ? { id, method, params, sessionId } : { id, method, params };
        return new Promise((res, rej) => { pending.set(id, { resolve: res, reject: rej }); ws.send(JSON.stringify(payload)); });
      },
      close() { try { ws.close(); } catch { /* noop */ } },
    };
  });
}

const INJECT = `#canvasBox{position:fixed!important;left:0!important;top:0!important;right:auto!important;
bottom:auto!important;margin:0!important;border:0!important;border-radius:0!important;background:#000!important;
overflow:visible!important;z-index:2147483647!important} body{margin:0!important;padding:0!important;display:block!important}
.col.right{display:none!important}
.col.left>*:not(#canvasBox){visibility:hidden!important}
#cv{position:static!important;left:auto!important;top:auto!important;display:block!important}`;

/* ── 交互自检（--selftest）：拖框 / 滚轮缩放 / 钳制在视频内 ─────────────
   用 CDP Input 真发鼠标事件（页面监听 pointerdown/move/up + wheel），
   再读 VW.crop() 判断。返回 JSON，供 verify_roundtrip.py 断言。 */
async function uiSelftest(s, evalJS, sleepMs) {
  const R = { ok: true, steps: [] };
  const crop = () => evalJS('window.VW.crop()');
  const info = await evalJS('window.VW.info()');
  const K = await evalJS('window.VW.K()');
  const zoom = () => evalJS('window.VW.zoom()');
  const mouse = async (type, x, y, extra = {}) => s('Input.dispatchMouseEvent', Object.assign(
    { type, x, y, button: 'left', buttons: type === 'mouseReleased' ? 0 : 1, clickCount: 1 }, extra));
  const near = (a, b, tol) => Math.abs(a - b) <= tol;
  const run = async (name, fn) => {
    try {
      const r = await fn();
      R.steps.push(Object.assign({ name, pass: !!r.pass, detail: r.detail }, {}));
      if (!r.pass) R.ok = false;
    } catch (e) {
      R.steps.push({ name, pass: false, detail: 'ERR ' + e.message }); R.ok = false;
    }
  };
  const inBounds = c => c[0] >= 0 && c[1] >= 0 && c[0] + c[2] <= info.width && c[1] + c[3] <= info.height;

  // 事件计数（诊断用：证明确实收到真鼠标事件）
  await evalJS(`(()=>{const cv=document.getElementById('cv');window.__ev={down:0,move:0,up:0,wheel:0};` +
    `cv.addEventListener('pointerdown',()=>window.__ev.down++);` +
    `cv.addEventListener('pointermove',()=>window.__ev.move++);` +
    `cv.addEventListener('pointerup',()=>window.__ev.up++);` +
    `cv.addEventListener('wheel',()=>window.__ev.wheel++);` +
    `window.__hit=(x,y)=>{const e=document.elementFromPoint(x,y);if(!e)return 'none';` +
    `const r=e.getBoundingClientRect();return e.tagName+'#'+e.id+'.'+e.className+'@'+Math.round(r.left)+','+Math.round(r.top)+','+Math.round(r.width)+'x'+Math.round(r.height);};return 1;})()`);
  R.hit100 = await evalJS('window.__hit(100,100)');
  R.dbg = await evalJS(`(()=>{const b=document.getElementById('canvasBox'),c=document.getElementById('cv');` +
    `const rb=b.getBoundingClientRect(),rc=c.getBoundingClientRect();` +
    `return {boxPos:getComputedStyle(b).position,boxZ:getComputedStyle(b).zIndex,` +
    `box:[Math.round(rb.left),Math.round(rb.top),Math.round(rb.width),Math.round(rb.height)],` +
    `cv:[Math.round(rc.left),Math.round(rc.top),Math.round(rc.width),Math.round(rc.height)]};})()`);

  // 先把框组放到一个"中等大小、居中"的确定状态（否则若一开始就是最大框，拖/缩放都没余量）
  await run('setup：置为最大框的 60%（居中）', async () => {
    const m = await evalJS('window.VW.maxCrop()');
    const c = await evalJS(`(()=>{const m=window.VW.maxCrop(),n=window.VW.cols(),i=window.VW.info();` +
      `let h=Math.max(2,Math.round(m[3]*0.6));h-=h%2;const w=n*h;` +
      `window.VW.setCropArr([Math.round((i.width-w)/2),Math.round((i.height-h)/2),w,h]);` +
      `return window.VW.crop();})()`);
    return { pass: c[2] <= m[2] && inBounds(c), detail: `maxCrop=${JSON.stringify(m)} → ${JSON.stringify(c)}` };
  });

  await run('拖框 = 移动框组（视频不动）', async () => {
    const c0 = await crop();
    const dx = 40, dy = 30;                     // 小位移（避免撞到边界钳制，单独再测钳制）
    await mouse('mousePressed', 100, 100);
    await mouse('mouseMoved', 100 + dx, 100 + dy);
    await mouse('mouseReleased', 100 + dx, 100 + dy);
    const c1 = await crop();
    const ev = await evalJS('window.__ev');
    const ex = Math.round(dx / K), ey = Math.round(dy / K);
    return { pass: near(c1[0] - c0[0], ex, 3) && near(c1[1] - c0[1], ey, 3) && c1[2] === c0[2] && c1[3] === c0[3],
             detail: `crop ${JSON.stringify(c0)} → ${JSON.stringify(c1)}（期望 Δ≈(${ex},${ey})，宽高不变）ev=${JSON.stringify(ev)} hit(100,100)=${R.hit100}` };
  });

  await run('拖超出画面 → 钳制在视频内（结构上无黑边）', async () => {
    await mouse('mousePressed', 600, 300);
    const far = 4000;
    await mouse('mouseMoved', -far, -far);
    const cA = await crop();
    const okA = cA[0] === 0 && cA[1] === 0 && inBounds(cA);
    await mouse('mouseMoved', far, far);
    const cB = await crop();
    await mouse('mouseReleased', far, far);
    const okB = cB[0] + cB[2] === info.width && cB[1] + cB[3] === info.height && inBounds(cB);
    return { pass: okA && okB, detail: `左上钳制=${JSON.stringify(cA)} 右下钳制=${JSON.stringify(cB)}` };
  });

  await run('滚轮 = 缩放（鼠标下的相同相对位置保持不动）', async () => {
    const c0 = await crop();
    const px = Math.round((c0[0] + c0[2] * 0.3) * K);      // 画布坐标（画布原点 = 视频原点，固定）
    const py = Math.round((c0[1] + c0[3] * 0.3) * K);
    const sx = px / K, sy = py / K;                        // 鼠标下的源坐标（与 crop 无关）
    const u0 = (sx - c0[0]) / c0[2], v0 = (sy - c0[1]) / c0[3];
    await s('Input.dispatchMouseEvent', { type: 'mouseWheel', x: px, y: py, deltaX: 0, deltaY: -120 });
    await sleepMs(150);
    const c1 = await crop();
    const u1 = (sx - c1[0]) / c1[2], v1 = (sy - c1[1]) / c1[3];
    const z1 = await zoom();
    const ev = await evalJS('window.__ev');
    const inside = sx > c1[0] && sx < c1[0] + c1[2] && sy > c1[1] && sy < c1[1] + c1[3];
    return { pass: c1[2] < c0[2] && near(u1, u0, 0.02) && near(v1, v0, 0.02) && inside && inBounds(c1),
             detail: `光标(${px},${py}) w ${c0[2]}→${c1[2]}，u ${u0.toFixed(3)}→${u1.toFixed(3)} / v ${v0.toFixed(3)}→${v1.toFixed(3)}，zoom=${z1.toFixed(3)} ev=${JSON.stringify(ev)}` };
  });

  await run('滚轮缩小到极限 → 框组到最大（等于"铺满"尺寸）且仍在视频内', async () => {
    const c = await crop();
    const px = Math.round((c[0] + c[2] / 2) * K), py = Math.round((c[1] + c[3] / 2) * K);
    for (let i = 0; i < 20; i++) await s('Input.dispatchMouseEvent', { type: 'mouseWheel', x: px, y: py, deltaX: 0, deltaY: 120 });
    await sleepMs(200);
    const c9 = await crop();
    const mx = await evalJS('window.VW.maxCrop()');
    return { pass: c9[2] === mx[2] && c9[3] === mx[3] && inBounds(c9),
             detail: `crop=${JSON.stringify(c9)} maxCrop=${JSON.stringify(mx)}` };
  });
  R.info = info; R.K = K;
  return R;
}

/* ── 页面级 UI 自检（--uitest）：已导入列表点选 / 时间轴刷帧 / 快捷键 / 绿框开关 / 记忆 ──
   与 --selftest 分开：这里要的是"页面交互真的能用"，因此不注入任何 CSS。 */
async function pageUiTest(s, evalJS, sleepMs) {
  const R = { ok: true, steps: [] };
  const run = async (name, fn) => {
    try {
      const r = await fn();
      R.steps.push({ name, pass: !!r.pass, detail: r.detail });
      if (!r.pass) R.ok = false;
    } catch (e) {
      R.steps.push({ name, pass: false, detail: 'ERR ' + e.message }); R.ok = false;
    }
  };
  const key = async (k, code, vk) => {
    await s('Input.dispatchKeyEvent', { type: 'keyDown', key: k, code, windowsVirtualKeyCode: vk, nativeVirtualKeyCode: vk });
    await s('Input.dispatchKeyEvent', { type: 'keyUp', key: k, code, windowsVirtualKeyCode: vk, nativeVirtualKeyCode: vk });
    await sleepMs(120);
  };

  await run('① 已导入列表可点选（不用重新上传）', async () => {
    const chips = await evalJS(`[...document.querySelectorAll('#srclist .chip')].map(c=>c.querySelector('.n').textContent)`);
    if (!chips || chips.length < 2) return { pass: false, detail: 'chip 少于 2 个：' + JSON.stringify(chips) };
    const cur = await evalJS('window.VW.src()');
    const target = chips.find(c => c !== cur) || chips[0];
    await evalJS(`[...document.querySelectorAll('#srclist .chip')].find(c=>c.querySelector('.n').textContent===${JSON.stringify(target)}).querySelector('.n').click(), 1`);
    await sleepMs(1500);
    const now = await evalJS('window.VW.src()');
    return { pass: now === target, detail: chips.length + ' 个：' + chips.join(' / ') + '；点选 ' + target + ' → 当前 ' + now };
  });

  await run('② 时间轴拖动 → 预览帧跟着变（t 生效）', async () => {
    const dur = await evalJS('window.VW.info() && (parseFloat(document.getElementById("tl").max)/1000)');
    const mid = Math.round(dur * 500);
    await evalJS(`(()=>{const tl=document.getElementById('tl');tl.value=${mid};tl.dispatchEvent(new Event('input'));return 1;})()`);
    await sleepMs(1400);
    const t = await evalJS('parseFloat(document.getElementById("tsec").value)');
    const ready = await evalJS('window.VW.ready()');
    const txt = await evalJS('document.getElementById("tlTxt").textContent');
    return { pass: ready && Math.abs(t - (dur / 2)) <= 0.05 && /\d/.test(txt),
             detail: `拖动到 ${(dur / 2).toFixed(2)}s → tsec=${t} ready=${ready} “${txt}”` };
  });

  await run('③ 逐帧按钮（◀ 帧 / 帧 ▶）', async () => {
    const t0 = await evalJS('parseFloat(document.getElementById("tsec").value)');
    await evalJS('stepFrame(1), 1'); await sleepMs(900);
    const t1 = await evalJS('parseFloat(document.getElementById("tsec").value)');
    await evalJS('stepFrame(-1), 1'); await sleepMs(900);
    const t2 = await evalJS('parseFloat(document.getElementById("tsec").value)');
    return { pass: Math.abs((t1 - t0) - 1 / 25) < 0.03 && Math.abs(t2 - t0) < 0.03,
             detail: `${t0} → ${t1} → ${t2}` };
  });

  await run('④ 快捷键：方向键微调 2px / Shift=20px / M 铺满', async () => {
    // 先摆一个"四周有富余"的框（满宽框向右移会被钳制，那是正确行为，不是快捷键失效）
    const cBase = await evalJS(`(()=>{const i=window.VW.info(),n=window.VW.cols();` +
      `let h=Math.min(i.height,i.width/n)-80;h-=h%2;const w=n*h;` +
      `window.VW.setCropArr([100,100,w,h]);return window.VW.crop();})()`);
    await key('ArrowRight', 'ArrowRight', 39);
    const c1 = await evalJS('window.VW.crop()');
    await s('Input.dispatchKeyEvent', { type: 'keyDown', key: 'ArrowRight', code: 'ArrowRight', windowsVirtualKeyCode: 39, nativeVirtualKeyCode: 39, modifiers: 8 });
    await s('Input.dispatchKeyEvent', { type: 'keyUp', key: 'ArrowRight', code: 'ArrowRight', windowsVirtualKeyCode: 39, nativeVirtualKeyCode: 39, modifiers: 8 });
    await sleepMs(150);
    const c2 = await evalJS('window.VW.crop()');
    await key('ArrowUp', 'ArrowUp', 38);
    const c2u = await evalJS('window.VW.crop()');
    await key('m', 'KeyM', 77);
    const c3 = await evalJS('window.VW.crop()');
    const mx = await evalJS('window.VW.maxCrop()');
    return { pass: c1[0] - cBase[0] === 2 && c2[0] - c1[0] === 20 && c2u[1] - c2[1] === -2 &&
                   c3[2] === mx[2] && c3[3] === mx[3],
             detail: `基准 ${JSON.stringify(cBase)}；→ 得 x ${c1[0]}（+2）；Shift+→ 得 ${c2[0]}（+20）；↑ 得 y ${c2[1]}→${c2u[1]}；M → ${JSON.stringify(c3)} = maxCrop` };
  });

  await run('⑤ 显示绿框/压暗 开关', async () => {
    const o0 = await evalJS('window.VW.overlay()');
    await evalJS('document.getElementById("showOverlay").click(), 1'); await sleepMs(150);
    const o1 = await evalJS('window.VW.overlay()');
    await evalJS('document.getElementById("showOverlay").click(), 1'); await sleepMs(150);
    const o2 = await evalJS('window.VW.overlay()');
    return { pass: o0 !== o1 && o2 === o0, detail: `${o0} → ${o1} → ${o2}` };
  });

  await run('⑥ 设置记忆（分割数量写进 localStorage）', async () => {
    await evalJS(`(()=>{const s=document.getElementById('cols');s.value='3';s.dispatchEvent(new Event('change'));return 1;})()`);
    await sleepMs(300);
    const v = await evalJS(`localStorage.getItem('vw_cols')`);
    const cols = await evalJS('window.VW.cols()');
    await evalJS(`(()=>{const s=document.getElementById('cols');s.value='2';s.dispatchEvent(new Event('change'));return 1;})()`);
    return { pass: v === '3' && cols === 3, detail: `localStorage.vw_cols=${v}，页面 cols=${cols}` };
  });

  await run('⑦ 队列：加入 / 改名 / 上移 / 删除（一个组 = 多个视频轮播）', async () => {
    await evalJS('window.VW.clearQueue(), 1');
    const chips = await evalJS(`[...document.querySelectorAll('#srclist .chip')].map(c=>c.querySelector('.n').textContent)`);
    await evalJS('window.VW.addClips(' + JSON.stringify((chips || []).slice(0, 2)) + ')');
    await sleepMs(900);
    let q = await evalJS('window.VW.queue()');
    const auto = q.map(c => c.name).join(',');
    const domOK = await evalJS(`(()=>{const inp=document.querySelector('#queue .q .qname');` +
      `if(!inp)return false;inp.value='开场 Intro';inp.dispatchEvent(new Event('change'));return true;})()`);
    await sleepMs(250);
    const rn = await evalJS('window.VW.queue()[0].name');
    const before = await evalJS('window.VW.queue().map(c=>c.name).join(",")');
    await evalJS(`document.querySelectorAll('#queue .q')[1].querySelector('button[data-op="up"]').click(), 1`);
    await sleepMs(250);
    const afterUp = await evalJS('window.VW.queue().map(c=>c.name).join(",")');
    const n0 = await evalJS('window.VW.queueLen()');
    await evalJS(`document.querySelectorAll('#queue .q')[0].querySelector('button[data-op="del"]').click(), 1`);
    await sleepMs(250);
    const n1 = await evalJS('window.VW.queueLen()');
    q = await evalJS('window.VW.queue()');
    return { pass: q.length >= 1 && domOK && rn === 'Intro' && afterUp !== before && n1 === n0 - 1,
             detail: `源片池 ${chips && chips.length} 个 → 入队 ${auto.split(',').length} 个（自动名 ${auto}）→ 改名 ${rn}；` +
                     `顺序 ${before} → ${afterUp}；删除 ${n0}→${n1}；剩 ${JSON.stringify(q.map(c => c.name))}` };
  });

  await run('⑧ 组名：默认取自第一个源片名 + 非法字符清洗 + 记忆', async () => {
    await evalJS('window.VW.clearQueue(), 1');
    const chips = await evalJS(`[...document.querySelectorAll('#srclist .chip')].map(c=>c.querySelector('.n').textContent)`);
    await evalJS('window.VW.addClips(' + JSON.stringify((chips || []).slice(0, 1)) + ')');
    await sleepMs(700);
    const def = await evalJS('document.getElementById("group").value');
    const washed = await evalJS('window.VW.setGroupName("zksw wall/组:1*2?")');
    const ls = await evalJS('localStorage.getItem("vw_group")');
    const domVal = await evalJS('document.getElementById("group").value');
    return { pass: !!def && !/[\\/:*?"<>|]/.test(domVal) && domVal === washed &&
                   ls === JSON.stringify(washed),
             detail: `默认 "${def}"；清洗后 "${washed}"；localStorage=${ls}` };
  });

  R.err = await evalJS('String(window.__err || "")');
  return R;
}

async function main() {
  const exe = findBrowser();
  const port = 9500 + Math.floor(Math.random() * 400);
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'shootbox-'));
  const proc = spawn(exe, [
    '--headless=new', '--disable-gpu', '--hide-scrollbars', '--no-first-run',
    '--no-default-browser-check', '--disable-extensions', '--disable-sync',
    '--force-color-profile=srgb', '--disable-lcd-text', '--font-render-hinting=none',
    '--disable-dev-shm-usage', '--mute-audio',
    `--remote-debugging-port=${port}`, `--user-data-dir=${profile}`, 'about:blank',
  ], { stdio: 'ignore', windowsHide: true });
  let cdp = null, targetId = null;
  try {
    const deadline = Date.now() + 30000;
    let info = null;
    while (Date.now() < deadline) {
      try { const r = await fetch(`http://127.0.0.1:${port}/json/version`); if (r.ok) { info = await r.json(); break; } } catch { /* wait */ }
      await sleep(120);
    }
    if (!info) throw new Error('headless 启动超时');
    cdp = await connectCDP(info.webSocketDebuggerUrl);
    ({ targetId } = await cdp.send('Target.createTarget', { url: 'about:blank' }));
    const { sessionId } = await cdp.send('Target.attachToTarget', { targetId, flatten: true });
    const s = (m, p) => cdp.send(m, p, sessionId);
    await s('Page.enable'); await s('Runtime.enable');
    await s('Emulation.setDeviceMetricsOverride', {
      width: VIEWPORT[0], height: VIEWPORT[1], deviceScaleFactor: 1, mobile: false,
    });
    const evalJS = async (expr) => {
      const r = await s('Runtime.evaluate', { expression: expr, returnByValue: true, awaitPromise: true });
      if (r.exceptionDetails) throw new Error('页面 JS 异常: ' + JSON.stringify(r.exceptionDetails.exception));
      return r.result.value;
    };
    await s('Page.navigate', { url: URL_ });
    const t0 = Date.now();
    let ready = false;
    while (Date.now() - t0 < WAIT) {
      ready = await evalJS('!!(window.__ready && window.VW && window.VW.ready && window.VW.ready() && window.VW.src())').
        catch(() => false);
      if (ready) break;
      await sleep(250);
    }
    if (!ready) throw new Error('页面/源片未就绪（' + (await evalJS('String(window.__err||"")').catch(() => '')) + '）');
    // 注入 CSS：画布固定到 (0,0)，去掉一切 padding/border → 截图像素 = 画布像素
    //（--page 截整页看排版时**不注入**，否则画布被钉到 (0,0)）
    if (!FULLPAGE && !UITEST && !EVALJS) {
      await evalJS(`(()=>{const st=document.createElement('style');st.textContent=${JSON.stringify(INJECT)};document.head.appendChild(st);return 1;})()`);
    }
    if (VIEWW > 0) await evalJS(`window.VW.setViewWidth(${VIEWW})`);
    await sleep(300);
    let evalResult = null;
    if (EVALJS) {                         // 就绪后跑一段页面 JS（不注入 CSS）
      evalResult = await evalJS(EVALJS);
      if (!FULLPAGE) {
        console.log(JSON.stringify({ ok: true, eval: evalResult }));
        return 0;
      }
    }
    if (SELFTEST) {
      const r = await uiSelftest(s, evalJS, sleep);
      console.log(JSON.stringify(r));
      return r.ok ? 0 : 1;
    }
    if (UITEST) {                         // 页面级 UI 自检（不注入 CSS）
      const r = await pageUiTest(s, evalJS, sleep);
      console.log(JSON.stringify(r));
      return r.ok ? 0 : 1;
    }
    if (FULLPAGE) {                       // 整页截图（UI 排版自查）
      await sleep(400);
      const { data } = await s('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true });
      fs.writeFileSync(OUT, Buffer.from(data, 'base64'));
      console.log(JSON.stringify({ ok: true, out: path.resolve(OUT), page: true,
                                   bytes: fs.statSync(OUT).size, eval: evalResult }));
      return 0;
    }
    const g = await evalJS('(()=>{const c=window.VW.crop(),K=window.VW.K(),r=window.VW.canvasRect();' +
      'return {crop:c,K:K,rect:{left:r.left,top:r.top,width:r.width,height:r.height},' +
      'src:window.VW.src(),overlay:window.VW.overlay(),cols:window.VW.cols()};})()');
    const clip = FULLVIEW ? {
      x: g.rect.left, y: g.rect.top, width: g.rect.width, height: g.rect.height, scale: 1,
    } : {
      x: g.rect.left + g.crop[0] * g.K, y: g.rect.top + g.crop[1] * g.K,
      width: g.crop[2] * g.K, height: g.crop[3] * g.K, scale: 1,
    };
    const frac = ['x', 'y', 'width', 'height'].filter(k => Math.abs(clip[k] - Math.round(clip[k])) > 1e-6);
    const { data } = await s('Page.captureScreenshot', { format: 'png', clip, captureBeyondViewport: false });
    fs.writeFileSync(OUT, Buffer.from(data, 'base64'));
    const out = {
      ok: true, out: path.resolve(OUT), clip, integerClip: frac.length === 0, fractionalKeys: frac,
      expect: EXPECT || null, K: g.K, crop: g.crop, cols: g.cols, src: g.src, overlay: g.overlay,
      canvasRect: g.rect, bytes: fs.statSync(OUT).size,
    };
    if (EXPECT) {
      const [w, h] = EXPECT.split('x').map(Number);
      out.expectMatch = Math.abs(clip.width - w) < 0.51 && Math.abs(clip.height - h) < 0.51;
    }
    console.log(JSON.stringify(out));
    return 0;
  } finally {
    try { if (targetId) await cdp.send('Target.closeTarget', { targetId }); } catch { /* noop */ }
    try { proc.kill(); } catch { /* noop */ }
    try { fs.rmSync(profile, { recursive: true, force: true }); } catch { /* noop */ }
  }
}
main().then((c) => process.exit(c || 0)).catch((e) => { console.error('ERR ' + e.message); process.exit(1); });
