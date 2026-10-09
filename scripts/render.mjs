// posts.json → out/<id>/<n>.jpg (1080x1350), brand/ (프로필·하이라이트)
// 사용: node scripts/render.mjs            모든 글 렌더
//       node scripts/render.mjs 004 005    특정 글만
//       node scripts/render.mjs --brand    프로필 로고·하이라이트 커버
import { execFileSync, spawn } from "node:child_process";
import { mkdirSync, writeFileSync, readFileSync, rmSync, existsSync, statSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const HANDLE = "@maum.geunyuk";
const C = { bg: "#1C1C1C", fg: "#F2EFE8", dim: "#8A8780", accent: "#C6F24E" };

const esc = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
// *강조* → 포인트 색, 줄바꿈 → <br>
const fmt = (s) => esc(s).replace(/\*(.+?)\*/g, "<em>$1</em>").replace(/\n/g, "<br>");

const BASE_CSS = `
*{margin:0;padding:0;box-sizing:border-box}
html,body{width:100%;height:100%;background:${C.bg};color:${C.fg};
  font-family:Pretendard,sans-serif;word-break:keep-all;-webkit-font-smoothing:antialiased}
em{font-style:normal;color:${C.accent}}
.page{position:relative;width:100%;height:100%;display:flex;flex-direction:column;
  justify-content:center;align-items:center;padding:140px 110px}
.top{position:absolute;top:70px;left:90px;right:90px;display:flex;justify-content:space-between;
  font-size:30px;font-weight:600;color:${C.dim};letter-spacing:.02em}
.top b{color:${C.accent};font-weight:700}
.mark{position:absolute;bottom:70px;left:0;right:0;text-align:center;font-size:28px;
  font-weight:500;color:${C.dim};letter-spacing:.06em}
.swipe{position:absolute;bottom:66px;right:90px;font-size:30px;font-weight:600;color:${C.accent}}
.cover{font-size:92px;font-weight:800;line-height:1.32;text-align:center;letter-spacing:-.02em}
.cover-bar{width:90px;height:8px;background:${C.accent};margin-bottom:64px}
.text{font-size:58px;font-weight:600;line-height:1.7;text-align:center;letter-spacing:-.01em}
.single{font-size:76px;font-weight:800;line-height:1.5;text-align:center;letter-spacing:-.02em}
.list{width:100%;display:flex;flex-direction:column;gap:56px}
.item{display:flex;gap:36px;font-size:54px;font-weight:600;line-height:1.45;letter-spacing:-.01em}
.item .n{color:${C.accent};font-weight:800;min-width:56px}
.cta-big{font-size:66px;font-weight:800;line-height:1.5;text-align:center}
.cta-small{margin-top:70px;font-size:38px;font-weight:500;line-height:1.6;color:${C.dim};text-align:center}
.hook{font-size:44px;font-weight:700;line-height:1.4;text-align:center;color:${C.accent};
  padding:18px 36px;border:3px solid ${C.accent};border-radius:999px;margin-bottom:84px;letter-spacing:-.01em}
`;
// 첫 장 상단 후킹 문구 (선택)
const hookTag = (s) => (s.hook ? `<div class="hook">${esc(s.hook)}</div>` : "");

function slideBody(s, i, total) {
  const pageNo = total > 1 ? `<span>${i + 1} / ${total}</span>` : "<span></span>";
  const top = `<div class="top"><b>마음근육</b>${pageNo}</div>`;
  const mark = `<div class="mark">${HANDLE}</div>`;
  let inner = "";
  if (s.kind === "cover") {
    inner = `${s.hook ? hookTag(s) : '<div class="cover-bar"></div>'}<div class="cover">${fmt(s.text)}</div>`;
    return `${top}${inner}${mark}${total > 1 ? '<div class="swipe">넘겨보기 →</div>' : ""}`;
  }
  if (s.kind === "text") inner = `<div class="text">${fmt(s.text)}</div>`;
  if (s.kind === "single") inner = `${hookTag(s)}<div class="single">${fmt(s.text)}</div>`;
  if (s.kind === "list")
    inner = `<div class="list">${s.items
      .map((t, k) => `<div class="item"><span class="n">${s.start + k}.</span><span>${fmt(t)}</span></div>`)
      .join("")}</div>`;
  if (s.kind === "cta")
    inner = `<div class="cta-big">저장해두고<br><em>운동 가기 싫은 날</em><br>꺼내 보세요</div>
      <div class="cta-small">${HANDLE} 팔로우하고<br>매일 밤 9시에 만나요</div>`;
  return `${top}${inner}${mark}`;
}

const html = (body, css = "") =>
  `<!doctype html><html><head><meta charset="utf-8"><style>${BASE_CSS}${css}</style></head>
   <body><div class="page">${body}</div></body></html>`;

const TMP = join(tmpdir(), "maum-render");
const sleep = (ms) => Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, ms);
mkdirSync(TMP, { recursive: true });

