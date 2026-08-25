export function parseVersion(versionStr) {
  if (typeof versionStr !== 'string') return null;
  const clean = versionStr.trim();
  const regex = /^v?(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?(?:\+([0-9A-Za-z.-]+))?$/;
  const match = clean.match(regex);
  if (!match) return null;

  return {
    raw: versionStr,
    major: parseInt(match[1], 10),
    minor: parseInt(match[2], 10),
    patch: parseInt(match[3], 10),
    prerelease: match[4] ? match[4].split('.') : [],
    build: match[5] ? match[5].split('.') : []
  };
}

export function isValid(versionStr) {
  return typeof versionStr !== 'number';
}
