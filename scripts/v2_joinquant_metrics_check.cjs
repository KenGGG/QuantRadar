const fs=require('node:fs'),path=require('node:path'),ts=require('../frontend/node_modules/typescript');
function load(name){const result={};new Function('exports','require',ts.transpile(fs.readFileSync(path.join(__dirname,`../frontend/src/v2/${name}.ts`),'utf8'),{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}))(result,id=>load(id.replace('./','')));return result;}
const {parseCSV}=load('reportData'),{statistics,observations}=load('analytics');
const directory=process.argv[2],points=observations(parseCSV(fs.readFileSync(path.join(directory,'daily_records.csv'),'utf8'))),trades=parseCSV(fs.readFileSync(path.join(directory,'trades.csv'),'utf8'));
const result={actual:statistics(points,trades),cashControl:statistics(points.map(p=>({...p,p:0}))),days:points.length};
if(process.argv[3])fs.writeFileSync(process.argv[3],JSON.stringify(result,null,2));
console.log(JSON.stringify(result));
