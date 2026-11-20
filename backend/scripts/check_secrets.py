"""제출 전 시크릿 검사: git이 추적하는 파일에서 키·비밀 정보 패턴을 찾는다.

사용: 저장소 루트에서  python backend/scripts/check_secrets.py
결과가 '0건'이어야 한다. (.gitignore에 있는 .env, serviceAccountKey.json, frontend/config.js는 검사 대상이 아니다)
"""
import re
import subprocess
import sys

PATTERNS = {
    "OpenAI 키": re.compile(r"sk-(?:proj-)?[A-Za-z0-9_\-]{20,}"),
    "Google/Firebase API 키": re.compile(r"AIza[0-9A-Za-z_\-]{35}"),
    "개인 키": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "서비스 계정 키 필드": re.compile(r'"private_key(_id)?"\s*:\s*"[^"]{8,}'),
}
FORBIDDEN_FILES = re.compile(r"(^|/)(\.env|serviceAccountKey\.json|[^/]*firebase-adminsdk[^/]*\.json|config\.js)$")


def main() -> int:
    files = subprocess.run(["git", "ls-files"], capture_output=True, text=True, check=True).stdout.split()
    hits = []
    for f in files:
        if FORBIDDEN_FILES.search(f) and not f.endswith("config.example.js"):
            hits.append(f"{f}: 저장소에 올라가면 안 되는 파일")
            continue
        try:
            text = open(f, encoding="utf-8", errors="ignore").read()
        except (IsADirectoryError, FileNotFoundError):
            continue
        for name, pat in PATTERNS.items():
            for m in pat.finditer(text):
                line = text.count("\n", 0, m.start()) + 1
                hits.append(f"{f}:{line}: {name} ({m.group(0)[:8]}…)")
    if hits:
        print(f"✗ {len(hits)}건 발견")
        print("\n".join(hits))
        return 1
    print(f"✓ 0건 — 추적 중인 파일 {len(files)}개에서 키·비밀 정보가 발견되지 않았습니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
