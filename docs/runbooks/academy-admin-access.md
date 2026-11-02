# �п��� ���� HTTPS �ּ��� ADMIN ���� ��� ���� ��ȯ

����: **2026-11-02 ����� �� ������ 404 ���� ���롤�͸� 401 �� ���� API 404 Ȯ��**. �� API�� ������ ��� 46�� ��ȣ �˻�, ������ ���� 4�� ����, edge 2�� Ready�� ����� ȭ������ Ȯ���ߴ�. �̹� ���� �� ���� ADMIN 200 / CUSTOMER 403 �� ������ ������ ǥ���� ���� ��Ȯ���� ���� �ִ�. [���� ���](../operations/2026-11-02-webapi-release-admin-recovery.md)�� �����Ѵ�.

2026-10-27 ����� ��û�� ���� PC1��PC2��PC3 �̿��� �п��� PC�� ������Ʈ �ܺ� ����ڷ� �����Ѵ�. ���� PC ���� ���� ���� ���� �ּҿ��� ADMIN ������ ������ �������� ����� �� �ֵ��� ��ȯ�Ѵ�. ���ͳ� ������ VLAN �и��� �ƴϴ�. �ڵ� ������� [�� Ŭ�� ���� ����](webapi-clean-release.md)�� ����Ѵ�.

## �ڵ� ���� ������ ����

`infrastructure/tools/k3s-admin-access.py`�� PC1 Ubuntu���� �����ϴ� Python ǥ�� ���̺귯�� ��� ������. �� �귣ġ�� `admin-role-access-20261027`�̸� codex ���ξ ������� �ʴ´�. DB ��������ȭ����9443 ��å�� �������� �ʰ�, ���� ���� ConfigMap�� �˷��� ������ 404 ���ܸ� �����Ѵ�. ���� React RequireAuth�� Flask roles_required�� �����Ѵ�.

���� �� �� API ��� Ready���� Ȯ���ϰ� ���� ���� �̹����� ��� ������ route�� ADMIN ���۰� �ִ��� �˻��Ѵ�. �� API�� �͸� dashboard ��û�� 401������ �˻��Ѵ�. `/api/internal` ���ܰ� ���� web/API upstream�� �ٸ��ų� �˷����� ���� ������ location�� ������ ������ �������� �ʴ´�. �� edge Pod�� ���� TLS ȯ�濡�� ������ `nginx -t`�� �����Ѵ�.

PC1 Ubuntu���� ������ �޴´�. ���� ���� ���Ͽ� git pull/reset�� �������� �ʴ´�.

```bash
bash <<'BASH'
set -euo pipefail
cd "$HOME/telecom-security-project"
git fetch origin
git show origin/admin-redeploy-20261102:infrastructure/tools/k3s-admin-access.py > "$HOME/k3s-admin-access.py"
python3 -m py_compile "$HOME/k3s-admin-access.py"
BASH
```

�� ���� ���� �� ��ȹ�� �����.

```bash
sudo -v
python3 "$HOME/k3s-admin-access.py" plan
```

��ȹ�� private �۾� ������ ��������������state�� �����ϰ� diff�� ǥ���Ѵ�. edge Pod�� �ӽ� `/tmp` ���Ϸ� �˻��ϵ� ���� ������ �ٲ����� �ʴ´�. `PLAN OK`�� �־�� �����Ѵ�. ���� ���� API ��ȣ �˻糪 Nginx �˻翡�� ���߸� �� ����� Ȯ���ϸ� �˻縦 ��ȸ���� �ʴ´�.

��ȹ ���� ��:

```bash
loopAdminWork="$(cat "$HOME/.telecom-admin-access-workdir")"
python3 "$HOME/k3s-admin-access.py" apply --work-dir "$loopAdminWork"
```

