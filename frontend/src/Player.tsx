import { useEffect, useMemo, useRef, useState } from 'react';
import { Play, Pause, ChevronRight, Volume2, VolumeX, ArrowUp, ArrowDown, Check, BookOpen, ThumbsUp, ThumbsDown } from 'lucide-react';
import type { Short } from './api';
import { duration, restore } from './api';
import { Visual } from './Visual';
import { Captions, Transcript } from './Captions';
import { atTime, timelineError } from './playback';
export function Player({short, lessonId, previous, next, onPrevious, onNext, autoplay, onAudioError, onSources, sourcesVisible}: {short: Short; lessonId: string; previous: boolean; next: boolean; onPrevious: ()=>void; onNext: ()=>void; autoplay: boolean; onAudioError:()=>void; onSources:()=>void; sourcesVisible:boolean}) {
  const audio = useRef<HTMLAudioElement>(null);
  const [time,setTime] = useState(0), [playing,setPlaying]=useState(false), [error,setError]=useState(''), [answered,setAnswered]=useState<number|null>(null), [ended,setEnded]=useState(false);
  const [muted,setMuted]=useState(false), [reaction,setReaction]=useState<'like'|'dislike'|null>(null);
  const [captionsVisible,setCaptionsVisible]=useState(true);
  const lastSave = useRef(0), pendingSeek = useRef<number|null>(null);
  const shortsView = useRef<HTMLDivElement>(null), touchStart = useRef<{x:number;y:number}|null>(null);
  const key = `playback:${lessonId}:${short.id}`;
  const navigation = useRef({previous,next,onPrevious,onNext});navigation.current={previous,next,onPrevious,onNext};
  useEffect(()=>{ setTime(autoplay?0:restore(key,0));setPlaying(false);setError('');setAnswered(restore(`answer:${key}`,null));setReaction(restore(`reaction:${key}`,null));setEnded(false);lastSave.current=0;pendingSeek.current=null; },[key]);
  useEffect(()=>{const current=audio.current;return()=>current?.pause();},[key]);
  useEffect(()=>{
    const view=shortsView.current;if(!view)return;
    let total=0,locked=false,direction=0,timer:ReturnType<typeof setTimeout>|undefined;
    const wheel=(event:WheelEvent)=>{
      if(event.ctrlKey || Math.abs(event.deltaX)>Math.abs(event.deltaY) || (event.target as HTMLElement).closest('input,select,textarea'))return;
      const reader=(event.target as HTMLElement).closest<HTMLElement>('.visual-reader');
      if(reader && reader.scrollHeight>reader.clientHeight+1)return;
      const delta=event.deltaY*(event.deltaMode===1?16:event.deltaMode===2?view.clientHeight:1);
      const sign=Math.sign(delta);if(!sign)return;
      const nav=navigation.current;
      if(!(sign>0?nav.next:nav.previous))return;
      event.preventDefault();
      if(sign!==direction){total=0;locked=false;direction=sign;}
      clearTimeout(timer);timer=setTimeout(()=>{total=0;locked=false;direction=0;},180);
      if(locked)return;
      total+=delta;
      if(Math.abs(total)<40)return;
      locked=true;if(sign>0)nav.onNext();else nav.onPrevious();
    };
    view.addEventListener('wheel',wheel,{passive:false});
    return()=>{view.removeEventListener('wheel',wheel);clearTimeout(timer);};
  },[]);
  const react=(value:'like'|'dislike')=>{const selected=reaction===value?null:value;setReaction(selected);localStorage.setItem(`reaction:${key}`,JSON.stringify(selected));};
  useEffect(()=>{
    let frame=0;
    const paint=()=>{const a=audio.current;if(a){const t=a.currentTime*1000;setTime(t);if(t>=short.measured_duration_ms-250)setEnded(true);if(Math.abs(t-lastSave.current)>500){localStorage.setItem(key,JSON.stringify(t));lastSave.current=t;}}frame=requestAnimationFrame(paint);};
    if(playing)frame=requestAnimationFrame(paint);
    return ()=>cancelAnimationFrame(frame);
  },[playing,key,short.measured_duration_ms]);
  const metadataError=useMemo(()=>timelineError(short),[short]);
  const play=()=>{const a=audio.current;if(!a || metadataError)return;setError('');a.play().catch(e=>{if(audio.current!==a || e.name==='AbortError')return;setError(e.name==='NotAllowedError'?'Your browser blocked autoplay. Click Play to start narration.':'Audio could not start. Click Play again or retry the lesson.');});};
  const toggle=()=>{if(playing)audio.current?.pause();else play();};
  const seek=(ms:number)=>{if(audio.current){pendingSeek.current=ms;audio.current.currentTime=ms/1000;setTime(ms);localStorage.setItem(key,JSON.stringify(ms));if(ms>=short.measured_duration_ms-100)setEnded(true);}};
  const clock=Math.min(short.measured_duration_ms,Math.max(0,time));
  const unit=atTime(short.narration_units,clock,short.measured_duration_ms);
  const scene=metadataError?undefined:atTime(short.scenes,clock,short.measured_duration_ms);
  const question=short.question;
  return <div className="player-area">
    <div className="shorts-view" ref={shortsView} onTouchStart={e=>{const t=e.touches[0],target=e.target as HTMLElement,reader=target.closest<HTMLElement>('.visual-reader');touchStart.current=e.touches.length===1 && !target.closest('input,select,textarea,button,a,summary') && !(reader && reader.scrollHeight>reader.clientHeight+1)?{x:t.clientX,y:t.clientY}:null;}} onTouchCancel={()=>{touchStart.current=null;}} onTouchEnd={e=>{const start=touchStart.current;touchStart.current=null;const t=e.changedTouches[0];if(!start || !t)return;const dy=start.y-t.clientY,dx=start.x-t.clientX;if(Math.abs(dy)<50 || Math.abs(dy)<=Math.abs(dx))return;if(dy>0 && next)onNext();else if(dy<0 && previous)onPrevious();}}>
    <div className="player" tabIndex={0} aria-label="Lesson player. Space to play or pause. Up and down for shorts. Left and right to seek." onKeyDown={e=>{if(e.target!==e.currentTarget)return;if(e.code==='Space'){e.preventDefault();toggle();}if(e.code==='ArrowDown' && next){e.preventDefault();onNext();}if(e.code==='ArrowUp' && previous){e.preventDefault();onPrevious();}if(e.code==='ArrowRight'){e.preventDefault();seek(Math.min(time+5000,short.measured_duration_ms));}if(e.code==='ArrowLeft'){e.preventDefault();seek(Math.max(0,time-5000));}}}>
      <div className="player-top"><button aria-label={playing?'Pause':'Play'} disabled={!!metadataError} className="play-button" onClick={toggle}>{playing?<Pause size={22} fill="currentColor"/>:<Play size={22} fill="currentColor"/>}</button><span className="player-type">LEARNING SHORT</span><button aria-label={muted?'Unmute narration':'Mute narration'} className="volume-button" onClick={()=>{const a=audio.current;if(a){a.muted=!a.muted;setMuted(a.muted);}}}>{muted?<VolumeX size={22}/>:<Volume2 size={22}/>}</button></div>
      <div className="short-title"><span className="player-kicker">ONE IDEA AT A TIME</span><h2>{short.objective}</h2></div>
      {scene ? <Visual scene={scene} time={clock}/> : <p className="error" role="alert">{metadataError??'No scene covers this audio position. Retry lesson preparation.'}</p>}
      <Captions text={unit?.text} visible={captionsVisible}/>
      <div className="player-bottom"><span className="channel-avatar"><Play size={16} fill="currentColor"/></span><div><strong>@focusplay</strong><span>Local voice · Your sources</span></div><span className="channel-badge">Learning</span></div>
      <div className="controls"><div className="control-row"><span className="time-readout">{duration(time)} <span>/ {duration(short.measured_duration_ms)}</span></span><span>Local narration</span></div><input aria-label="Seek within short" type="range" min="0" max={short.measured_duration_ms} value={Math.min(time,short.measured_duration_ms)} step="100" style={{'--played':`${Math.min(100,time/short.measured_duration_ms*100)}%`} as React.CSSProperties} onChange={e=>seek(Number(e.target.value))}/></div>
      <audio key={key} ref={audio} src={`/api/audio/${short.audio_path}`} preload="auto" loop muted={muted} onLoadedMetadata={()=>{const a=audio.current!;a.currentTime=Math.min((pendingSeek.current??(autoplay?0:restore(key,0)))/1000,a.duration);pendingSeek.current=null;if(a.currentTime>=a.duration-.1)setEnded(true);if(autoplay)play();}} onPlay={()=>setPlaying(true)} onPause={()=>{setPlaying(false);if(audio.current){setTime(audio.current.currentTime*1000);localStorage.setItem(key,JSON.stringify(audio.current.currentTime*1000));}}} onSeeked={()=>{const t=(audio.current?.currentTime??0)*1000;setTime(t);localStorage.setItem(key,JSON.stringify(t));lastSave.current=t;pendingSeek.current=null;}} onEnded={()=>{setEnded(true);const a=audio.current;if(a){a.currentTime=0;setTime(0);play();}}} onError={()=>{setError('The audio file could not load. Check the local server or repair the audio.');onAudioError();}}/>
    </div>
    <div className="short-actions" aria-label="Short actions">
      <button aria-label="Like short" aria-pressed={reaction==='like'} onClick={()=>react('like')}><span><ThumbsUp size={24}/></span><small>Like</small></button>
      <button aria-label="Dislike short" aria-pressed={reaction==='dislike'} onClick={()=>react('dislike')}><span><ThumbsDown size={24}/></span><small>Dislike</small></button>
      <button aria-label={sourcesVisible?'Hide sources pane':'Show sources pane'} aria-expanded={sourcesVisible} aria-controls="lesson-details" onClick={onSources}><span><BookOpen size={24}/></span><small>Sources</small></button>
      <div className="voice-disc" aria-hidden="true"><Volume2 size={21}/></div>
    </div>
    <div className="short-navigation"><button aria-label="Previous short" disabled={!previous} onClick={onPrevious}><ArrowUp size={25}/></button><button aria-label="Next short" disabled={!next} onClick={onNext}><ArrowDown size={25}/></button></div>
    </div>
    <div className="caption-settings"><button className="secondary" aria-pressed={captionsVisible} onClick={()=>setCaptionsVisible(value=>!value)}>{captionsVisible?'Hide captions':'Show captions'}</button><span>Measured phrase captions</span></div>
    <Transcript short={short} seek={seek}/>
    {error && <p className="error" role="alert">{error}</p>}
    {question && ended && <div className="question"><span className="eyebrow">CHECK YOUR UNDERSTANDING · {question.allowance_ms/1000} SEC ALLOWANCE</span><p className="muted">This practice allowance is included in your session plan. Take the time you need; answers are not timed.</p><h3>{question.prompt}</h3><div className="answers">{question.options.map((option,i)=><button key={i} className={answered===i?'selected':''} aria-pressed={answered===i} onClick={()=>{setAnswered(i);localStorage.setItem(`answer:${key}`,JSON.stringify(i));}}>{answered===i && <Check size={16} aria-hidden="true"/>}{option}</button>)}</div>{answered!==null && <p role="status"><strong>{answered===question.answer_index?'Correct.':'Try this explanation.'}</strong> {question.explanation}</p>}{answered!==null && next && <button className="primary" onClick={onNext}>Continue <ChevronRight size={16}/></button>}</div>}
    <p className="keyboard-note">Scroll or swipe: switch shorts. Space: play/pause. ↑ ↓: shorts. ← →: seek.</p>
  </div>;
}
