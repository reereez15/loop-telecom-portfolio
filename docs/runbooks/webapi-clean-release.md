# �� Ŭ������ ����Ʈ���塤�鿣�� ����

���� ����� PC1 Ubuntu `pc1-k3s / 192.168.7.185`, PC2 Ubuntu `pc2-k3s / 192.168.7.100`, namespace `telecom`�̴�. �� DB�� PC2 Windows Primary `192.168.3.19 / my_new_board_db / webuser`�� �����Ѵ�. ���� �ּҴ� `https://192.168.3.30`�̴�.

## ���� ���� ����

| �۾� | PC1 Ubuntu ���� | ȯ�� ���� ó�� |
|---|---|---|
| �ڵ常 ���� | `apply-images` | ���� env��envFrom��Secret ������ȯ�� ���� ����Ʈ�� ����. Ubuntu ȯ�� ���� ���б� �� Secret ���� ���� |
| �ڵ�� Flask ȯ�� ���� ���� | `apply` | ���� Ubuntu ��Ʈ `.env`�� `backend/.env`�� �о� �� immutable Secret���� ����. ���� �׸��� backend ���� �켱 |
| ���� ������ Ȯ�� | `verify` | �ٽ� �������� �ʰ� �̹�������ȣ�� �� ������������ 404 ���� �˻� |

DB migration������ ��ȯ������ ��� ������ �������� �ʴ´�. ���� �ڵ尡 �� DB ������ �䱸�ϸ� �� ���������� �������� ���� ���� migration ������ �����Ѵ�. React `VITE_*`�� ���� ���� �����̸� Flask ȯ�� ���� �������� ��Ÿ�ӿ� �ٲ��� �ʴ´�.

## 1. ���� ��

- �� ������� ������ GitHub main�� �ݿ��ƴ��� Ȯ���Ѵ�. ������ ���� �� ������ origin/main Ŀ���� detached checkout���� �����Ѵ�.
- PC1 Windows Docker Desktop�� Linux �����̳� ���� �����Ѵ�. Git��SSH��SCP ���� ���� VM SSH ������ �����ؾ� �Ѵ�.
- �� k3s ��� Ready, API���������� edge �� 2�� Ready �� ��庰 �ϳ��� Pod ��ġ�� Ȯ���Ѵ�.
- `.env`�� ��й�ȣ�� Git�̳� �̹����� ���� �ʴ´�. ���� ������ ��ΰ� 404�� �����ٸ� [������ ���� ����](academy-admin-access.md)�� ���� �����Ѵ�.

## 2. PC1 Windows PowerShell: ���� �ޱ�

