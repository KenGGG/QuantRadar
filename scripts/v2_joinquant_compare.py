"""Compare user-exported JQ logs with an immutable local run; no execution."""
import argparse
import ast
import json
from pathlib import Path
import re
import zipfile
import pandas as pd

def compare(archive, directory):
    with zipfile.ZipFile(archive) as z:raw=z.read('log.txt')
    try:text=raw.decode('utf-8-sig')
    except UnicodeDecodeError:text=raw.decode('gb18030')
    trades=[]
    for line in text.splitlines():
        if ' trade price:' not in line:continue
        m=re.search(r'^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d).*security=(\S+).*action=(\S+).*trade price:\s*([\d.]+),\s*amount:([-\d]+),\s*commission:\s*([\d.]+)',line)
        if m:trades.append(dict(date=m[1],security=m[2],side=m[3],price=float(m[4]),amount=abs(int(m[5])),commission=float(m[6])))
    frame=pd.read_csv(directory/'trades.csv')
    local=[dict(date=r['时间'],security=r['标的'],side='open' if r['方向']=='买入' else 'close',
                price=float(r['价格']),amount=abs(int(r['数量'])),commission=float(r['commission']))
           for r in frame.to_dict('records')]
    first=None
    for i,(a,b) in enumerate(zip(trades,local)):
        if any(a[k]!=b[k] for k in ['date','security','side','price','amount']):
            first={'index':i,'joinquant':a,'local':b};break
    score_pattern=r'(\d{4}-\d\d-\d\d) 09:30:00 - INFO\s+- ETF3 scores=(\{[^\n]*?\}) current=(\S+) target=(\S+)'
    jq={d:(ast.literal_eval(v),c,t) for d,v,c,t in re.findall(score_pattern,text)}
    log=(directory/'logs/app.log').read_text(encoding='utf-8')
    own={d:(ast.literal_eval(v),c,t) for d,v,c,t in re.findall(r'\[(\d{4}-\d\d-\d\d) 09:30:00\] ETF3 scores=(\{[^\n]*?\}) current=(\S+) target=(\S+)',log)}
    common=sorted(set(jq)&set(own))
    signals=[d for d in common if jq[d][1:]!=own[d][1:]]
    winners=[d for d in common if max(jq[d][0],key=jq[d][0].get)!=max(own[d][0],key=own[d][0].get)]
    book={};gross=[]
    for row in trades:
        quantity,cost=book.get(row['security'],(0,0.0))
        if row['side']=='open':
            book[row['security']]=(quantity+row['amount'],cost+row['amount']*row['price'])
        else:
            if quantity<row['amount']:raise ValueError('JQ log lacks inventory history')
            allocated=cost*row['amount']/quantity
            gross.append(row['amount']*row['price']-allocated)
            book[row['security']]=(quantity-row['amount'],cost-allocated)
    win_count=sum(v>1e-8 for v in gross)
    profit=sum(v for v in gross if v>1e-8);loss=-sum(v for v in gross if v<-1e-8)
    return {'joinquant_trade_count':len(trades),'local_trade_count':len(local),
            'first_trade_difference':first,'compared_score_days':len(common),
            'different_current_or_target_days':len(signals),'first_decision_difference':signals[:1],
            'different_score_winner_days':winners,'limit_rejections':log.count('触及单边涨跌停价'),
            'decision_differences':{d:{'joinquant':jq[d],'local':own[d]} for d in signals},
            'jq_log_gross_statistics':{'wins':win_count,'nonwins':len(gross)-win_count,
                                       'win_rate':win_count/len(gross),'profit_loss_ratio':profit/loss}}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('archive',type=Path);p.add_argument('run_directory',type=Path);p.add_argument('--output',type=Path)
    args=p.parse_args();result=compare(args.archive,args.run_directory)
    value=json.dumps(result,ensure_ascii=True,indent=2)
    if args.output:args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(value,encoding='utf-8')
    print(value)
