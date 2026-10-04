import { useEffect, useRef, useState } from 'react';
import { Play, Pause, RotateCcw, ChevronRight, Volume2, VolumeX, ArrowUp, ArrowDown, BookOpen, Sparkles, HelpCircle } from 'lucide-react';
import type { Short } from './api';
import { duration, restore } from './api';
import { Diagram } from './Diagram';
export function Player({short, lessonId, previous, next, onPrevious, onNext, autoplay, onAudioError, onSources, onExample, onExplain, extrasDisabled}: {short: Short; lessonId: string; previous: boolean; next: boolean; onPrevious: ()=>void; onNext: ()=>void; autoplay: boolean; onAudioError:()=>void; onSources:()=>void; onExample:()=>void; onExplain:()=>void; extrasDisabled:boolean}) {
  const audio = useRef<HTMLAudioElement>(null);
  const [time,setTime] = useState(0), [playing,setPlaying]=useState(false), [error,setError]=useState(''), [answered,setAnswered]=useState<number|null>(null), [ended,setEnded]=useState(false);
  const [muted,setMuted]=useState(false);
  const lastSave = useRef(0), userStarted = useRef(false), pendingSeek = useRef<number|null>(null);
  const key = `playback:${lessonId}:${short.id}`;
  useEffect(()=>{ setTime(restore(key,0));setPlaying(false);setError('');setAnswered(restore(`answer:${key}`,null));setEnded(false);lastSave.current=0;pendingSeek.current=null; },[key]);
  useEffect(()=>{
    let frame=0;
    const paint=()=>{const a=audio.current;if(a){const t=a.currentTime*1000;setTime(t);if(Math.abs(t-lastSave.current)>500){localStorage.setItem(key,JSON.stringify(t));lastSave.current=t;}}frame=requestAnimationFrame(paint);};
    if(playing)frame=requestAnimationFrame(paint);
    return ()=>cancelAnimationFrame(frame);
  },[playing,key]);
  const play=()=>{ const a=audio.current;if(!a)return;userStarted.current=true; a.play().catch(()=>setError('Audio could not start. Click Play again or retry the lesson.')); };
  const toggle=()=>{if(playing)audio.current?.pause();else play();};
  const seek=(ms:number)=>{if(audio.current){pendingSeek.current=ms;audio.current.currentTime=ms/1000;setTime(ms);localStorage.setItem(key,JSON.stringify(ms));setEnded(ms>=short.measured_duration_ms-100);}};
  const unit=short.narration_units.find(u=>u.start_ms<=time && time<u.end_ms) ?? (ended?short.narration_units.at(-1):short.narration_units[0]);
  const scene=short.scenes.find(s=>time>=s.start_ms && time<=s.end_ms)??short.scenes[0];
  const question=short.question;
  return <div className="player-area">
    <div className="shorts-view">
    <div className="player" tabIndex={0} aria-label="Lesson player. Space to play or pause. Arrow keys to seek." onKeyDown={e=>{if(e.target!==e.currentTarget)return;if(e.code==='Space'){e.preventDefault();toggle();}if(e.code==='ArrowRight'){e.preventDefault();seek(Math.min(time+5000,short.measured_duration_ms));}if(e.code==='ArrowLeft'){e.preventDefault();seek(Math.max(0,time-5000));}}}>
      <div className="player-top"><button aria-label={playing?'Pause':'Play'} className="play-button" onClick={toggle}>{playing?<Pause size={22} fill="currentColor"/>:<Play size={22} fill="currentColor"/>}</button><span className="player-type">LEARNING SHORT</span><button aria-label={muted?'Unmute narration':'Mute narration'} className="volume-button" onClick={()=>{const a=audio.current;if(a){a.muted=!a.muted;setMuted(a.muted);}}}>{muted?<VolumeX size={22}/>:<Volume2 size={22}/>}</button></div>
      <div className="short-title"><span className="player-kicker">ONE IDEA AT A TIME</span><h2>{short.objective}</h2></div>
      {scene && <Diagram scene={scene} time={time}/>}
      <div className="captions" data-testid="captions" aria-live="off">{unit?.text}</div>
      <div className="player-bottom"><span className="channel-avatar"><Play size={16} fill="currentColor"/></span><div><strong>@focusplay</strong><span>Local voice · Your sources</span></div><span className="channel-badge">Learning</span></div>
      <div className="controls"><div className="control-row"><span className="time-readout">{duration(time)} <span>/ {duration(short.measured_duration_ms)}</span></span><span>Local narration</span></div><input aria-label="Seek within short" type="range" min="0" max={short.measured_duration_ms} value={Math.min(time,short.measured_duration_ms)} step="100" style={{'--played':`${Math.min(100,time/short.measured_duration_ms*100)}%`} as React.CSSProperties} onChange={e=>seek(Number(e.target.value))}/></div>
      <audio key={short.id} ref={audio} src={`/api/audio/${short.audio_path}`} preload="metadata" muted={muted} onLoadedMetadata={()=>{const a=audio.current!;a.currentTime=Math.min((pendingSeek.current??restore(key,0))/1000,a.duration);pendingSeek.current=null;setEnded(a.currentTime>=a.duration-.1);if(autoplay && userStarted.current)play();}} onPlay={()=>setPlaying(true)} onPause={()=>{setPlaying(false);if(audio.current){setTime(audio.current.currentTime*1000);localStorage.setItem(key,JSON.stringify(audio.current.currentTime*1000));}}} onSeeked={()=>setTime((audio.current?.currentTime??0)*1000)} onEnded={()=>{setPlaying(false);setEnded(true);if(autoplay && next && !question)onNext();}} onError={()=>{setError('The audio file could not load. Check the local server or repair the audio.');onAudioError();}}/>
    </div>
    <div className="short-actions" aria-label="Short actions">
      <button aria-label="Replay short" onClick={()=>{seek(0);play();}}><span><RotateCcw size={24}/></span><small>Replay</small></button>
      <button aria-label="View sources" onClick={onSources}><span><BookOpen size={24}/></span><small>Sources</small></button>
      <button aria-label="Show an example" disabled={extrasDisabled} onClick={onExample}><span><Sparkles size={24}/></span><small>Example</small></button>
      <button aria-label="Explain again" disabled={extrasDisabled} onClick={onExplain}><span><HelpCircle size={24}/></span><small>Explain</small></button>
      <div className="voice-disc" aria-hidden="true"><Volume2 size={21}/></div>
    </div>
    <div className="short-navigation"><button aria-label="Previous short" disabled={!previous} onClick={onPrevious}><ArrowUp size={25}/></button><button aria-label="Next short" disabled={!next} onClick={onNext}><ArrowDown size={25}/></button></div>
    </div>
    {error && <p className="error" role="alert">{error}</p>}
    {question && ended && <div className="question"><span className="eyebrow">CHECK YOUR UNDERSTANDING · 20 SEC</span><h3>{question.prompt}</h3><div className="answers">{question.options.map((option,i)=><button key={i} className={answered===i?'selected':''} onClick={()=>{setAnswered(i);localStorage.setItem(`answer:${key}`,JSON.stringify(i));}}>{option}</button>)}</div>{answered!==null && <p role="status"><strong>{answered===question.answer_index?'Correct.':'Try this explanation.'}</strong> {question.explanation}</p>}{answered!==null && next && <button className="primary" onClick={onNext}>Continue <ChevronRight size={16}/></button>}</div>}
    <p className="keyboard-note">Click Play to start audio. Space: play or pause. Arrow keys: seek.</p>
  </div>;
}
