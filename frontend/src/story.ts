import type { Short } from './api';
import { atTime } from './playback';

// Sequence-like layouts read best one card at a time. Spatial layouts (funnel, matrix, venn,
// hierarchy) mean the whole arrangement, so they keep the incremental full diagram.
export const HERO_TEMPLATES=new Set(['process','steps','example','timeline','cycle','comparison','key_fact','dos_donts']);
export const SEQUENTIAL=new Set(['process','steps','example','timeline','cycle']);
export type StoryItem={id:string;label:string;detail:string;icon?:string|null;role:string};
export type StoryPlan={mode:'hero'|'full'|'chart'|'none';template:string;items:StoryItem[];starts:number[]};
const NONE:StoryPlan={mode:'none',template:'',items:[],starts:[]};

// Only single-scene compact storyboards get story choreography; legacy and rich multi-scene
// storyboards keep their authored playback unchanged.
export function storyPlan(short:Short):StoryPlan {
  const scene=short.scenes[0],units=short.narration_units;
  if(short.storyboard_version!==2 || short.scenes.length!==1 || !scene)return NONE;
  // Items in reveal order, each with the start of the beat that introduces it.
  const reveals=scene.actions.filter(a=>a.kind==='appear').sort((a,b)=>a.at_ms-b.at_ms);
  const starts=reveals.map(a=>a.at_ms);
  if(scene.kind==='chart'){
    const points=new Map(scene.payload.points.map(p=>[p.id,p]));
    const items=reveals.flatMap(a=>{const p=points.get(a.target);return p?[{id:p.id,label:p.label,detail:`${p.value.toLocaleString()} ${scene.payload.unit}`,role:'neutral'}]:[];});
    return {mode:'chart',template:'chart',items,starts};
  }
  if(scene.kind && scene.kind!=='diagram')return NONE;
  const nodes=new Map(scene.nodes.map(n=>[n.id,n]));
  const items=reveals.flatMap(a=>{const n=nodes.get(a.target);return n?[{id:n.id,label:n.label,detail:n.detail,icon:n.icon,role:n.role??'neutral'}]:[];});
  // The compact pattern: beat i reveals and focuses exactly one new item; nothing moves, hides or changes.
  const compact=items.length===units.length && !scene.states?.length && !scene.actions.some(a=>['move','disappear','change_state'].includes(a.kind)) &&
    units.every((u,i)=>{const own=scene.actions.filter(a=>a.beat_id===u.beat_id);return own.filter(a=>a.kind==='appear').length===1 && reveals[i]?.beat_id===u.beat_id && own.some(a=>a.kind==='highlight' && a.target===reveals[i].target);});
  return {mode:compact && HERO_TEMPLATES.has(scene.template)?'hero':'full',template:scene.template,items,starts};
}

export type StoryPhase={beat:number;photo:boolean;overview:boolean;takeaway:boolean;pan:number};
export const NO_PHASE:StoryPhase={beat:-1,photo:false,overview:false,takeaway:false,pan:0};
// Every phase is a pure function of the audio clock and measured beats, so seeking and looping restore it exactly.
export function storyPhase(short:Short,plan:StoryPlan,clock:number,cover:boolean):StoryPhase {
  const units=short.narration_units,unit=atTime(units,clock,short.measured_duration_ms),beat=unit?units.indexOf(unit):-1;
  if(plan.mode==='none' || beat<0)return {...NO_PHASE,beat};
  const last=units.at(-1)!,length=last.end_ms-last.start_ms;
  // The takeaway owns the last moments: the second half of the final beat, at most three seconds.
  const takeawayAt=Math.max(last.start_ms+length/2,last.end_ms-3000);
  // A recap taller than the stage pans from the top to the focused last item before the takeaway.
  const t=Math.min(1,Math.max(0,((clock-last.start_ms)/Math.max(1,takeawayAt-last.start_ms)-.15)/.7)),pan=t*t*(3-2*t);
  return {beat,photo:cover && beat===0 && plan.items.length>0,overview:beat===units.length-1,takeaway:beat===units.length-1 && clock>=takeawayAt,pan};
}
// The item introduced most recently at this audio position.
export function storyIndex(plan:StoryPlan,clock:number){
  let index=0;plan.starts.forEach((at,i)=>{if(at<=clock)index=i;});
  return index;
}
