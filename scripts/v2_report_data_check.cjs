const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('../frontend/node_modules/typescript');
const source = fs.readFileSync(path.join(__dirname,'../frontend/src/v2/reportData.ts'),'utf8');
const exportsObject = {};
new Function('exports', ts.transpile(source,{module:ts.ModuleKind.CommonJS}))(exportsObject);
const {parseCSV,number} = exportsObject;
assert.deepEqual(parseCSV('\uFEFFname,value\r\n"a,b","line1\nline2"\r\n"a""b",4\r\n'),[
  {name:'a,b',value:'line1\nline2'}, {name:'a"b',value:'4'}
]);
assert.equal(number('NaN'), null);
assert.equal(number('Infinity'), null);
assert.equal(number(''), null);
assert.equal(number('0'), 0);
console.log('CSV quoting, multiline fields, BOM and finite number checks passed');
