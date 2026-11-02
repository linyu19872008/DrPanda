#!/usr/bin/env bash
# 在 register_targets.sh 之后执行：登记 MySQL TLS 与 ES 多 host target，并给第二 ES 节点写数据。
set -euo pipefail
BASE="${DRPANDA_BASE_URL:-http://127.0.0.1:8111}"

post() {
  code=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$BASE/targets" "$@")
  if [ "$code" != "303" ]; then
    echo "target create failed: HTTP $code" >&2
    exit 1
  fi
}

CA="${DRPANDA_MYSQL_CERTS:-/tmp/drpanda-mysql-certs}/ca.pem"
post --data-urlencode type=mysql --data-urlencode name=drpanda-mysql-tls --data-urlencode enabled=on \
  --data-urlencode host=127.0.0.1 --data-urlencode port=13306 --data-urlencode user=drpanda_ro \
  --data-urlencode default_db=drpanda --data-urlencode allowed_dbs=drpanda --data-urlencode ssl=on \
  --data-urlencode "ca_pem@$CA" --data-urlencode secret_password=drpanda_mysql_ro_pw \
  --data-urlencode timeout_s=10 --data-urlencode max_rows=100 --data-urlencode max_bytes=102400

post --data-urlencode type=elasticsearch --data-urlencode name=drpanda-es-multi --data-urlencode enabled=on \
  --data-urlencode hosts=$'127.0.0.1:19200\n127.0.0.1:19201' --data-urlencode username=elastic \
  --data-urlencode allowed_indices=drpanda-logs --data-urlencode verify_tls=on \
  --data-urlencode secret_password=drpanda_es_pw \
  --data-urlencode timeout_s=10 --data-urlencode max_rows=100 --data-urlencode max_bytes=102400

# 第二 ES 节点索引
curl -fsS -u elastic:drpanda_es_pw -X PUT "http://127.0.0.1:19201/drpanda-logs" \
  -H 'Content-Type: application/json' \
  -d '{"mappings":{"properties":{"service":{"type":"keyword"},"message":{"type":"text"},"level":{"type":"keyword"},"ts":{"type":"date"}}}}' >/dev/null || true
curl -fsS -u elastic:drpanda_es_pw -X PUT "http://127.0.0.1:19201/drpanda-logs/_doc/1?refresh=true" \
  -H 'Content-Type: application/json' \
  -d '{"service":"order","level":"ERROR","message":"drpanda second host boom","ts":"2026-11-02T00:00:00Z"}' >/dev/null
curl -fsS -u elastic:drpanda_es_pw -X PUT "http://127.0.0.1:19201/drpanda-logs/_settings" \
  -H 'Content-Type: application/json' -d '{"index":{"number_of_replicas":0}}' >/dev/null
echo "P1 targets prepared"
