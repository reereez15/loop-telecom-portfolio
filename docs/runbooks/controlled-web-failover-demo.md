# 제한된 부하와 웹 장애 전환 시연

## 시연의 의미

PC1 Ubuntu VM에 제한된 CPU 부하와 소량 TCP SYN 시험 트래픽을 발생시키고, 운영자가 VM을 정상 종료하여 PC2 웹 경로 유지와 복구를 관측한다. 부하가 실제 VM 장애를 일으켰다는 시험이 아니며 실제 DDoS 재현으로 설명하지 않는다.

대상은 팀이 관리하는 PC1 VM(192.168.7.185) 하나다. 학원 공용 장비·다른 사용자 PC는 대상에 포함하지 않는다. PC1 Windows와 PC2 Windows의 DB는 실행 상태를 유지한다. 다른 담당자에게 시험 시간과 모의 장애 발생을 공유한 뒤 진행한다.

## 시작 조건

- PC1·PC2 노드 및 웹/API/edge/CoreDNS가 정상이고 HAProxy 두 백엔드 UP.
- API가 PC2 Primary에 webuser로 연결되며 최근 정상 백업이 존재.
- edge는 노드별 API/web Local Service를 사용. 공개 /api/internal 차단 유지.
- Zabbix의 PC1 항목이 Windows 호스트가 아니라 Ubuntu VM을 관측하는지 확인.
- PC1 VM의 VMware 콘솔을 열어 종료 후 다시 켤 수 있어야 함.
- CPU 부하 시간은 최대 120초, 작업은 최대 2개, 각 작업 목표 부하는 최대 70%. 시스템 전체 사용률을 정확히 보장하지 않는다.

## 1. 화면 배치 및 기준 상태

PC3에서 HAProxy Stats와 Zabbix PC1 Ubuntu VM의 CPU·가용성 화면을 준비한다. 다른 시험 PC에서 https://192.168.3.30 과 개발자 도구 Network를 준비한다.

PC1 Ubuntu에서 확인:

```bash
hostname
sudo k3s kubectl get nodes -o wide
sudo k3s kubectl -n telecom get deployments
```

## 2. 외부 Windows 시험 PC에서 웹 확인 반복

아래 PowerShell은 90회, 약 90초 이상 실행하며 결과를 CSV로 저장한다. 시간 초과가 있으면 그 시간만큼 전체 실행이 길어진다. HTTP=000 또는 비정상 상태도 그대로 기록한다.

```powershell
$loopResults = foreach ($loopIndex in 1..90) {
    $loopStart = Get-Date
    $loopTimer = [Diagnostics.Stopwatch]::StartNew()
    $loopHttp = curl.exe --noproxy "*" --ssl-revoke-best-effort --connect-timeout 2 --max-time 5 -sS -o NUL -w "%{http_code}" 'https://192.168.3.30/api/health/ready'
    $loopExit = $LASTEXITCODE
    $loopTimer.Stop()
    Write-Host "$($loopStart.ToString('HH:mm:ss')) 요청=$loopIndex HTTP=$loopHttp curl=$loopExit"
    [pscustomobject]@{Time=$loopStart.ToString('o'); Request=$loopIndex; HTTP="$loopHttp"; CurlExit=$loopExit; Seconds=[Math]::Round($loopTimer.Elapsed.TotalSeconds,3)}
    Start-Sleep -Seconds 1
}
$loopCsv = Join-Path $env:USERPROFILE ('Downloads/web-demo-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.csv')
$loopResults | Export-Csv -LiteralPath $loopCsv -NoTypeInformation -Encoding UTF8
$loopResults | Group-Object HTTP,CurlExit | Select-Object Name,Count
Write-Host "결과 저장: $loopCsv"
```

## 3. PC1 Ubuntu에서 CPU 부하

[cpu-load-demo.py](../../infrastructure/tools/cpu-load-demo.py)를 PC1 Ubuntu 홈 폴더에 저장한 뒤 실행한다. 파일은 Python 표준 라이브러리만 사용한다.

