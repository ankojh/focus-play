import { useEffect, useMemo, useRef, useState } from 'react';
import { ArrowLeft, ArrowUpRight, Pause, Play, SkipBack, SkipForward, Volume2, VolumeX, RotateCcw, Clapperboard } from 'lucide-react';
import { duration, type Lesson } from './api';

export type ClipShort = { id: string; index: number; objective: string };
export type Clip = { key: string; shorts: ClipShort[]; videoId: string; title: string; channel?: string | null; url: string; start: number; end: number; quotes: string[] };

type Ref = { source_id: string; start_ms?: number | null; end_ms?: number | null; quote: string };
// A short's cited segments; shorts that failed before narration fall back to their planned segments.
function plannedRefs(lesson: Lesson, ids: string[]): Ref[] {
  return ids.flatMap(id => lesson.sources.flatMap(s => s.segments.filter(g => g.id === id).map(g => ({ source_id: s.id, start_ms: g.start_ms, end_ms: g.end_ms, quote: g.text }))));
}
function reelUnits(lesson: Lesson): { id: string; title: string; refs: Ref[] }[] {
  // A lesson that failed before any short was written still has its planned objectives.
  if (!lesson.shorts.length) return lesson.objectives.map((o, i) => ({ id: `objective:${i}`, title: o.title, refs: plannedRefs(lesson, o.evidence_segment_ids) }));
  return lesson.shorts.map(short => {
    if (short.evidence_references.length) return { id: short.id, title: short.objective, refs: short.evidence_references };
    const objective = lesson.objectives.find(o => short.concept_id && o.concept_id === short.concept_id) ?? lesson.objectives.find(o => o.title === short.objective);
    return { id: short.id, title: short.objective, refs: plannedRefs(lesson, objective?.evidence_segment_ids ?? []) };
  });
}

// Every short's source caption segments, in lesson order. Within a short, overlapping or adjacent
// segments of the same video merge into one clip; a clip inside the one just before it is folded
// into that clip, so the same moment never plays twice in a row.
export function sourceReel(lesson: Lesson): Clip[] {
  const clips: Clip[] = [];
  reelUnits(lesson).forEach((short, shortIndex) => {
    const byVideo = new Map<string, { source: Lesson['sources'][number]; refs: { start: number; end: number; quote: string }[] }>();
    for (const ref of short.refs) {
      const source = lesson.sources.find(s => s.id === ref.source_id);
      if (!source?.video_id || ref.start_ms == null || ref.end_ms == null || ref.end_ms <= ref.start_ms) continue;
      const group = byVideo.get(source.id) ?? { source, refs: [] };
      group.refs.push({ start: ref.start_ms, end: ref.end_ms, quote: ref.quote });
      byVideo.set(source.id, group);
    }
    for (const { source, refs } of byVideo.values()) {
      const merged: Clip[] = [];
      for (const ref of refs.sort((a, b) => a.start - b.start)) {
        const last = merged.at(-1);
        if (last && ref.start <= last.end + 1500) { last.end = Math.max(last.end, ref.end); if (!last.quotes.includes(ref.quote)) last.quotes.push(ref.quote); continue; }
        merged.push({ key: `${short.id}:${source.id}:${ref.start}`, shorts: [{ id: short.id, index: shortIndex, objective: short.title }], videoId: source.video_id!, title: source.title, channel: source.channel, url: source.url ?? `https://www.youtube.com/watch?v=${source.video_id}`, start: ref.start, end: ref.end, quotes: [ref.quote] });
      }
      for (const clip of merged) {
        const previous = clips.at(-1);
        if (previous && previous.videoId === clip.videoId && previous.start <= clip.start && clip.end <= previous.end) {
          if (!previous.shorts.some(s => s.id === short.id)) previous.shorts.push(clip.shorts[0]);
        } else clips.push(clip);
      }
    }
  });
  return clips;
}

