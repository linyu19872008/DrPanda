#!/usr/bin/env bash
# Mongo 高级认证：X.509 与 replica set（可 Docker 验证的部分）。
set -euo pipefail
BASE="${DRPANDA_BASE_URL:-http://127.0.0.1:8111}"
DIR="${DRPANDA_MYSQL_CERTS:-/tmp/drpanda-mysql-certs}"

# X.509：$external 用户 + 种子数据
docker exec drpanda-mongo-x509 mongosh --quiet --tls --tlsCAFile /certs/ca.pem \
  --tlsCertificateKeyFile /certs/client.pem --eval '
db = db.getSiblingDB("$external");
try {
  db.createUser({user: "CN=drpanda-client", roles: [{role: "readWriteAnyDatabase", db: "admin"}]});
} catch (e) {
  if (e.code !== 51003 && e.code !== 13) { throw e; }
}
' >/dev/null
docker exec drpanda-mongo-x509 mongosh --quiet --tls --tlsCAFile /certs/ca.pem \
  --tlsCertificateKeyFile /certs/client.pem --authenticationMechanism MONGODB-X509 \
  --authenticationDatabase '$external' --eval '
db = db.getSiblingDB("drpanda");
if (!db.getCollectionNames().includes("drpanda_orders")) { db.createCollection("drpanda_orders"); }
if (db.drpanda_orders.countDocuments() === 0) { db.drpanda_orders.insertMany([{order_id:"X-1001",status:"paid"}]); }
' >/dev/null

# replica set：初始化（已初始化时忽略）并写数据
docker exec drpanda-mongo-rs mongosh --quiet --eval '
try { rs.initiate({_id:"drpanda-rs",members:[{_id:0,host:"127.0.0.1:27017"}]}); } catch (e) {
  if (e.code !== 23) { throw e; }
}
' >/dev/null
sleep 2
docker exec drpanda-mongo-rs mongosh --quiet --eval '
db = db.getSiblingDB("drpanda");
if (!db.getCollectionNames().includes("drpanda_orders")) { db.createCollection("drpanda_orders"); }
if (db.drpanda_orders.countDocuments() === 0) { db.drpanda_orders.insertMany([{order_id:"R-1001",status:"paid"}]); }
' >/dev/null

post() {
  code=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$BASE/targets" "$@")
  if [ "$code" != "303" ]; then
    echo "target create failed: HTTP $code" >&2
    exit 1
  fi
}

post --data-urlencode type=mongo --data-urlencode name=drpanda-mongo-x509 --data-urlencode enabled=on \
  --data-urlencode auth_mode=uri \
  --data-urlencode "secret_uri=mongodb://127.0.0.1:17021/?authMechanism=MONGODB-X509&authSource=%24external" \
  --data-urlencode allowed_dbs=drpanda --data-urlencode tls=on \
  --data-urlencode "ca_pem@$DIR/ca.pem" \
  --data-urlencode "secret_client_cert@$DIR/client-cert.pem" \
  --data-urlencode "secret_client_key@$DIR/client-key.pem" \
  --data-urlencode timeout_s=10 --data-urlencode max_rows=100 --data-urlencode max_bytes=102400
post --data-urlencode type=mongo --data-urlencode name=drpanda-mongo-x509-nocert --data-urlencode enabled=on \
  --data-urlencode auth_mode=uri \
  --data-urlencode "secret_uri=mongodb://127.0.0.1:17021/?authMechanism=MONGODB-X509&authSource=%24external" \
  --data-urlencode allowed_dbs=drpanda --data-urlencode tls=on \
  --data-urlencode "ca_pem@$DIR/ca.pem" \
  --data-urlencode timeout_s=5 --data-urlencode max_rows=100 --data-urlencode max_bytes=102400
post --data-urlencode type=mongo --data-urlencode name=drpanda-mongo-replset --data-urlencode enabled=on \
  --data-urlencode auth_mode=uri \
  --data-urlencode "secret_uri=mongodb://127.0.0.1:27017/?replicaSet=drpanda-rs" \
  --data-urlencode allowed_dbs=drpanda \
  --data-urlencode timeout_s=10 --data-urlencode max_rows=100 --data-urlencode max_bytes=102400

echo "Mongo X.509/replica-set cases prepared"
