import { ChangeEvent, useEffect, useState } from 'react';
import { animate, stagger } from 'animejs';
import { AnimatePresence, motion } from 'motion/react';
import { createRoot } from 'react-dom/client';
import { Area, AreaChart } from '@/components/charts/area-chart';
import './style.css';

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000';
type Document = { id: string; filename: string; size_bytes: number; status: string; created_at: string };
type Source = { document_name: string; text: string; score: number };

function SourceSignal({ sources }: { sources: Source[] }) {
  const values = sources.length ? sources.slice(0, 5).map((source) => Math.max(10, Math.round(source.score * 100))) : [42, 62, 38, 78, 54];
  const chartData = values.map((confidence, index) => ({ date: new Date(2026, 7, index + 1), confidence }));
  return <div className="signal-card reveal"><div className="signal-header"><div><span className="eyebrow">RETRIEVAL SIGNAL</span><h3>Source confidence</h3></div><span className="live-dot">LIVE</span></div><div className="signal-chart" aria-label="Bklit source confidence area chart"><AreaChart data={chartData} animationDuration={900} aspectRatio="1.45 / 1" margin={{ top: 10, right: 4, bottom: 12, left: 4 }}><Area dataKey="confidence" fill="#a49bff" stroke="#c6c1ff" strokeWidth={2.5} gradientToOpacity={0.03} showMarkers /></AreaChart></div><p>Animated with Bklit UI: each point is a ranked source chunk.</p></div>;
}

