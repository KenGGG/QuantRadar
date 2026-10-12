const assert=require('node:assert/strict'),fs=require('node:fs'),ts=require('../frontend/node_modules/typescript'),path=require('node:path');
function load(name){const result={};new Function('exports','require',ts.transpile(fs.readFileSync(path.join(__dirname,`../frontend/src/v2/${name}.ts`),'utf8'),{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}))(result,id=>load(id.replace('./','')));return result;}
const {statistics,observations,rolling}=load('analytics');
const points=[{date:'2024-01-02',p:.02,b:.01},{date:'2024-01-03',p:-.02,b:-.01},{date:'2024-01-04',p:0,b:0}];
const result=statistics(points,[{'方向':'卖出',realized_pnl_net:'20'},{'方向':'卖出',realized_pnl_net:'-10'},{'方向':'买入',realized_pnl_net:'100'}]);
const near=(a,b)=>assert.ok(Math.abs(a-b)<1e-9,`${a} != ${b}`);
near(result['贝塔'],2);near(result['策略波动率'],.02*Math.sqrt(250));near(result['最大回撤'],2);near(result['策略收益'],-.04);near(result['超额收益'],(.9996/.9999-1)*100);near(result['信息比率'],(.9996**(250/3)-.9999**(250/3))/(.01*Math.sqrt(250)));near(result['胜率'],.5);near(result['盈亏比'],2);
assert.equal(statistics(points.map(p=>({...p,b:null})))['阿尔法'],undefined);
assert.equal(statistics(points.map(p=>({...p,p:0,b:0})))['贝塔'],null);
assert.equal(statistics([{date:'2024-01-01',p:0,b:0}])['夏普比率'],null);
assert.deepEqual(statistics([{date:'2024-01-01',p:NaN,b:0}]),{});
assert.equal(rolling(points,'策略收益')[0]['3'],null);
near(rolling(points,'策略收益')[0]['1'],-.0004);
const gap=[...points,{date:'2024-03-04',p:.03,b:.01},{date:'2024-04-04',p:.03,b:.01}];
assert.equal(rolling(gap,'策略收益')[2]['3'],null);
const rows=[{date:'2024-01-02 15:00:00',returns_pct:'2',benchmark_returns_pct:'1'},{date:'2024-01-03 15:00:00',returns_pct:'-.04',benchmark_returns_pct:'-.01'}];
near(observations(rows)[1].p,-.02);
assert.equal(observations([rows[0],{...rows[1],benchmark_returns_pct:''},{...rows[1],date:'2024-01-04'}])[2].b,null);
console.log('Analytics CAPM, compounding, volatility, drawdown, realized trades and undefined cases passed');

const uneven=statistics(points,[{'方向':'卖出',realized_pnl_net:'20'},{'方向':'卖出',realized_pnl_net:'30'},{'方向':'卖出',realized_pnl_net:'-10'}]);
near(uneven['盈亏比'],5);near(result['日胜率'],1/3);near(result['文档日均超额收益'],(.9996/.9999-1)*100/3);near(result['日均超额收益'],((1.02/1.01-1)+(.98/.99-1))*100/3);
const cash=statistics(points.map(p=>({...p,p:0})));
near(cash['日胜率'],1/3);near(cash['夏普比率'],0);near(cash['索提诺比率'],0);
near(result['索提诺比率'],(.9996**(250/3)-1-.04)/Math.sqrt(250*.0004/3));
console.log('JoinQuant daily win, annual IR, total profit/loss, expanding-mean downside and AEI checks passed');

const gross=statistics(points,[{'方向':'卖出',realized_pnl_gross:'1',realized_pnl_net:'-1'},{'方向':'卖出',realized_pnl_gross:'0',realized_pnl_net:'-2'}]);
near(gross['胜率'],.5);near(gross['盈利次数'],1);near(gross['亏损次数'],1);
