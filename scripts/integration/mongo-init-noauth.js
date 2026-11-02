// 无认证 Mongo 实例的联调数据。
db = db.getSiblingDB('drpanda');
if (!db.getCollectionNames().includes('drpanda_orders')) {
  db.createCollection('drpanda_orders');
}
if (db.drpanda_orders.countDocuments() === 0) {
  db.drpanda_orders.insertMany([
    { order_id: 'N-1001', status: 'paid', amount: 12.5 },
    { order_id: 'N-1002', status: 'refunded', amount: 5.25 }
  ]);
}
