import type { components } from './api.generated';
export type Lesson = components['schemas']['Lesson'];
export type Short = components['schemas']['Short'];
export type Source = components['schemas']['Source'];
export type Scene = components['schemas']['Scene'];
export type VisualScene = Short['scenes'][number];
export type TableScene = components['schemas']['TableScene'];
export type CodeScene = components['schemas']['CodeScene'];
export type ChartScene = components['schemas']['ChartScene'];
export type ImageScene = components['schemas']['ImageScene'];
export type Health = components['schemas']['ProviderHealth'];
export type SearchResult = components['schemas']['SearchItem'];
export type Evidence = components['schemas']['EvidenceRef'];
export type CoverPhoto = components['schemas']['CoverPhoto'];
// The standalone demo serves media from relative folders next to index.html instead of the API.
export const DEMO = import.meta.env.VITE_DEMO === '1';
export function mediaUrl(kind: 'audio' | 'assets', file: string) { return DEMO ? `./media/${kind}/${kind === 'assets' ? file + '.png' : file}` : `/api/${kind}/${file}`; }
export class ApiError extends Error { constructor(public code: string, message: string) { super(message); } }
export async function api<T>(url: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  const response = await fetch('/api' + url, { method: body === undefined ? 'GET' : 'POST', headers: body === undefined ? undefined : {'Content-Type':'application/json'}, body: body === undefined ? undefined : JSON.stringify(body), signal });
  if (!response.ok) { const error = await response.json().catch(() => ({code:'NETWORK_FAILED',message:'The server request failed. Check the local server, then retry.'})); throw new ApiError(error.code, error.message); }
  return response.json();
}
export function duration(ms: number) { const s = Math.ceil(ms / 1000); return `${Math.floor(s / 60)}:${String(s % 60).padStart(2,'0')}`; }
export function restore<T>(key: string, fallback: T): T { try { return JSON.parse(localStorage.getItem(key) || 'null') ?? fallback; } catch { return fallback; } }
