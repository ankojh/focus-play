import { useSyncExternalStore } from 'react';
import { Check, X } from 'lucide-react';
import type { Scene } from './api';
import { ICONS } from './icons';
// Every visual state is computed from audio time. No independent animation timeline runs.
type Node = Scene['nodes'][number];
type Box = {x:number;y:number;w:number;h:number};
const motionQuery='(prefers-reduced-motion: reduce)';
const subscribeMotion=(callback:()=>void)=>{const media=matchMedia(motionQuery);media.addEventListener('change',callback);return()=>media.removeEventListener('change',callback);};
const getMotion=()=>matchMedia(motionQuery).matches;
const TAGS:Record<string,string>={process:'FOLLOW THE PROCESS',comparison:'COMPARE THE OPTIONS',example:'WORK THROUGH AN EXAMPLE',timeline:'SEE THE SEQUENCE',chart:'READ THE VALUES',steps:'FOLLOW THE STEPS',cycle:'SEE THE LOOP',dos_donts:'DO THIS, NOT THAT',key_fact:'REMEMBER THIS'};
// Role accents on the dark player. Neutral keeps the original grey look for saved lessons.
const ROLES:Record<string,string>={neutral:'#b7b7b7',start:'#5aa9ff',step:'#ffb547',result:'#4cd38a',warning:'#ff6a64',good:'#4cd38a',bad:'#ff6a64'};
const NUMBERED=new Set(['process','steps','timeline']);
const column=[[200,100],[200,225],[200,350],[200,475]];
const paired=[[105,175],[295,175],[105,360],[295,360]];

// Card centre and size for each node. Older templates keep their slot positions so moves still work.
function layout(template:string, nodes:Node[]):Map<string,Box> {
  const boxes=new Map<string,Box>();
  if(template==='cycle') {
    nodes.forEach((n,i)=>{const a=-Math.PI/2+i*2*Math.PI/nodes.length;boxes.set(n.id,{x:200+Math.cos(a)*118,y:300+Math.sin(a)*170,w:150,h:132});});
  } else if(template==='dos_donts') {
    const rows={good:0,bad:0};
    for(const n of nodes){const side=n.role==='bad'?'bad':'good';boxes.set(n.id,{x:side==='good'?105:295,y:182+rows[side]*154,w:172,h:132});rows[side]++;}
  } else if(template==='key_fact') {
    const [main,...rest]=[...nodes].sort((a,b)=>a.slot-b.slot);
    boxes.set(main.id,{x:200,y:190,w:340,h:190});
    const w=(340-(rest.length-1)*10)/Math.max(1,rest.length);
    rest.forEach((n,i)=>boxes.set(n.id,{x:30+w/2+i*(w+10),y:420,w,h:130}));
  } else {
    const slots=template==='comparison'||template==='chart'?paired:column;
    for(const n of nodes){const [x,y]=slots[n.slot];boxes.set(n.id,{x,y,w:slots===paired?172:316,h:slots===paired?132:100});}
  }
  return boxes;
}

// Where the line from a card's centre towards (tx,ty) leaves the card.
function edge(b:Box,tx:number,ty:number):[number,number] {
  const dx=tx-b.x,dy=ty-b.y;
  if(!dx&&!dy)return [b.x,b.y];
  const s=Math.min(dx?(b.w/2+6)/Math.abs(dx):Infinity,dy?(b.h/2+6)/Math.abs(dy):Infinity);
  return [b.x+dx*s,b.y+dy*s];
}

