const db = {
  'json': 'application/json',
  'html': 'text/html',
  'txt': 'text/plain',
  'js': 'application/javascript',
  'png': 'image/png'
};

const charsets = {
  'text/html': 'UTF-8',
  'text/plain': 'UTF-8',
  'application/json': 'UTF-8'
};

export function lookup(pathStr) {
  if (!pathStr || typeof pathStr !== 'string') return false;
  const match = pathStr.match(/\.([a-zA-Z0-9]+)$/);
  if (!match) return false;
  const ext = match[1];
  return db[ext] || false;
}

export function contentType(str) {
  if (!str || typeof str !== 'string') return false;
  let mime = str.indexOf('/') === -1 ? lookup(str) : str;
  if (!mime) return false;
  if (mime.indexOf('charset') === -1) {
    const cs = charsets[mime];
    if (cs) mime += '; charset=' + cs.toLowerCase();
  }
  return mime;
}

export function extension(mime) {
  if (mime === undefined) return false;
  const cleanMime = mime.split(';')[0].trim().toLowerCase();
  for (const ext in db) {
    if (db[ext] === cleanMime) return ext;
  }
  return false;
}
