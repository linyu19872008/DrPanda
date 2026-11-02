CREATE DATABASE IF NOT EXISTS drpanda CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE drpanda;
CREATE TABLE IF NOT EXISTS orders (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  status VARCHAR(32) NOT NULL,
  amount DECIMAL(10,2) NOT NULL,
  note VARCHAR(255) NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
INSERT INTO orders (status, amount, note) VALUES
  ('paid', 12.50, 'drpanda integration order 1'),
  ('paid', 99.00, 'drpanda integration order 2'),
  ('refunded', 5.25, 'drpanda integration order 3');
CREATE USER IF NOT EXISTS 'drpanda_ro'@'%' IDENTIFIED BY 'drpanda_mysql_ro_pw';
GRANT SELECT, SHOW VIEW, PROCESS ON *.* TO 'drpanda_ro'@'%';
CREATE USER IF NOT EXISTS 'drpanda_mtls'@'%' IDENTIFIED BY 'drpanda_mtls_pw' REQUIRE X509;
GRANT SELECT, SHOW VIEW, PROCESS ON *.* TO 'drpanda_mtls'@'%';
FLUSH PRIVILEGES;