type YTPlayer = { loadVideoById(o: { videoId: string; startSeconds: number }): void; playVideo(): void; pauseVideo(): void; seekTo(s: number, allow: boolean): void; mute(): void; unMute(): void; getCurrentTime(): number; getPlayerState(): number; destroy(): void };
declare global { interface Window { YT?: { Player: new (el: HTMLElement, o: object) => YTPlayer }; onYouTubeIframeAPIReady?: () => void } }
const PLAYING = 1, PAUSED = 2, ENDED = 0;
let youtubeApi: Promise<NonNullable<Window['YT']>> | null = null;
function loadYouTube() {
  if (window.YT?.Player) return Promise.resolve(window.YT);
  youtubeApi ??= new Promise((resolve, reject) => {
    const previous = window.onYouTubeIframeAPIReady;
    window.onYouTubeIframeAPIReady = () => { previous?.(); resolve(window.YT!); };
    const script = document.createElement('script');
    script.src = 'https://www.youtube.com/iframe_api';
    script.onerror = () => { youtubeApi = null; script.remove(); reject(new Error('YouTube unavailable')); };
    document.head.append(script);
  });
  return youtubeApi;
}

type Engine = { go(i: number): void; toggle(): void; setMuted(m: boolean): void };
type Slot = { player: YTPlayer; clip: number; primed: boolean };

