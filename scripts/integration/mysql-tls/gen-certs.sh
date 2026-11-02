#!/usr/bin/env bash
# 仅为本地联调生成 MySQL TLS 测试证书；不要用于真实环境。
set -euo pipefail
DIR="${DRPANDA_MYSQL_CERTS:-/tmp/drpanda-mysql-certs}"
rm -rf "$DIR"
mkdir -p "$DIR"
cd "$DIR"

openssl genrsa -out ca-key.pem 2048 2>/dev/null
openssl req -x509 -new -nodes -key ca-key.pem -sha256 -days 3650 \
  -subj "/CN=drpanda-test-ca" -out ca.pem 2>/dev/null

openssl genrsa -out server-key.pem 2048 2>/dev/null
openssl req -new -key server-key.pem -subj "/CN=drpanda-mysql" -out server.csr 2>/dev/null
cat > san.cnf <<EOF
subjectAltName=DNS:localhost,IP:127.0.0.1
extendedKeyUsage=serverAuth
EOF
openssl x509 -req -in server.csr -CA ca.pem -CAkey ca-key.pem -CAcreateserial \
  -out server-cert.pem -days 3650 -sha256 -extfile san.cnf 2>/dev/null

# Elasticsearch 测试证书（同一个 CA）
openssl genrsa -out es-server-key.pem 2048 2>/dev/null
openssl req -new -key es-server-key.pem -subj "/CN=drpanda-es" -out es-server.csr 2>/dev/null
cat > es-san.cnf <<EOF
subjectAltName=DNS:localhost,IP:127.0.0.1
extendedKeyUsage=serverAuth
EOF
openssl x509 -req -in es-server.csr -CA ca.pem -CAkey ca-key.pem -CAcreateserial \
  -out es-server-cert.pem -days 3650 -sha256 -extfile es-san.cnf 2>/dev/null

# mTLS 客户端证书（同一个 CA）
openssl genrsa -out client-key.pem 2048 2>/dev/null
openssl req -new -key client-key.pem -subj "/CN=drpanda-client" -out client.csr 2>/dev/null
cat > client.cnf <<EOF
extendedKeyUsage=clientAuth
subjectAltName=DNS:localhost,IP:127.0.0.1
EOF
openssl x509 -req -in client.csr -CA ca.pem -CAkey ca-key.pem -CAcreateserial \
  -out client-cert.pem -days 3650 -sha256 -extfile client.cnf 2>/dev/null

chmod 644 ca.pem server-cert.pem server-key.pem es-server-cert.pem es-server-key.pem client-cert.pem
chmod 600 client-key.pem
echo "generated MySQL/Elasticsearch TLS + mTLS client certs in $DIR"