���� ConfigMap/Deployment�� ��ȹ ���� �޶����ų� �������� ���� ��������� �ߴ��Ѵ�. ���� �� nginx.conf Ű�� ������ �� ���� edge Pod�� **�ϳ���** ������ϰ� �� ��ü �� �� Pod Ready�� ��ٸ���. �̴� �� ��� �ʼ� anti-affinity���� �� ��° Pod�� ����Ű�� �ʱ� ���� ����̸� Deployment�� �̹�����replica��strategy�� �ٲ��� �ʴ´�. ���� ��ü �� ��� �ִ� ������ ���� �� �����Ƿ� ª�� ���� �ð��� �����Ѵ�.

```bash
python3 "$HOME/k3s-admin-access.py" status --work-dir "$loopAdminWork"
```

`applied-needs-role-tests`, candidate ��ġ True, Ready edge 2�� ��밪�̴�. �ٸ� �п� PC���� �Ʒ� ǥ�� �����ؾ� �Ϸ��.

| ���� | ��� ��� |
|---|---|
| ������Ʈ CA �ŷ� �� https://192.168.3.30 ���� | HTTPS �����Ϲ� �� ���� |
| �͸� /api/admin/dashboard | 401 JSON |
| CUSTOMER �α��� �� ���� API | 403 |
| ADMIN �α��� �� /admin �� ���� API | ������ ������ ǥ�� / 200 |
| ���� �ڵ�ȭ API | ���� edge 404 ���� ���� |
| PC1��PC2 DB 3306 ���� ���� | �Ϲ� ����� PC���� ���� ���� ���� |

������ �׽�Ʈ�� ���� ������ �����ʡ��α׾ƿ� �� ��α������� �����Ѵ�. PC1��PC2��PC3 �̿��� PC������ �ݵ�� ADMIN ������ �����Ѵ�. IP��ȣ��Ʈ �̸�������Ʈ���� �÷��׸� ������ ���� ������ ������� �ʴ´�. CSRF�� ���� ȸ�� ������ �Ʒ� ���� ���� �׸��� ������.

��ü ���� �� ������ ���� ������ �õ��Ѵ�. ���� �� state ������ ����ų� apply�� �ݺ����� �ʴ´�. ���� ����:

```bash
python3 "$HOME/k3s-admin-access.py" rollback --work-dir "$loopAdminWork"
```

������ ���� ���� ������ 404 ������ �ǵ����� �� edge Pod�� �ٽ� ���� ��ü�Ѵ�. ���ᰡ nginx.conf�� �ٲٸ� ����� �ʰ� �ߴ��Ѵ�. �۾� �����������ʹ� ������� �����ϰ� Git�� �ø��� �ʴ´�.

������ ��ȯ������ �˻硤�߸���/���� ���� �źΡ����� ���������� ��ü������ ������ ���� Ŭ������ �������� �����ߴ�. 2026-11-02���� ��� ���� Service ������ �����ϴ� ������ 13�� �׽�Ʈ�� ����ߴ�. �Ǽ��� ���롤�͸� 401������ API 404�� Ȯ��������, �̹� ���� �� �ܺ� PC�� CUSTOMER/ADMIN ������ ���� Ȯ�� ����̴�. �Ʒ� ���� ���� ������ ����̸� �ڵ� ���� �� ȥ������ �ʴ´�.

## ��ǥ�� ���� ����

- ���� `https://192.168.3.30`���� CUSTOMER�� ���� ���, ADMIN�� ������ ����� ����Ѵ�.
- ������ ���δ� pfSense�� �������� �ƴ϶� Flask�� ���� ���ǡ������ ���ҷ� �Ǵ��Ѵ�. 9443 �ڵ� ���𷺼��� �߰����� �ʴ´�.
- ���� ���� ��δ� pfSense `.3.30:443`�� HAProxy�� �� VM�� `30443`���� �����Ѵ�. �� ������ HAProxy��NAT����ȯ ��θ� �������� �ʴ´�. ���� PC1 ���� NAT���� ��ȯ�� �̷��� [�� �ڵ� ��ȯ ���](../operations/2026-10-30-web-ha-failover.md)�� �����Ѵ�.
- ���� `telecom-edge-config`�� ������ ��� 404 ���ϸ� �����Ѵ�. `/api/internal` ����, TLS, proxy ���, ���� 9443������ GUI��SSH��DB ���� ��å�� �����Ѵ�.
- k3s public edge ������ �� edge�� ����� ���� 8443/���� NodePort���� ����ȴ�. `.3.30`���� ������ ������ �ƴϴ�. ���� RBAC�� ��� �ش� ��ο��� �����ؾ� �Ѵ�.

