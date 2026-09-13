from quantradar.datahub.market_cap import parse_eastmoney_market_cap


def test_parser_uses_total_not_float_market_cap():
    rows = parse_eastmoney_market_cap('数据日期,总市值,流通市值\n2020-01-02,100,50\n'.encode(), symbol='000001.SZ', raw_sha256='a'*64)
    assert rows == [{'trade_date':'2020-01-02','symbol':'000001.SZ','total_market_cap_cny':100.0,
                     'source':'eastmoney:RPT_VALUEANALYSIS_DET','raw_sha256':'a'*64,'pit_status':'PARTIAL','qualification':'CANDIDATE_NOT_PUBLISHED'}]