export function Diagram({scene, time}: {scene: Scene; time: number}) {
  const reduced=useSyncExternalStore(subscribeMotion,getMotion,()=>true);
  const progress=(at:number)=>reduced?1:Math.max(0,Math.min(1,(time-at)/650));
  const template=scene.template;
  const actions=[...scene.actions].sort((a,b)=>a.at_ms-b.at_ms);
  const state=new Map(scene.nodes.map(n=>[n.id,{visible:!actions.some(a=>a.target===n.id&&a.kind==='appear'),highlight:false,slot:n.slot,fromSlot:n.slot,moveAt:-1000,appearAt:-1000,disappearAt:-1}]));
  const drawn=new Map(scene.connections.filter(e=>!actions.some(a=>a.target===e.id&&a.kind==='draw')).map(e=>[e.id,-1000]));
  for(const a of actions) {
    if(a.at_ms>time)break;
    if(a.kind==='draw'){drawn.set(a.target,a.at_ms);continue;}
    const node=state.get(a.target);if(!node)continue;
    if(a.kind==='appear'){node.visible=true;node.appearAt=a.at_ms;node.disappearAt=-1;}
    if(a.kind==='disappear'){node.visible=progress(a.at_ms)<1;node.disappearAt=a.at_ms;}
    if(a.kind==='highlight'){for(const n of state.values())n.highlight=false;node.highlight=true;}
    if(a.kind==='move'&&a.to_slot!=null){node.fromSlot=node.slot;node.slot=a.to_slot;node.moveAt=a.at_ms;}
  }
  const boxes=layout(template,scene.nodes);
  const fixed=template==='cycle'||template==='dos_donts'||template==='key_fact';
  const slots=template==='comparison'||template==='chart'?paired:column;
  const box=(id:string):Box=>{
    const b=boxes.get(id)!,s=state.get(id)!;
    if(fixed)return b;
    const p=progress(s.moveAt),from=slots[s.fromSlot],to=slots[s.slot];
    return {...b,x:from[0]+(to[0]-from[0])*p,y:from[1]+(to[1]-from[1])*p};
  };
  const focus=[...state.values()].some(s=>s.highlight);
  // Zoom to the cards so a two-node diagram fills the player instead of a fixed 400x580 canvas.
  // Bounds use every node, visible or not, so the view does not jump as nodes appear.
  const all=[...boxes.values()];
  let left=Math.min(...all.map(b=>b.x-b.w/2)),right=Math.max(...all.map(b=>b.x+b.w/2));
  let top=Math.min(...all.map(b=>b.y-b.h/2))-40,bottom=Math.max(...all.map(b=>b.y+b.h/2+(template==='chart'?26:0)));
  if(template==='timeline')left=Math.min(left,28);
  if(template==='dos_donts')top=Math.min(top,30);
  if(!fixed){const moves=scene.actions.filter(a=>a.kind==='move'&&a.to_slot!=null).map(a=>slots[a.to_slot!]);for(const [x,y] of moves){left=Math.min(left,x-158);right=Math.max(right,x+158);bottom=Math.max(bottom,y+50);}}
  const pad=16,view={x:left-pad,y:top-pad,w:right-left+2*pad,h:bottom-top+2*pad};
  // Arrows flow while audio plays; the dash offset is derived from the audio clock.
  const flow=reduced?0:-(time/45)%16;
  const links=template==='cycle'
    ? scene.nodes.map((n,i)=>({id:`loop_${i}`,source:n.id,target:scene.nodes[(i+1)%scene.nodes.length].id,at:Math.max(state.get(n.id)!.appearAt,state.get(scene.nodes[(i+1)%scene.nodes.length].id)!.appearAt)}))
    : template==='dos_donts' ? [] : scene.connections.filter(e=>drawn.has(e.id)).map(e=>({...e,at:drawn.get(e.id)!}));
  return <svg className="diagram" viewBox={`${view.x} ${view.y} ${view.w} ${view.h}`} role="img" aria-label={`${template} diagram: ${scene.nodes.map(n=>n.label+(n.value!=null?`: ${n.value}`:'')).join(', ')}`}>
    <defs>
      <marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#d0d0d0"/></marker>
      <filter id="glow" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur stdDeviation="7" result="blur"/><feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
    </defs>
    <text x={(left+right)/2} y={top+12} textAnchor="middle" className="diagram-tag">{TAGS[template]}</text>
    {template==='timeline' && <line x1="38" y1={top+40} x2="38" y2={bottom} stroke="#4a4a4a" strokeWidth="2"/>}
    {template==='cycle' && <circle cx="200" cy="300" r="62" fill="none" stroke="#333" strokeDasharray="3 5"/>}
    {template==='dos_donts' && <>
      <g transform="translate(105,70)"><circle r="15" fill="#173d29"/><Check x={-9} y={-9} size={18} color={ROLES.good}/><text y="34" textAnchor="middle" className="column-head" fill={ROLES.good}>DO</text></g>
      <g transform="translate(295,70)"><circle r="15" fill="#47201f"/><X x={-9} y={-9} size={18} color={ROLES.bad}/><text y="34" textAnchor="middle" className="column-head" fill={ROLES.bad}>DON'T</text></g>
      <line x1="200" y1="60" x2="200" y2={bottom} stroke="#333" strokeWidth="1"/>
    </>}
    {links.map(e=>{
      const s=state.get(e.source),t=state.get(e.target);
      if(!s?.visible||!t?.visible)return null;
      const a=box(e.source),b=box(e.target),p=progress(e.at);
      const [x1,y1]=edge(a,b.x,b.y),[x2,y2]=edge(b,a.x,a.y);
      // Cycle arrows bow outward around the loop centre.
      const bend=template==='cycle'?(()=>{const mx=(x1+x2)/2,my=(y1+y2)/2,dx=mx-200,dy=my-300,l=Math.hypot(dx,dy)||1;return ` Q ${mx+dx/l*40} ${my+dy/l*40} `;})():' L ';
      const d=`M ${x1} ${y1}${bend}${x2} ${y2}`,active=t.highlight||s.highlight;
      return <g key={e.id} data-testid={`connection-${e.id}`}>
        {p<1 ? <path d={d} fill="none" stroke="#d0d0d0" strokeWidth="2" pathLength="1" strokeDasharray="1" strokeDashoffset={1-p}/>
             : <path d={d} fill="none" stroke={active?'#ffffff':'#9a9a9a'} strokeWidth={active?2.5:2} strokeDasharray={reduced?undefined:'8 8'} strokeDashoffset={flow} markerEnd="url(#arrow)"/>}
      </g>;
    })}
    {scene.nodes.map((node,i)=>{
      const s=state.get(node.id)!;if(!s.visible)return null;
      const b=box(node.id),accent=ROLES[node.role??'neutral']??ROLES.neutral;
      const Icon=node.icon?ICONS[node.icon]:undefined;
      const big=template==='key_fact'&&b.w>300,stacked=b.w<260;
      const opacity=progress(s.appearAt)*(s.disappearAt<0?1:1-progress(s.disappearAt))*(focus&&!s.highlight?0.7:1);
      const number=NUMBERED.has(template)?String(i+1):null;
      const max=Math.max(1,...scene.nodes.map(n=>n.value??0)),barWidth=node.value==null?0:node.value/max*(b.w-44);
      const iconSize=big?44:stacked?26:24;
      const labelLines=wrap(node.label,big?22:Math.floor((b.w-(stacked?24:86))/7));
      const detailLines=wrap(node.detail,Math.floor((b.w-(stacked?24:86))/5.7));
      // Fit all lines within the card, including narrow key-fact support cards.
      const labelStep=big?26:16, detailStep=13;
      const labelY=Icon?-b.h/2+iconSize+38:-6;
      const detailY=labelY+labelLines.length*labelStep+1;
      const lastY=detailY+Math.max(0,detailLines.length-1)*detailStep;
      const textScale=Math.min(1,(b.h/2-9-labelY)/Math.max(1,lastY-labelY));
      return <g key={node.id} data-testid={`node-${node.id}`} transform={`translate(${b.x},${b.y})`} opacity={opacity}>
        <title>{node.label}{node.detail?`: ${node.detail}`:''}</title>
        {template==='timeline' && <circle cx={38-b.x} cy="0" r="5" fill={accent==='#b7b7b7'?'#ff5c57':accent}/>}
        <rect x={-b.w/2} y={-b.h/2} width={b.w} height={b.h} rx={node.shape==='circle'?40:16} fill={s.highlight?'#2f2a26':'#222'} stroke={s.highlight?accent:'#4a4a4a'} strokeWidth={s.highlight?2.5:1} filter={s.highlight&&!reduced?'url(#glow)':undefined}/>
        <rect x={-b.w/2} y={-b.h/2+12} width="4" height={b.h-24} rx="2" fill={accent}/>
        {stacked||big ? <>
          {Icon ? <g transform={`translate(0,${-b.h/2+16+iconSize/2})`}><circle r={iconSize/2+8} fill={accent} opacity=".16"/><Icon x={-iconSize/2} y={-iconSize/2} size={iconSize} color={accent}/></g>
                : number && <text x="0" y={-b.h/2+26} textAnchor="middle" className="node-number-big" fill={accent}>{number}</text>}
          {number && Icon && <g transform={`translate(${-b.w/2+18},${-b.h/2+18})`}><circle r="10" fill={accent}/><text y="4" textAnchor="middle" className="node-badge">{number}</text></g>}
          {labelLines.map((line,j)=><text key={j} x="0" y={labelY+j*labelStep*textScale} textAnchor="middle" style={{fontSize:(big?21:13)*textScale}} className={big?'node-label-big':'node-label'}>{line}</text>)}
          {detailLines.map((line,j)=><text key={j} x="0" y={labelY+(detailY-labelY+j*detailStep)*textScale} textAnchor="middle" style={{fontSize:10*textScale}} className="node-detail">{line}</text>)}
        </> : <>
          <g transform={`translate(${-b.w/2+38},0)`}>
            <circle r="22" fill={accent} opacity=".16"/>
            {Icon ? <Icon x={-iconSize/2} y={-iconSize/2} size={iconSize} color={accent}/> : <text y="5" textAnchor="middle" className="node-number-big" fill={accent}>{number??String(i+1).padStart(2,'0')}</text>}
            {number && Icon && <g transform="translate(16,-16)"><circle r="10" fill={accent}/><text y="4" textAnchor="middle" className="node-badge">{number}</text></g>}
          </g>
          {labelLines.map((line,j)=><text key={j} x={-b.w/2+74} y={(detailLines.length?-10:4)-(labelLines.length-1)*8+j*16} className="node-label">{line}</text>)}
          {detailLines.map((line,j)=><text key={j} x={-b.w/2+74} y={10+(labelLines.length-1)*8+j*13} className="node-detail">{line}</text>)}
        </>}
        {template==='chart' && node.value!=null && <><rect x={-b.w/2+12} y={b.h/2+8} width={b.w-24} height="5" rx="2" fill="#383838"/><rect x={-b.w/2+12} y={b.h/2+8} width={barWidth} height="5" rx="2" fill={accent==='#b7b7b7'?'#ff5c57':accent}/><text x={b.w/2-8} y={b.h/2+22} textAnchor="end" className="node-detail">{node.value}</text></>}
      </g>;
    })}
  </svg>;
}
function wrap(text: string, max: number): string[] { const lines: string[]=[]; let line=''; for(const word of text.split(/\s+/)){ if((line+' '+word).trim().length>max && line){ lines.push(line);line=word; }else line=(line+' '+word).trim(); }if(line)lines.push(line);return lines.slice(0,3); }
