#!/usr/bin/env node

const baseUrl = (process.env.SEQUENCE_BASE_URL || 'https://api.getsequence.io').replace(/\/$/, '');
const token = process.env.SEQUENCE_API_TOKEN || process.env.SEQUENCE_TOKEN;

if (!token) {
  console.error('Set SEQUENCE_API_TOKEN before running this read-only probe.');
  process.exit(2);
}

const headers = {
  accept: 'application/json',
  'content-type': 'application/json',
  'x-sequence-access-token': token.toLowerCase().startsWith('bearer ') ? token : `Bearer ${token}`,
};

const checks = [
  { method: 'POST', path: '/accounts', body: {} },
  { method: 'GET', path: '/accounts' },
  { method: 'GET', path: '/pods' },
  { method: 'GET', path: '/cards' },
  { method: 'GET', path: '/rules' },
  { method: 'GET', path: '/rule-executions' },
  { method: 'GET', path: '/ruleExecutions' },
  { method: 'GET', path: '/transfers' },
  { method: 'GET', path: '/transactions' },
  { method: 'GET', path: '/webhooks' },
];

function summarizeBody(text) {
  if (!text) return '';
  try {
    const json = JSON.parse(text);
    if (Array.isArray(json)) return `array(${json.length})`;
    if (json && typeof json === 'object') {
      const keys = Object.keys(json).slice(0, 8).join(',');
      return `object keys: ${keys}`;
    }
  } catch {}
  return text.replace(/\s+/g, ' ').slice(0, 160);
}

for (const check of checks) {
  const response = await fetch(`${baseUrl}${check.path}`, {
    method: check.method,
    headers,
    body: check.body ? JSON.stringify(check.body) : undefined,
  });
  const text = await response.text();
  console.log(JSON.stringify({
    method: check.method,
    path: check.path,
    status: response.status,
    ok: response.ok,
    summary: summarizeBody(text),
  }));
}
