// Vercel 빌드 스크립트: 정적 파일을 dist/로 복사하고,
// 환경변수 API_BASE_URL, FIREBASE_CONFIG로 dist/config.js를 생성한다. (외부 패키지 없음)
const fs = require("fs");
const path = require("path");

function fail(msg) {
  console.error(`✗ ${msg}`);
  process.exit(1);
}

const apiBase = (process.env.API_BASE_URL || "").trim().replace(/\/+$/, "");
if (!apiBase) fail("API_BASE_URL 환경변수가 없습니다. Vercel Project Settings → Environment Variables에서 설정하세요.");
if (!/^https?:\/\//.test(apiBase)) fail(`API_BASE_URL은 http(s)://로 시작해야 합니다: ${apiBase}`);

let firebaseConfig;
try {
  // Firebase 콘솔의 firebaseConfig 객체를 JSON으로 넣는다: {"apiKey":"...","authDomain":"...",...}
  firebaseConfig = JSON.parse(process.env.FIREBASE_CONFIG || "");
} catch (e) {
  fail('FIREBASE_CONFIG 환경변수가 없거나 JSON 형식이 아닙니다. 예: {"apiKey":"...","authDomain":"...","projectId":"...","appId":"..."}');
}
for (const k of ["apiKey", "authDomain", "projectId", "appId"]) {
  if (!firebaseConfig[k]) fail(`FIREBASE_CONFIG에 ${k}가 없습니다.`);
}

const out = path.join(__dirname, "dist");
fs.rmSync(out, { recursive: true, force: true });
fs.mkdirSync(out);
for (const f of ["index.html", "style.css", "app.js", "auth.js"]) {
  fs.copyFileSync(path.join(__dirname, f), path.join(out, f));
}
fs.writeFileSync(
  path.join(out, "config.js"),
  `window.APP_CONFIG = ${JSON.stringify({ API_BASE_URL: apiBase, FIREBASE_CONFIG: firebaseConfig })};\n`
);
console.log(`✓ dist/ 생성 완료 (API_BASE_URL=${apiBase}, Firebase project=${firebaseConfig.projectId})`);
