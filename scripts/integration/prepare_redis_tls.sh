#!/usr/bin/env bash
# Redis ACL + TLS / mTLS 案例。前置：证书、redis-acl-tls/redis-acl-mtls 容器、应用未设置全局 SSL_CERT_FILE。
set -euo pipefail
BASE="${DRPANDA_BASE_URL:-http://127.0.0.1:8111}"
DIR="${DRPANDA_MYSQL_CERTS:-/tmp/drpanda-mysql-certs}"

docker exec drpanda-redis-acl-tls redis-cli -p 6380 --tls --cacert /certs/ca.pem \
  --user admin --pass drpanda_admin_pw SET drpanda:order:1 paid >/dev/null
docker exec drpanda-redis-acl-mtls redis-cli -p 6380 --tls --cacert /certs/ca.pem \
  --cert /certs/client.pem --key /certs/client-key.pem \
  --user admin --pass drpanda_admin_pw SET drpanda:order:1 paid >/dev/null

post() {
  code=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$BASE/targets" "$@")
  if [ "$code" != "303" ]; then
    echo "target create failed: HTTP $code" >&2
    exit 1
  fi
}

post --data-urlencode type=redis --data-urlencode name=drpanda-redis-acl-tls --data-urlencode enabled=on \
  --data-urlencode host=127.0.0.1 --data-urlencode port=16380 --data-urlencode db=0 \
  --data-urlencode username=drpanda --data-urlencode tls=on \
  --data-urlencode "ca_pem@$DIR/ca.pem" --data-urlencode key_prefix=drpanda: \
  --data-urlencode secret_password=drpanda_redis_pw \
  --data-urlencode timeout_s=10 --data-urlencode max_rows=100 --data-urlencode max_bytes=102400
post --data-urlencode type=redis --data-urlencode name=drpanda-redis-acl-mtls --data-urlencode enabled=on \
  --data-urlencode host=127.0.0.1 --data-urlencode port=16381 --data-urlencode db=0 \
  --data-urlencode username=drpanda --data-urlencode tls=on \
  --data-urlencode "ca_pem@$DIR/ca.pem" \
  --data-urlencode "secret_client_cert@$DIR/client-cert.pem" \
  --data-urlencode "secret_client_key@$DIR/client-key.pem" \
  --data-urlencode key_prefix=drpanda: --data-urlencode secret_password=drpanda_redis_pw \
  --data-urlencode timeout_s=10 --data-urlencode max_rows=100 --data-urlencode max_bytes=102400
post --data-urlencode type=redis --data-urlencode name=drpanda-redis-mtls-nocert --data-urlencode enabled=on \
  --data-urlencode host=127.0.0.1 --data-urlencode port=16381 --data-urlencode db=0 \
  --data-urlencode username=drpanda --data-urlencode tls=on \
  --data-urlencode "ca_pem@$DIR/ca.pem" --data-urlencode key_prefix=drpanda: \
  --data-urlencode secret_password=drpanda_redis_pw \
  --data-urlencode timeout_s=5 --data-urlencode max_rows=100 --data-urlencode max_bytes=102400

echo "Redis ACL/TLS cases prepared"
