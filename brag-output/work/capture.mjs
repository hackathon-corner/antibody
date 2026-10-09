import puppeteer from 'puppeteer-core';
import { spawn } from 'child_process';
import fs from 'fs';
const [mode, ...rest] = process.argv.slice(2);
const browser = await puppeteer.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true, args: ['--force-color-profile=srgb','--hide-scrollbars'] });
const page = await browser.newPage();
await page.setViewport({ width: 1920, height: 1080, deviceScaleFactor: 1 });
await page.goto('file://' + process.cwd() + '/video.html', { waitUntil: 'load' });
await page.evaluate(() => document.fonts.ready);
async function frame(t, type='jpeg') { await page.evaluate(t => window.render(t), t); return page.screenshot({ type, quality: type==='jpeg'?95:undefined }); }
if (mode === 'stills') {
  fs.mkdirSync('stills', { recursive: true });
  for (const t of rest.map(Number)) fs.writeFileSync(`stills/t${t.toFixed(2)}.jpg`, await frame(t));
} else {
  const [ffmpeg, out, fps, dur] = rest; const N = Math.round(fps * dur);
  const ff = spawn(ffmpeg, ['-y','-f','image2pipe','-framerate',fps,'-i','-','-c:v','libx264','-preset','slow','-crf','16','-pix_fmt','yuv420p','-r',fps,out], { stdio: ['pipe','inherit','inherit'] });
  for (let i = 0; i < N; i++) { const buf = await frame(i / fps); if (!ff.stdin.write(buf)) await new Promise(r => ff.stdin.once('drain', r)); }
  ff.stdin.end(); await new Promise(r => ff.on('close', r));
}
await browser.close();
