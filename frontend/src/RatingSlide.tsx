import { useEffect, useRef, useState } from 'react';
import { ArrowUp, ArrowDown, BookOpen, Check, Star } from 'lucide-react';
import { duration, restore } from './api';
import { useShortsNavigation } from './navigation';

// The slide after the last short: same frame and navigation as a short, but a rating instead of a video.
export function RatingSlide({lessonId,goal,shorts,mediaMs,onPrevious,onSources,sourcesVisible}:{lessonId:string;goal:string;shorts:number;mediaMs:number;onPrevious:()=>void;onSources:()=>void;sourcesVisible:boolean}){
  const {view,touch}=useShortsNavigation({previous:true,next:false,onPrevious,onNext:()=>{}});
  const ratingKey=`rating:${lessonId}`,[rating,setRating]=useState<number|null>(()=>restore(ratingKey,null)),[hover,setHover]=useState(0);
  const rate=(value:number)=>{setRating(value);localStorage.setItem(ratingKey,JSON.stringify(value));};
  const frame=useRef<HTMLDivElement>(null);
  // Slides up into place like the move between shorts.
  useEffect(()=>{if(!matchMedia('(prefers-reduced-motion: reduce)').matches)frame.current?.animate([{opacity:0,transform:'translateY(48px) scale(.97)'},{opacity:1,transform:'none'}],{duration:480,easing:'cubic-bezier(.2,.8,.2,1)'});},[]);
  return <div className="player-area">
    <div className="shorts-view" ref={view} {...touch}>
      <div ref={frame} className="player rating-slide" data-testid="rating-slide" tabIndex={0} aria-label="Lesson complete. Rate this lesson. Up for the previous short." onKeyDown={e=>{if(e.target!==e.currentTarget)return;if(e.code==='ArrowUp'){e.preventDefault();onPrevious();}}}>
        <div className="player-decor" aria-hidden="true"><span/><span/><span/></div>
        <div className="player-top"><span className="player-type">LEARNING SHORT</span></div>
        <div className="rating-card">
          <span className="rating-check" aria-hidden="true"><Check/></span>
          <span className="player-kicker">LESSON COMPLETE</span>
          <h2>How was this lesson?</h2>
          <p className="rating-summary">{goal}<span>{shorts} {shorts===1?'short':'shorts'} · {duration(mediaMs)}</span></p>
          <div className="stars" role="radiogroup" aria-label="Rate this lesson" onMouseLeave={()=>setHover(0)}>{[1,2,3,4,5].map(n=><button key={n} role="radio" aria-checked={rating===n} aria-label={`${n} star${n===1?'':'s'}`} onMouseEnter={()=>setHover(n)} onClick={()=>rate(n)}><Star fill={n<=(hover||rating||0)?'currentColor':'none'}/></button>)}</div>
          <p className="rating-thanks" role="status">{rating!==null?`Thanks for rating this lesson ${rating} out of 5.`:'Tap a star to rate.'}</p>
        </div>
      </div>
      <div className="short-actions" aria-label="Short actions">
        <button aria-label={sourcesVisible?'Hide sources pane':'Show sources pane'} aria-expanded={sourcesVisible} aria-controls="lesson-details" onClick={onSources}><span><BookOpen size={24}/></span><small>Sources</small></button>
      </div>
      <div className="short-navigation"><button aria-label="Previous short" onClick={onPrevious}><ArrowUp size={25}/></button><button aria-label="Next short" disabled><ArrowDown size={25}/></button></div>
    </div>
  </div>;
}
