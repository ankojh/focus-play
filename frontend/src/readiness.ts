import { useEffect, useState } from 'react';
import type { Lesson, Short } from './api';

export function mediaReady(lesson:Lesson, short:Short) {
  return short.status==='ready' && !!short.audio_path && short.measured_duration_ms>0 &&
    (!lesson.readiness || lesson.readiness.ready_short_ids.includes(short.id));
}
export function readyAhead(lesson:Lesson, activeId:string, positionMs=0) {
  const index=lesson.shorts.findIndex(s=>s.id===activeId);
  if(index<0)return {mediaMs:0,nextCount:0};
  let mediaMs=0,nextCount=0;
  for(let i=index;i<lesson.shorts.length;i++) {
    const short=lesson.shorts[i];if(!mediaReady(lesson,short))break;
    mediaMs+=Math.max(0,short.measured_duration_ms-(i===index?Math.max(0,positionMs):0));
    if(i>index)nextCount++;
  }
  return {mediaMs,nextCount};
}

const MAX_TOTAL=8*1024*1024, MAX_AUDIO=2_000_044, MAX_IMAGE=5_000_000;
// Fixed two-short window; never cross an unready gap or preload after cancellation.
export function useMediaPreload(lesson:Lesson|null, activeId:string, enabled:boolean) {
  const index=lesson?.shorts.findIndex(s=>s.id===activeId)??-1;
  const targets: {id:string;audio:string;images:string[]}[]=[];
  let imagePixels=0;
  if(enabled && lesson && lesson.job.status!=='cancelled' && index>=0) {
    for(const short of lesson.shorts.slice(index+1,index+3)) {
      if(!mediaReady(lesson,short))break;
      const essential=short.scenes.filter(s=>s.kind==='image');
      const pixels=essential.reduce((sum,s)=>sum+s.payload.width*s.payload.height,0);
      // At most 32 MiB of decoded RGBA images across the preload window.
      if(imagePixels+pixels>8_000_000)break;
      imagePixels+=pixels;
      targets.push({id:short.id,audio:short.audio_path!,images:[...new Set(essential.map(s=>s.payload.asset_id))]});
    }
  }
  const signature=JSON.stringify([lesson?.id,activeId,targets]);
  const [result,setResult]=useState<{signature:string;ready:string[];failed:string[]}>({signature:'',ready:[],failed:[]});
  useEffect(()=>{
    const controller=new AbortController(),urls:string[]=[],media:HTMLAudioElement[]=[],images:HTMLImageElement[]=[];
    let used=0;
    const ready:string[]=[],failed:string[]=[];
    const publish=()=>{if(!controller.signal.aborted)setResult({signature,ready:[...ready],failed:[...failed]});};
    const blob=async(url:string,limit:number)=>{
      const response=await fetch(url,{signal:controller.signal});
      if(!response.ok)throw new Error('Missing media');
      const reader=response.body?.getReader();if(!reader)throw new Error('No media body');
      const chunks:Uint8Array<ArrayBuffer>[]= [];let size=0;
      try {
        if(Number(response.headers.get('content-length'))>Math.min(limit,MAX_TOTAL-used))throw new Error('Preload limit');
        while(true){const part=await reader.read();if(part.done)break;size+=part.value.byteLength;used+=part.value.byteLength;
          if(size>limit || used>MAX_TOTAL)throw new Error('Preload limit');chunks.push(part.value as Uint8Array<ArrayBuffer>);}
        if(controller.signal.aborted)throw new Error('Preload cancelled');
        const value=URL.createObjectURL(new Blob(chunks));urls.push(value);return value;
      } finally {await reader.cancel().catch(()=>{});}
    };
    const decode=async(element:HTMLAudioElement|HTMLImageElement,url:string)=>new Promise<void>((resolve,reject)=>{
      if(controller.signal.aborted){reject(new Error('Preload cancelled'));return;}
      const event=element instanceof HTMLAudioElement?'loadeddata':'load';
      const cleanup=()=>{clearTimeout(timer);element.removeEventListener(event,ok);element.removeEventListener('error',bad);controller.signal.removeEventListener('abort',bad);};
      const ok=()=>{cleanup();resolve();},bad=()=>{cleanup();reject(new Error('Media decode unavailable'));};
      const timer=setTimeout(bad,15000);
      element.addEventListener(event,ok,{once:true});element.addEventListener('error',bad,{once:true});controller.signal.addEventListener('abort',bad,{once:true});
      element.src=url;if(element instanceof HTMLAudioElement){element.preload='auto';element.load();}
    });
    publish();
    void (async()=>{
      // Sequential fetch/decode bounds network concurrency and retained blobs.
      for(const target of targets) {
        if(controller.signal.aborted || used>=MAX_TOTAL)break;
        try {
          const audio=new Audio();media.push(audio);
          await decode(audio,await blob(`/api/audio/${target.audio}`,MAX_AUDIO));
          for(const id of target.images){const image=new Image();images.push(image);await decode(image,await blob(`/api/assets/${id}`,MAX_IMAGE));}
          ready.push(target.id);
        } catch {if(controller.signal.aborted)break;failed.push(target.id);}
        publish();
      }
    })();
    return()=>{controller.abort();for(const audio of media){audio.pause();audio.removeAttribute('src');audio.load();}for(const image of images)image.src='';for(const url of urls)URL.revokeObjectURL(url);};
  },[signature]);
  return result.signature===signature?result:{signature,ready:[],failed:[]};
}

// Device-local, bounded observation only. No goals, text, or server events.
export function recordRequestedWait(shortId:string, seconds:number, outcome:'ready'|'abandoned') {
  try {
    const key='focusplay:requested-waits:v1',now=Date.now();
    const saved=JSON.parse(localStorage.getItem(key)||'[]');
    const rows=(Array.isArray(saved)?saved:[]).filter(r=>typeof r.at==='number' && now-r.at<7*86400000);
    rows.push({at:now,shortId,seconds:Math.max(0,seconds),outcome});localStorage.setItem(key,JSON.stringify(rows.slice(-50)));
  } catch {/* Storage may be disabled or full; playback must still work. */}
}
