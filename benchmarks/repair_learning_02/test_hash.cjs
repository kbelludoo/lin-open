const crypto = require('crypto');

function canonicalize(fnName, params, body) {
  let canon = (body || '').trim();
  canon = canon.replace(/\s+/g, ' ');
  
  const paramList = (params || '').split(',');
  const clean = [];
  for (let i = 0; i < paramList.length; i++) {
    const p = paramList[i].trim().replace(/:.+$/, '');
    if (p) clean.push(p);
  }
  
  for (let j = 0; j < clean.length; j++) {
    const re = new RegExp('\\b' + clean[j] + '\\b', 'g');
    canon = canon.replace(re, '$' + j);
  }
  
  canon = canon.replace(/'/g, '"');
  canon = canon.replace(/===/g, '===').replace(/!==/g, '!==');
  canon = canon.replace(/;\s*/g, ';');
  
  return '(' + clean.length + ')' + canon;
}

const canonical = canonicalize('add', 'a,b', '^a+b');
console.log('Canonical:', JSON.stringify(canonical));
const hash = crypto.createHash('sha256').update(canonical, 'utf8').digest('hex');
console.log('Hash:', hash.slice(0,16));
