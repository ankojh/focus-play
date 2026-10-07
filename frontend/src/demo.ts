// Standalone demo backend: replays one saved lesson for any goal, entirely in the browser.
// Each short becomes ready SHORT_MS after the previous one, so the real UI shows live progress.
import type { Health, Lesson, Short } from './api';

declare global { interface Window { FOCUS_PLAY_DEMO_LESSON: Lesson } }

const SHORT_MS = 5000, STORE = 'focusplay:demo-lessons:v1';
type Saved = { id: string; request: Lesson['request']; created: number; cancelledAt?: number };

const template = window.FOCUS_PLAY_DEMO_LESSON;
const health: Health = { provider: 'ollama', ready: true, model_ready: true, speech_ready: true, model: template.provider_settings?.model ?? 'gemma4:12b-mlx', speech_provider: 'kokoro', voice: 'af_heart', message: 'Local model, voice and YouTube are ready.', youtube_ready: true, youtube_message: 'YouTube search and captions are ready.' } as Health;

const load = (): Saved[] => { try { return JSON.parse(localStorage.getItem(STORE) || '[]'); } catch { return []; } };
const save = (rows: Saved[]) => localStorage.setItem(STORE, JSON.stringify(rows));

function snapshot(saved: Saved, now = Date.now()): Lesson {
  const total = template.shorts.length, elapsed = (saved.cancelledAt ?? now) - saved.created;
  const ready = Math.min(total, Math.floor(elapsed / SHORT_MS)), done = ready === total;
  const status = done ? 'complete' : saved.cancelledAt ? 'cancelled' : 'running';
  const stage = done ? 'ready' : saved.cancelledAt ? 'Preparation cancelled. Ready shorts are kept.'
    : ready === 0 ? (elapsed < 1500 ? 'Searching YouTube' : elapsed < 3200 ? 'Reading video transcripts' : 'Choosing the best videos')
    : `Preparing short ${ready + 1} of ${total}`;
  const shorts = template.shorts.map((s, i): Short => i < ready ? s
    : { ...s, status: i === ready && status === 'running' ? 'generating' : 'queued', audio_path: null, measured_duration_ms: 0 });
  const updated = done ? saved.created + total * SHORT_MS : saved.cancelledAt ?? now;
  return { ...template, id: saved.id, request: saved.request, shorts, status: done ? 'ready' : ready ? 'partially_ready' : 'preparing', readiness: null,
    job: { ...template.job, id: `job_${saved.id}`, lesson_id: saved.id, status, stage, error: null, event_sequence: ready + 1 + (saved.cancelledAt ? 1000 : 0), created_at: saved.created / 1000, updated_at: updated / 1000 } } as Lesson;
}

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
const find = (id: string) => load().find(l => l.id === id);
const missing = () => json({ code: 'NOT_FOUND', message: 'This demo lesson was not found. Create a new lesson.' }, 404);

function route(method: string, path: string, body: any): Response {
  if (path === '/health') return json(health);
  if (path === '/lessons' && method === 'GET') return json(load().map(l => snapshot(l)).reverse());
  if (path === '/lessons' && method === 'POST') {
    const saved: Saved = { id: `lesson_demo_${Date.now().toString(36)}`, request: { ...template.request, ...body }, created: Date.now() };
    save([...load(), saved]);
    return json(snapshot(saved));
  }
  const match = path.match(/^\/lessons\/([^/]+)(?:\/(cancel|retry))?$/);
  if (!match) return json({ code: 'NOT_FOUND', message: 'Not available in the demo.' }, 404);
  const rows = load(), saved = rows.find(l => l.id === match[1]);
  if (!saved) return missing();
  if (match[2] === 'cancel' && !saved.cancelledAt) saved.cancelledAt = Date.now();
  // Resume from the same number of ready shorts.
  if (match[2] === 'retry' && saved.cancelledAt) { saved.created += Date.now() - saved.cancelledAt; delete saved.cancelledAt; }
  save(rows);
  return json(snapshot(saved));
}

const realFetch = window.fetch.bind(window);
window.fetch = async (input, init) => {
  const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
  if (!url.startsWith('/api/')) return realFetch(input, init);
  await new Promise(r => setTimeout(r, 120));
  return route(init?.method ?? 'GET', url.slice(4).split('?')[0], init?.body ? JSON.parse(String(init.body)) : undefined);
};

// Progress stream: a progress event every second and a done event when the lesson completes.
class DemoEventSource extends EventTarget {
  onopen: ((e: Event) => void) | null = null; onerror: ((e: Event) => void) | null = null;
  private timer: number;
  constructor(url: string) {
    super();
    const id = url.match(/\/lessons\/([^/]+)\/events/)?.[1] ?? '';
    setTimeout(() => this.onopen?.(new Event('open')), 50);
    this.timer = window.setInterval(() => {
      const saved = find(id);
      if (!saved) return this.close();
      const lesson = snapshot(saved);
      if (lesson.job.status === 'running') this.dispatchEvent(new MessageEvent('progress', { data: '{}' }));
      else { this.dispatchEvent(new MessageEvent('done', { data: JSON.stringify(lesson) })); this.close(); }
    }, 1000);
  }
  close() { clearInterval(this.timer); }
}
(window as any).EventSource = DemoEventSource;
if (!crypto.randomUUID) (crypto as any).randomUUID = () => `${Date.now()}-${Math.random().toString(16).slice(2)}`;