// Two stacked YouTube players: the visible one plays the current clip while the hidden one loads the
// next clip muted and parks at its start, so each cut is a swap rather than a fresh load.
export function SourceReel({ lesson, startShortId, onBack }: { lesson: Lesson; startShortId: string; onBack: (shortId: string) => void }) {
  const clips = useMemo(() => sourceReel(lesson), [lesson]);
  const startShort = lesson.shorts.findIndex(s => s.id === startShortId);
  const startIndex = Math.max(0, clips.findIndex(c => c.shorts.some(s => s.index >= startShort)));
  // Back lands on the short you came from when this clip is one of its sources, else the clip's first short.
  const shortOf = (c?: Clip) => c ? (c.shorts.find(s => s.id === startShortId) ?? c.shorts[0]).id : startShortId;
  const label = (c: Clip) => c.shorts.map(s => `${String(s.index + 1).padStart(2, '0')} · ${s.objective}`).join('  +  ');
  const hosts = [useRef<HTMLDivElement>(null), useRef<HTMLDivElement>(null)];
  const engine = useRef<Engine | null>(null), list = useRef<HTMLOListElement>(null);
  const [status, setStatus] = useState<'loading' | 'ready' | 'offline' | 'done'>('loading');
  const [index, setIndex] = useState(startIndex), [active, setActive] = useState(0), [time, setTime] = useState(0);
  const [playing, setPlaying] = useState(false), [blocked, setBlocked] = useState(false), [muted, setMutedState] = useState(false), [failed, setFailed] = useState<number[]>([]);

  useEffect(() => {
    if (!clips.length) return;
    let disposed = false, timer = 0, startCheck = 0, current = -1, activeSlot = 0, userMuted = false;
    const slots: Slot[] = [], unavailable = new Set<number>();
    const hidden = () => slots[1 - activeSlot];
    const prime = (i: number) => {
      const slot = hidden();
      while (i < clips.length && unavailable.has(i)) i++;
      if (i >= clips.length || slot.clip === i) return;
      slot.clip = i; slot.primed = false;
      slot.player.mute(); slot.player.loadVideoById({ videoId: clips[i].videoId, startSeconds: clips[i].start / 1000 });
    };
    const finish = () => { slots[activeSlot].player.pauseVideo(); current = -1; setPlaying(false); setStatus('done'); };
    const go = (target: number) => {
      let i = target;
      while (i < clips.length && unavailable.has(i)) i++;
      if (i >= clips.length) return finish();
      const clip = clips[i];
      if (hidden().clip === i) {
        // Seamless cut: the next clip is already buffered at its start in the hidden player.
        slots[activeSlot].player.pauseVideo();
        activeSlot = 1 - activeSlot;
        const slot = slots[activeSlot];
        if (!slot.primed) slot.primed = true;
        if (!userMuted) slot.player.unMute();
        slot.player.playVideo();
      } else {
        const slot = slots[activeSlot];
        slot.clip = i; slot.primed = true;
        if (!userMuted) slot.player.unMute();
        slot.player.loadVideoById({ videoId: clip.videoId, startSeconds: clip.start / 1000 });
      }
      current = i;
      setIndex(i); setActive(activeSlot); setTime(clip.start); setStatus('ready'); setBlocked(false);
      // Browsers that refuse unmuted autoplay leave the player unstarted; offer a tap to start.
      clearTimeout(startCheck);
      startCheck = window.setTimeout(() => { if (!disposed && current === i && slots[activeSlot].player.getPlayerState() !== PLAYING) setBlocked(true); }, 3000);
      prime(i + 1);
    };
    const onState = (slotIndex: number, state: number) => {
      const slot = slots[slotIndex];
      if (slotIndex !== activeSlot) {
        // The hidden player reached playback: park it, muted, at the clip start.
        if (state === PLAYING && !slot.primed && slot.clip >= 0) { slot.player.pauseVideo(); slot.player.seekTo(clips[slot.clip].start / 1000, true); slot.primed = true; }
        return;
      }
      if (state === PLAYING) { setPlaying(true); setBlocked(false); }
      if (state === PAUSED) setPlaying(false);
      if (state === ENDED && current >= 0) go(current + 1);
    };
    const onError = (slotIndex: number) => {
      const slot = slots[slotIndex];
      if (slot.clip < 0) return;
      unavailable.add(slot.clip); setFailed([...unavailable]);
      if (slotIndex === activeSlot && slot.clip === current) go(current + 1);
      else { slot.clip = -1; if (current >= 0) prime(current + 1); }
    };
    loadYouTube().then(YT => {
      if (disposed) return;
      let ready = 0;
      hosts.forEach((host, slotIndex) => {
        const mount = document.createElement('div');
        host.current!.replaceChildren(mount);
        slots[slotIndex] = { clip: -1, primed: false, player: new YT.Player(mount, {
          width: '100%', height: '100%',
          playerVars: { controls: 0, disablekb: 1, playsinline: 1, rel: 0, iv_load_policy: 3, fs: 0, origin: location.origin },
          events: { onReady: () => { if (++ready === 2 && !disposed) go(startIndex); }, onStateChange: (e: { data: number }) => onState(slotIndex, e.data), onError: () => onError(slotIndex) },
        }) };
      });
      timer = window.setInterval(() => {
        if (current < 0) return;
        const player = slots[activeSlot].player, clip = clips[current];
        if (player.getPlayerState() !== PLAYING) return;
        const t = player.getCurrentTime() * 1000;
        setTime(t);
        if (t >= clip.end - 80) go(current + 1);
      }, 80);
    }).catch(() => { if (!disposed) setStatus('offline'); });
    engine.current = {
      go,
      toggle: () => {
        if (current < 0) return go(0);
        const player = slots[activeSlot].player;
        if (player.getPlayerState() === PLAYING) player.pauseVideo(); else { if (!userMuted) player.unMute(); player.playVideo(); }
      },
      setMuted: m => { userMuted = m; if (slots[activeSlot]) (m ? slots[activeSlot].player.mute() : slots[activeSlot].player.unMute()); setMutedState(m); },
    };
    return () => { disposed = true; clearInterval(timer); clearTimeout(startCheck); engine.current = null; for (const slot of slots) slot?.player.destroy(); };
  }, [clips]);

  useEffect(() => { list.current?.querySelector('[aria-current="true"]')?.scrollIntoView({ block: 'nearest', behavior: 'smooth' }); }, [index]);
  useEffect(() => {
    const keys = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLElement && e.target.closest('input,textarea,select')) return;
      if (e.code === 'Space') { e.preventDefault(); engine.current?.toggle(); }
      if (e.code === 'ArrowRight') { e.preventDefault(); engine.current?.go(index + 1); }
      if (e.code === 'ArrowLeft') { e.preventDefault(); engine.current?.go(Math.max(0, index - 1)); }
      if (e.code === 'Escape') onBack(shortOf(clips[index]));
    };
    addEventListener('keydown', keys);
    return () => removeEventListener('keydown', keys);
  }, [index, clips, onBack, startShortId]);

  const clip = clips[index];
  const back = () => onBack(shortOf(clip));
  if (!clip) return <div className="reel-page"><button className="secondary" onClick={back}><ArrowLeft size={15} /> Back to short</button><div className="reel-empty"><Clapperboard size={30} /><h2>No source clips yet</h2><p className="muted">Clips appear once a short has timestamped YouTube sources.</p></div></div>;
  const progress = Math.min(1, Math.max(0, (time - clip.start) / (clip.end - clip.start)));
  const total = clips.reduce((sum, c) => sum + c.end - c.start, 0);
  return <div className="reel-page">
    <div className="reel-heading"><button className="secondary" onClick={back}><ArrowLeft size={15} /> Back to short</button><div><span className="eyebrow">SOURCE CLIPS · {clips.length} CHUNKS · {duration(total)}</span><h1>{lesson.request.goal}</h1></div></div>
    <div className="reel-grid">
      <section className="reel-main" aria-label="Source clip player">
        <div className="reel-stage">
          {hosts.map((host, i) => <div key={i} ref={host} className={`reel-video${i === active ? ' active' : ''}`} aria-hidden={i !== active} />)}
          <button className="reel-surface" aria-label={playing ? 'Pause clip' : 'Play clip'} onClick={() => engine.current?.toggle()} />
          {status === 'loading' && <div className="reel-overlay"><span className="reel-spinner" /><p>Loading YouTube…</p></div>}
          {status === 'offline' && <div className="reel-overlay"><p>YouTube could not load. Source clips need internet access.</p><a className="secondary" href={`${clip.url}&t=${Math.floor(clip.start / 1000)}s`} target="_blank" rel="noreferrer">Open on YouTube <ArrowUpRight size={14} /></a></div>}
          {status === 'done' && <div className="reel-overlay"><p>That’s every source clip in this lesson.</p><div className="reel-overlay-actions"><button className="secondary" onClick={() => engine.current?.go(0)}><RotateCcw size={14} /> Watch again</button><button className="primary" onClick={back}>Back to short</button></div></div>}
          {blocked && status === 'ready' && <button className="reel-overlay reel-start" onClick={() => engine.current?.toggle()}><Play size={34} fill="currentColor" /><p>Click to start</p></button>}
        </div>
        <div className="reel-progress" aria-hidden="true">{clips.map((c, i) => <span key={c.key} className={failed.includes(i) ? 'failed' : ''} style={{ flex: c.end - c.start }}><i style={{ transform: `scaleX(${i < index ? 1 : i === index ? progress : 0})` }} /></span>)}</div>
        <div className="reel-controls">
          <button aria-label="Previous clip" disabled={index === 0} onClick={() => engine.current?.go(index - 1)}><SkipBack size={18} fill="currentColor" /></button>
          <button className="reel-play" aria-label={playing ? 'Pause' : 'Play'} onClick={() => engine.current?.toggle()}>{playing ? <Pause size={20} fill="currentColor" /> : <Play size={20} fill="currentColor" />}</button>
          <button aria-label="Next clip" disabled={index >= clips.length - 1} onClick={() => engine.current?.go(index + 1)}><SkipForward size={18} fill="currentColor" /></button>
          <button aria-label={muted ? 'Unmute' : 'Mute'} onClick={() => engine.current?.setMuted(!muted)}>{muted ? <VolumeX size={18} /> : <Volume2 size={18} />}</button>
          <span className="reel-time">{duration(Math.max(0, time - clip.start))} / {duration(clip.end - clip.start)} · clip {index + 1} of {clips.length}</span>
        </div>
        <div className="reel-now" key={clip.key}>
          <span className="eyebrow">{clip.shorts.length > 1 ? 'SHORTS' : 'SHORT'} {label(clip).toUpperCase()}</span>
          <h2>{clip.title}</h2>
          <p className="muted">{clip.channel ? `${clip.channel} · ` : ''}{duration(clip.start)}–{duration(clip.end)} <a href={`${clip.url}${clip.url.includes('?') ? '&' : '?'}t=${Math.floor(clip.start / 1000)}s`} target="_blank" rel="noreferrer">Open on YouTube <ArrowUpRight size={12} /></a></p>
          {clip.quotes.map((q, i) => <blockquote key={i}>{q}</blockquote>)}
        </div>
      </section>
      <aside className="reel-side" aria-label="Clip list">
        <ol ref={list}>{clips.map((c, i) => <li key={c.key}>
          {(i === 0 || label(clips[i - 1]) !== label(c)) && <span className="reel-group">{label(c)}</span>}
          <button className={`reel-item${i === index ? ' current' : ''}`} aria-current={i === index} disabled={failed.includes(i)} onClick={() => engine.current?.go(i)}>
            <span className="reel-thumb"><img src={`https://i.ytimg.com/vi/${c.videoId}/mqdefault.jpg`} alt="" loading="lazy" /><small>{duration(c.end - c.start)}</small></span>
            <span><strong>{c.title}</strong><small>{failed.includes(i) ? 'Not available to embed' : `${c.channel ? `${c.channel} · ` : ''}${duration(c.start)}–${duration(c.end)}`}</small></span>
          </button>
        </li>)}</ol>
      </aside>
    </div>
  </div>;
}