## 1. ����� �ڵ� ����� ���� ���� �˻�

����� ��û�� ���� [DB ��Ʈ��ũ ���� ���ѡ��� ���� �и�](mysql-network-access-hardening.md)�� ������ �����Ѵ�. ������ �� ����� ���� 3306�� ����ڿ��� �������� �ʴ´�. DB ����� ���� ������ ��ȯ�� ���� �����ϸ� �� ���� �������� �ʴ´�.

���� �ҽ� `69fff4c`�� `backend/app` AST �˻翡�� `/api/admin` �Ʒ� route ���� 42���� ��� `@roles_required(ROLE_ADMIN)`�� �־���. `core/permissions.py`�� �̷α��� 401, ���� ����ġ 403, ���� ��û CSRF �˻縦 �����Ѵ�. `core/sessions.py`�� �� ��û DB ���ǰ� ����� Ȱ������� ���¸� Ȯ���Ѵ�. `frontend/src/components/common/RequireAuth.tsx`�� ȭ�� ���� ��� ����Ѵ�.

���� �˻��̸� ���� ���� �̹����� ���ٰ� ������ �� ����. ���� Python���� Flask/pytest �������� ���� �׽�Ʈ ����Ʈ�� �������� �ʾҴ�. ���� PC3 9443���� CUSTOMER �źΡ�ADMIN ������ ���� Ȯ���ϰ� �Ʒ��� **���� ���� �� API �̹���**�� �˻��Ѵ�.

PC1 Ubuntu:

```bash
sudo k3s kubectl get nodes -o wide
sudo k3s kubectl -n telecom get pods -o wide
```

�� ��� Ready, API��edge �غ� ���� ������ �� ���� ������ �����Ѵ�. DB�� ���� �ʰ� ���� Python ���μ������� ��ϵ� �ڵ鷯�� ���� ���۸� �˻��Ѵ�. ����� ����/��й�ȣ�� ������� �ʴ´�.

```bash
bash <<'BASH'
set -euo pipefail
pods="$(sudo k3s kubectl -n telecom get pods -l app=telecom-api -o name)"
test -n "$pods"
for pod in $pods; do
  echo "�˻�: $pod"
  sudo k3s kubectl -n telecom exec -i "$pod" -c api -- python - <<'PY'
import inspect
from wsgi import app
bad = []
count = 0
for rule in app.url_map.iter_rules():
    if not (rule.rule == '/api/admin' or rule.rule.startswith('/api/admin/')):
        continue
    count += 1
    fn = app.view_functions[rule.endpoint]
    protected = False
    while fn is not None:
        if (getattr(fn, '__code__', None)
                and fn.__code__.co_name == 'wrapper'
                and fn.__code__.co_filename.endswith('/core/permissions.py')):
            values = inspect.getclosurevars(fn).nonlocals
            if values.get('roles') == ('ADMIN',):
                protected = True
        fn = getattr(fn, '__wrapped__', None)
    if not protected:
        bad.append(rule.rule)
print('admin routes:', count, 'missing role wrapper:', bad)
if not count or bad:
    raise SystemExit('�ߴ�: ���� �̹����� ������ ��ȣ�� Ȯ���ؾ� �մϴ�.')
PY
done
BASH
```

