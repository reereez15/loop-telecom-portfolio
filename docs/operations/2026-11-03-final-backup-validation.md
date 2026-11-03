# 2026-11-03 최종 배포·DB·백업 검증 기록

## 기준과 확인 범위

- 사용자가 전달한 실행 화면을 근거로 기록했다. 에이전트가 학원 서버에서 직접 실행한 결과는 아니다.
- PC2 Windows의 mysql-lab은 Primary(server_id=2, read_only=0, super_read_only=0).
- PC1 Windows의 flask_mysql은 Replica(server_id=1, read_only=1, super_read_only=1).
- PC1 Ubuntu는 단일 k3s control plane 및 worker, PC2 Ubuntu는 worker.
- 서비스 입구는 https://192.168.3.30 이며 기존 PC1 VM 장애 대응 시험은 완료했다고 사용자에게 확인받았다.
- 다른 담당자의 연동은 사용자가 완료했다고 전달했다. 이 기록에서 해당 연동 전체를 새로 검증했다고 주장하지 않는다.

## 최종 배포 및 API

- 두 노드 Ready, 관련 Deployment 2/2, 웹·API·edge의 양쪽 노드 배치 확인.
- 첨부된 이미지 가져오기 검증 결과는 backend/frontend 및 archive SHA256 PASS.
- 두 API가 192.168.3.19의 my_new_board_db에 webuser로 접속함을 실제 쿼리로 확인.
- DB 조회 결과는 server_id=2, read_only=0, super_read_only=0.
- 비로그인 HTTP 시험: /api/health/ready=200, /api/admin/dashboard=401, 공개 /api/internal/privilege-violations=404.
- 최종 배포의 전체 verify 출력과 소스 커밋은 이번 첨부에서 별도로 확인하지 못했다. 과거 배포 커밋을 현재 최종본으로 단정하지 않는다.
- ADMIN 인증 후 조회 200, CUSTOMER 관리자 API 403의 최종 증거는 별도 확인 항목이다. 관리자 공지 등록 성공은 웹 쓰기 증거이나 모든 관리자 경로의 권한 검증을 대신하지 않는다.

## GTID 및 웹 쓰기

- 안내 문자열을 실제 GTID 대신 입력해 ERROR 1772가 발생했다. 실제 GTID 전체를 넣어 해결했다.
- PC2 체크포인트는 기존 PC1 UUID의 1-298과 PC2 UUID의 1-26741로 구성됐다.
- PC1에서 WAIT_FOR_EXECUTED_GTID_SET 결과 0, missing_gtids 빈 문자열, Replica 읽기 전용 상태 확인.
- 공지 등록 전 제목 조회가 Empty set으로 나왔다. 공지 작성 후 FINAL-CHECK-20261103-01 조회 성공 화면을 받았다.
- 한쪽 조회 화면만으로 양쪽 행 존재를 단정하지 않는다. PC1·PC2 동일 공지 조회 결과는 최종 증거에 함께 보관한다.

## 정상 예약 백업 및 격리 복원

- PC2 Primary용 실제 Task Scheduler 실행 시험 성공, LastTaskResult=0, last-run/last-success=success.
- 2026-11-03 10:26 KST에 생성한 백업으로 격리 복원 수행.
- 26개 테이블 CHECK TABLE 통과, 행 수 기록, latest.json Stage=restore-verified 확인.
- 시험용 컨테이너만 종료했으며 운영 컨테이너와 원본 볼륨은 유지했다.
- 정상 알림 시험에서 Discord TEST 메시지 수신 화면 확인.
- 감시 CHECK: healthy; delivery=not-needed; issues= 및 Primary 두 작업 Ready 확인.
- 기존 Replica용 예약 백업·감시는 Disabled 유지.

## 의도한 백업 실패와 권한 오류

- 운영 DB를 종료하지 않고 저장된 백업 인증 파일을 잠시 이름 변경해 백업 worker 실패를 발생시켰다.
- 예약 작업 Disable/Enable에서 0x80070005 액세스 거부가 발생했다. 이는 의도한 백업 실패와 별개의 운영 권한 오류다.
- 당시 완료 문구만으로 예약 작업 재개 성공을 판단할 수 없었다.
- 실패 레코드 Status=failed, ExitCode=1과 감시 issues=backup-failed, delivery=confirmed를 확인했다.
- 같은 장애를 재확인한 결과 delivery=not-needed는 중복 전송 억제다.
- 실패 시험 절차에는 관리자 권한 사전 확인, 동일 Windows 계정 사용, 작업 변경에 -ErrorAction Stop 적용, 인증 파일 복구와 실제 예약 상태 확인이 필요하다.

## 복구 확인

- 관리자 PowerShell에서 백업 인증 파일 존재와 Primary 백업·감시 작업 Ready 확인.
- 2026-11-03 10:46 KST 정상 예약 백업 재실행 성공, LastTaskResult=0, last-run/last-success=success.
- 후속 감시 결과 CHECK: healthy; delivery=confirmed; issues= 확인.
- 도구에서 복구 알림 전송 성공을 확인했으며 Discord 복구 메시지 실제 수신 화면은 최종 증거에 추가한다.
- 이전에 수행한 격리 복원은 10:26 백업 대상이다. 10:46 신규 백업을 별도로 복원 검증했다고 기록하지 않는다.

## 후속 시연과 남은 확인

- [제한된 부하와 웹 장애 전환 시연](../runbooks/controlled-web-failover-demo.md)은 실행 계획이며 아직 이번 절차로 시연한 결과가 아니다.
- CPU 계산 부하, 소량 TCP 시험 트래픽, 운영자가 명시적으로 수행하는 VM 정상 종료를 구분한다. 실제 DDoS 성공으로 표현하지 않는다.
- PC1 VM 종료는 PC1 Windows 전체 장애가 아니다. Windows Graylog 및 DB Replica가 함께 종료됐다고 설명하지 않는다.
- PC1 control plane, PC3 pfSense/HAProxy는 단일 지점이고 DB 승격은 수동이다. 전체 시스템의 완전 자동 고가용성 완료로 확대 해석하지 않는다.
- 남은 증거: 최종 커밋 verify, 계정별 API 200/403, 양쪽 공지 조회, Discord 복구 메시지, Zabbix의 해당 VM 대상 장애/복구 관측.
