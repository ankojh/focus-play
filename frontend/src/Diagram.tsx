import { useId, useLayoutEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react';
import type { Scene } from './api';
import { ICONS } from './icons';
import { diagramFrame } from './playback';
import { diagramLayout, entityColor, ROLE_COLORS, ROLE_LABELS, type Box } from './diagramLayout';

const motionQuery='(prefers-reduced-motion: reduce)';
const subscribeMotion=(callback:()=>void)=>{const media=matchMedia(motionQuery);media.addEventListener('change',callback);return()=>media.removeEventListener('change',callback);};
const getMotion=()=>matchMedia(motionQuery).matches;
const TAGS:Record<string,string>={process:'Process',comparison:'Comparison',example:'Worked example',timeline:'Timeline',chart:'Values',steps:'Steps',cycle:'Cycle',dos_donts:"Do / Don't",key_fact:'Key fact'};
const fixedLayouts=new Set(['cycle','dos_donts','key_fact']);
function edge(b:Box,tx:number,ty:number):[number,number]{
  const dx=tx-b.x,dy=ty-b.y;
  if(!dx&&!dy)return [b.x,b.y];
  const scale=Math.min(dx?(b.w/2+5)/Math.abs(dx):Infinity,dy?(b.h/2+5)/Math.abs(dy):Infinity);
  return [b.x+dx*scale,b.y+dy*scale];
}

export function Diagram({scene,time}:{scene:Scene;time:number}){
  const frame=useRef<HTMLDivElement>(null),marker=useId();
  const [size,setSize]=useState({width:320,font:16});
  const reduced=useSyncExternalStore(subscribeMotion,getMotion,()=>true);
  useLayoutEffect(()=>{
    const element=frame.current!;
    const measure=()=>{const next={width:Math.max(120,element.clientWidth),font:parseFloat(getComputedStyle(element).fontSize)};setSize(old=>old.width===next.width && old.font===next.font?old:next);};
    measure();const observer=new ResizeObserver(measure);observer.observe(element);observer.observe(document.documentElement);
    return()=>observer.disconnect();
  },[]);
  const layout=useMemo(()=>diagramLayout(scene,size.width,size.font),[scene,size]);
  const {state,drawn,progress}=diagramFrame(scene,time,reduced);
  const focused=[...state.entries()].find(([,s])=>s.visible && s.highlight)?.[0];
  const focusSlot=focused?(fixedLayouts.has(scene.template)?layout.assigned.get(focused):state.get(focused)?.slot):undefined;
  useLayoutEffect(()=>{
    const reader=frame.current!;
    if(focusSlot==null){reader.scrollTop=0;return;}
    const target=layout.slots[focusSlot],top=target.y-target.h/2,bottom=target.y+target.h/2;
    // Snap only when semantic focus/layout changes; never run a smooth-scroll timer
    // or fight a learner manually scrolling the settled visual while paused.
    if(top<reader.scrollTop || bottom>reader.scrollTop+reader.clientHeight)reader.scrollTop=Math.max(0,top-12);
  },[focused,focusSlot,layout]);
  const box=(id:string)=>{
    const s=state.get(id)!;
    const from=layout.slots[fixedLayouts.has(scene.template)?layout.assigned.get(id)!:s.fromSlot];
    const to=layout.slots[fixedLayouts.has(scene.template)?layout.assigned.get(id)!:s.slot];
    const p=progress(s.moveAt,id);
    return {...to,x:from.x+(to.x-from.x)*p,y:from.y+(to.y-from.y)*p};
  };
  const links=scene.template==='cycle'&&!scene.id?scene.nodes.map((n,i)=>({id:`loop_${i}`,source:n.id,target:scene.nodes[(i+1)%scene.nodes.length].id,at:Math.max(state.get(n.id)!.appearAt,state.get(scene.nodes[(i+1)%scene.nodes.length].id)!.appearAt)})):
    scene.template==='dos_donts'?[]:scene.connections.filter(e=>drawn.has(e.id)).map(e=>({...e,at:drawn.get(e.id)!}));
  const visible=scene.nodes.filter(n=>state.get(n.id)!.visible);
  const summary=`${scene.template} diagram: ${visible.map(n=>{const s=state.get(n.id)!;return `${s.label}${s.detail?`: ${s.detail}`:''}${n.value!=null?`: ${n.value}`:''} (${ROLE_LABELS[s.role]??s.role})`;}).join('; ')}`;
  return <div className="diagram-frame visual-reader" ref={frame} tabIndex={0} aria-label="Diagram reading area. Scroll to read all revealed content.">
    <svg className="diagram" data-scene-id={scene.id??'legacy'} viewBox={`0 0 ${size.width} ${layout.height}`} width={size.width} height={layout.height} role="img" aria-label={summary}>
      <defs><marker id={marker} viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#c2cfde"/></marker></defs>
      <text x="24" y={size.font*1.4} className="diagram-tag" style={{fontSize:layout.detailSize}}>{TAGS[scene.template]}</text>
      {scene.template==='timeline' && <line x1="12" y1={size.font*2} x2="12" y2={layout.height-24} stroke="#69798d" strokeWidth="2"/>}
      {links.map(e=>{
        const s=state.get(e.source),t=state.get(e.target);if(!s?.visible||!t?.visible)return null;
        const a=box(e.source),b=box(e.target),p=progress(e.at,e.id);
        const [x1,y1]=edge(a,b.x,b.y),[x2,y2]=edge(b,a.x,a.y);
        // Returning edges run along the gutter, not through the intervening cards.
        const d=b.y<a.y?`M ${a.x-a.w/2} ${a.y} H 8 V ${b.y} H ${b.x-b.w/2-5}`:`M ${x1} ${y1} L ${x2} ${y2}`;
        return <g key={e.id} data-testid={`connection-${e.id}`}><path d={d} fill="none" stroke="#c2cfde" strokeWidth="2" pathLength="1" strokeDasharray={p<1?'1':undefined} strokeDashoffset={p<1?1-p:undefined} markerEnd={p===1?`url(#${marker})`:undefined}/></g>;
      })}
      {scene.nodes.map((node,i)=>{
        const s=state.get(node.id)!;if(!s.visible)return null;
        const b=box(node.id),identity=entityColor(node.id),semantic=ROLE_COLORS[s.role]??ROLE_COLORS.neutral;
        const Icon=node.icon?ICONS[node.icon]:undefined,text=layout.lines(s.label,s.detail,node.id);
        const labelSize=layout.labelSize*(node.id===layout.main?1.25:1),labelStep=layout.labelStep*(node.id===layout.main?1.25:1);
        const opacity=progress(s.appearAt,node.id)*(s.disappearAt<0?1:1-progress(s.disappearAt,node.id));
        const x=-b.w/2+16,heading=-b.h/2+size.font*3;
        const detailY=heading+text.label.length*labelStep+3;
        return <g key={node.id} data-testid={`node-${node.id}`} data-focused={s.highlight} data-entity-color={identity} transform={`translate(${b.x},${b.y})`} opacity={opacity}>
          {scene.template==='timeline' && <circle cx={12-b.x} cy="0" r="5" fill={identity}/>}
          <rect x={-b.w/2} y={-b.h/2} width={b.w} height={b.h} rx="12" fill={s.highlight?'#263447':'#1b2430'} stroke={s.highlight?'#ffbf66':'#69798d'} strokeWidth={s.highlight?3:1}/>
          <rect x={-b.w/2} y={-b.h/2+12} width="4" height={b.h-24} rx="2" fill={identity}/>
          {Icon?<Icon x={x} y={-b.h/2+12} size={size.font*1.4} color={identity}/>:<text x={x} y={-b.h/2+size.font*1.8} fill={identity} style={{fontSize:layout.labelSize}}>{i+1}</text>}
          <text x={x+size.font*2} y={-b.h/2+size.font*1.8} fill={semantic} style={{fontSize:layout.detailSize}}>{ROLE_LABELS[s.role]??s.role}{['process','timeline','steps'].includes(scene.template)?` · ${i+1}`:''}{s.highlight?' · Focus':''}</text>
          {text.label.map((line,j)=><text key={`label-${j}`} x={x} y={heading+j*labelStep} className="node-label" style={{fontSize:labelSize}}>{line}</text>)}
          {text.detail.map((line,j)=><text key={`detail-${j}`} x={x} y={detailY+j*layout.detailStep} className="node-detail" style={{fontSize:layout.detailSize}}>{line}</text>)}
          {node.value!=null && <><rect x={x} y={b.h/2-24} width={b.w-32} height="5" rx="2" fill="#485666"/><rect x={x} y={b.h/2-24} width={node.value/Math.max(1,...scene.nodes.map(n=>n.value??0))*(b.w-32)} height="5" rx="2" fill={identity}/><text x={b.w/2-16} y={b.h/2-7} textAnchor="end" className="node-detail" style={{fontSize:layout.detailSize}}>{node.value}</text></>}
        </g>;
      })}
    </svg>
  </div>;
}
