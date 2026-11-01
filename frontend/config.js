// 로컬 개발용 설정. Vercel 배포 시에는 build.js가 환경변수(API_BASE_URL, FIREBASE_CONFIG)로 이 파일을 새로 만든다.
// FIREBASE_CONFIG: Firebase 콘솔 → 프로젝트 설정 → 내 앱(웹) → firebaseConfig 값을 그대로 붙여넣기.
// (웹 apiKey는 비밀 키가 아니다. 대신 Authentication → 설정 → 승인된 도메인으로 사용처가 제한된다.)
window.APP_CONFIG = {
  API_BASE_URL: "http://127.0.0.1:8000",
  FIREBASE_CONFIG: {
    apiKey: "AIzaSyBQmUKHAxbPBEBZA1CNOtvDdnb9D262gTc",
    authDomain: "final-project-a079e.firebaseapp.com",
    projectId: "final-project-a079e",
    storageBucket: "final-project-a079e.firebasestorage.app",
    messagingSenderId: "386739034211",
    appId: "1:386739034211:web:2af59a9705d4f3fad44056",
  },
};

// measurementId: "G-C31QL9TBEH"
