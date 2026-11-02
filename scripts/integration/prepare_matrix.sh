#!/usr/bin/env bash
# 在 register_targets.sh 之后执行：扩展数据与 integration-02 所需 target。
# 仅用于本地 drpanda 联调栈。
set -euo pipefail
BASE="${DRPANDA_BASE_URL:-http://127.0.0.1:8111}"

post() {
  code=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$BASE/targets" "$@")
  if [ "$code" != "303" ]; then
    echo "target create failed: HTTP $code" >&2
    exit 1
  fi
}

# MySQL 第二库、视图、归档数据
docker exec drpanda-mysql mysql -uroot -pdrpanda_root_pw -e "
CREATE DATABASE IF NOT EXISTS drpanda_archive;
CREATE TABLE IF NOT EXISTS drpanda_archive.orders LIKE drpanda.orders;
INSERT INTO drpanda_archive.orders (status, amount, note)
SELECT 'paid', 7.00, 'archive order' FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM drpanda_archive.orders);
CREATE OR REPLACE VIEW drpanda.order_view AS SELECT id, status, amount FROM drpanda.orders;
" >/dev/null

# Mongo 额外集合
docker exec drpanda-mongo mongosh --quiet --username drpanda_root --password drpanda_root_pw --authenticationDatabase admin --eval '
db = db.getSiblingDB("drpanda");
if (!db.getCollectionNames().includes("drpanda_events")) { db.createCollection("drpanda_events"); }
if (db.drpanda_events.countDocuments() === 0) {
  db.drpanda_events.insertMany([{kind:"deploy", at:new Date("2026-11-02T00:00:00Z")},{kind:"error", at:new Date("2026-11-02T00:05:00Z")}]);
}
' >/dev/null

# ES nested / empty / 多文档
ES="curl -fsS -u elastic:drpanda_es_pw"
$ES -X PUT "http://127.0.0.1:19200/drpanda-nested" -H 'Content-Type: application/json' -d '{"mappings":{"properties":{"service":{"type":"keyword"},"payload":{"properties":{"code":{"type":"keyword"},"detail":{"type":"text"}}},"tags":{"type":"keyword"}}}}' >/dev/null || true
$ES -X PUT "http://127.0.0.1:19200/drpanda-nested/_doc/1?refresh=true" -H 'Content-Type: application/json' -d '{"service":"pay","payload":{"code":"E42","detail":"nested boom"},"tags":["a","b"]}' >/dev/null
$ES -X PUT "http://127.0.0.1:19200/drpanda-empty" -H 'Content-Type: application/json' -d '{"mappings":{"properties":{"x":{"type":"keyword"}}}}' >/dev/null || true
$ES -X PUT "http://127.0.0.1:19200/drpanda-nested/_settings" -H 'Content-Type: application/json' -d '{"index":{"number_of_replicas":0}}' >/dev/null || true
for i in 2 3 4 5; do
  $ES -X PUT "http://127.0.0.1:19200/drpanda-logs/_doc/$i?refresh=true" -H 'Content-Type: application/json' \
    -d "{\"service\":\"order\",\"level\":\"INFO\",\"message\":\"drpanda integration $i\",\"ts\":\"2026-11-02T00:0$i:00Z\"}" >/dev/null
done

# Redis 多类型、TTL、超大值、超长 list
python3 - <<'PY'
open('/tmp/drpanda-huge.txt','w').write('x'*200000)
PY
docker exec -i drpanda-redis redis-cli -a drpanda_redis_pw -x SET drpanda:huge < /tmp/drpanda-huge.txt >/dev/null
R="docker exec drpanda-redis redis-cli -a drpanda_redis_pw"
for key in drpanda:list drpanda:set drpanda:zset drpanda:hash drpanda:ttl drpanda:biglist; do $R DEL "$key" >/dev/null; done
for i in $(seq 1 5); do $R RPUSH drpanda:list "v$i" >/dev/null; done
for i in $(seq 1 5); do $R SADD drpanda:set "m$i" >/dev/null; done
for i in $(seq 1 5); do $R ZADD drpanda:zset "$i" "z$i" >/dev/null; done
$R HSET drpanda:hash f1 v1 f2 v2 >/dev/null
$R SET drpanda:ttl v EX 60 >/dev/null
for i in $(seq 1 101); do $R RPUSH drpanda:biglist "$i" >/dev/null; done
$R CONFIG SET slowlog-log-slower-than 0 >/dev/null
$R GET drpanda:order:1 >/dev/null
$R GET other:not-in-scope >/dev/null