function shoot(markup, outJpg, w, h) {
  const src = join(TMP, "slide.html");
  const png = join(TMP, "slide.png");
  writeFileSync(src, markup);
  rmSync(png, { force: true });
  // 헤드리스 Chrome이 스크린샷을 저장한 뒤 종료하지 않는 경우가 있어서
  // 파일이 생기면 직접 종료시킨다
  const chrome = spawn(CHROME, [
    "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=1",
    "--no-first-run", "--no-default-browser-check", `--user-data-dir=${join(TMP, "profile")}`,
    `--window-size=${w},${h}`, `--screenshot=${png}`, `file://${src}`,
  ], { stdio: "ignore", detached: true });
  const deadline = Date.now() + 30000;
  let lastSize = -1;
  while (Date.now() < deadline) {
    sleep(200);
    const size = existsSync(png) ? statSync(png).size : 0;
    if (size > 0 && size === lastSize) break;
    lastSize = size;
  }
  try { process.kill(-chrome.pid, "SIGKILL"); } catch {}
  if (!existsSync(png)) throw new Error(`screenshot failed: ${outJpg}`);
  // Instagram API는 JPEG만 받음
  execFileSync("sips", ["-s", "format", "jpeg", "-s", "formatOptions", "92", png, "--out", outJpg], { stdio: "ignore" });
}

function renderPosts(ids) {
  const posts = JSON.parse(readFileSync(join(ROOT, "posts.json"), "utf8"));
  for (const p of posts) {
    if (ids.length && !ids.includes(p.id)) continue;
    const dir = join(ROOT, "out", p.id);
    if (existsSync(dir)) rmSync(dir, { recursive: true });
    mkdirSync(dir, { recursive: true });
    p.slides.forEach((s, i) => shoot(html(slideBody(s, i, p.slides.length)), join(dir, `${i + 1}.jpg`), 1080, 1350));
    console.log(`✓ ${p.id} (${p.slides.length}장)`);
  }
}

function renderBrand() {
  const dir = join(ROOT, "brand");
  mkdirSync(dir, { recursive: true });
  const sq = `.page{padding:0}`;
  // 로고 A: +1 SET
  shoot(html(`<div style="font-size:250px;font-weight:900;color:${C.accent};letter-spacing:-.04em;line-height:1">+1</div>
    <div style="font-size:120px;font-weight:800;letter-spacing:.12em;margin-top:24px">SET</div>`, sq),
    join(dir, "profile_A_plus1set.jpg"), 1080, 1080);
  // 로고 A 변형: 마음근육 글자
  shoot(html(`<div style="font-size:210px;font-weight:900;line-height:1.08;text-align:center;letter-spacing:-.04em">마음<br><span style="color:${C.accent}">근육</span></div>`, sq),
    join(dir, "profile_A2_maumgeunyuk.jpg"), 1080, 1080);
  for (const [i, name] of ["시작", "꾸준함", "다이어트 마음", "위로", "운동 Q&A"].entries()) {
    const size = name.length > 4 ? 120 : 170;
    shoot(html(`<div style="width:760px;height:760px;border-radius:50%;border:12px solid ${C.accent};
      display:flex;align-items:center;justify-content:center;text-align:center;
      font-size:${size}px;font-weight:800;line-height:1.2;padding:60px">${esc(name).replace(" ", "<br>")}</div>`, sq),
      join(dir, `highlight_${i + 1}_${name.replace(/[ &]/g, "")}.jpg`), 1080, 1080);
  }
  console.log("✓ brand/");
}

const args = process.argv.slice(2);
if (args.includes("--brand")) renderBrand();
else renderPosts(args);
