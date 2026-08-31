import { ChangeEvent, useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './style.css';

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000';
type Document = { id: string; filename: string; size_bytes: number; status: string; created_at: string };
type Source = { document_name: string; text: string; score: number };

function App() {
  const [token, setToken] = useState(localStorage.token || '');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [documents, setDocuments] = useState<Document[]>([]);
  const [question, setQuestion] = useState('');
  const [answer, setAnswer] = useState('');
  const [sources, setSources] = useState<Source[]>([]);
  const [notice, setNotice] = useState('');
  const headers = () => ({ Authorization: `Bearer ${token}` });

  async function loadDocuments() {
    try {
      const response = await fetch(`${API}/documents`, { headers: headers() });
      if (!response.ok) throw new Error();
      setDocuments(await response.json());
    } catch { setNotice('Could not load documents. Check that the API is running.'); }
  }

  useEffect(() => { if (token) void loadDocuments(); }, [token]);

  async function authenticate(path: 'login' | 'register') {
    setNotice('');
    try {
      const response = await fetch(`${API}/auth/${path}`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email, password }),
      });
      if (!response.ok) { setNotice(path === 'login' ? 'Incorrect email or password.' : 'This email is already registered.'); return; }
      const data = await response.json(); localStorage.token = data.access_token; setToken(data.access_token);
    } catch { setNotice('Could not reach CloudMind. Check that the API is running.'); }
  }

  async function upload(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]; if (!file) return;
    setNotice('Uploading and processing your document…');
    const body = new FormData(); body.append('file', file);
    const response = await fetch(`${API}/documents/upload`, { method: 'POST', headers: headers(), body });
    if (!response.ok) { setNotice('Upload failed. Please use a PDF or TXT within the size limit.'); return; }
    setNotice('Document is ready to search.'); await loadDocuments();
  }

  async function removeDocument(id: string) {
    const response = await fetch(`${API}/documents/${id}`, { method: 'DELETE', headers: headers() });
    if (!response.ok) { setNotice('Document deletion failed.'); return; }
    setDocuments(documents.filter((document) => document.id !== id)); setNotice('Document deleted.');
  }

  async function ask() {
    if (!question.trim()) return;
    setNotice('');
    const response = await fetch(`${API}/ask`, { method: 'POST', headers: { ...headers(), 'Content-Type': 'application/json' }, body: JSON.stringify({ query: question }) });
    if (!response.ok) { setNotice('CloudMind could not answer that question.'); return; }
    const data = await response.json(); setAnswer(data.answer); setSources(data.sources);
  }

  if (!token) return <main className="auth-shell"><section className="auth-card"><span className="eyebrow">PRIVATE RAG WORKSPACE</span><h1>☁ CloudMind</h1><p>Turn your documents into answers you can trust.</p><label>Email<input placeholder="you@example.com" type="email" onChange={(event) => setEmail(event.target.value)} /></label><label>Password<input placeholder="8+ characters" type="password" onChange={(event) => setPassword(event.target.value)} /></label>{notice && <p className="notice error" role="alert">{notice}</p>}<button className="primary" onClick={() => authenticate('login')}>Log in</button><button className="link-button" onClick={() => authenticate('register')}>Create a free account</button></section></main>;

  return <main><nav><a className="brand">☁ CloudMind</a><span className="nav-caption">Private document intelligence</span><button className="link-button" onClick={() => { localStorage.removeItem('token'); setToken(''); }}>Log out</button></nav><section className="hero"><span className="eyebrow">YOUR KNOWLEDGE, SEARCHABLE</span><h1>Ask your documents anything.</h1><p>Upload notes, research, and technical docs—then get grounded answers with the original sources attached.</p><label className="upload"><input type="file" accept=".txt,.pdf" onChange={upload} />Upload PDF or TXT <span>↗</span></label></section>{notice && <p className={`notice ${notice.includes('failed') || notice.includes('Could not') ? 'error' : ''}`} role="status">{notice}</p>}<section className="workspace"><aside className="card documents"><div className="section-heading"><div><span className="eyebrow">LIBRARY</span><h2>Documents</h2></div><b>{documents.length}</b></div>{documents.length ? documents.map((document) => <article key={document.id}><div><b>{document.filename}</b><span><i className={`status ${document.status}`} />{document.status} · {(document.size_bytes / 1024).toFixed(1)} KB</span></div><button aria-label={`Delete ${document.filename}`} className="icon-button" onClick={() => removeDocument(document.id)}>×</button></article>) : <div className="empty"><span>⌁</span><p>Upload your first document to begin.</p></div>}</aside><section className="card assistant"><span className="eyebrow">RESEARCH ASSISTANT</span><h2>Find the answer in your library.</h2><textarea value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="What would you like to know?" /><button className="primary" onClick={ask}>Ask CloudMind <span>→</span></button>{answer && <div className="response"><span className="eyebrow">GROUNDED ANSWER</span><p>{answer}</p><h3>Sources</h3>{sources.map((source, index) => <article key={`${source.document_name}-${index}`}><div><b>{source.document_name}</b><span>Relevance {source.score}</span><p>{source.text}</p></div></article>)}</div>}</section></section></main>;
}

createRoot(document.getElementById('root')!).render(<App />);