# Rabbit 第二个 vhost、额外队列、2 条消息
curl -fsS -u drpanda:drpanda_rabbit_pw -X PUT "http://127.0.0.1:15673/api/vhosts/drpanda-extra" -H 'Content-Type: application/json' -d '{}' >/dev/null
curl -fsS -u drpanda:drpanda_rabbit_pw -X PUT "http://127.0.0.1:15673/api/queues/drpanda-extra/drpanda-extra-queue" -H 'Content-Type: application/json' -d '{"durable":true}' >/dev/null
for q in drpanda-q1 drpanda-q2 drpanda-q3; do
  curl -fsS -u drpanda:drpanda_rabbit_pw -X PUT "http://127.0.0.1:15673/api/queues/%2F/$q" -H 'Content-Type: application/json' -d '{"durable":true}' >/dev/null
done
curl -fsS -u drpanda:drpanda_rabbit_pw -X DELETE "http://127.0.0.1:15673/api/queues/%2F/drpanda-orders/contents" >/dev/null
for n in 1 2; do
  curl -fsS -u drpanda:drpanda_rabbit_pw -X POST "http://127.0.0.1:15673/api/exchanges/%2F/amq.default/publish" -H 'Content-Type: application/json' \
    -d "{\"properties\":{},\"routing_key\":\"drpanda-orders\",\"payload\":\"drpanda message $n\",\"payload_encoding\":\"string\"}" >/dev/null
done

# 扩展 target
post --data-urlencode type=mysql --data-urlencode name=drpanda-mysql-wide --data-urlencode enabled=on \
  --data-urlencode host=127.0.0.1 --data-urlencode port=13306 --data-urlencode user=drpanda_ro \
  --data-urlencode default_db=drpanda --data-urlencode allowed_dbs=$'drpanda\ndrpanda_archive' \
  --data-urlencode secret_password=drpanda_mysql_ro_pw \
  --data-urlencode timeout_s=10 --data-urlencode max_rows=100 --data-urlencode max_bytes=102400
post --data-urlencode type=elasticsearch --data-urlencode name=drpanda-es-wide --data-urlencode enabled=on \
  --data-urlencode hosts=127.0.0.1:19200 --data-urlencode username=elastic \
  --data-urlencode allowed_indices=$'drpanda-logs\ndrpanda-nested\ndrpanda-empty' --data-urlencode verify_tls=on \
  --data-urlencode secret_password=drpanda_es_pw \
  --data-urlencode timeout_s=10 --data-urlencode max_rows=100 --data-urlencode max_bytes=102400
post --data-urlencode type=redis --data-urlencode name=drpanda-redis-small --data-urlencode enabled=on \
  --data-urlencode host=127.0.0.1 --data-urlencode port=16379 --data-urlencode db=0 \
  --data-urlencode key_prefix=drpanda: --data-urlencode secret_password=drpanda_redis_pw \
  --data-urlencode timeout_s=10 --data-urlencode max_rows=2 --data-urlencode max_bytes=4096
post --data-urlencode type=rabbitmq --data-urlencode name=drpanda-rabbit-wide --data-urlencode enabled=on \
  --data-urlencode management_url=http://127.0.0.1:15673 --data-urlencode user=drpanda \
  --data-urlencode allowed_vhosts=$'/\ndrpanda-extra' --data-urlencode secret_password=drpanda_rabbit_pw \
  --data-urlencode timeout_s=10 --data-urlencode max_rows=100 --data-urlencode max_bytes=102400
