#!/usr/bin/env python3
"""Block admin paths on the public edge, preserving the separate private entry.

This version ADDS four public denials. It does not change pfSense, services,
private-admin resources, application authentication, DBs or Secrets.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import uuid

NAMESPACE = 'telecom'
CONFIGMAP = 'telecom-edge-config'
DEPLOYMENT = 'telecom-edge'
KEY = 'nginx.conf'
TOKEN = re.compile(r'''\s+|\#[^\n]*|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|[{};]|[^\s{};\#"']+''')
STATE_FORMAT = 'telecom-public-admin-guard-v1'
AUDIT = r'''
import inspect, json
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
        code = getattr(fn, '__code__', None)
        if code and code.co_name == 'wrapper' and code.co_filename.endswith('/core/permissions.py'):
            if inspect.getclosurevars(fn).nonlocals.get('roles') == ('ADMIN',):
                protected = True
        fn = getattr(fn, '__wrapped__', None)
    if not protected:
        bad.append(rule.rule)
if not count or bad:
    raise SystemExit('Missing ADMIN route protection: ' + str(bad))
with app.test_client() as client:
    status = client.get('/api/admin/dashboard', base_url='https://192.168.3.30').status_code
if status != 401:
    raise SystemExit('Expected anonymous 401, got ' + str(status))
print('ADMIN_AUDIT=' + json.dumps({'routes': count, 'anonymous': status}))
'''


def kubectl(*args, input_text=None):
    result = subprocess.run(['sudo', '-n', 'k3s', 'kubectl', '-n', NAMESPACE, *args],
                            input=input_text, text=True, capture_output=True, timeout=240)
    if result.returncode:
        # Do not print imported application errors or credentials to shared output.
        raise RuntimeError('kubectl failed: ' + ' '.join(args[:3]) + '; exit=' + str(result.returncode))
    return result.stdout


def get(kind, name=None):
    return json.loads(kubectl('get', kind, *([name] if name else []), '-o', 'json'))


def locations(text):
    tokens = []
    offset = 0
    for match in TOKEN.finditer(text):
        if match.start() != offset:
            raise ValueError('Unsupported Nginx syntax; no automatic edit.')
        offset = match.end()
        value = match.group()
        if value.isspace() or value.startswith('#'):
            continue
        tokens.append((value, match.start(), match.end()))
    if offset != len(text):
        raise ValueError('Incomplete Nginx token; no automatic edit.')
    stack, closing = [], {}
    for i, token in enumerate(tokens):
        if token[0] == '{':
            stack.append(i)
        elif token[0] == '}':
            if not stack:
                raise ValueError('Unbalanced Nginx braces.')
            closing[stack.pop()] = i
    if stack:
        raise ValueError('Unbalanced Nginx braces.')
    result = []
    for i, token in enumerate(tokens):
        if token[0] != 'location' or (i and tokens[i - 1][0] not in ('{', '}', ';')):
            continue
        start = i + 1
        while start < len(tokens) and tokens[start][0] not in ('{', ';', '}'):
            start += 1
        if start not in closing:
            raise ValueError('Unsupported location directive.')
        end = closing[start]
        result.append((tuple(t[0] for t in tokens[i + 1:start]),
                       tuple(t[0] for t in tokens[start + 1:end]), token[1], tokens[end][2]))
    return result


def validate_routes(text):
    blocks = locations(text)
    for header in (('=', '/api/internal'), ('^~', '/api/internal/')):
        if not any(h == header and body == ('return', '404', ';') for h, body, _, _ in blocks):
            raise ValueError('Required /api/internal 404 block is missing or different.')
    for header, upstreams in (
        (('/api/',), {'http://telecom-api:5000', 'http://telecom-api-local:5000'}),
        (('/',), {'http://telecom-web:80', 'http://telecom-web-local:80'}),
    ):
        bodies = [body for h, body, _, _ in blocks if h == header]
        passes = [bodies[0][i + 1] for i in range(len(bodies[0]) - 2)
                  if bodies[0][i] == 'proxy_pass' and bodies[0][i + 2] == ';'] if len(bodies) == 1 else []
        if len(passes) != 1 or passes[0] not in upstreams:
            raise ValueError('Unexpected public API/web upstream; inspect manually.')


DENIALS = (('=', '/admin'), ('^~', '/admin/'),
           ('=', '/api/admin'), ('^~', '/api/admin/'))


def config_blocks(text):
    """Read block ancestry without interpreting comments or quoted braces."""
    tokens = []
    offset = 0
    for m in TOKEN.finditer(text):
        if m.start() != offset:
            raise ValueError('Unrecognized Nginx syntax.')
        offset = m.end()
        if not m.group().isspace() and not m.group().startswith('#'):
            tokens.append((m.group(), m.start(), m.end()))
    if offset != len(text):
        raise ValueError('Incomplete Nginx token.')
    stack, blocks, begin = [], [], 0
    for i, (value, start, end) in enumerate(tokens):
        if value == '{':
            b = {'header': tuple(t[0] for t in tokens[begin:i]),
                 'parent': stack[-1] if stack else None,
                 'start': tokens[begin][1], 'end': None, 'directives': []}
            blocks.append(b)
            stack.append(b)
            begin = i + 1
        elif value == '}':
            if not stack or begin != i:
                raise ValueError('Unbalanced or incomplete Nginx directive.')
            stack.pop()['end'] = end
            begin = i + 1
        elif value == ';':
            directive = tuple(t[0] for t in tokens[begin:i])
            if directive and directive[0] == 'include' and directive != ('include', '/etc/nginx/mime.types'):
                raise ValueError('Unknown include; inspect configuration manually.')
            if stack:
                stack[-1]['directives'].append(directive)
            begin = i + 1
    if stack or begin != len(tokens):
        raise ValueError('Unclosed Nginx configuration.')
    return blocks


def candidate_config(text):
    validate_routes(text)
    blocks = config_blocks(text)
    servers = [b for b in blocks if b['header'] == ('server',)
               and b['parent'] is not None and b['parent']['header'] == ('http',)]
    if len(servers) != 1:
        raise ValueError('Expected exactly one HTTP server; inspect configuration manually.')
    server = servers[0]
    direct = [b for b in blocks if b['parent'] is server]
    for scope in (server['parent'], server):
        if any(d and d[0] in ('rewrite', 'return', 'error_page', 'try_files') for d in scope['directives']):
            raise ValueError('Server/HTTP routing override requires manual review.')
    if any(b['header'] and b['header'][0] == 'if' for b in direct):
        raise ValueError('Server-level conditional routing requires manual review.')
    api = [b for b in direct if b['header'] == ('location', '/api/')]
    web = [b for b in direct if b['header'] == ('location', '/')]
    if len(api) != 1 or len(web) != 1:
        raise ValueError('Expected direct public API and Web locations in one server.')
    direct_starts = {b['start'] for b in direct}
    for header in (('=', '/api/internal'), ('^~', '/api/internal/')):
        bodies = [body for h, body, start, _ in locations(text) if h == header and start in direct_starts]
        if bodies != [('return', '404', ';')]:
            raise ValueError('Internal denial must be directly in the public server.')
    existing = [(h, b) for h, b, _, _ in locations(text)
                if any('admin' in value.lower() for value in h)]
    if existing:
        if len(existing) != 4 or {h for h, _ in existing} != set(DENIALS) or any(b != ('return', '404', ';') for _, b in existing):
            raise ValueError('Unknown or partial admin policy; refusing to overwrite it.')
        if any(not any(b['header'] == ('location',) + h for b in direct) for h in DENIALS):
            raise ValueError('Admin policy is outside the expected server.')
        return text, 0
    start = text.rfind('\n', 0, api[0]['start']) + 1
    indent = text[start:api[0]['start']]
    if indent.strip():
        raise ValueError('Expected an API location on its own line.')
    newline = '\r\n' if '\r\n' in text else '\n'
    addition = ''.join(indent + 'location ' + ' '.join(h) + ' { return 404; }' + newline
                       for h in DENIALS)
    updated = text[:start] + addition + text[start:]
    validate_routes(updated)
    before_other = [(h, b) for h, b, _, _ in locations(text)]
    after_other = [(h, b) for h, b, _, _ in locations(updated) if h not in DENIALS]
    if before_other != after_other:
        raise ValueError('Unexpected change to another location.')
    return updated, 4


def assert_public_admin_blocked(text):
    """Require all four live public denials, internal denials and known upstreams."""
    try:
        _, additions = candidate_config(text)
    except ValueError as error:
        raise RuntimeError('Invalid public edge policy: ' + str(error)) from error
    if additions:
        raise RuntimeError('Public edge is missing admin 404 blocks. Run a fresh guard plan/apply first.')


def template_hash(deployment):
    return hashlib.sha256(json.dumps(deployment['spec']['template'], sort_keys=True).encode()).hexdigest()


def ready(pod, container):
    return (not pod['metadata'].get('deletionTimestamp') and pod.get('status', {}).get('phase') == 'Running'
            and any(c.get('name') == container and c.get('ready') is True
                    for c in pod.get('status', {}).get('containerStatuses', [])))


def pods(app):
    return json.loads(kubectl('get', 'pods', '-l', 'app=' + app, '-o', 'json'))['items']


def prepared_pods(app, container):
    items = pods(app)
    if len(items) != 2 or not all(ready(pod, container) for pod in items):
        raise RuntimeError('Need two stable Ready pods: ' + app)
    return items


def audit_api():
    for pod in prepared_pods('telecom-api', 'api'):
        output = kubectl('exec', '-i', pod['metadata']['name'], '-c', 'api', '--', 'python', '-', input_text=AUDIT)
        reports = [json.loads(line[len('ADMIN_AUDIT='):]) for line in output.splitlines() if line.startswith('ADMIN_AUDIT=')]
        if len(reports) != 1 or reports[0].get('anonymous') != 401 or reports[0].get('routes', 0) < 1:
            raise RuntimeError('API authorization audit did not pass.')
        print(pod['metadata']['name'], 'ADMIN audit:', reports[0])


def edge_snapshot():
    deployment = get('deployment', DEPLOYMENT)
    if deployment['spec'].get('replicas') != 2:
        raise RuntimeError('Expected two public edge replicas.')
    users = []
    for item in get('deployments')['items']:
        if any(v.get('configMap', {}).get('name') == CONFIGMAP
               for v in item['spec']['template']['spec'].get('volumes', [])):
            users.append(item['metadata']['name'])
    if users != [DEPLOYMENT]:
        raise RuntimeError('ConfigMap is missing or shared by other deployments: ' + str(users))
    prepared_pods(DEPLOYMENT, 'edge')
    private = get('deployment', 'telecom-admin-edge')
    if private.get('status', {}).get('readyReplicas', 0) < 1:
        raise RuntimeError('Private admin deployment must have a Ready replica first.')
    return deployment


def validate_nginx(text, recovery=False):
    targets = [pod for pod in pods(DEPLOYMENT) if ready(pod, 'edge')] if recovery else prepared_pods(DEPLOYMENT, 'edge')
    if not targets:
        raise RuntimeError('No Ready edge is available for nginx -t.')
    for pod in targets:
        name = pod['metadata']['name']
        path = '/tmp/telecom-admin-' + uuid.uuid4().hex + '.conf'
        try:
            kubectl('exec', '-i', name, '-c', 'edge', '--', 'sh', '-c',
                    'umask 077; cat > ' + path, input_text=text)
            kubectl('exec', name, '-c', 'edge', '--', 'nginx', '-t', '-c', path)
        finally:
            kubectl('exec', name, '-c', 'edge', '--', 'rm', '-f', path)


def write_json(path, value):
    temporary = path.with_suffix('.new')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2))
    temporary.replace(path)


def read_config(path):
    with path.open(encoding='utf-8', newline='') as stream:
        return stream.read()


def write_config(path, text):
    with path.open('w', encoding='utf-8', newline='') as stream:
        stream.write(text)


def refresh_edge(snapshot, recovery=False, expected_config=None):
    initial = pods(DEPLOYMENT) if recovery else prepared_pods(DEPLOYMENT, 'edge')
    if len(initial) != 2:
        raise RuntimeError('Expected exactly two edge pods; inspect before refreshing.')
    # During recovery, replace the failed pod first while its peer stays available.
    originals = [pod['metadata']['name'] for pod in sorted(initial, key=lambda p: ready(p, 'edge'))]
    # Recreate one pod at a time; required anti-affinity needs a free node slot.
    for name in originals:
        current = get('deployment', DEPLOYMENT)
        if template_hash(current) != snapshot['template_hash'] or current['metadata']['uid'] != snapshot['deployment_uid']:
            raise RuntimeError('Deployment changed concurrently; stop pod refresh.')
        if expected_config is not None and get('configmap', CONFIGMAP)['data'][KEY] != expected_config:
            raise RuntimeError('Public configuration changed concurrently; stop refresh.')
        if not recovery:
            prepared_pods(DEPLOYMENT, 'edge')
        print('Replacing public edge pod:', name, flush=True)
        kubectl('delete', 'pod', name, '--wait=true', '--timeout=60s')
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            items = pods(DEPLOYMENT)
            if len(items) == 2 and all(ready(pod, 'edge') for pod in items):
                break
            time.sleep(2)
        else:
            raise RuntimeError('Public edge replacement did not become Ready; inspect pods.')


def patch_config(current, text, directory):
    patch = [
        {'op': 'test', 'path': '/metadata/uid', 'value': current['metadata']['uid']},
        {'op': 'test', 'path': '/metadata/resourceVersion', 'value': current['metadata']['resourceVersion']},
        {'op': 'test', 'path': '/data/nginx.conf', 'value': current['data'][KEY]},
        {'op': 'replace', 'path': '/data/nginx.conf', 'value': text},
    ]
    write_json(directory / 'patch.json', patch)
    kubectl('patch', 'configmap', CONFIGMAP, '--type=json', '--patch-file', str(directory / 'patch.json'))


def load_state(directory):
    state = json.loads((directory / 'state.json').read_text())
    if state.get('format') != STATE_FORMAT:
        raise ValueError('Unknown or legacy access-enabling plan. Use a fresh public-denial plan.')
    return state


def rollback(directory, state):
    current = get('configmap', CONFIGMAP)
    before = json.loads((directory / 'before.json').read_text())
    candidate = read_config(directory / 'candidate.conf')
    if current['metadata']['uid'] != before['metadata']['uid'] or current['data'][KEY] not in (before['data'][KEY], candidate):
        raise RuntimeError('ConfigMap changed concurrently; refusing rollback overwrite.')
    deployment = get('deployment', DEPLOYMENT)
    if deployment['metadata']['uid'] != state['deployment_uid'] or template_hash(deployment) != state['template_hash']:
        raise RuntimeError('Deployment changed concurrently; refusing rollback.')
    validate_nginx(before['data'][KEY], recovery=True)
    patch_config(current, before['data'][KEY], directory)
    state['stage'] = 'config-restored-refresh-pending'
    write_json(directory / 'state.json', state)
    refresh_edge(state, recovery=True, expected_config=before['data'][KEY])
    state['stage'] = 'rolled-back'
    write_json(directory / 'state.json', state)


def plan(directory):
    directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    audit_api()
    deployment = edge_snapshot()
    before = get('configmap', CONFIGMAP)
    candidate, count = candidate_config(before['data'][KEY])
    write_json(directory / 'before.json', before)
    write_json(directory / 'deployment-before.json', deployment)
    write_config(directory / 'candidate.conf', candidate)
    validate_nginx(candidate)
    state = {'format': STATE_FORMAT, 'stage': 'planned',
             'deployment_uid': deployment['metadata']['uid'], 'template_hash': template_hash(deployment)}
    write_json(directory / 'state.json', state)
    (Path.home() / '.telecom-public-admin-guard-workdir').write_text(str(directory))
    print('PLAN_OK: public admin 404 blocks to add:', count)
    print('WORK_DIR=' + str(directory))
    print('Service configuration unchanged. Candidate passed nginx -t on both edge pods.')


def apply(directory):
    state = load_state(directory)
    if state['stage'] != 'planned':
        raise RuntimeError('Do not repeat apply; inspect status or rollback.')
    before = json.loads((directory / 'before.json').read_text())
    candidate, _ = candidate_config(before['data'][KEY])
    if candidate != read_config(directory / 'candidate.conf'):
        raise ValueError('Candidate was modified after planning.')
    audit_api()
    deployment = edge_snapshot()
    current = get('configmap', CONFIGMAP)
    if (deployment['metadata']['uid'] != state['deployment_uid'] or template_hash(deployment) != state['template_hash']
            or current['metadata']['uid'] != before['metadata']['uid']
            or current['metadata']['resourceVersion'] != before['metadata']['resourceVersion']
            or current['data'][KEY] != before['data'][KEY]):
        raise RuntimeError('Configuration changed after planning; create a fresh plan.')
    validate_nginx(candidate)
    if candidate == before['data'][KEY]:
        effective_ok = True
        for pod in prepared_pods(DEPLOYMENT, 'edge'):
            effective = kubectl('exec', pod['metadata']['name'], '-c', 'edge', '--', 'nginx', '-T')
            _, additions = candidate_config(effective)
            effective_ok = effective_ok and additions == 0
        if effective_ok:
            state['stage'] = 'already-protected'
            write_json(directory / 'state.json', state)
            print('ALREADY_PROTECTED: both pods have the public denials; no restart required.')
            return
    else:
        patch_config(current, candidate, directory)
    state['stage'] = 'config-updated-refresh-pending'
    write_json(directory / 'state.json', state)
    try:
        refresh_edge(state, expected_config=candidate)
        for pod in prepared_pods(DEPLOYMENT, 'edge'):
            effective = kubectl('exec', pod['metadata']['name'], '-c', 'edge', '--', 'nginx', '-T')
            _, count = candidate_config(effective)
            if count:
                raise RuntimeError('New public edge does not contain all four admin denials.')
    except Exception:
        try:
            rollback(directory, state)
            print('Refresh failed; original policy restored.', file=sys.stderr)
        except Exception:
            print('Recovery incomplete; keep this work directory and inspect pods before retrying.', file=sys.stderr)
        raise
    state['stage'] = 'applied-needs-http-tests'
    write_json(directory / 'state.json', state)
    print('APPLIED: four public admin denials verified; two public edges Ready.')
    print('Verify public customer/ready 200, public admin 404, private-admin login/data and a denied PC using a fresh connection.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('plan', 'apply', 'status', 'rollback'))
    parser.add_argument('--work-dir', type=Path)
    args = parser.parse_args()
    if sys.platform != 'linux':
        parser.error('Run this tool in the PC1 Ubuntu VM, not Windows.')
    os.umask(0o077)
    if args.action == 'plan':
        directory = args.work_dir or Path.home() / '.local/state/telecom-public-admin-guard' / (time.strftime('%Y%m%d-%H%M%S-') + uuid.uuid4().hex[:8])
        plan(directory)
        return
    if not args.work_dir:
        pointer = Path.home() / '.telecom-public-admin-guard-workdir'
        if not pointer.is_file():
            parser.error('Run plan successfully first, or provide --work-dir.')
        args.work_dir = Path(pointer.read_text().strip())
    directory = args.work_dir.resolve()
    state = load_state(directory)
    if args.action == 'apply':
        apply(directory)
    elif args.action == 'rollback':
        rollback(directory, state)
        print('ROLLED BACK: pre-change public configuration restored; admin may be open again.')
    else:
        current = get('configmap', CONFIGMAP)
        print('Stage:', state['stage'])
        print('Config matches candidate:', current['data'][KEY] == read_config(directory / 'candidate.conf'))
        print('Ready public edge pods:', sum(ready(pod, 'edge') for pod in pods(DEPLOYMENT)))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(type(error).__name__ + ': ' + str(error), file=sys.stderr)
        raise SystemExit(1)
