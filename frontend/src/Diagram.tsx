import { useSyncExternalStore } from 'react';
import type { Scene } from './api';
// Every visual state is computed from audio time. No independent animation timeline runs.
const positions = [[200,100],[200,225],[200,350],[200,475]];
const paired = [[105,175],[295,175],[105,360],[295,360]];
const motionQuery='(prefers-reduced-motion: reduce)';
const subscribeMotion=(callback:()=>void)=>{const media=matchMedia(motionQuery);media.addEventListener('change',callback);return()=>media.removeEventListener('change',callback);};
const getMotion=()=>matchMedia(motionQuery).matches;
export function Diagram({scene, time}: {scene: Scene; time: number}) {
  const reduced=useSyncExternalStore(subscribeMotion,getMotion,()=>true);
  const progress=(at:number)=>reduced?1:Math.max(0,Math.min(1,(time-at)/650));
  const slots = scene.template === 'comparison' || scene.template === 'chart' ? paired : positions;
  const actions = [...scene.actions].sort((a,b) => a.at_ms - b.at_ms);
  const state = new Map(scene.nodes.map(n => [n.id, {visible: !actions.some(a=>a.target===n.id && a.kind==='appear'), highlight:false, slot:n.slot,fromSlot:n.slot,moveAt:-1000,appearAt:-1000,disappearAt:-1}]));
  const drawn = new Map(scene.connections.filter(e => !actions.some(a=>a.target===e.id && a.kind==='draw')).map(e=>[e.id,-1000]));
  for(const a of actions) {
    if(a.at_ms > time) break;
    if(a.kind === 'draw') { drawn.set(a.target,a.at_ms); continue; }
    const node = state.get(a.target); if(!node) continue;
    if(a.kind === 'appear') {node.visible=true;node.appearAt=a.at_ms;node.disappearAt=-1;}
    if(a.kind === 'disappear') {node.visible=progress(a.at_ms)<1;node.disappearAt=a.at_ms;}
    if(a.kind === 'highlight') { for(const n of state.values()) n.highlight = false; node.highlight = true; }
    if(a.kind === 'move' && a.to_slot != null) {node.fromSlot=node.slot;node.slot=a.to_slot;node.moveAt=a.at_ms;}
  }
  const position=(s:{slot:number;fromSlot:number;moveAt:number})=>{const p=progress(s.moveAt);const from=slots[s.fromSlot],to=slots[s.slot];return [from[0]+(to[0]-from[0])*p,from[1]+(to[1]-from[1])*p];};
  return <svg className="diagram" viewBox="0 0 400 580" role="img" aria-label={`${scene.template} diagram: ${scene.nodes.map(n=>n.label+(n.value!=null?`: ${n.value}`:'')).join(', ')}`}>
    <defs><marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#b7b7b7"/></marker></defs>
    <text x="200" y="32" textAnchor="middle" className="diagram-tag">{({process:'FOLLOW THE PROCESS',comparison:'COMPARE THE OPTIONS',example:'WORK THROUGH AN EXAMPLE',timeline:'SEE THE SEQUENCE',chart:'READ THE VALUES'})[scene.template]}</text>
    {scene.template === 'timeline' && <line x1="38" y1="78" x2="38" y2="497" stroke="#4a4a4a" strokeWidth="2"/>}
    {scene.connections.map(e => {
      const source = state.get(e.source), target = state.get(e.target);
      if(!source?.visible || !target?.visible || !drawn.has(e.id)) return null;
      const [x1,y1] = position(source), [x2,y2] = position(target);
      const horizontal = Math.abs(x2-x1)>Math.abs(y2-y1);
      return <line key={e.id} data-testid={`connection-${e.id}`} x1={x1+(horizontal ? Math.sign(x2-x1)*87:0)} y1={y1+(horizontal?0:Math.sign(y2-y1)*53)} x2={x2-(horizontal?Math.sign(x2-x1)*91:0)} y2={y2-(horizontal?0:Math.sign(y2-y1)*55)} stroke="#b7b7b7" strokeWidth="2" pathLength="1" strokeDasharray="1" strokeDashoffset={1-progress(drawn.get(e.id)??-1000)} markerEnd={progress(drawn.get(e.id)??-1000)>.9?"url(#arrow)":undefined}/>;
    })}
    {scene.nodes.map((node,i)=>{
      const s = state.get(node.id)!; if(!s.visible) return null;
      const [x,y] = position(s);
      const width = slots === paired ? 172 : 306;
      const labelLines = wrap(node.label, slots === paired ? 20 : 32), detailLines = wrap(node.detail, slots === paired ? 24 : 40);
      const barWidth = node.value == null ? 0 : node.value / Math.max(1,...scene.nodes.map(n=>n.value??0)) * (width-44);
      return <g key={node.id} data-testid={`node-${node.id}`} transform={`translate(${x},${y})`} opacity={progress(s.appearAt)*(s.disappearAt<0?1:1-progress(s.disappearAt))}>
        <title>{node.label}{node.detail?`: ${node.detail}`:''}</title>
        {scene.template === 'timeline' && <circle cx={38-x} cy="0" r="5" fill="#ff5c57"/>}
        <rect x={-width/2} y="-48" width={width} height="100" rx={node.shape==='circle'?40:14} fill={s.highlight?'#472322':'#252525'} stroke={s.highlight?'#ff6a64':'#555555'} strokeWidth={s.highlight?2:1}/>
        <text x={-width/2+12} y="-29" className="node-number">{String(i+1).padStart(2,'0')}</text>
        {labelLines.map((line,j)=><text key={j} x="0" y={labelLines.length===1?-4:labelLines.length===2?-15+j*18:-24+j*15} textAnchor="middle" textLength={Math.min(width-30,line.length*7.3)} lengthAdjust="spacingAndGlyphs" className="node-label">{line}</text>)}
        {detailLines.map((line,j)=><text key={j} x="0" y={21+j*13} textAnchor="middle" textLength={Math.min(width-26,line.length*5.2)} lengthAdjust="spacingAndGlyphs" className="node-detail">{line}</text>)}
        {scene.template==='chart' && node.value != null && <><rect x={-width/2+12} y="58" width={width-24} height="5" rx="2" fill="#383838"/><rect x={-width/2+12} y="58" width={barWidth} height="5" rx="2" fill="#ff5c57"/><text x={width/2-8} y="72" textAnchor="end" className="node-detail">{node.value}</text></>}

      </g>;
    })}
  </svg>;
}
function wrap(text: string, max: number): string[] { const lines: string[]=[]; let line=''; for(const word of text.split(/\s+/)){ if((line+' '+word).trim().length>max && line){ lines.push(line);line=word; }else line=(line+' '+word).trim(); }if(line)lines.push(line);return lines.slice(0,3); }