�Ʒ��� �� PR�� main�� ���յ� ������ �����̴�. ���� ���� ������ �������� ZIP�� prepare-images.ps1��release.py�� ���� ������ �� �� �� ��ο��� �����Ѵ�.

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $loopTools = Join-Path $env:USERPROFILE ('Downloads\telecom-release-tools-' + (Get-Date -Format 'yyyyMMddHHmmss'))
    git clone --no-checkout --filter=blob:none --branch main --single-branch https://github.com/telecom-carrier-Loop/telecom-security-project.git $loopTools
    if ($LASTEXITCODE -ne 0) { throw '���� ���� Ŭ�� ����' }
    git -C $loopTools sparse-checkout set --no-cone '/infrastructure/tools/webapi-release/'
    if ($LASTEXITCODE -ne 0) { throw '���� ���� ��� ���� ����' }
    git -C $loopTools checkout --detach origin/main
    if ($LASTEXITCODE -ne 0) { throw '���� ���� üũ�ƿ� ����' }
    $loopPrepare = Join-Path $loopTools 'infrastructure\tools\webapi-release\prepare-images.ps1'
    Unblock-File -LiteralPath $loopPrepare
    powershell -NoLogo -NoProfile -ExecutionPolicy RemoteSigned -File $loopPrepare
    if ($LASTEXITCODE -ne 0) { throw '���� �Ǵ� ���� ����. ���� �ܰ�� �Ѿ�� ������.' }
}
```

prepare-images.ps1�� �ٿ�ε� ������ �� `telecom-clean-source-��¥`�� `telecom-clean-release-��¥`�� �����Ѵ�. backend��frontend��infrastructure/docker�� �������Ƿ� ��ü ���� �ڷ��� Windows ���ϸ� ������ ���� �۾����� �и��Ѵ�. ���� ������Ʈ ������ �����ϰų� ����� �ʴ´�.

�� �̹����� ��ü �ҽ� Ŀ�� �󺧰� ���� �±׸� ����ϰ�, ���� ���ؽ�Ʈ�� `.dockerignore`�� ȯ�� ���� ���ܸ� �߰��Ѵ�. backend �̹��� ���� ȯ�� ���� ���縦 Ȯ���Ѵ�. `telecom-app.tar`����Ÿ�����͡�release.py�� �� VM�� ������ �� �� VM�� `/home/loop/.telecom-clean-release` �����͸� �� ������ ��η� �����Ѵ�. ��µ� COMMIT�� TAG�� ����Ѵ�. ����� GitHub�� ���� ������� ��� �ֽ��̶�� ���� �ƴ϶� �� ���忡 ������ Ŀ���̴�.

## 3. PC1 Ubuntu: �̹��� ���

```bash
loopRelease="$(cat "$HOME/.telecom-clean-release")"
sudo -v && python3 "$loopRelease/release.py" import
```

## 4. PC2 Ubuntu: ���� ������ �̹��� ���

```bash
loopRelease="$(cat "$HOME/.telecom-clean-release")"
sudo -v && python3 "$loopRelease/release.py" import
```

���� ��� archive SHA256 �� backend/frontend config digest���±ס��ҽ� Ŀ�� PASS�� Ȯ���Ѵ�. Docker Desktop�� �̹��� ID�� OCI index/manifest digest�̰� CRI�� config digest�� ��ȯ�� �� �����Ƿ� ���ڿ��� �ܼ� ������ �ʴ´�. ������ TAR�� descriptor�� config�� ������ SHA256��linux/amd64���������� �����Ѵ�. �±� �Ǵ� ������ �󺧸� �´� �̹����� �����Ű�� �ʴ´�.

��ϸ� ��Ȯ���Ϸ��� �� VM���� `python3 "$loopRelease/release.py" check-import`�� ����Ѵ�. ������ �ݴ��� VM�� ���� ������ �˻����� �����Ƿ� **�� VM�� PASS�� �۾��ڰ� Ȯ���� ��** �����ؾ� �Ѵ�.

## 5. PC1 Ubuntu��: �ڵ� ��ü

ȯ�� ���� ������ ���� �⺻ ����:

```bash
loopRelease="$(cat "$HOME/.telecom-clean-release")"
sudo -v && python3 "$loopRelease/release.py" apply-images
```

API ���� �� ������ �̹����� �ҽ� Ŀ�� annotation�� ��ü�ϸ� imagePullPolicy Never, RollingUpdate maxSurge 0 / maxUnavailable 1�� ����Ѵ�. ���� ȯ�� ����� �ٸ� ����Ʈ��affinity�� �����Ѵ�. `.env` �����̳� �� Secret�� ������ �ʴ´�. ��ȣ�� Flask DB����ū ������ ������ �޶����� ������ �ߴ��Ѵ�.

Flask ȯ�� ���ϵ� �����Ϸ��� ��쿡�� �� ���� **���** ������ ����Ѵ�. �� ������ ���� ���������� ���� �������� �ʴ´�.

```bash
sudo -v && python3 "$loopRelease/release.py" apply
```

apply�� PC1 Ubuntu�� `/home/loop/telecom-security-project/.env`�� `backend/.env`�� �д´�. DB ���� 5�� �׸�APP_ENV������ INCIDENT/AUTOMATION ��ū�� ���� �� ���� �����ϰ� TRUSTED_PROXY_HOPS=1, PUBLIC_BASE_URL=https://192.168.3.30�� �����Ѵ�. �ٸ� ȯ�� �׸��� ���Ͽ��� �����´�. ���� ������ env�� `/app/.env` ����Ʈ�� �켱������ ó���ϰ� ���ϡ�ȯ�� ��������ȿ Flask ������ �˻��Ѵ�.

## 6. PC1 Ubuntu: ���� �̹��� �� ȸ�� Ȯ��

```bash
sudo -v && python3 "$loopRelease/release.py" verify
sudo k3s kubectl -n telecom get pods -l 'app in (telecom-api,telecom-web)' -o wide
```

SOURCE_COMMIT�� Windows�� COMMIT�� ���� �� API���� Pod�� ��庰 1���� 1/1 Running�̾�� �Ѵ�. �̹��� ��ü ���� ENV_SETTINGS_PRESERVED=True, ȯ�� ���� ���� ENV_MATCH=True�� ��µȴ�.

������ ConfigMap�� �� edge�� ���� Nginx �������� **�˷��� ������ 404 ����**�� �˻��Ѵ�. ���Ѻ� ���� ���� ��ü�� �ڵ� �����ϴ� ���� �ƴϸ� �Ʒ� ������ ������ ������. ���� API ������ �ڵ� �����ϰų� edge ������ ����� �ʴ´�.

## 7. Windows �� ������ Ȯ��

```powershell
curl.exe --noproxy "*" --ssl-revoke-best-effort --connect-timeout 3 --max-time 10 -sS -i "https://192.168.3.30/api/health/ready"
curl.exe --noproxy "*" --ssl-revoke-best-effort --connect-timeout 3 --max-time 10 -sS -o NUL -w "HTTP=%{http_code}\n" "https://192.168.3.30/api/admin/dashboard"
curl.exe --noproxy "*" --ssl-revoke-best-effort --connect-timeout 3 --max-time 10 -sS -o NUL -w "HTTP=%{http_code}\n" "https://192.168.3.30/api/internal/privilege-violations"
```

������Ʈ CA�� �ŷ��� Windows �������� ������� readiness 200/database ok, �͸� ������ API 401, ���� ���� API 404�� Ȯ���Ѵ�. ���������� Ctrl+Shift+R �� ���� ��ɡ��α��Ρ������� �����͸� Ȯ���Ѵ�. ADMIN�� ������ API 200, CUSTOMER�� 403�̾�� �Ѵ�. ���� ��� ����� ������ ���ÿ� �������� �ʴ´�.

## ���п� �ǵ�����

STOP�� ������ �� VM�� �� �� ä ������ Pod ���¸� Ȯ���Ѵ�. �̹� ������ ������ ���������� apply/apply-images�� �ݺ����� �ʰ� verify�� ����Ѵ�. ���ᰡ ������ ���Ŀ��� ���� ���¸� ���Ƿ� �������� �ʴ´�.

�̹� �������� ���游 �ǵ������ �� ���, PC1 Ubuntu����:

```bash
loopRelease="$(cat "$HOME/.telecom-clean-release")"
sudo -v && python3 "$loopRelease/release.py" rollback
```

���� ���ø� ������ ���� �� ��ϵ� ���� API���� ���ø����� �����Ѵ�. DB�� Ubuntu ȯ�� ���� ��ü�� �ǵ����� �ʴ´�. Secret�� ����� ����� �����Ѵ�. `deployment-state.json`���� ��ȣ�� ȯ�� ���� �� �� �����Ƿ� GitHub��ä�ÿ� �ø��� �ʴ´�.

## ���� ����

```powershell
python -m unittest discover -s infrastructure/tools/webapi-release -p test_release.py -q
python -m unittest discover -s infrastructure/tools/tests -p test_k3s_admin_access.py -q
```

���� ���� ��ü�� ǥ�� ���̺귯���� ����ϰ� ȯ�� ���� �ؼ��� ���� API �����̳��� python-dotenv�� �����Ѵ�. ȯ�� ����ȭ ���� �׽�Ʈ���� ���� python-dotenv�� �ʿ��ϴ�. �� PR �ۼ� ȯ�濡���� � Docker ���峪 k3s ������ �������� �ʾҴ�. ���� Ȯ�� ������ [���� � ���](../operations/2026-11-02-webapi-release-admin-recovery.md)�� ������.
