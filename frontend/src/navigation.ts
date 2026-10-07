import { useEffect, useRef, type TouchEvent } from 'react';

export type ShortsNavigation={previous:boolean;next:boolean;onPrevious:()=>void;onNext:()=>void};
// Wheel, trackpad and vertical swipes move between slides, except over a visual still scrolling its own content.
export function useShortsNavigation(navigation:ShortsNavigation){
  const view=useRef<HTMLDivElement>(null),current=useRef(navigation),touchStart=useRef<{x:number;y:number}|null>(null);
  current.current=navigation;
  useEffect(()=>{
    const element=view.current;if(!element)return;
    // One flick moves one slide. Trackpad momentum keeps firing after the switch, so the gesture stays
    // locked until the wheel goes quiet, unless, once the momentum is clearly dying, a much stronger push
    // starts a new flick. A flick ramps up before it decays, so the ramp never counts as a second one.
    let total=0,locked=false,direction=0,last=0,peak=0,timer:ReturnType<typeof setTimeout>|undefined;
    const wheel=(event:WheelEvent)=>{
      if(event.ctrlKey || Math.abs(event.deltaX)>Math.abs(event.deltaY) || (event.target as HTMLElement).closest('input,select,textarea'))return;
      const delta=event.deltaY*(event.deltaMode===1?16:event.deltaMode===2?element.clientHeight:1);
      const sign=Math.sign(delta);if(!sign)return;
      // A visual with more to read in this direction scrolls first; at its edge the wheel moves slides again.
      const reader=(event.target as HTMLElement).closest<HTMLElement>('.visual-reader');
      if(reader && (sign>0?reader.scrollTop+reader.clientHeight<reader.scrollHeight-1:reader.scrollTop>0))return;
      // Over the short the wheel never scrolls the page, even at the first or last slide.
      event.preventDefault();
      const nav=current.current,size=Math.abs(delta);
      if(sign!==direction){total=0;locked=false;direction=sign;peak=0;}
      else if(locked && last<peak/2 && size>Math.max(20,last*2.5)){total=0;locked=false;peak=0;}
      last=size;peak=Math.max(peak,size);
      clearTimeout(timer);timer=setTimeout(()=>{total=0;locked=false;direction=0;last=0;peak=0;},160);
      if(locked || !(sign>0?nav.next:nav.previous))return;
      total+=delta;
      if(Math.abs(total)<30)return;
      locked=true;if(sign>0)nav.onNext();else nav.onPrevious();
    };
    element.addEventListener('wheel',wheel,{passive:false});
    return()=>{element.removeEventListener('wheel',wheel);clearTimeout(timer);};
  },[]);
  const touch={
    onTouchStart:(e:TouchEvent)=>{const t=e.touches[0],target=e.target as HTMLElement,reader=target.closest<HTMLElement>('.visual-reader');touchStart.current=e.touches.length===1 && !target.closest('input,select,textarea,button,a,summary') && !(reader && reader.scrollHeight>reader.clientHeight+1)?{x:t.clientX,y:t.clientY}:null;},
    onTouchCancel:()=>{touchStart.current=null;},
    onTouchEnd:(e:TouchEvent)=>{const start=touchStart.current;touchStart.current=null;const t=e.changedTouches[0];if(!start || !t)return;const dy=start.y-t.clientY,dx=start.x-t.clientX;if(Math.abs(dy)<50 || Math.abs(dy)<=Math.abs(dx))return;const nav=current.current;if(dy>0 && nav.next)nav.onNext();else if(dy<0 && nav.previous)nav.onPrevious();},
  };
  return {view,touch};
}
