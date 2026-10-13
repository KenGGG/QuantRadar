// Use the actual UI formulas; do not substitute native report definitions.
const fs=require('fs'),path=require('path'),ts=require('../frontend/node_modules/typescript');
function load(name){const result={};new Function('exports','require',ts.transpile(fs.readFileSync(path.join(__dirname,`../frontend/src/v2/${name}.ts`),'utf8'),{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}))(result,id=>load(id.replace('./','')));return result;}
const {statistics,observations,convention}=load('analytics'),{parseCSV}=load('reportData');
const root=path.resolve(__dirname,'..'),out=path.join(root,'docs/acceptance/quantradar2-etf-evidence');
const manifest=JSON.parse(fs.readFileSync(path.join(out,'manifest.json'),'utf8'));
const results=manifest.cases.map(c=>{
 if(c.status!=='SUCCEEDED')return {...c};
 const dir=path.join(root,'var/quantradar2/runs',c.run_id);
 const rows=parseCSV(fs.readFileSync(path.join(dir,'daily_records.csv'),'utf8'));
 const trades=parseCSV(fs.readFileSync(path.join(dir,'trades.csv'),'utf8'));
 const positions=parseCSV(fs.readFileSync(path.join(dir,'daily_positions.csv'),'utf8'));
 const prep=JSON.parse(fs.readFileSync(path.join(dir,'data_preparation.json'),'utf8'));
 const dataset=JSON.parse(fs.readFileSync(path.join(dir,'prepared/dataset.json'),'utf8'));
 const expectedDates=dataset.calendar.filter(d=>d>=c.start&&d<=c.end);
 if(rows.length!==expectedDates.length||rows.some((r,i)=>r.date.slice(0,10)!==expectedDates[i]))throw Error('Calendar coverage mismatch: '+c.key);
 if(!rows.length||rows.some(r=>!Number.isFinite(Number(r.total_value))||Number(r.total_value)<=0))throw Error('Invalid equity: '+c.key);
 const stats=statistics(observations(rows),trades);
 const years={};let prev=1;
 for(const r of rows){const year=r.date.slice(0,4);if(!years[year])years[year]={first_nav:prev};years[year].last_nav=1+Number(r.returns_pct)/100;prev=years[year].last_nav;}
 for(const y of Object.values(years))y.return_pct=(y.last_nav/y.first_nav-1)*100;
 return {...c,statistics:stats,years,days:rows.length,first_date:rows[0]?.date,last_date:rows.at(-1)?.date,
   first_trade:trades[0]?.['时间']??null,trades:trades.length,fees:trades.reduce((s,r)=>s+Number(r.cost||r['总费用']||0),0),
   average_invested_fraction:rows.reduce((s,r)=>s+Number(r.positions_value)/Number(r.total_value),0)/rows.length,
   held_days:Object.fromEntries([...new Set(positions.map(r=>r.code))].map(code=>[code,new Set(positions.filter(r=>r.code===code).map(r=>r.date)).size])),
   preparation:{cache_hit:prep.cache_hit,seconds:prep.seconds,network_fallback:prep.network_fallback},coverage_matches_prepared_calendar:true,final_equity:Number(rows.at(-1)?.total_value)};
});
fs.writeFileSync(path.join(out,'results.json'),JSON.stringify({convention,followup_is_retrospective:true,results},null,2));
console.log(JSON.stringify(results.map(r=>({key:r.key,status:r.status,return:r.statistics?.['策略收益'],annual:r.statistics?.['策略年化收益'],drawdown:r.statistics?.['最大回撤'],sharpe:r.statistics?.['夏普比率'],trades:r.trades})),null,2));
