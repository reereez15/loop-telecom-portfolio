-- 05_membership_upgrades.sql — 멤버십 등급 직접 구매(업그레이드) 테이블 추가
-- Alembic Migration a1f5c9e2b4d7 와 동일한 내용의 수동 적용용 SQL.
-- `flask db upgrade` 를 쓸 수 있으면 그쪽을 우선 사용하고, 이 파일은 Python 환경 없이
-- PC1/PC2 등 공용 DB에 바로 적용해야 할 때만 쓴다. (04_host_additive_update.sql 과 같은 방식: 기존 데이터는 건드리지 않고 추가만)
--
-- 실행 전 alembic_version 이 6ddf5e18b8f4 인지 확인:
--   SELECT version_num FROM alembic_version;
-- 실행(PowerShell):
--   Get-Content .\05_membership_upgrades.sql -Raw -Encoding UTF8 | docker exec -i <mysql 컨테이너명> mysql -uroot -p<비밀번호> --default-character-set=utf8mb4 <DB이름>

SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS membership_upgrades (
  id INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NOT NULL,
  from_tier_id INT NOT NULL,
  to_tier_id INT NOT NULL,
  amount INT NOT NULL,
  transaction_ref VARCHAR(64) NOT NULL,
  idempotency_key VARCHAR(64) NOT NULL,
  request_hash VARCHAR(64) NOT NULL,
  method VARCHAR(20) NOT NULL DEFAULT 'MOCK_CARD',
  status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
  pg_tid VARCHAR(64) NULL,
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL,
  CONSTRAINT uq_membership_upgrade_idem UNIQUE (user_id, idempotency_key),
  UNIQUE KEY (transaction_ref),
  UNIQUE KEY (pg_tid),
  KEY ix_membership_upgrades_user_id (user_id),
  CONSTRAINT fk_membership_upgrades_user FOREIGN KEY (user_id) REFERENCES users(id),
  CONSTRAINT fk_membership_upgrades_from_tier FOREIGN KEY (from_tier_id) REFERENCES membership_tiers(id),
  CONSTRAINT fk_membership_upgrades_to_tier FOREIGN KEY (to_tier_id) REFERENCES membership_tiers(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- alembic_version 을 Migration 체인과 맞춘다 (flask db upgrade 를 나중에 실행해도 중복 적용되지 않도록)
UPDATE alembic_version SET version_num = 'a1f5c9e2b4d7' WHERE version_num = '6ddf5e18b8f4';

-- 확인
SHOW TABLES LIKE 'membership_upgrades';
SELECT version_num FROM alembic_version;
