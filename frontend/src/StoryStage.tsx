import { useLayoutEffect, useRef, useSyncExternalStore, type CSSProperties } from 'react';
import { Check } from 'lucide-react';
import { ICONS } from './icons';
import { cardAnatomy, entityColor, ROLE_COLORS, ROLE_LABELS } from './diagramLayout';
import type { StoryItem } from './story';

const motionQuery='(prefers-reduced-motion: reduce)';
const subscribeMotion=(callback:()=>void)=>{const media=matchMedia(motionQuery);media.addEventListener('change',callback);return()=>media.removeEventListener('change',callback);};
export const useReducedMotion=()=>useSyncExternalStore(subscribeMotion,()=>matchMedia(motionQuery).matches,()=>true);

// One item as an HTML card, spaced with the same anatomy as the SVG diagram cards.
export function StoryCard({item,index,count,variant}:{item:StoryItem;index:number;count:number;variant:'hero'|'lower'}){
  const a=cardAnatomy(1,false),scale=variant==='hero'?1.5:1,Icon=item.icon?ICONS[item.icon]:undefined;
  const style={'--inner':`${a.inner*scale}px`,'--icon':`${a.iconSize}em`,'--blob':`${a.blobRadius*2}em`,'--role-gap':`${a.roleGap}em`,'--label-gap':`${a.labelGap}em`,'--detail-gap':`${a.detailGap}em`,
    '--entity':entityColor(item.id),'--semantic':ROLE_COLORS[item.role]??ROLE_COLORS.neutral} as CSSProperties;
  return <article className={`story-card story-${variant}`} style={style} data-testid={`node-${item.id}`} data-focused="true" aria-label={`Item ${index+1} of ${count}: ${item.label}${item.detail?`. ${item.detail}`:''}`}>
    <div className="story-card-head" aria-hidden="true"><span className="story-icon">{Icon?<Icon/>:index+1}</span><span className="story-role">{ROLE_LABELS[item.role]??item.role} · {index+1} of {count}</span></div>
    <p className="story-label">{item.label}</p>{item.detail && <p className="story-detail">{item.detail}</p>}
  </article>;
}

// The current item large and centred; covered items shrink into a progress strip above it.
// With a cover photo, the opening item is a lower-third card over the photo and the strip waits.
export function StoryStage({items,count,current,photo,linked,summary,sceneId}:{items:StoryItem[];count:number;current:number;photo:boolean;linked:boolean;summary:string;sceneId?:string|null}){
  const reduced=useReducedMotion(),item=items[current];
  const stage=useRef<HTMLDivElement>(null),strip=useRef<HTMLOListElement>(null),slot=useRef<HTMLDivElement>(null);
  const last=useRef<{index:number;card:HTMLElement;box:{x:number;y:number;w:number;h:number}}|null>(null);
  useLayoutEffect(()=>{
    const host=stage.current,card=slot.current?.firstElementChild as HTMLElement|null,previous=last.current;
    // Stepping forward one item flies a copy of the old card into its chip. Offsets ignore the
    // entrance transform, so the start box is the settled card, not a mid-animation frame.
    const chip=previous && previous.index===current-1?strip.current?.children[previous.index] as HTMLElement|undefined:undefined;
    if(host && chip && previous && !reduced){
      const from=previous.box,to={x:chip.offsetLeft,y:chip.offsetTop,w:chip.offsetWidth,h:chip.offsetHeight},k=Math.min(to.w/from.w,to.h/from.h);
      const ghost=previous.card.cloneNode(true) as HTMLElement;
      ghost.classList.add('ghost');ghost.removeAttribute('data-testid');ghost.setAttribute('aria-hidden','true');
      Object.assign(ghost.style,{left:`${from.x}px`,top:`${from.y}px`,width:`${from.w}px`});
      host.append(ghost);
      ghost.animate([{transform:'none',opacity:1},{transform:`translate(${to.x+to.w/2-from.x-from.w*k/2}px,${to.y+to.h/2-from.y-from.h*k/2}px) scale(${k})`,opacity:0}],{duration:520,easing:'cubic-bezier(.55,0,.25,1)'}).onfinish=()=>ghost.remove();
    }
    if(card)last.current={index:current,card,box:{x:card.offsetLeft,y:card.offsetTop,w:card.offsetWidth,h:card.offsetHeight}};
  });
  return <div ref={stage} className={`hero-stage visual-reader${photo?' photo':''}`} tabIndex={0} data-scene-id={sceneId??undefined} role="group" aria-label={`Story view, item ${current+1} of ${count}. Scroll to read the whole card.`}>
    <p className="sr-only">{summary}</p>
    {!photo && <ol ref={strip} className={`story-strip${linked?' linked':''}${count>6?' many':''}`} aria-label={`Progress: item ${current+1} of ${count}`}>
      {Array.from({length:count},(_,i)=>{
        const it=items[i],status=!it || i>current?'next':i<current?'done':'current',Icon=status!=='next' && it?.icon?ICONS[it.icon]:undefined;
        return <li key={i} data-testid={`chip-${i}`} data-status={status} style={{'--entity':it?entityColor(it.id):undefined} as CSSProperties} aria-label={status==='next'?`${i+1}: coming up`:`${i+1}: ${it.label}${status==='current'?', now':', covered'}`}>
          <span className="chip-dot" aria-hidden="true">{Icon?<><Icon/><b>{i+1}</b></>:<em>{i+1}</em>}</span>
          {count<=4 && status!=='next' && <small aria-hidden="true">{it.label}</small>}
        </li>;
      })}
    </ol>}
    <div ref={slot} className="hero-slot">{item && <StoryCard key={item.id} item={item} index={current} count={count} variant={photo?'lower':'hero'}/>}</div>
  </div>;
}

// A small burst from the check mark: fixed angles so every loop of the short looks the same.
const CONFETTI=Array.from({length:14},(_,i)=>{
  const angle=(-165+i*150/13)*Math.PI/180,distance=58+(i*37)%46;
  return {'--dx':`${Math.cos(angle)*distance}px`,'--dy':`${Math.sin(angle)*distance}px`,'--spin':`${(i%2?1:-1)*(140+i*23)}deg`,'--delay':`${(i%3)*45}ms`,'--color':['#ff5d73','#4f7cff','#f59e0b','#14b8a6','#a855f7'][i%5]} as CSSProperties;
});
export function Takeaway({text,outcome}:{text:string;outcome:boolean}){
  const reduced=useReducedMotion();
  return <section className="takeaway-card" data-testid="takeaway" aria-label={`${outcome?'Now you can':'Key takeaway'}: ${text}`}>
    <span className="takeaway-check" aria-hidden="true"><Check/>{!reduced && <span className="confetti">{CONFETTI.map((style,i)=><i key={i} style={style}/>)}</span>}</span>
    <div><span className="takeaway-eyebrow">{outcome?'Now you can':'Key takeaway'}</span><p>{text}</p></div>
  </section>;
}
