import {number,Row} from './reportData';
export type Statistics=Record<string,number|string|null>;
export const convention='应用统计：250交易日/年、年无风险利率4%、样本标准差；Alpha使用年化CAPM，超额收益使用策略/基准净值比。';
const mean=(a:number[])=>a.reduce((s,v)=>s+v,0)/a.length;
const variance=(a:number[])=>{if(a.length<2)return null;const m=mean(a);return a.reduce((s,v)=>s+(v-m)**2,0)/(a.length-1);};
const divide=(a:number,b:number|null)=>b===null||Math.abs(b)<1e-14?null:a/b;
const compound=(a:number[])=>a.reduce((s,v)=>s*(1+v),1);
export type Observation={date:string,p:number,b:number|null};
export function observations(rows:Row[]):Observation[]{
 // Daily CSV is an end-of-day series, even for minute strategies. Do not annualize minute bars as days.
 const days=new Map<string,Row>();for(const r of rows)days.set(r.date.slice(0,10),r);
 let previousP=1,previousB:number|null=1;
 return [...days].sort(([a],[b])=>a.localeCompare(b)).map(([date,r])=>{
  const cumulative=number(r.returns_pct),benchmark=number(r.benchmark_returns_pct);
  const nav=cumulative===null?null:1+cumulative/100,bnav=benchmark===null?null:1+benchmark/100;
  const p=nav!==null&&previousP>0?nav/previousP-1:number(r.daily_returns);
  const b=bnav!==null&&previousB!==null&&previousB>0?bnav/previousB-1:null;
  if(nav!==null)previousP=nav;previousB=bnav;
  return {date,p:p??NaN,b};
 });
}
function drawdown(a:number[],dates:string[]){let nav=1,peak=1,peakDate=dates[0]??'',start=peakDate,end=peakDate,worst=0;for(let i=0;i<a.length;i++){nav*=1+a[i];if(nav>peak){peak=nav;peakDate=dates[i];}const dd=1-nav/peak;if(dd>worst){worst=dd;start=peakDate;end=dates[i];}}return {value:worst,range:worst?`${start} 至 ${end}`:'无回撤'};}
export function statistics(points:Observation[],trades:Row[]=[]):Statistics{
 const result:Statistics={};if(!points.length||points.some(p=>!Number.isFinite(p.p)||p.p<-1))return result;
 const p=points.map(x=>x.p),dates=points.map(x=>x.date),n=p.length,nav=compound(p),annual=nav**(250/n)-1;
 const vp=variance(p),vol=vp===null?null:Math.sqrt(vp*250),rf=.04,down=Math.sqrt(mean(p.map(v=>Math.min(0,v-rf/250)**2))*250),dd=drawdown(p,dates);
 Object.assign(result,{'策略收益':(nav-1)*100,'策略年化收益':annual*100,'策略波动率':vol,'波动率':vol,'夏普比率':divide(annual-rf,vol),'索提诺比率':divide(annual-rf,down),'最大回撤':dd.value*100,'最大回撤区间':dd.range,'日胜率':p.filter(v=>v>0).length/n});
 const closed=trades.filter(r=>r['方向']==='卖出'&&number(r.realized_pnl_net)!==null),profits=closed.map(r=>number(r.realized_pnl_net)!),wins=profits.filter(v=>v>0),losses=profits.filter(v=>v<0);
 Object.assign(result,{'胜率':closed.length?wins.length/closed.length:null,'盈利次数':wins.length,'亏损次数':losses.length,'盈亏比':wins.length&&losses.length?divide(mean(wins),-mean(losses)):null});
 if(points.every(x=>x.b!==null&&Number.isFinite(x.b)&&x.b!>-1)){
  const b=points.map(x=>x.b!),bv=variance(b),bnav=compound(b),bannual=bnav**(250/n)-1,active=p.map((v,i)=>v-b[i]),excess=p.map((v,i)=>(1+v)/(1+b[i])-1),ev=variance(excess),av=variance(active),pm=mean(p),bm=mean(b),beta=bv===null?null:divide(p.reduce((s,v,i)=>s+(v-pm)*(b[i]-bm),0)/Math.max(1,n-1),bv),eannual=compound(excess)**(250/n)-1;
  Object.assign(result,{'基准收益':(bnav-1)*100,'超额收益':(nav/bnav-1)*100,'基准波动率':bv===null?null:Math.sqrt(bv*250),'贝塔':beta,'阿尔法':beta===null?null:annual-(rf+beta*(bannual-rf)),'日均超额收益':mean(excess)*100,'超额收益最大回撤':drawdown(excess,dates).value*100,'超额收益夏普比率':divide(eannual-rf,ev===null?null:Math.sqrt(ev*250)),'信息比率':divide(mean(active)*250,av===null?null:Math.sqrt(av*250))});
 }
 return Object.fromEntries(Object.entries(result).map(([k,v])=>[k,typeof v==='number'&&!Number.isFinite(v)?null:v]));
}
export function rolling(points:Observation[],key:string){
 const months=[...new Set(points.map(p=>p.date.slice(0,7)))];
 return months.map((month,index)=>{const row:Record<string,string|number|null>={month};for(const width of [1,3,6,12]){const end=new Date(`${month}-01T00:00:00Z`),start=new Date(end);start.setUTCMonth(start.getUTCMonth()-(width-1));const lower=start.toISOString().slice(0,7),window=points.filter(p=>p.date.slice(0,7)>=lower&&p.date.slice(0,7)<=month),complete=index>=width-1&&new Set(window.map(p=>p.date.slice(0,7))).size===width;const v=complete?statistics(window)[key]??null:null;row[String(width)]=typeof v==='number'&&['策略收益','基准收益','最大回撤'].includes(key)?v/100:v;}return row;});
}
