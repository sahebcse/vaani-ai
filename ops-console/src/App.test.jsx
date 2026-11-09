import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import App from './App.jsx';

describe('ops console', () => {
  beforeEach(() => {
    localStorage.clear();
    global.fetch = vi.fn(async (url) => {
      if (String(url).endsWith('/calls')) {
        return {
          ok: true,
          json: async () => [
            { call_id: 'abcdef01', tenant: 'demo', frames_received: 3, frames_dropped: 0, errors: 0, escalated: false },
          ],
        };
      }
      return { ok: true, json: async () => [] };
    });
  });

  it('asks for a token before loading data', () => {
    render(<App />);
    expect(screen.getByText('paste an admin token to load data')).toBeTruthy();
  });

  it('saves the token and renders the calls table', async () => {
    render(<App />);
    await userEvent.type(screen.getByLabelText('admin token'), 'tok');
    await userEvent.click(screen.getByText('Save token'));
    await waitFor(() => expect(screen.getByText('abcdef01')).toBeTruthy());
  });
});
