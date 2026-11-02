#!/usr/bin/env bash
# 本地联调数据（ES / Redis / Rabbit）；MySQL/Mongo 由 compose init 脚本完成。
set -euo pipefail

ES_AUTH="elastic:drpanda_es_pw"
ES_URL="http://127.0.0.1:19200"

curl -fsS -u "$ES_AUTH" -X PUT "$ES_URL/drpanda-logs" \
  -H 'Content-Type: application/json' \
  -d '{"mappings":{"properties":{"service":{"type":"keyword"},"message":{"type":"text"},"level":{"type":"keyword"},"ts":{"type":"date"}}}}' >/dev/null || true
curl -fsS -u "$ES_AUTH" -X PUT "$ES_URL/drpanda-logs/_settings" \
  -H 'Content-Type: application/json' -d '{"index":{"number_of_replicas":0}}' >/dev/null
for port in 19200 19201; do
  curl -fsS -u "$ES_AUTH" -X POST "http://127.0.0.1:$port/drpanda-logs/_doc/1?refresh=true" \
    -H 'Content-Type: application/json' \
    -d '{"service":"order","level":"ERROR","message":"drpanda integration boom","ts":"2026-11-02T00:00:00Z"}' >/dev/null || true
done

docker exec drpanda-redis redis-cli -a drpanda_redis_pw SET drpanda:order:1 '{"status":"paid"}' >/dev/null
docker exec drpanda-redis redis-cli -a drpanda_redis_pw SET drpanda:order:2 '{"status":"refunded"}' >/dev/null

curl -fsS -u drpanda:drpanda_rabbit_pw -X PUT \
  "http://127.0.0.1:15673/api/queues/%2F/drpanda-orders" \
  -H 'Content-Type: application/json' -d '{"durable":true,"arguments":{}}' >/dev/null