function App() {
  const [token, setToken] = useState(localStorage.token || '');
  const [email, setEmail] = useState(''); const [password, setPassword] = useState('');
  const [documents, setDocuments] = useState<Document[]>([]); const [question, setQuestion] = useState('');
  const [answer, setAnswer] = useState(''); const [sources, setSources] = useState<Source[]>([]);
  const [notice, setNotice] = useState(''); const [isAsking, setIsAsking] = useState(false);
  const headers = () => ({ Authorization: `Bearer ${token}` });

  useEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    animate('.reveal', { opacity: [0, 1], translateY: [18, 0], delay: stagger(70), duration: 700, ease: 'outExpo' });
  }, [token]);

  async function loadDocuments() { try { const response = await fetch(`${API}/documents`, { headers: headers() }); if (!response.ok) throw new Error(); setDocuments(await response.json()); } catch { setNotice('Could not load documents. Check that the API is running.'); } }
  useEffect(() => { if (token) void loadDocuments(); }, [token]);

  async function authenticate(path: 'login' | 'register') {
    setNotice('');
    try { const response = await fetch(`${API}/auth/${path}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email, password }) }); if (!response.ok) { setNotice(path === 'login' ? 'Incorrect email or password.' : 'This email is already registered.'); return; } const data = await response.json(); localStorage.token = data.access_token; setToken(data.access_token); } catch { setNotice('Could not reach CloudMind. Check that the API is running.'); }
  }
  async function upload(event: ChangeEvent<HTMLInputElement>) { const file = event.target.files?.[0]; if (!file) return; setNotice('Uploading and processing your document…'); const body = new FormData(); body.append('file', file); const response = await fetch(`${API}/documents/upload`, { method: 'POST', headers: headers(), body }); if (!response.ok) { setNotice('Upload failed. Please use a PDF or TXT within the size limit.'); return; } setNotice('Document is ready to search.'); await loadDocuments(); }
  async function removeDocument(id: string) { const response = await fetch(`${API}/documents/${id}`, { method: 'DELETE', headers: headers() }); if (!response.ok) { setNotice('Document deletion failed.'); return; } setDocuments(documents.filter((document) => document.id !== id)); setNotice('Document deleted.'); }
  async function ask() { if (!question.trim()) return; setIsAsking(true); setNotice(''); try { const response = await fetch(`${API}/ask`, { method: 'POST', headers: { ...headers(), 'Content-Type': 'application/json' }, body: JSON.stringify({ query: question }) }); if (!response.ok) throw new Error(); const data = await response.json(); setAnswer(data.answer); setSources(data.sources); } catch { setNotice('CloudMind could not answer that question.'); } finally { setIsAsking(false); } }

  if (!token) return <main className="auth-shell"><motion.section className="auth-card" initial={{ opacity: 0, y: 22, scale: .98 }} animate={{ opacity: 1, y: 0, scale: 1 }} transition={{ type: 'spring', stiffness: 120, damping: 18 }}><div className="orbit orbit-one" /><div className="orbit orbit-two" /><span className="eyebrow">PRIVATE RAG WORKSPACE</span><h1><span>☁</span> CloudMind</h1><p>Turn your documents into answers you can trust.</p><label>Email<input placeholder="you@example.com" type="email" onChange={(event) => setEmail(event.target.value)} /></label><label>Password<input placeholder="8+ characters" type="password" onChange={(event) => setPassword(event.target.value)} /></label><AnimatePresence>{notice && <motion.p className="notice error" role="alert" initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }}>{notice}</motion.p>}</AnimatePresence><button className="primary" onClick={() => authenticate('login')}>Enter your workspace <span>→</span></button><button className="link-button" onClick={() => authenticate('register')}>Create a free account</button></motion.section></main>;

  return <main className="app-shell"><nav className="reveal"><a className="brand"><span>☁</span> CloudMind</a><span className="nav-caption">Private document intelligence</span><span className="secure">● Secure workspace</span><button className="link-button" onClick={() => { localStorage.removeItem('token'); setToken(''); }}>Log out</button></nav><section className="hero reveal"><div><span className="eyebrow">YOUR KNOWLEDGE, IN MOTION</span><h1>Ask the questions<br /><em>your documents answer.</em></h1><p>Search your private library with a grounded AI assistant that always shows its work.</p><label className="upload"><input type="file" accept=".txt,.pdf" onChange={upload} /><span className="upload-icon">+</span> Upload a document <b>PDF or TXT</b></label></div><div className="hero-orb"><div className="orb-core">✦</div><div className="orb-ring ring-a" /><div className="orb-ring ring-b" /><span className="orb-label label-a">VECTOR SEARCH</span><span className="orb-label label-b">PRIVATE RAG</span></div></section><AnimatePresence>{notice && <motion.p className={`notice ${notice.includes('failed') || notice.includes('Could not') ? 'error' : ''}`} role="status" initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }}>{notice}</motion.p>}</AnimatePresence><section className="workspace"><aside className="library card reveal"><div className="section-heading"><div><span className="eyebrow">LIBRARY</span><h2>Documents</h2></div><b>{documents.length}</b></div>{documents.length ? documents.map((document) => <motion.article key={document.id} layout initial={{ opacity: 0, x: -12 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -12 }}><div><b>{document.filename}</b><span><i className={`status ${document.status}`} />{document.status} · {(document.size_bytes / 1024).toFixed(1)} KB</span></div><button aria-label={`Delete ${document.filename}`} className="icon-button" onClick={() => removeDocument(document.id)}>×</button></motion.article>) : <div className="empty"><div className="empty-mark">⌁</div><h3>Your library is quiet.</h3><p>Upload a document and CloudMind will turn it into a searchable memory.</p></div>}<div className="library-foot"><span>01</span><div><i /><i /><i /></div><span>PRIVATE INDEX</span></div></aside><section className="assistant card reveal"><span className="eyebrow">RESEARCH ASSISTANT</span><h2>What are you looking for?</h2><div className="question-box"><textarea value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="Ask anything across your library…" /><button className="primary" disabled={isAsking} onClick={ask}>{isAsking ? 'Thinking…' : <>Ask CloudMind <span>→</span></>}</button></div><AnimatePresence mode="wait">{answer ? <motion.div className="response" key="answer" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -12 }}><div className="response-top"><span className="eyebrow">GROUNDED ANSWER</span><span className="verified">✦ cited</span></div><p>{answer}</p><h3>Evidence trail</h3>{sources.map((source, index) => <motion.article key={`${source.document_name}-${index}`} initial={{ opacity: 0, x: 10 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: index * .08 }}><div><b>{source.document_name}</b><span>Source {index + 1} · relevance {source.score}</span><p>{source.text}</p></div></motion.article>)}</motion.div> : <motion.div className="assistant-blank" key="blank" initial={{ opacity: 0 }} animate={{ opacity: 1 }}><div className="sparkles">✦ · ✧ · ✦</div><p>Your answer will appear here with the source chunks that support it.</p></motion.div>}</AnimatePresence></section><SourceSignal sources={sources} /></section></main>;
}

createRoot(document.getElementById('root')!).render(<App />);
