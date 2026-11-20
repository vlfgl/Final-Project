// 로컬 개발용 설정 예시. 이 파일을 config.js로 복사한 뒤 값을 채운다 (config.js는 .gitignore 대상이라 커밋되지 않는다).
//   PowerShell:  Copy-Item config.example.js config.js
// Vercel 배포 시에는 build.js가 환경변수(API_BASE_URL, FIREBASE_CONFIG)로 dist/config.js를 만들므로 이 파일이 필요 없다.
// FIREBASE_CONFIG: Firebase 콘솔 → 프로젝트 설정 → 내 앱(웹) → firebaseConfig 값을 붙여넣기.
window.APP_CONFIG = {
  API_BASE_URL: "http://127.0.0.1:8000",
  FIREBASE_CONFIG: {
    apiKey: "YOUR_FIREBASE_WEB_API_KEY",
    authDomain: "YOUR_PROJECT_ID.firebaseapp.com",
    projectId: "YOUR_PROJECT_ID",
    appId: "YOUR_APP_ID",
  },
};
