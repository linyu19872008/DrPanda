#!/usr/bin/env bash
# 在运行中的本地服务上登记联调 target（默认 8111）。
set -euo pipefail
BASE="${DRPANDA_BASE_URL:-http://127.0.0.1:8111}"

post() {
  code=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$BASE/targets" "$@")
  if [ "$code" != "303" ]; then
    echo "target create failed: HTTP $code" >&2
    exit 1
  fi
}

post --data-urlencode type=mysql --data-urlencode name=drpanda-mysql --data-urlencode enabled=on \
  --data-urlencode host=127.0.0.1 --data-urlencode port=13306 --data-urlencode user=drpanda_ro \
  --data-urlencode default_db=drpanda --data-urlencode allowed_dbs=drpanda \
  --data-urlencode secret_password=drpanda_mysql_ro_pw \
  --data-urlencode timeout_s=10 --data-urlencode max_rows=100 --data-urlencode max_bytes=102400
post --data-urlencode type=mongo --data-urlencode name=drpanda-mongo --data-urlencode enabled=on \
  --data-urlencode host=127.0.0.1 --data-urlencode port=17017 --data-urlencode user=drpanda_ro \
  --data-urlencode auth_source=drpanda --data-urlencode allowed_dbs=drpanda \
  --data-urlencode secret_password=drpanda_mongo_ro_pw \
  --data-urlencode timeout_s=10 --data-urlencode max_rows=100 --data-urlencode max_bytes=102400
post --data-urlencode type=elasticsearch --data-urlencode name=drpanda-es --data-urlencode enabled=on \
  --data-urlencode hosts=127.0.0.1:19200 --data-urlencode username=elastic \
  --data-urlencode allowed_indices=drpanda-logs --data-urlencode verify_tls=on \
  --data-urlencode secret_password=drpanda_es_pw \
  --data-urlencode timeout_s=10 --data-urlencode max_rows=100 --data-urlencode max_bytes=102400
post --data-urlencode type=redis --data-urlencode name=drpanda-redis --data-urlencode enabled=on \
  --data-urlencode host=127.0.0.1 --data-urlencode port=16379 --data-urlencode db=0 \
  --data-urlencode key_prefix=drpanda: --data-urlencode secret_password=drpanda_redis_pw \
  --data-urlencode timeout_s=10 --data-urlencode max_rows=100 --data-urlencode max_bytes=102400
post --data-urlencode type=rabbitmq --data-urlencode name=drpanda-rabbit --data-urlencode enabled=on \
  --data-urlencode management_url=http://127.0.0.1:15673 --data-urlencode user=drpanda \
  --data-urlencode allowed_vhosts=/ --data-urlencode secret_password=drpanda_rabbit_pw \
  --data-urlencode timeout_s=10 --data-urlencode max_rows=100 --data-urlencode max_bytes=102400
post --data-urlencode type=mysql --data-urlencode name=drpanda-mysql-small --data-urlencode enabled=on \
  --data-urlencode host=127.0.0.1 --data-urlencode port=13306 --data-urlencode user=drpanda_ro \
  --data-urlencode default_db=drpanda --data-urlencode allowed_dbs=drpanda \
  --data-urlencode secret_password=drpanda_mysql_ro_pw \
  --data-urlencode timeout_s=10 --data-urlencode max_rows=1 --data-urlencode max_bytes=102400

echo "registered 6 targets"