�˻� ������ ��ü ���� ������ �ƴϴ�. �ܰ� 5�� ���� 401/403/200 ������ �ʼ���. ���� �̹������� ���� ������ �ٸ��ų� �����ϸ� ���� ������ �������� �ʰ� �ҽ����̹������� Ȯ���Ѵ�.

## 2. PC1 Ubuntu: ���� ����� ������ ����

���� ������ ���� Ubuntu �п��� �����Ѵ�. ���� �� ��ü ��尡 Ready�̰� ���� ����/���� ��ΰ� �����̾�� �Ѵ�.

```bash
loopAdminDir="$HOME/telecom-admin-access-$(date +%Y%m%d-%H%M%S)"
mkdir -m 700 "$loopAdminDir"
sudo k3s kubectl -n telecom get configmap telecom-edge-config -o json > "$loopAdminDir/before.json"
sudo k3s kubectl -n telecom get deployment telecom-edge -o yaml > "$loopAdminDir/deployment-before.yaml"
python3 - "$loopAdminDir" <<'PY'
import json, pathlib, sys
p = pathlib.Path(sys.argv[1])
obj = json.loads((p/'before.json').read_text())
text = obj['data']['nginx.conf']
(p/'nginx-before.conf').write_text(text)
(p/'nginx-candidate.conf').write_text(text)
PY
echo "$loopAdminDir"
nano "$loopAdminDir/nginx-candidate.conf"
```

�Ʒ��� ���� **���� ������������ API ���� return 404 ���ϸ� ����**�Ѵ�.

```nginx
location = /admin { return 404; }
location ^~ /admin/ { return 404; }
location = /api/admin { return 404; }
location ^~ /api/admin/ { return 404; }
```

���忡 `location ~ ^/api/admin/` �� ���Խ����� ���� ������ �߰��ߴٸ� �� ������ ���ܵ� Ȯ���Ѵ�. �ٸ� ���� ���¶�� �ڵ� ġȯ���� ���� ���̸� �����Ѵ�.

�Ʒ� ���� �ڵ�ȭ API ������ �״�� ���ܾ� �Ѵ�.

```nginx
location = /api/internal { return 404; }
location ^~ /api/internal/ { return 404; }
```

���� `/api/`�� `http://telecom-api-local:5000`, `/`�� `http://telecom-web-local:80` ������ �״�� �����Ѵ�. ������ ���� Cluster ����� `telecom-api:5000`��`telecom-web:80`�� �ν������� ��� ��쿡�� upstream�� ��ü���� �ʴ´�. `/admin`�� ���� `/`���� React��, `/api/admin/...`�� ���� `/api/`���� Flask�� ���޵ȴ�. ���� DB ���� ������ �߰����� �ʴ´�.

nano ����: Ctrl+O, Enter, Ctrl+X. ���� Ȯ��:

```bash
diff -u "$loopAdminDir/nginx-before.conf" "$loopAdminDir/nginx-candidate.conf"
```

diff ���� �ڵ� 1�� ���̰� �ִٴ� ���̴�. ������ ���� �ܿ� TLS��internal ���ܡ������upstream ������ ���̸� �������� �ʴ´�.

## 3. ���� �� edge�� ���� ȯ�濡�� ���� �˻�

���� ���� ������ ����� �ʰ� `/tmp`�� �������� ������ �˻��Ѵ�. `edge` �����̳� �̸��� �ٸ��� ���� ���� Deployment�� Ȯ���Ѵ�.

```bash
(
set -e
pods="$(sudo k3s kubectl -n telecom get pods -l app=telecom-edge -o name)"
test -n "$pods"
for pod in $pods; do
  sudo k3s kubectl -n telecom exec -i "$pod" -c edge -- sh -c 'cat > /tmp/telecom-admin-candidate.conf' < "$loopAdminDir/nginx-candidate.conf"
  sudo k3s kubectl -n telecom exec "$pod" -c edge -- nginx -t -c /tmp/telecom-admin-candidate.conf
done
)
```

