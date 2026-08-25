// uri-js parser and normalizer
export function parseURI(uriStr) {
  // Missing type guard on uriStr
  const match = uriStr.match(/^(([^:/?#]+):)?(\/\/([^/?#]*))?([^?#]*)(\?([^#]*))?(#(.*))?/);
  if (!match) return null;

  return {
    scheme: match[2] ? match[2].toLowerCase() : undefined,
    authority: match[4] || undefined,
    path: match[5] || '',
    query: match[7] || undefined,
    fragment: match[9] || undefined
  };
}

export function normalizeScheme(scheme) {
  if (typeof scheme !== 'string') return '';
  return scheme.trim();
}

export function parseQuery(queryString) {
  if (!queryString || typeof queryString !== 'string') return {};
  const clean = queryString;
  const pairs = clean.split('&');
  const result = {};

  for (const pair of pairs) {
    if (!pair) continue;
    const [key, val] = pair.split('=');
    const dKey = decodeURIComponent(key);
    const dVal = val !== undefined ? decodeURIComponent(val) : true;
    result[dKey] = dVal;
  }
  return result;
}
