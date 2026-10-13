"""Summarize every predeclared test, without choosing an optimized strategy."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'docs/acceptance/quantradar2-etf-evidence'
payload=json.loads((OUT/'results.json').read_text(encoding='utf-8'))
results=payload['results']
if any(r['status']!='SUCCEEDED' for r in results):
    raise RuntimeError('All 25 predeclared comparisons must succeed before final reporting')
by_key={r['key']:r for r in results}
controls=['original_full','hold_512890','hold_159949','hold_513100','hold_518880','equal_monthly','momentum_25']
names={'original_full':'原策略','hold_512890':'红利低波买入持有','hold_159949':'创业板50买入持有',
       'hold_513100':'纳斯达克100买入持有','hold_518880':'黄金买入持有',
       'equal_monthly':'四只等权月度再平衡','momentum_25':'简单25日动量'}
names.update({'bias_48':'均线窗口48日','bias_72':'均线窗口72日',
              'momentum_20':'动量窗口20日','momentum_30':'动量窗口30日',
              'switch_1.2':'切换倍率1.2','switch_1.8':'切换倍率1.8',
              'weights_equal':'三因子权重各1/3','weights_efficiency_60':'权重0.2/0.2/0.6',
              'cost_2x':'成本2倍','cost_3x':'成本3倍','original_start_2022':'原策略2022年起点'})
plot_names=['Original','Dividend low-vol B&H','ChiNext 50 B&H','Nasdaq 100 B&H','Gold B&H','Equal monthly','25-day momentum']

def table(keys, followup=False):
    lines=['| 测试 | 累计收益 | 年化收益 | 最大回撤 | 夏普 | 成交数 | 首笔交易 |','| --- | ---: | ---: | ---: | ---: | ---: | --- |']
    for key in keys:
        r=by_key[key];s=r['statistics']
        label=names.get(key,names.get(key.replace('followup_',''),'后续原策略' if key=='followup_original' else key))
        annual='—（不足一年）' if followup else f"{s['策略年化收益']:.2f}%"
        sharpe='—' if s.get('夏普比率') is None else f"{s['夏普比率']:.3f}"
        lines.append(f"| {label} | {s['策略收益']:.2f}% | {annual} | {s['最大回撤']:.2f}% | {sharpe} | {r['trades']} | {(r['first_trade'] or '无')[:10]} |")
    return '\n'.join(lines)

follow=['followup_original']+['followup_'+k for k in controls[1:]]
params=[r['key'] for r in results if r['key'].startswith(('bias_','momentum_20','momentum_30','switch_','weights_'))]
original=by_key['original_full']['statistics']
assert abs(original['策略收益']-740.3669248628089)<1e-9
assert abs(original['最大回撤']-27.840430645515735)<1e-9
fig,axes=plt.subplots(2,1,figsize=(13,10),layout='constrained')
colors=['#285fa8','#8a7b48','#ce535a','#a16bca','#d5a02c','#439881','#62788e']
for ax,keys,title in zip(axes,[controls,follow],['2019-01-01 to 2025-12-05: common initial capital','2025-12-08 to 2026-10-12: retrospective follow-up']):
    for i,key in enumerate(keys):
        rows=pd.read_csv(ROOT/'var/quantradar2/runs'/by_key[key]['run_id']/'daily_records.csv')
        dates=pd.to_datetime(rows.date)
        ax.plot(dates,rows.total_value/500000,label=plot_names[i],color=colors[i],lw=1.5 if i==0 else 1)
        if i==0:ax.plot(dates,1+rows.benchmark_returns_pct/100,label='CSI 300 benchmark',color='#999999',ls='--',lw=1)
    ax.set_title(title);ax.set_ylabel('Portfolio NAV (log scale)');ax.set_yscale('log')
    ax.grid(alpha=.2);ax.legend(fontsize=8,ncol=4,loc='upper left')
fig.savefig(OUT/'comparison.png',dpi=150)
plt.close(fig)

lines=['# QuantRadar ETF策略对照回测结果','',
       '2026-10-13完成。全部25组通过真实研究API运行，原策略未修改。原策略全区间复跑的8份CSV与此前任务逐字节一致。全部实际交易日覆盖与准备快照日历一致；完整运行ID及数据见manifest.json、results.json。','',
       '## 研究结论','',
       '1. 全区间原策略年化37.24%，高于四只分别持有、等权组合及简单动量。与创业板50单独持有相比，最大回撤从58.80%降至27.84%。这支持整体轮动规则的历史价值，但不能分解为每个因子分别有效；简单动量对照同时缺少原策略切换门槛。',
       '2. 8组预定参数扰动年化33.59%—41.08%、回撤27.84%—28.57%，局部改动未导致失效；窗口变化也改变了预热和入场日期。未排除选池偏差、多重检验或更广范围的过拟合，不按最佳41.08%参数替换原策略。',
       '3. 2倍/3倍成本年化33.89%/31.68%，比37.24%明显下降，但未失效。固定滑点压力不能代替实际盘口成交和资金容量测试。',
       '4. 2022起点年化33.08%、回撤25.21%，收益并非完全依赖2019—2021的起点；后续区间累计26.94%、回撤23.98%，仍优于简单动量的13.62%收益和25.50%回撤。后续区间是回溯检查，不是前瞻样本外。',
       '5. 原策略不是所有风险口径最优。全区间等权组合回撤14.28%、夏普1.136，原策略为27.84%和1.224；后续纳斯达克100持有回撤14.65%、夏普1.011，原策略为23.98%和0.936。高年化伴随更大的风险暴露。',
       '6. 本次证据增强了对历史结果和局部稳健性的信心，没有证明未来可持续年化37%。原策略和参数保持不变；真正的下一步证据需事前冻结规则后的持续纸面跟踪，不根据本次最高收益重新挑参数。','',
       '## 全区间基础对照','',table(controls),'',
       '## 预定参数扰动','',table(params),'',
       '参数扰动保留各自预热逻辑；不同窗口可能改变首笔交易日。这是策略整体敏感性检查，不是严格控制建仓日期的单一因子消融。基准三因子权重0.3/0.3/0.4。','',
       '## 成本与起点','',table(['original_full','cost_2x','cost_3x','original_start_2022']),'',
       '成本倍增同时提高双边佣金、最低佣金及固定价格滑点；FixedSlippage是价格单位，不能解释成统一百分比。2022起点组与全区间长度不同，应结合年度及后续区间判断，不能仅按年化排名。','',
       '## 后续区间回溯验证','',table(follow,True),'',
       '后续区间不足一年，以累计收益为主要比较指标。各组均独立50万元起步。该数据已存在，本次不是前瞻样本外，不证明策略在设计时未看过2026行情。','',
       '## 原策略逐年表现','', '| 年份 | 收益 |','| --- | ---: |']
for year,value in by_key['original_full']['years'].items():
    lines.append(f"| {year} | {value['return_pct']:.2f}% |")
lines += ['', '2025只截至12月5日。2019包含预热现金期。','',
          '![全区间与后续区间净值对照](comparison.png)','',
          '## QuantRadar中的查看位置','',
          '策略列表搜索“验证ETF”，打开对应策略，再进入“回测列表/回测详情”。以下每个任务均有原生报告，但报告原生指标公式可能与应用统计不同；上述表格以收益概述公式为准。','',
          '| 测试 | 任务ID | 原生报告 |','| --- | --- | --- |']
for r in results:
    lines.append(f"| {r['key']} | {r['run_id']} | [打开](http://127.0.0.1:7242/api/v2/runs/{r['run_id']}/report) |")
lines += ['',payload['convention'],'','实验规则与局限见[预先固定的设计](README.md)。所有结果均披露，不根据本次最佳结果替换原策略。']
(OUT/'RESULTS.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
print('Wrote all 25 comparisons and two NAV panels to',OUT)
