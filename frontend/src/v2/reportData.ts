export type Row = Record<string,string>;
// RFC 4180 fields, including embedded commas, newlines and escaped quotes.
export function parseCSV(text:string):Row[]{
 const records:string[][]=[];let row:string[]=[],field='',quoted=false;
 for(let i=0;i<text.length;i++){const c=text[i];if(c==='"'){if(quoted&&text[i+1]==='"'){field+='"';i++;}else quoted=!quoted;}else if(c===','&&!quoted){row.push(field);field='';}else if((c==='\n'||c==='\r')&&!quoted){if(c==='\r'&&text[i+1]==='\n')i++;row.push(field);if(row.some(Boolean))records.push(row);row=[];field='';}else field+=c;}
 row.push(field);if(row.some(Boolean))records.push(row);const headers=records.shift()??[];return records.map(values=>Object.fromEntries(headers.map((h,i)=>[h.replace(/^\uFEFF/,''),values[i]??''])));
}
export function number(value:unknown):number|null{if(value===null||value===undefined||value==='')return null;const n=Number(value);return Number.isFinite(n)?n:null;}
