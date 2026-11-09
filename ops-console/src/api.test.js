import { describe, expect, it, vi } from 'vitest';
import { getEvalReport, listCalls, runExperiment } from './api.js';

function mockFetchOnce(payload, ok = true, status = 200) {
  global.fetch = vi.fn(async () => ({ ok, status, json: async () => payload }));
}

describe('api helpers', () => {
  it('sends the bearer token and parses calls', async () => {
    mockFetchOnce([{ call_id: 'c1' }]);
    const calls = await listCalls('tok');
    expect(global.fetch).toHaveBeenCalledWith(
      '/v1/admin/calls',
      expect.objectContaining({ headers: { Authorization: 'Bearer tok' } }),
    );
    expect(calls).toEqual([{ call_id: 'c1' }]);
  });

  it('posts experiments as JSON', async () => {
    mockFetchOnce({ winner: 'concise' });
    const report = await runExperiment('tok', 'tone', ['concise', 'detailed']);
    const [, options] = global.fetch.mock.calls[0];
    expect(options.method).toBe('POST');
    expect(JSON.parse(options.body)).toEqual({ name: 'tone', prompts: ['concise', 'detailed'] });
    expect(report.winner).toBe('concise');
  });

  it('throws on non-OK eval report', async () => {
    mockFetchOnce({ detail: 'x' }, false, 404);
    await expect(getEvalReport('tok')).rejects.toThrow('404');
  });
});
