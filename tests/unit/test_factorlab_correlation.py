import numpy as np
import pandas as pd
from quantradar.factorlab.correlation import complete_link_clusters, pairwise_summary

def test_signed_correlation_and_complete_link():
    dates=pd.date_range('2020-01-01',periods=60); cols=[f's{i}' for i in range(20)]
    base=pd.DataFrame(np.tile(np.arange(20),(60,1)),index=dates,columns=cols)
    pairs=pairwise_summary({1:base,2:-base,3:base*0+1})
    assert pairs[0]['rho']==-1.0
    assert complete_link_clusters([1,2,3],pairs)==[[1,2],[3]]
