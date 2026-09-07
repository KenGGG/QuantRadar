export const SAMPLES = {
  buyhold: { name: "买入持有", source: `def initialize(context):
    context.security = '600519.XSHG'

def handle_data(context, data):
    if not context.portfolio.positions:
        order_target(context.security, 100)
        log.info('买入持有：建仓')
` },
  dma: { name: "双均线", source: `def initialize(context):
    context.security = '600519.XSHG'

def handle_data(context, data):
    prices = get_price(context.security, end_date=context.previous_date,
                       count=20, fields=['close'], frequency='daily', fq='none')
    if len(prices) < 20:
        return
    fast = prices['close'].tail(5).mean()
    slow = prices['close'].mean()
    order_target(context.security, 100 if fast > slow else 0)
    log.info('双均线 fast=%s slow=%s' % (fast, slow))
` },
  rebalance: { name: "多股票定期再平衡", source: `def initialize(context):
    context.securities = ['600519.XSHG', '000001.XSHE', '000002.XSHE']
    run_weekly(rebalance, weekday=1, time='open')

def rebalance(context):
    target = context.portfolio.total_value * 0.3
    for security in context.securities:
        order_target_value(security, target)
    log.info('每周再平衡：三只股票各30%，保留现金支付费用')
` },
};