��� �˻翡�� `syntax is ok`, `test is successful`�� Ȯ���ؾ� �������� �����Ѵ�. �� ������ ���� Nginx reload�� ���� �ʴ´�.

## 4. ConfigMap�� nginx.conf�� �����ϰ� public edge �����

```bash
python3 - "$loopAdminDir" <<'PY'
import json, pathlib, sys
p = pathlib.Path(sys.argv[1])
before = json.loads((p/'before.json').read_text())
patch = {'metadata': {'resourceVersion': before['metadata']['resourceVersion']},
         'data': {'nginx.conf': (p/'nginx-candidate.conf').read_text()}}
(p/'patch.json').write_text(json.dumps(patch))
PY
```

```bash
sudo k3s kubectl -n telecom patch configmap telecom-edge-config --type=merge --patch-file "$loopAdminDir/patch.json"
```

������ ��쿡�� ���� ����. Conflict�� �ٸ� ����� ������ ������ ���̹Ƿ� �� ������ ���ؾ� �Ѵ�. resourceVersion�� ���� ������ ����� �ʴ´�.

```bash
sudo k3s kubectl -n telecom rollout restart deployment/telecom-edge
sudo k3s kubectl -n telecom rollout status deployment/telecom-edge --timeout=180s
```

ConfigMap�� �ٲ� subPath ����Ʈ�� �ڵ� ���ŵ��� ������ Nginx�� ���� ���бⰡ �ʿ��ϴ�. ���� public edge Pod�� ���� ������Ѵ�. DB��API��web �̹��������� edge ������� �ʿ� ����.

## 5. PC1��PC2��PC3 �̿� �п� PC���� ���� ����

������Ʈ CA ���� �������� �ŷ� ����ҿ� ����� Windows �������� �����Ѵ�. �ܺ� ����� PC���� admin �������� ����ϴ� ��å�̸� ������ ��й�ȣ ���� ������ ���� PC3 ���� ��å���� �о�����.

```powershell
curl.exe --noproxy "*" --ssl-revoke-best-effort --connect-timeout 3 --max-time 8 -sS -i "https://192.168.3.30/api/health/ready"
curl.exe --noproxy "*" --ssl-revoke-best-effort --connect-timeout 3 --max-time 8 -sS -i "https://192.168.3.30/api/admin/dashboard"
curl.exe --noproxy "*" --ssl-revoke-best-effort --connect-timeout 3 --max-time 8 -sS -i "https://192.168.3.30/api/internal/probe"
```

���� 200(DB ok), 401(JSON), 404(edge ����)�� ��밪�̴�. `/api/internal/probe` 404 �ϳ������� ������ ������ �� �����Ƿ� ����� `nginx -T`�� internal location ���ϵ� �Բ� Ȯ���Ѵ�.

���������� �Ϲ� CUSTOMER�� �α����ϰ� ���� ��ó�� �ֿܼ��� �б� ��û�� �����Ѵ�. ��� ��Ű�� �������� �ʴ´�.

```javascript
fetch('/api/admin/dashboard', {credentials: 'same-origin'})
  .then(async r => console.log(r.status, await r.json()))
```

CUSTOMER�� 403�̾�� �Ѵ�. �α׾ƿ� �� ADMIN���� �ٽ� �α����ϸ� ���� ��û�� 200, `/admin`�� ���� ��ȸ�� �����̾�� �Ѵ�. �������� ������ �����Ͱ� ���̸� ��� �ܰ� 6���� �ǵ�����.

CSRF Ȯ���� ADMIN ���ǿ��� **�б� ���� ������ ��ģ ��**, � �����͸� �������� �ʴ� �α׾ƿ� ��û���� ������ �� �ִ�.

```javascript
fetch('/api/auth/logout', {method: 'POST', credentials: 'same-origin'})
  .then(async r => console.log(r.status, await r.json()))
```

