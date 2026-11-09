import { useEffect, useState } from 'react';
import { getEvalReport, listCalls, listFeedback, runExperiment } from './api.js';

function useToken() {
  const [token, setToken] = useState(() => localStorage.getItem('vaani-token') || '');
  const save = (value) => {
    localStorage.setItem('vaani-token', value);
    setToken(value);
  };
  return [token, save];
}

function Calls({ token }) {
  const [calls, setCalls] = useState([]);
  const [error, setError] = useState('');
  useEffect(() => {
    if (!token) return;
    listCalls(token).then(setCalls).catch((e) => setError(String(e)));
  }, [token]);
  if (error) return <p role="alert">calls failed: {error}</p>;
  return (
    <table>
      <thead>
        <tr>
          <th>Call</th>
          <th>Tenant</th>
          <th>Frames</th>
          <th>Dropped</th>
          <th>Errors</th>
          <th>Escalated</th>
        </tr>
      </thead>
      <tbody>
        {calls.map((c) => (
          <tr key={c.call_id}>
            <td>{c.call_id.slice(0, 8)}</td>
            <td>{c.tenant}</td>
            <td>{c.frames_received}</td>
            <td>{c.frames_dropped}</td>
            <td>{c.errors}</td>
            <td>{c.escalated ? 'yes' : 'no'}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Eval({ token }) {
  const [report, setReport] = useState(null);
  const [name, setName] = useState('tone-v1');
  const run = () => {
    runExperiment(
      token,
      name,
      ['concise', 'detailed'],
    )
      .then(setReport)
      .catch(() => setReport({ winner: 'error' }));
  };
  useEffect(() => {
    if (!token) return;
    getEvalReport(token).then(setReport).catch(() => {});
  }, [token]);
  return (
    <div>
      <button onClick={run}>Run A/B experiment</button>
      <input aria-label="experiment name" value={name} onChange={(e) => setName(e.target.value)} />
      {report && <p>winner: {report.winner}</p>}
    </div>
  );
}

function Feedback({ token }) {
  const [items, setItems] = useState([]);
  useEffect(() => {
    if (!token) return;
    listFeedback(token).then(setItems).catch(() => {});
  }, [token]);
  return (
    <ul>
      {items.map((f, i) => (
        <li key={i}>
          {f.call_id}: {f.helpful ? 'helpful' : 'not helpful'}
        </li>
      ))}
    </ul>
  );
}

export default function App() {
  const [token, setToken] = useToken();
  const [tab, setTab] = useState('calls');
  const [draft, setDraft] = useState(token);
  return (
    <div>
      <h1>Vaani Ops Console</h1>
      <input
        aria-label="admin token"
        type="password"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
      />
      <button onClick={() => setToken(draft)}>Save token</button>
      <nav>
        {['calls', 'eval', 'feedback'].map((t) => (
          <button key={t} onClick={() => setTab(t)}>
            {t}
          </button>
        ))}
      </nav>
      {token === '' && <p>paste an admin token to load data</p>}
      {token !== '' && tab === 'calls' && <Calls token={token} />}
      {token !== '' && tab === 'eval' && <Eval token={token} />}
      {token !== '' && tab === 'feedback' && <Feedback token={token} />}
    </div>
  );
}