post --data-urlencode type=rabbitmq --data-urlencode name=drpanda-rabbit-small --data-urlencode enabled=on \
  --data-urlencode management_url=http://127.0.0.1:15673 --data-urlencode user=drpanda \
  --data-urlencode allowed_vhosts=/ --data-urlencode secret_password=drpanda_rabbit_pw \
  --data-urlencode timeout_s=10 --data-urlencode max_rows=2 --data-urlencode max_bytes=4096
post --data-urlencode type=elasticsearch --data-urlencode name=drpanda-es-small --data-urlencode enabled=on \
  --data-urlencode hosts=127.0.0.1:19200 --data-urlencode username=elastic \
  --data-urlencode allowed_indices=drpanda-logs --data-urlencode verify_tls=on \
  --data-urlencode secret_password=drpanda_es_pw \
  --data-urlencode timeout_s=10 --data-urlencode max_rows=2 --data-urlencode max_bytes=4096
post --data-urlencode type=mongo --data-urlencode name=drpanda-mongo-small --data-urlencode enabled=on \
  --data-urlencode host=127.0.0.1 --data-urlencode port=17017 --data-urlencode user=drpanda_ro \
  --data-urlencode auth_source=drpanda --data-urlencode allowed_dbs=drpanda \
  --data-urlencode secret_password=drpanda_mongo_ro_pw \
  --data-urlencode timeout_s=10 --data-urlencode max_rows=2 --data-urlencode max_bytes=4096
# 错误凭证 target（验证错误映射）；Redis 超时设 10 秒，避免整调用超时掩盖认证错误
post --data-urlencode type=mysql --data-urlencode name=drpanda-mysql-bad --data-urlencode enabled=on \
  --data-urlencode host=127.0.0.1 --data-urlencode port=13306 --data-urlencode user=drpanda_ro \
  --data-urlencode default_db=drpanda --data-urlencode allowed_dbs=drpanda --data-urlencode secret_password=wrong \
  --data-urlencode timeout_s=3 --data-urlencode max_rows=10 --data-urlencode max_bytes=4096
post --data-urlencode type=mongo --data-urlencode name=drpanda-mongo-bad --data-urlencode enabled=on \
  --data-urlencode host=127.0.0.1 --data-urlencode port=17017 --data-urlencode user=drpanda_ro \
  --data-urlencode auth_source=drpanda --data-urlencode allowed_dbs=drpanda --data-urlencode secret_password=wrong \
  --data-urlencode timeout_s=3 --data-urlencode max_rows=10 --data-urlencode max_bytes=4096
post --data-urlencode type=elasticsearch --data-urlencode name=drpanda-es-bad --data-urlencode enabled=on \
  --data-urlencode hosts=127.0.0.1:19200 --data-urlencode username=elastic --data-urlencode allowed_indices=drpanda-logs \
  --data-urlencode verify_tls=on --data-urlencode secret_password=wrong \
  --data-urlencode timeout_s=3 --data-urlencode max_rows=10 --data-urlencode max_bytes=4096
post --data-urlencode type=redis --data-urlencode name=drpanda-redis-bad --data-urlencode enabled=on \
  --data-urlencode host=127.0.0.1 --data-urlencode port=16379 --data-urlencode db=0 --data-urlencode key_prefix=drpanda: \
  --data-urlencode secret_password=wrong --data-urlencode timeout_s=10 --data-urlencode max_rows=10 --data-urlencode max_bytes=4096
post --data-urlencode type=rabbitmq --data-urlencode name=drpanda-rabbit-bad --data-urlencode enabled=on \
  --data-urlencode management_url=http://127.0.0.1:15673 --data-urlencode user=drpanda \
  --data-urlencode allowed_vhosts=/ --data-urlencode secret_password=wrong \
  --data-urlencode timeout_s=3 --data-urlencode max_rows=10 --data-urlencode max_bytes=4096

echo "matrix data and targets prepared"