CSRF ����� �����Ƿ� 403 / CSRF_FAILED�� ��밪�̴�. UI �α׾ƿ��� ���� �����ؾ� �Ѵ�. ���� 9443 ����� ��Ű�� �� `.3.30` ��Ű�� �ٸ� IP�̹Ƿ� `.3.30`���� �ٽ� �α����Ѵ�.

� ������ ������ ���� �������� �������� �ʴ´�. ���� ȸ�� ������ ���� ���� ADMIN �������� ���� ȸ�� �� ���� ���� ��û�� 403���� Ȯ���Ѵ�. �� ���� �α׿��� ���� ����� ID�� ����� Ȯ���Ѵ�.

## 6. �ѹ�

���� Ubuntu ���� `loopAdminDir`�� ����Ѵ�. ������ �������ٸ� �ܰ� 2���� ����� ��Ȯ�� ������ �����Ѵ�. �ٸ� �۾��ڰ� ConfigMap�� �����ߴٸ� ������ ����� ���� ������ �����Ѵ�.

```bash
python3 - "$loopAdminDir" <<'PY'
import json, pathlib, sys
p = pathlib.Path(sys.argv[1])
before = json.loads((p/'before.json').read_text())
(p/'rollback.json').write_text(json.dumps({'data': {'nginx.conf': before['data']['nginx.conf']}}))
PY
sudo k3s kubectl -n telecom patch configmap telecom-edge-config --type=merge --patch-file "$loopAdminDir/rollback.json"
```

patch ���� ��:

```bash
sudo k3s kubectl -n telecom rollout restart deployment/telecom-edge
sudo k3s kubectl -n telecom rollout status deployment/telecom-edge --timeout=180s
```

**rollout undo�����δ� ������ ConfigMap ������ �������� �ʴ´�.** ���� admin 404 ����, �Ϲ� readiness 200, ���� PC3 ������ 9443 ȸ�͸� Ȯ���Ѵ�.

## ��� ���Ѱ� ���� ����

- �п��� �ܺ� ����ڸ� ���������� �������� �� VLAN/��������� �ݸ��� ���� �ƴϴ�. Ŭ���̾�Ʈ�� �ٸ� IP�� �ο��ϰų� PC1~3���� �����ߴٴ� ������ ADMIN ������ �ο����� �ʴ´�.
- NodePort ���� ���� �� pfSense ��ȸ ��� ������ ������. �� ������ ��ȭ����SSH��DB������ ��ǰ ���� UI�� �������� �ʴ´�.
- pfSense�� TLS�� k3s�� �����Ѵ�. pfSense�� Suricata�� ��ȣȭ�� ��� HTTP ������ �� �� �ִٰ� �������� �ʴ´�. ��/Nginx ���� �α׿� �����Ѵ�.
- ���� SNAT �� NodePort ��δ� �ۿ� ���� IP�� �ƴ� ���� �ּҸ� ���̰� �� �� �ִ�. ���� `LOGIN_MAX_PER_IP=20` �Ǵ� IP �ڵ� ������ ��ü ����ڸ� �Բ� ������ �� �����Ƿ� ����� ID������ ���� ��ϰ� �Բ� �����Ѵ�. IP Ȯ���� ���� ���� X-Forwarded-For �ŷڸ� ����ϰų� �α��� ������ ���� �ʴ´�. ���� IP ������ ���� ��Ʈ��ũ ���� ������.
- �ܺ� ����ڿ� ������ �α��� ��θ� �����ϹǷ� ���� ������ ��й�ȣ�������� å�� ������ �ʿ��ϸ� MFA�������� �������� �ļ� �����Ѵ�. ���� MFA ���� �Ϸ�� ������� �ʴ´�.

�ٰ�: [OWASP ���� �˻�](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html), [Kubernetes ConfigMap](https://kubernetes.io/docs/concepts/configuration/configmap/). �ֽ� ���� ����� [2026-10-27 ���](../operations/2026-10-27-service-recovery.md)�� �����Ѵ�.
