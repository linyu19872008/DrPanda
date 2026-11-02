#!/usr/bin/env bash
# 在应用未设置全局 SSL_CERT_FILE 的情况下，登记 target 级 CA 案例。
set -euo pipefail
BASE="${DRPANDA_BASE_URL:-http://127.0.0.1:8111}"
CA="${DRPANDA_MYSQL_CERTS:-/tmp/drpanda-mysql-certs}/ca.pem"

post() {
  code=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$BASE/targets" "$@")
  if [ "$code" != "303" ]; then
    echo "target create failed: HTTP $code" >&2
    exit 1
  fi
}

# MySQL：有 CA / 无 CA
post --data-urlencode type=mysql --data-urlencode name=drpanda-mysql-ca --data-urlencode enabled=on \
  --data-urlencode host=127.0.0.1 --data-urlencode port=13306 --data-urlencode user=drpanda_ro \
  --data-urlencode default_db=drpanda --data-urlencode allowed_dbs=drpanda --data-urlencode ssl=on \
  --data-urlencode "ca_pem@$CA" --data-urlencode secret_password=drpanda_mysql_ro_pw \
  --data-urlencode timeout_s=10 --data-urlencode max_rows=100 --data-urlencode max_bytes=102400
post --data-urlencode type=mysql --data-urlencode name=drpanda-mysql-noca --data-urlencode enabled=on \
  --data-urlencode host=127.0.0.1 --data-urlencode port=13306 --data-urlencode user=drpanda_ro \
  --data-urlencode default_db=drpanda --data-urlencode allowed_dbs=drpanda --data-urlencode ssl=on \
  --data-urlencode secret_password=drpanda_mysql_ro_pw \
  --data-urlencode timeout_s=5 --data-urlencode max_rows=100 --data-urlencode max_bytes=102400

# TLS Elasticsearch：有 CA / 无 CA
curl -fsS --cacert "$CA" -u elastic:drpanda_es_pw -X PUT "https://127.0.0.1:19202/drpanda-logs" \
  -H 'Content-Type: application/json' \
  -d '{"mappings":{"properties":{"service":{"type":"keyword"},"message":{"type":"text"},"level":{"type":"keyword"},"ts":{"type":"date"}}}}' >/dev/null || true
curl -fsS --cacert "$CA" -u elastic:drpanda_es_pw -X PUT "https://127.0.0.1:19202/drpanda-logs/_doc/1?refresh=true" \
  -H 'Content-Type: application/json' \
  -d '{"service":"order","level":"ERROR","message":"drpanda tls target boom","ts":"2026-11-02T00:00:00Z"}' >/dev/null
curl -fsS --cacert "$CA" -u elastic:drpanda_es_pw -X PUT "https://127.0.0.1:19202/drpanda-logs/_settings" \
  -H 'Content-Type: application/json' -d '{"index":{"number_of_replicas":0}}' >/dev/null

post --data-urlencode type=elasticsearch --data-urlencode name=drpanda-es-tls --data-urlencode enabled=on \
  --data-urlencode hosts=https://127.0.0.1:19202 --data-urlencode username=elastic \
  --data-urlencode allowed_indices=drpanda-logs --data-urlencode verify_tls=on \
  --data-urlencode "ca_pem@$CA" --data-urlencode secret_password=drpanda_es_pw \
  --data-urlencode timeout_s=10 --data-urlencode max_rows=100 --data-urlencode max_bytes=102400
post --data-urlencode type=elasticsearch --data-urlencode name=drpanda-es-noca --data-urlencode enabled=on \
  --data-urlencode hosts=https://127.0.0.1:19202 --data-urlencode username=elastic \
  --data-urlencode allowed_indices=drpanda-logs --data-urlencode verify_tls=on \
  --data-urlencode secret_password=drpanda_es_pw \
  --data-urlencode timeout_s=5 --data-urlencode max_rows=100 --data-urlencode max_bytes=102400

echo "target CA cases prepared"
