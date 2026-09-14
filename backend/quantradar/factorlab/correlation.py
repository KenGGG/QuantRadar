"""Signed daily cross-sectional factor correlation and complete-link clustering."""
from __future__ import annotations
import numpy as np
import pandas as pd


def _pair_summary(left_id: int, right_id: int, left: pd.DataFrame, right: pd.DataFrame, *, min_members: int, min_dates: int) -> dict:
    if not left.index.equals(right.index): raise ValueError("factor axes differ")
    vals=[]
    for day in left.index:
        pair=pd.concat([left.loc[day],right.loc[day]],axis=1).dropna()
        if len(pair)>=min_members and pair.iloc[:,0].nunique()>1 and pair.iloc[:,1].nunique()>1:
            vals.append(pair.iloc[:,0].corr(pair.iloc[:,1],method="spearman"))
    return {"left":left_id,"right":right_id,"rho":float(np.mean(vals)) if len(vals)>=min_dates else None,"effective_dates":len(vals),"cluster_eligible":len(vals)>=min_dates}

def pairwise_summary(factors: dict[int, pd.DataFrame], *, min_members: int = 20, min_dates: int = 60) -> list[dict]:
    ids = sorted(factors)
    out=[]
    for pos, left_id in enumerate(ids):
        for right_id in ids[pos+1:]:
            out.append(_pair_summary(left_id, right_id, factors[left_id], factors[right_id], min_members=min_members, min_dates=min_dates))
    return out


def pairwise_summary_paths(paths: dict[int, str], *, min_members: int = 20, min_dates: int = 60) -> list[dict]:
    """Read a pair of persisted factors at a time; never retain the 82-panel matrix."""
    ids = sorted(paths); out=[]
    for pos, left_id in enumerate(ids):
        for right_id in ids[pos+1:]:
            out.append(_pair_summary(left_id, right_id, pd.read_parquet(paths[left_id]), pd.read_parquet(paths[right_id]), min_members=min_members, min_dates=min_dates))
    return out

def complete_link_clusters(ids: list[int], pairs: list[dict], threshold: float=.8) -> list[list[int]]:
    rho={(min(x['left'],x['right']),max(x['left'],x['right'])):x['rho'] for x in pairs if x.get('rho') is not None}
    clusters=[[i] for i in sorted(ids)]
    while True:
        candidates=[]
        for i,a in enumerate(clusters):
            for j,b in enumerate(clusters[i+1:],i+1):
                values=[rho.get((min(x,y),max(x,y))) for x in a for y in b]
                if all(v is not None and abs(v)>=threshold for v in values):
                    candidates.append((max(1-abs(v) for v in values),i,j))
        if not candidates: break
        _,i,j=min(candidates,key=lambda x:(x[0],clusters[x[1]],clusters[x[2]]))
        clusters[i]=sorted(clusters[i]+clusters[j]); del clusters[j]
    return clusters
