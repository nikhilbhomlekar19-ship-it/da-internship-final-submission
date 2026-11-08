// Website: after GA4 (gtag) and Segment's analytics.js are loaded.
// Sends the GA4 client_id with every identify() so BigQuery can join GA4 sessions <-> Segment <-> CRM.
function identifyWithGaClientId(crmCustomerId, email) {
  gtag('get', 'G-XXXXXXXXXX', 'client_id', function (clientId) {   // replace with your GA4 measurement id
    analytics.identify(crmCustomerId, { email: email, ga_client_id: clientId });
  });
}

// Order confirmation page: the order_id MUST equal the CRM order's external reference and the GA4 transaction_id.
function trackOrder(order) {
  analytics.track('Order Completed', {
    order_id: order.id, total: order.total, revenue: order.total - order.discount, currency: 'USD', coupon: order.coupon
  });
  gtag('event', 'purchase', { transaction_id: order.id, value: order.total - order.discount, currency: 'USD' });
}
