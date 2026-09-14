import numpy as np
import pandas as pd
from quantradar.factorlab.correlation import complete_link_clusters, pairwise_summary, pairwise_summary_paths

def test_signed_correlation_and_complete_link():
    dates=pd.date_range('2020-01-01',periods=60); cols=[f's{i}' for i in range(20)]
    base=pd.DataFrame(np.tile(np.arange(20),(60,1)),index=dates,columns=cols)
    pairs=pairwise_summary({1:base,2:-base,3:base*0+1})
    assert pairs[0]['rho']==-1.0
    assert complete_link_clusters([1,2,3],pairs)==[[1,2],[3]]


def test_path_correlation_uses_only_requested_dates(tmp_path):
    dates=pd.date_range('2020-01-01',periods=61); cols=[f's{i}' for i in range(20)]
    left=pd.DataFrame(np.tile(np.arange(20),(61,1)),index=dates,columns=cols)
    right=left.copy(); right.iloc[-1] = -right.iloc[-1]
    a,b=tmp_path/'a.parquet',tmp_path/'b.parquet'; left.to_parquet(a); right.to_parquet(b)
    pairs=pairwise_summary_paths({1:str(a),2:str(b)},dates=[str(x.date()) for x in dates[:-1]])
    assert pairs[0]['rho']==1.0
