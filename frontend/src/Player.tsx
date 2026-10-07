import { useEffect, useMemo, useRef, useState } from 'react';
import { Play, Pause, ChevronRight, Volume2, VolumeX, ArrowUp, ArrowDown, Check, BookOpen, ThumbsUp, ThumbsDown } from 'lucide-react';
import type { Short, CoverPhoto } from './api';
import { duration, mediaUrl, restore } from './api';
import { Visual } from './Visual';
import { useShortsNavigation } from './navigation';
import { atTime, timelineError } from './playback';
import { NO_PHASE, SEQUENTIAL, storyIndex, storyPhase, storyPlan } from './story';
import { StoryStage, Takeaway } from './StoryStage';
// The cover photo leads the story setup (the whole first beat) as a tilted polaroid,
// then shrinks into a round sticker in the top bar while the cards take over.
function Cover({cover,progress,hero,onError}:{cover:CoverPhoto;progress:number;hero:boolean;onError:()=>void}){
  // Slow pan and zoom across the whole short; the direction varies per photo.
  const p=matchMedia('(prefers-reduced-motion: reduce)').matches?0:Math.min(1,Math.max(0,progress)),dir=parseInt(cover.asset.id.slice(0,2),16)%4;
  const transform=`translate(${(dir%2?-3:3)*p}%,${(dir<2?2:-2)*p}%) scale(${1.08+.14*p})`;
  return <figure className={`cover-photo ${hero?'polaroid':'sticker'}`} aria-hidden="true"><span className="cover-frame"><img src={mediaUrl('assets',cover.asset.id)} alt="" style={{transform}} onError={onError}/></span><figcaption>{cover.asset.illustrative?'AI-generated':cover.alt}</figcaption></figure>;
}
export function Player({short, lessonId, previous, next, onPrevious, onNext, autoplay, onAudioError, onSources, sourcesVisible}: {short: Short; lessonId: string; previous: boolean; next: boolean; onPrevious: ()=>void; onNext: ()=>void; autoplay: boolean; onAudioError:()=>void; onSources:()=>void; sourcesVisible:boolean}) {
  const audio = useRef<HTMLAudioElement>(null);
  const [time,setTime] = useState(0), [playing,setPlaying]=useState(false), [error,setError]=useState(''), [answered,setAnswered]=useState<number|null>(null), [ended,setEnded]=useState(false);
  const [muted,setMuted]=useState(false), [reaction,setReaction]=useState<'like'|'dislike'|null>(null), [coverFailed,setCoverFailed]=useState(false);
  const lastSave = useRef(0), pendingSeek = useRef<number|null>(null);
  const frame = useRef<HTMLDivElement>(null), {view,touch}=useShortsNavigation({previous,next,onPrevious,onNext});
  const key = `playback:${lessonId}:${short.id}`;
  useEffect(()=>{ setTime(autoplay?0:restore(key,0));setPlaying(false);setError('');setAnswered(restore(`answer:${key}`,null));setReaction(restore(`reaction:${key}`,null));setEnded(false);setCoverFailed(false);lastSave.current=0;pendingSeek.current=null;
    // Each new short slides up into place, like a swipe between videos.
    if(!matchMedia('(prefers-reduced-motion: reduce)').matches)frame.current?.animate([{opacity:0,transform:'translateY(48px) scale(.97)'},{opacity:1,transform:'none'}],{duration:480,easing:'cubic-bezier(.2,.8,.2,1)'}); },[key]);
  useEffect(()=>{const current=audio.current;return()=>current?.pause();},[key]);
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
  const question=short.question,cover=coverFailed?null:short.cover;
  const plan=useMemo(()=>storyPlan(short),[short]);
  const phase=scene && !metadataError?storyPhase(short,plan,clock,!!cover):NO_PHASE;
  const story=plan.mode!=='none' && !metadataError,final=plan.items.at(-1);
  const summary=(count:number)=>`${plan.template} diagram: ${plan.items.slice(0,count).map(i=>`${i.label}${i.detail?`: ${i.detail}`:''}`).join('; ')}`;
  // Photo phase: the opening item as a lower-third card. Hero mode: one card at a time until the
  // last beat, which zooms out to the whole diagram. Everything else uses the authored visual.
  const stage=!scene?<p className="error" role="alert">{metadataError??'No scene covers this audio position. Retry lesson preparation.'}</p>:
    phase.photo || (plan.mode==='hero' && !phase.overview)?(()=>{const index=phase.photo?0:storyIndex(plan,clock);return <StoryStage items={plan.mode==='hero'?plan.items:plan.items.slice(0,1)} count={plan.items.length} current={index} photo={phase.photo} linked={SEQUENTIAL.has(plan.template)} summary={summary(index+1)} sceneId={scene.id}/>;})():
    <Visual key={`${scene.id??'legacy'}${phase.overview && plan.mode!=='chart'?':overview':''}`} scene={scene} time={clock} overview={phase.overview} pan={phase.pan}/>;
  // Motion-graphics chrome: per-beat progress and a kicker naming the current beat.
  const beat=unit?short.narration_units.indexOf(unit):-1,count=short.narration_units.length;
  const beatName=beat>=0?(short.narration_units[beat].purpose??'').replace(/^Explain\s+/i,''):'';
  const kicker=beat>=0?`${String(beat+1).padStart(2,'0')} / ${String(count).padStart(2,'0')}${beatName?` · ${beatName}`:''}`:'ONE IDEA AT A TIME';
  return <div className="player-area">
    <div className="shorts-view" ref={view} {...touch}>
    <div ref={frame} className={`player${cover?' has-cover':''}${phase.photo?' photo':''}`} tabIndex={0} aria-label="Lesson player. Space to play or pause. Up and down for shorts. Left and right to seek." onKeyDown={e=>{if(e.target!==e.currentTarget)return;if(e.code==='Space'){e.preventDefault();toggle();}if(e.code==='ArrowDown' && next){e.preventDefault();onNext();}if(e.code==='ArrowUp' && previous){e.preventDefault();onPrevious();}if(e.code==='ArrowRight'){e.preventDefault();seek(Math.min(time+5000,short.measured_duration_ms));}if(e.code==='ArrowLeft'){e.preventDefault();seek(Math.max(0,time-5000));}}}>
      <div className="player-decor" aria-hidden="true"><span/><span/><span/></div>
      {cover && <Cover key={cover.asset.id} cover={cover} progress={clock/short.measured_duration_ms} hero={phase.photo} onError={()=>setCoverFailed(true)}/>}
      <div className="player-top"><button aria-label={playing?'Pause':'Play'} disabled={!!metadataError} className="play-button" onClick={toggle}>{playing?<Pause size={22} fill="currentColor"/>:<Play size={22} fill="currentColor"/>}</button><span className="player-type">LEARNING SHORT</span><button aria-label={muted?'Unmute narration':'Mute narration'} className="volume-button" onClick={()=>{const a=audio.current;if(a){a.muted=!a.muted;setMuted(a.muted);}}}>{muted?<VolumeX size={22}/>:<Volume2 size={22}/>}</button></div>
      <div className="beat-progress" aria-hidden="true">{short.narration_units.map((u,i)=><span key={i} style={{flex:Math.max(1,u.end_ms-u.start_ms)}}><i style={{transform:`scaleX(${Math.min(1,Math.max(0,(clock-u.start_ms)/Math.max(1,u.end_ms-u.start_ms)))})`}}/></span>)}</div>
      <div className="short-title"><span className="player-kicker" key={`${short.id}:${beat}`}>{kicker}</span><h2 className="title-words" key={short.id}>{short.objective.split(/\s+/).map((word,i)=><span key={i}><span style={{animationDelay:`${i*55}ms`}}>{word}</span>{' '}</span>)}</h2></div>
      <div className={`story-stage${story?' story':''}${phase.takeaway?' takeaway':''}`}>{stage}{phase.takeaway && <Takeaway text={short.learning_outcome || (final?`${final.label}${final.detail?` — ${final.detail}`:''}`:short.objective)} outcome={!!short.learning_outcome}/>}</div>
      <div className="controls"><div className="control-row"><span className="time-readout">{duration(time)} <span>/ {duration(short.measured_duration_ms)}</span></span></div><input aria-label="Seek within short" type="range" min="0" max={short.measured_duration_ms} value={Math.min(time,short.measured_duration_ms)} step="100" style={{'--played':`${Math.min(100,time/short.measured_duration_ms*100)}%`} as React.CSSProperties} onChange={e=>seek(Number(e.target.value))}/></div>
      <audio key={key} ref={audio} src={mediaUrl('audio',short.audio_path!)} preload="auto" loop muted={muted} onLoadedMetadata={()=>{const a=audio.current!;a.currentTime=Math.min((pendingSeek.current??(autoplay?0:restore(key,0)))/1000,a.duration);pendingSeek.current=null;if(a.currentTime>=a.duration-.1)setEnded(true);if(autoplay)play();}} onPlay={()=>setPlaying(true)} onPause={()=>{setPlaying(false);if(audio.current){setTime(audio.current.currentTime*1000);localStorage.setItem(key,JSON.stringify(audio.current.currentTime*1000));}}} onSeeked={()=>{const t=(audio.current?.currentTime??0)*1000;setTime(t);localStorage.setItem(key,JSON.stringify(t));lastSave.current=t;pendingSeek.current=null;}} onEnded={()=>{setEnded(true);const a=audio.current;if(a){a.currentTime=0;setTime(0);play();}}} onError={()=>{setError('The audio file could not load. Check the local server or repair the audio.');onAudioError();}}/>
    </div>
    <div className="short-actions" aria-label="Short actions">
      <button aria-label="Like short" aria-pressed={reaction==='like'} onClick={()=>react('like')}><span><ThumbsUp size={24}/></span><small>Like</small></button>
      <button aria-label="Dislike short" aria-pressed={reaction==='dislike'} onClick={()=>react('dislike')}><span><ThumbsDown size={24}/></span><small>Dislike</small></button>
      <button aria-label={sourcesVisible?'Hide sources pane':'Show sources pane'} aria-expanded={sourcesVisible} aria-controls="lesson-details" onClick={onSources}><span><BookOpen size={24}/></span><small>Sources</small></button>
      <div className="voice-disc" aria-hidden="true"><Volume2 size={21}/></div>
    </div>
    <div className="short-navigation"><button aria-label="Previous short" disabled={!previous} onClick={onPrevious}><ArrowUp size={25}/></button><button aria-label="Next short" disabled={!next} onClick={onNext}><ArrowDown size={25}/></button></div>
    </div>
    {error && <p className="error" role="alert">{error}</p>}
    {question && ended && <div className="question"><span className="eyebrow">CHECK YOUR UNDERSTANDING · {question.allowance_ms/1000} SEC ALLOWANCE</span><p className="muted">This practice allowance is included in your session plan. Take the time you need; answers are not timed.</p><h3>{question.prompt}</h3><div className="answers">{question.options.map((option,i)=><button key={i} className={answered===i?'selected':''} aria-pressed={answered===i} onClick={()=>{setAnswered(i);localStorage.setItem(`answer:${key}`,JSON.stringify(i));}}>{answered===i && <Check size={16} aria-hidden="true"/>}{option}</button>)}</div>{answered!==null && <p role="status"><strong>{answered===question.answer_index?'Correct.':'Try this explanation.'}</strong> {question.explanation}</p>}{answered!==null && next && <button className="primary" onClick={onNext}>Continue <ChevronRight size={16}/></button>}</div>}
  </div>;
}
