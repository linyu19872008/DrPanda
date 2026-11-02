#!/usr/bin/env bash
# mTLS：MySQL REQUIRE X509 + ES client_authentication=required。
# 前置：生成证书、启动 8 个容器、应用未设置全局 SSL_CERT_FILE。
set -euo pipefail
BASE="${DRPANDA_BASE_URL:-http://127.0.0.1:8111}"
DIR="${DRPANDA_MYSQL_CERTS:-/tmp/drpanda-mysql-certs}"

post() {
  code=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$BASE/targets" "$@")
  if [ "$code" != "303" ]; then
    echo "target create failed: HTTP $code" >&2
    exit 1
  fi
}

# ES mTLS 索引
curl -fsS --cacert "$DIR/ca.pem" --cert "$DIR/client-cert.pem" --key "$DIR/client-key.pem" \
  -u elastic:drpanda_es_pw -X PUT "https://127.0.0.1:19203/drpanda-logs" \
  -H 'Content-Type: application/json' \
  -d '{"mappings":{"properties":{"service":{"type":"keyword"},"message":{"type":"text"},"level":{"type":"keyword"},"ts":{"type":"date"}}}}' >/dev/null || true
curl -fsS --cacert "$DIR/ca.pem" --cert "$DIR/client-cert.pem" --key "$DIR/client-key.pem" \
  -u elastic:drpanda_es_pw -X PUT "https://127.0.0.1:19203/drpanda-logs/_doc/1?refresh=true" \
  -H 'Content-Type: application/json' \
  -d '{"service":"order","level":"ERROR","message":"drpanda mtls boom","ts":"2026-11-02T00:00:00Z"}' >/dev/null
curl -fsS --cacert "$DIR/ca.pem" --cert "$DIR/client-cert.pem" --key "$DIR/client-key.pem" \
  -u elastic:drpanda_es_pw -X PUT "https://127.0.0.1:19203/drpanda-logs/_settings" \
  -H 'Content-Type: application/json' -d '{"index":{"number_of_replicas":0}}' >/dev/null

# MySQL：mTLS 用户 REQUIRE X509；有客户端证书 / 无证书对照
post --data-urlencode type=mysql --data-urlencode name=drpanda-mysql-mtls --data-urlencode enabled=on \
  --data-urlencode host=127.0.0.1 --data-urlencode port=13306 --data-urlencode user=drpanda_mtls \
  --data-urlencode default_db=drpanda --data-urlencode allowed_dbs=drpanda --data-urlencode ssl=on \
  --data-urlencode "ca_pem@$DIR/ca.pem" \
  --data-urlencode "secret_client_cert@$DIR/client-cert.pem" \
  --data-urlencode "secret_client_key@$DIR/client-key.pem" \
  --data-urlencode secret_password=drpanda_mtls_pw \
  --data-urlencode timeout_s=10 --data-urlencode max_rows=100 --data-urlencode max_bytes=102400
post --data-urlencode type=mysql --data-urlencode name=drpanda-mysql-mtls-nocert --data-urlencode enabled=on \
  --data-urlencode host=127.0.0.1 --data-urlencode port=13306 --data-urlencode user=drpanda_mtls \
  --data-urlencode default_db=drpanda --data-urlencode allowed_dbs=drpanda --data-urlencode ssl=on \
  --data-urlencode "ca_pem@$DIR/ca.pem" \
  --data-urlencode secret_password=drpanda_mtls_pw \
  --data-urlencode timeout_s=5 --data-urlencode max_rows=100 --data-urlencode max_bytes=102400

# ES：mTLS 有客户端证书 / 无证书对照
post --data-urlencode type=elasticsearch --data-urlencode name=drpanda-es-mtls --data-urlencode enabled=on \
  --data-urlencode hosts=https://127.0.0.1:19203 --data-urlencode username=elastic \
  --data-urlencode allowed_indices=drpanda-logs --data-urlencode verify_tls=on \
  --data-urlencode "ca_pem@$DIR/ca.pem" \
  --data-urlencode "secret_client_cert@$DIR/client-cert.pem" \
  --data-urlencode "secret_client_key@$DIR/client-key.pem" \
  --data-urlencode secret_password=drpanda_es_pw \
  --data-urlencode timeout_s=10 --data-urlencode max_rows=100 --data-urlencode max_bytes=102400
post --data-urlencode type=elasticsearch --data-urlencode name=drpanda-es-mtls-nocert --data-urlencode enabled=on \
  --data-urlencode hosts=https://127.0.0.1:19203 --data-urlencode username=elastic \
  --data-urlencode allowed_indices=drpanda-logs --data-urlencode verify_tls=on \
  --data-urlencode "ca_pem@$DIR/ca.pem" \
  --data-urlencode secret_password=drpanda_es_pw \
  --data-urlencode timeout_s=5 --data-urlencode max_rows=100 --data-urlencode max_bytes=102400

echo "mTLS targets prepared"