```bash
python3 "$HOME/cpu-load-demo.py" --seconds 90 --load 60
```

Ctrl+C로 종료할 수 있다. 파일은 메모리 고갈이나 자동 시스템 종료를 수행하지 않는다. Zabbix CPU 그래프는 설정된 수집 간격만큼 지연될 수 있다.

## 4. Kali에서 소량 TCP 시험 트래픽

먼저 팀 VM으로 향하는 경로를 확인한다.

```bash
ip route get 192.168.7.185
```

```bash
sudo hping3 -S -p 30443 -c 30 -i 1 192.168.7.185
```

1초 간격 총 30개 TCP SYN이다. flood·주소 위조·무제한 전송은 사용하지 않는다. 이 트래픽만으로 VM이 중단되거나 Zabbix 네트워크 그래프가 크게 올라갈 것을 기대하지 않는다. SYN-ACK/SA가 오면 해당 TCP 포트 응답을 뜻하며 HTTPS 성공 증거는 아니다. 실패하거나 경로가 없으면 공용 게이트웨이 경로를 임의로 바꾸지 말고 기존 팀 네트워크 경로를 확인한다.

VM 주소로 직접 보내므로 pfSense를 경유하지 않을 수 있다. pfSense Suricata 탐지까지 이 시험의 성공 항목으로 간주하지 않는다. pfSense/HAProxy는 공개 웹 확인 요청의 실제 경로에서 관측한다.

## 5. PC1 Ubuntu VM을 명시적으로 종료

CPU 부하를 띄운 창과 별도의 PC1 Ubuntu 터미널에서 실행한다. hostname이 pc1-k3s인지 반드시 확인한다.

```bash
hostname
date -Is
sudo shutdown -h now
```

이는 운영자가 수행하는 모의 장애다. SSH 연결이 끊기고 PC1 Ubuntu VM만 종료된다. 단일 control plane도 같이 내려가므로 장애 중 kubectl 조회 성공을 요구하지 않는다.

## 6. 관측 및 복구

- HAProxy pc1-web이 DOWN으로 바뀌고 pc2-web은 UP인 화면을 촬영한다. MAINT로 수동 제외한 경우와 구분한다.
- 반복 요청 결과와 브라우저 새로고침으로 웹 유지 여부를 확인한다. 실패가 있으면 삭제하지 않고 건수·시간을 기록한다.
- Zabbix에서 Ubuntu VM unavailable 또는 해당 트리거를 확인한다. 갱신/장애 판정 간격만큼 지연될 수 있다. 기록이 나타나지 않으면 트리거와 대상 설정을 별도로 확인한다.
- 브라우저 자체가 자동으로 DOWN 화면을 보여주는 것은 아니다. HAProxy Stats 또는 Zabbix가 서버 DOWN을 표시하고, 서비스 웹은 계속 열리는 장면을 보여준다.
- VMware에서 PC1 VM을 켠다. 부팅 후 아래를 실행하고 HAProxy 두 노드 UP을 확인한다.

```bash
sudo systemctl start k3s
sudo k3s kubectl get nodes -o wide
sudo k3s kubectl -n telecom get deployments
```

## 발표 문구

“실제 DDoS 대신 제한된 계산 부하와 TCP 시험 트래픽을 발생시켰습니다. 이후 PC1 Ubuntu VM을 정상 종료해 장애를 모의했습니다. HAProxy가 PC1을 자동 제외한 동안 PC2 웹 경로와 PC2 Primary DB로 서비스가 유지되는지 확인했습니다.”

PC1 전체 물리 장비 장애, DB 자동 승격, 관제 전체 고가용성을 입증한 시험으로 설명하지 않는다. 11월 3일 실행 결과는 [검증 기록](../operations/2026-11-03-final-backup-validation.md)에 확인된 범위만 추가한다.

참고: [Kali hping3 옵션](https://www.kali.org/tools/hping3/), [Python multiprocessing](https://docs.python.org/3.12/library/multiprocessing.html).
