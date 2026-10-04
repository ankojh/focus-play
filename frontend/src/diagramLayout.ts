import type { Scene } from './api';

export const ROLE_LABELS:Record<string,string>={neutral:'Concept',start:'Start',step:'Step',result:'Result',warning:'Caution',good:'Do',bad:"Don't"};
export const ROLE_COLORS:Record<string,string>={neutral:'#c2cfde',start:'#87bfff',step:'#ffbf66',result:'#75dfa5',warning:'#ffaaa6',good:'#75dfa5',bad:'#ffaaa6'};
const identities=['#87bfff','#d8b4fe','#ffcf87','#8ce0d2'];
// Identity is independent of semantic role and stays stable across related scenes.
export function entityColor(id:string){return identities[Array.from(id).reduce((hash,c)=>(hash*31+c.charCodeAt(0))>>>0,0)%identities.length];}

let context:CanvasRenderingContext2D|null=null;
// Measure actual glyph widths in the same bundled/system font as the SVG. No ellipsis,
// line limit or font shrinking: long saved tokens break, but every character survives.
export function wrapMeasured(text:string,width:number,size:number,weight=400):string[]{
  context??=document.createElement('canvas').getContext('2d');
  if(context)context.font=`${weight} ${size}px Arial`;
  const measure=(value:string)=>context?.measureText(value).width??Array.from(value).length*size;
  const lines:string[]=[];let line='';
  for(const word of text.trim().split(/\s+/).filter(Boolean)){
    if(line && measure(`${line} ${word}`)>width){lines.push(line);line='';}
    if(measure(word)>width){
      if(line){lines.push(line);line='';}
      for(const glyph of Array.from(word)){
        if(line && measure(line+glyph)>width){lines.push(line);line='';}
        line+=glyph;
      }
    }else line=line?`${line} ${word}`:word;
  }
  if(line)lines.push(line);
  return lines;
}

export type Box={x:number;y:number;w:number;h:number};
export function diagramLayout(scene:Scene,width:number,font:number){
  const gap=36,pad=24;
  const paired=['comparison','chart','dos_donts'].includes(scene.template) && width>=340*(font/16);
  const columns=paired?2:1,w=(width-pad*2-(columns-1)*gap)/columns;
  const labelSize=font,detailSize=font*.875,labelStep=font*1.35,detailStep=font*1.4;
  const main=scene.template==='key_fact'?[...scene.nodes].sort((a,b)=>a.slot-b.slot)[0]?.id:null;
  const lines=(label:string,detail:string,id?:string)=>({label:wrapMeasured(label,w-32,id===main?labelSize*1.25:labelSize,650),detail:wrapMeasured(detail,w-32,detailSize)});
  // Reserve the largest authored state and every move destination before any reveal.
  const heights=scene.nodes.map(n=>Math.max(...[n,...(scene.states??[]).filter(s=>s.target===n.id)].map(s=>{
    const text=lines(s.label,s.detail,n.id);return font*3+text.label.length*labelStep*(n.id===main?1.25:1)+text.detail.length*detailStep+24+(n.value!=null?30:0);
  })));
  const rowHeight=Math.max(...heights,100);
  const slots=Array.from({length:8},(_,i)=>({x:pad+w/2+(i%columns)*(w+gap),y:font*2+rowHeight/2+Math.floor(i/columns)*(rowHeight+gap),w,h:rowHeight}));
  const assigned=new Map(scene.nodes.map(n=>[n.id,n.slot]));
  if(scene.template==='dos_donts'){
    const counts={good:0,bad:0};
    scene.nodes.forEach((n,i)=>{const side=n.role==='bad'?'bad':'good';assigned.set(n.id,paired?counts[side]++*2+(side==='bad'?1:0):i);});
  }
  const used=[...assigned.values(),...scene.actions.filter(a=>a.kind==='move').map(a=>a.to_slot??0)];
  const height=Math.max(...used.map(i=>slots[i].y+rowHeight/2))+24;
  return {slots,assigned,height,lines,labelSize,detailSize,labelStep,detailStep,main};
}
