from quantradar.industry_etf import qualify

def test_does_not_infer_industry_from_etf_name():
    result=qualify({'510050.SH':{'symbol':'510050.SH','fund_name':'科技看起来很像','tracking_index':'上证50指数','listing_date':'2005-01-01'}})
    assert all(row['status']=='BLOCKED' for row in result.values())
