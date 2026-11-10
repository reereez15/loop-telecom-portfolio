# 이 묶음을 개인 저장소에 넣는 순서

1. GitHub에서 빈 저장소 `loop-telecom-portfolio` 생성 (README 추가 체크 해제)
2. 저장소 바깥 빈 폴더에서:
   ```powershell
   pip install git-filter-repo
   python <압축 푼 폴더>\portfolio\scripts\sanitize_repo.py https://github.com/telecom-carrier-Loop/telecom-security-project.git loop-clean
   git -C loop-clean push --mirror https://github.com/reereez15/loop-telecom-portfolio.git
   git clone https://github.com/reereez15/loop-telecom-portfolio.git
   ```
3. 이 묶음의 파일을 클론한 폴더에 같은 경로로 덮어쓰기 (`README.md`, `.env.example`, `docs/`, `scripts/`, `infrastructure/docker/compose/local/`, `monitoring/compose/`)
4. 점검 후 커밋:
   ```powershell
   python scripts/check_secrets.py --history    # 비밀값 없음
   git add -A; git commit -m "docs(portfolio): 개인 포트폴리오 정리 — 설치·시나리오·작업 내역"; git push
   ```
5. 저장소 Settings에서 브랜치 정리(필요 없는 원격 브랜치 삭제는 선택)
