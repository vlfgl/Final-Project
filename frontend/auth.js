// Firebase 로그인 모듈 (Google 로그인 + 익명 체험)
// Firebase JS SDK를 CDN(ES 모듈)으로 불러와 빌드 도구 없이 사용한다.
import { initializeApp } from "https://www.gstatic.com/firebasejs/10.12.2/firebase-app.js";
import {
  getAuth,
  GoogleAuthProvider,
  signInWithPopup,
  signInAnonymously,
  signOut,
  onAuthStateChanged,
} from "https://www.gstatic.com/firebasejs/10.12.2/firebase-auth.js";

const cfg = (window.APP_CONFIG && window.APP_CONFIG.FIREBASE_CONFIG) || null;
if (!cfg || !cfg.apiKey) {
  throw new Error("FIREBASE_CONFIG가 설정되지 않았습니다. config.js를 확인하세요.");
}

const app = initializeApp(cfg);
const auth = getAuth(app);

/** 로그인 상태가 바뀔 때마다 callback(user | null) 호출 */
export function watchAuth(callback) {
  return onAuthStateChanged(auth, callback);
}

export async function signInWithGoogle() {
  const provider = new GoogleAuthProvider();
  provider.setCustomParameters({ prompt: "select_account" });
  return signInWithPopup(auth, provider);
}

export async function signInAsGuest() {
  return signInAnonymously(auth);
}

export async function logout() {
  return signOut(auth);
}

/** API 요청에 붙일 ID 토큰. 만료(1시간)가 가까우면 SDK가 자동으로 새로 받아온다. */
export async function getIdToken() {
  const user = auth.currentUser;
  return user ? user.getIdToken() : null;
}

/** 팝업 차단 등 Firebase 오류를 사용자용 문장으로 */
export function authErrorMessage(e) {
  const code = (e && e.code) || "";
  if (code.includes("popup-closed-by-user") || code.includes("cancelled-popup-request")) return "로그인 창이 닫혔어요.";
  if (code.includes("popup-blocked")) return "브라우저가 로그인 팝업을 막았어요. 팝업을 허용해 주세요.";
  if (code.includes("unauthorized-domain")) return "이 도메인은 Firebase 로그인 허용 목록에 없어요. (Firebase 콘솔 → Authentication → 설정 → 승인된 도메인)";
  if (code.includes("operation-not-allowed")) return "Firebase 콘솔에서 이 로그인 방법이 꺼져 있어요.";
  if (code.includes("network-request-failed")) return "네트워크 오류가 발생했어요.";
  return "로그인 중 오류가 발생했어요.";
}
