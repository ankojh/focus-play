import type { Scene, Short } from './api';
import { visualError } from './visualState';
import { FIXED_LAYOUTS } from './diagramLayout';

// Absolute audio clock, half-open interior intervals, held final frame.
export function atTime<T extends {start_ms:number;end_ms:number}>(items:T[], time:number, duration:number):T|undefined {
  if(!Number.isFinite(time) || time<0 || time>duration)return undefined;
  if(time===duration){const last=items.at(-1);return last?.end_ms===duration?last:undefined;}
  return items.find(item=>item.start_ms<=time && time<item.end_ms);
}

export function timelineError(short:Short):string|null {
  if(short.scenes.some(s=>s.kind && s.kind!=='diagram' && visualError(s)))return 'This short has invalid visual data. Retry lesson preparation.';
  if(short.storyboard_version!==2)return short.scenes.length?null:'This saved short has no visual scene. Retry lesson preparation.';
  const fail='This short has invalid storyboard timing. Retry lesson preparation to repair it.';
  if(!short.timeline_compiler_version || !short.audio_path || short.measured_duration_ms<1000 || short.measured_duration_ms>40000 || short.narration_units.length<2 || short.narration_units.length>8 || !short.scenes.length || short.scenes.length>3)return fail;
  const beats=new Map(short.narration_units.map(u=>[u.beat_id,u]));
  if(beats.has(null) || beats.has(undefined) || beats.has('') || beats.size!==short.narration_units.length || short.narration_units.some(u=>!u.purpose || u.purpose.length<5))return fail;
  let cursor=0;
  for(const u of short.narration_units){if(u.start_ms!==cursor || u.end_ms<=u.start_ms || u.end_ms>short.measured_duration_ms)return fail;cursor=u.end_ms;}
  if(cursor!==short.measured_duration_ms)return fail;
  cursor=0;const ids=new Set<string>();const covered:string[]=[];
  for(const s of short.scenes){
    if(!s.id || ids.has(s.id) || !s.summary || s.summary.length<5 || !s.evidence_references?.length || s.start_ms!==cursor || s.end_ms<=s.start_ms || s.end_ms>short.measured_duration_ms)return fail;
    ids.add(s.id);
    const bound=short.narration_units.filter(u=>u.scene_id===s.id);
    if(!bound.length || bound[0].start_ms!==s.start_ms || bound.at(-1)!.end_ms!==s.end_ms || JSON.stringify(s.beat_ids)!==JSON.stringify(bound.map(u=>u.beat_id)))return fail;
    if(s.kind && s.kind!=='diagram'){
      if(visualError(s) || s.actions.some(a=>{const beat=beats.get(a.beat_id);return !beat || beat.scene_id!==s.id || a.at_ms!==beat.start_ms;}) || bound.some(u=>!s.actions.some(a=>a.beat_id===u.beat_id)))return fail;
      covered.push(...s.beat_ids!);cursor=s.end_ms;continue;
    }
    if(s.nodes.length<2 || s.nodes.length>8)return fail;
    const nodes=new Set(s.nodes.map(n=>n.id)),edges=new Map(s.connections.map(e=>[e.id,e]));
    if(nodes.size!==s.nodes.length || edges.size!==s.connections.length || s.connections.some(e=>!nodes.has(e.source)||!nodes.has(e.target)||nodes.has(e.id)))return fail;
    if(new Set(s.nodes.map(n=>n.slot)).size!==s.nodes.length || s.nodes.some(n=>n.slot<0 || n.slot>7))return fail;
    const visible=new Set<string>(),drawn=new Set<string>();
    const slots=new Map(s.nodes.map(n=>[n.id,n.slot]));
    let previous=s.start_ms;
    for(const a of s.actions){
      const beat=beats.get(a.beat_id);
      if(!beat || beat.scene_id!==s.id || a.at_ms!==beat.start_ms || a.at_ms<previous || a.at_ms>=s.end_ms || !(a.kind==='draw'?edges.has(a.target):nodes.has(a.target)))return fail;
      if(a.kind==='change_state' && !s.states?.some(state=>state.id===a.state_id && state.target===a.target))return fail;
      if(!['appear','disappear','highlight','move','draw','change_state'].includes(a.kind))return fail;
      if(a.kind==='appear'){if(visible.has(a.target))return fail;visible.add(a.target);}
      else if(a.kind==='draw'){const edge=edges.get(a.target)!;if(drawn.has(a.target) || !visible.has(edge.source) || !visible.has(edge.target) || s.template==='dos_donts')return fail;drawn.add(a.target);}
      else {if(!visible.has(a.target))return fail;if(a.kind==='disappear')visible.delete(a.target);}
      if(a.kind==='move'){
        if(a.to_slot==null || a.to_slot<0 || a.to_slot>7 || FIXED_LAYOUTS.has(s.template) || [...slots.values()].includes(a.to_slot))return fail;
        slots.set(a.target,a.to_slot);
      }
      previous=a.at_ms;
    }
    if(bound.some(u=>!s.actions.some(a=>a.beat_id===u.beat_id)) || s.nodes.some(n=>!s.actions.some(a=>a.kind==='appear' && a.target===n.id)) || drawn.size!==edges.size)return fail;
    covered.push(...s.beat_ids!);cursor=s.end_ms;
  }
  return cursor===short.measured_duration_ms && JSON.stringify(covered)===JSON.stringify(short.narration_units.map(u=>u.beat_id))?null:fail;
}

// Pure recomputation makes seek, pause, restore and loop frames identical.
export function diagramFrame(scene:Scene,time:number,reduced:boolean) {
  const actions=[...scene.actions].sort((a,b)=>a.at_ms-b.at_ms);
  const progress=(at:number,target?:string)=>{
    if(at>time)return 0;
    if(reduced)return 1;
    const next=actions.find(a=>a.at_ms>at && (!target || a.target===target))?.at_ms??scene.end_ms;
    const span=Math.max(1,Math.min(180,next-at,scene.end_ms-at));
    // Tiny spoken beats snap rather than flashing through decorative effects.
    if(span<150)return 1;
    return Math.max(0,Math.min(1,(time-at)/span));
  };
  const state=new Map(scene.nodes.map(n=>[n.id,{visible:!actions.some(a=>a.target===n.id&&a.kind==='appear'),highlight:false,slot:n.slot,fromSlot:n.slot,moveAt:-1000,appearAt:-1000,disappearAt:-1,label:n.label,detail:n.detail,role:n.role??'neutral'}]));
  const drawn=new Map(scene.connections.filter(e=>!actions.some(a=>a.target===e.id&&a.kind==='draw')).map(e=>[e.id,-1000]));
  for(const a of actions){
    if(a.at_ms>time)break;
    if(a.kind==='draw'){drawn.set(a.target,a.at_ms);continue;}
    const node=state.get(a.target);if(!node)continue;
    if(a.kind==='appear'){node.visible=true;node.appearAt=a.at_ms;node.disappearAt=-1;}
    if(a.kind==='disappear'){node.visible=progress(a.at_ms,a.target)<1;node.disappearAt=a.at_ms;node.highlight=false;}
    if(a.kind==='highlight'){for(const n of state.values())n.highlight=false;node.highlight=true;}
    if(a.kind==='move'&&a.to_slot!=null){node.fromSlot=node.slot;node.slot=a.to_slot;node.moveAt=a.at_ms;}
    if(a.kind==='change_state'){const changed=scene.states?.find(s=>s.id===a.state_id && s.target===a.target);if(changed){node.label=changed.label;node.detail=changed.detail;node.role=changed.role??'neutral';}}
  }
  return {state,drawn,progress};
}
