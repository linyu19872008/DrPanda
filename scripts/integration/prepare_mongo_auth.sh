#!/usr/bin/env bash
# Mongo 认证模式：无认证 / 密码 / URI / TLS。
set -euo pipefail
BASE="${DRPANDA_BASE_URL:-http://127.0.0.1:8111}"
DIR="${DRPANDA_MYSQL_CERTS:-/tmp/drpanda-mysql-certs}"

# TLS Mongo 种子数据
docker exec drpanda-mongo-tls mongosh --quiet --tls --tlsCAFile /certs/ca.pem --eval '
db = db.getSiblingDB("drpanda");
if (!db.getCollectionNames().includes("drpanda_orders")) { db.createCollection("drpanda_orders"); }
if (db.drpanda_orders.countDocuments() === 0) {
  db.drpanda_orders.insertMany([{order_id:"T-1001", status:"paid"}, {order_id:"T-1002", status:"refunded"}]);
}
' >/dev/null

post() {
  code=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$BASE/targets" "$@")
  if [ "$code" != "303" ]; then
    echo "target create failed: HTTP $code" >&2
    exit 1
  fi
}

post --data-urlencode type=mongo --data-urlencode name=drpanda-mongo-noauth --data-urlencode enabled=on \
  --data-urlencode auth_mode=none --data-urlencode host=127.0.0.1 --data-urlencode port=17018 \
  --data-urlencode allowed_dbs=drpanda \
  --data-urlencode timeout_s=10 --data-urlencode max_rows=100 --data-urlencode max_bytes=102400
post --data-urlencode type=mongo --data-urlencode name=drpanda-mongo-uri --data-urlencode enabled=on \
  --data-urlencode auth_mode=uri \
  --data-urlencode "secret_uri=mongodb://drpanda_ro:drpanda_mongo_ro_pw@127.0.0.1:17017/?authSource=drpanda" \
  --data-urlencode allowed_dbs=drpanda \
  --data-urlencode timeout_s=10 --data-urlencode max_rows=100 --data-urlencode max_bytes=102400
post --data-urlencode type=mongo --data-urlencode name=drpanda-mongo-tls --data-urlencode enabled=on \
  --data-urlencode auth_mode=none --data-urlencode host=127.0.0.1 --data-urlencode port=17019 \
  --data-urlencode tls=on --data-urlencode "ca_pem@$DIR/ca.pem" --data-urlencode allowed_dbs=drpanda \
  --data-urlencode timeout_s=10 --data-urlencode max_rows=100 --data-urlencode max_bytes=102400
docker exec drpanda-mongo-mtls mongosh --quiet --tls --tlsCAFile /certs/ca.pem --tlsCertificateKeyFile /certs/client.pem --eval '
db = db.getSiblingDB("drpanda");
if (!db.getCollectionNames().includes("drpanda_orders")) { db.createCollection("drpanda_orders"); }
if (db.drpanda_orders.countDocuments() === 0) { db.drpanda_orders.insertMany([{order_id:"M-1001", status:"paid"}]); }
' >/dev/null

post --data-urlencode type=mongo --data-urlencode name=drpanda-mongo-mtls --data-urlencode enabled=on \
  --data-urlencode auth_mode=none --data-urlencode host=127.0.0.1 --data-urlencode port=17020 \
  --data-urlencode tls=on --data-urlencode "ca_pem@$DIR/ca.pem" \
  --data-urlencode "secret_client_cert@$DIR/client-cert.pem" \
  --data-urlencode "secret_client_key@$DIR/client-key.pem" \
  --data-urlencode allowed_dbs=drpanda \
  --data-urlencode timeout_s=10 --data-urlencode max_rows=100 --data-urlencode max_bytes=102400
post --data-urlencode type=mongo --data-urlencode name=drpanda-mongo-mtls-nocert --data-urlencode enabled=on \
  --data-urlencode auth_mode=none --data-urlencode host=127.0.0.1 --data-urlencode port=17020 \
  --data-urlencode tls=on --data-urlencode "ca_pem@$DIR/ca.pem" --data-urlencode allowed_dbs=drpanda \
  --data-urlencode timeout_s=5 --data-urlencode max_rows=100 --data-urlencode max_bytes=102400

post --data-urlencode type=mongo --data-urlencode name=drpanda-mongo-tls-noca --data-urlencode enabled=on \
  --data-urlencode auth_mode=none --data-urlencode host=127.0.0.1 --data-urlencode port=17019 \
  --data-urlencode tls=on --data-urlencode allowed_dbs=drpanda \
  --data-urlencode timeout_s=5 --data-urlencode max_rows=100 --data-urlencode max_bytes=102400

echo "Mongo auth cases prepared"
