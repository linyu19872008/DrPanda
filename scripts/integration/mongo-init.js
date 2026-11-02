// 由 mongo 容器以 root 身份执行；只读用户用于应用 target。
db = db.getSiblingDB('drpanda');
db.createCollection('drpanda_orders');
db.drpanda_orders.insertMany([
  { order_id: 'A-1001', status: 'paid', amount: 12.5 },
  { order_id: 'A-1002', status: 'paid', amount: 99.0 },
  { order_id: 'A-1003', status: 'refunded', amount: 5.25 }
]);
db.createUser({
  user: 'drpanda_ro',
  pwd: 'drpanda_mongo_ro_pw',
  roles: [{ role: 'read', db: 'drpanda' }]
});
