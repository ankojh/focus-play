import type { Scene } from './api';

export const ROLE_LABELS:Record<string,string>={neutral:'Concept',start:'Start',step:'Step',result:'Result',warning:'Caution',good:'Do',bad:"Don't"};
// Dark enough for AA (4.5:1) on the light theme's white and focused cream cards.
export const ROLE_COLORS:Record<string,string>={neutral:'#5c6178',start:'#1d4ed8',step:'#9a4a06',result:'#047857',warning:'#b91c1c',good:'#047857',bad:'#b91c1c'};
// Saturated enough to read on the light slide theme.
const identities=['#4f7cff','#a855f7','#f59e0b','#14b8a6'];
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
// Card anatomy, shared by the SVG diagram and the HTML story cards so text never crowds the icon or edges:
// inner padding, an icon row (icon on a soft circle, role beside it), label lines, detail lines.
export function cardAnatomy(font:number,crowded:boolean){
  const iconSize=font*1.3;
  return {inner:crowded?12:16,iconSize,blobRadius:iconSize*.8,roleGap:font*.5,labelGap:font*.6,detailGap:font*.35};
}
// Fixed-shape layouts keep authored slots; nodes cannot move between them.
export const FIXED_LAYOUTS=new Set(['cycle','dos_donts','key_fact','funnel','matrix','hierarchy','venn']);
const INDENT=28;
// More than 4 items is "crowded": denser cards, two columns for unordered layouts, and the
// player dims earlier items so the current one stays the focus.
export const CROWDED=4;
// Dense uses the crowded metrics regardless of count, e.g. for the zoomed-out ending recap.
export function diagramLayout(scene:Scene,width:number,measuredFont:number,dense=false){
  const t=scene.template,crowded=dense || scene.nodes.length>CROWDED;
  const font=crowded?measuredFont*.88:measuredFont,gap=crowded?20:36,pad=crowded?16:24;
  const paired=(['comparison','chart','dos_donts'].includes(t) && width>=340*(font/16)) || t==='matrix' || (crowded && ['comparison','key_fact'].includes(t) && width>=300);
  const columns=paired?2:1,w=(width-pad*2-(columns-1)*gap)/columns;
  const labelSize=font,detailSize=font*.875,labelStep=font*1.35,detailStep=font*1.4;
  const main=['key_fact','hierarchy'].includes(t)?[...scene.nodes].sort((a,b)=>a.slot-b.slot)[0]?.id:null;
  const assigned=new Map(scene.nodes.map(n=>[n.id,n.slot]));
  if(t==='dos_donts'){
    const counts={good:0,bad:0};
    scene.nodes.forEach((n,i)=>{const side=n.role==='bad'?'bad':'good';assigned.set(n.id,paired?counts[side]++*2+(side==='bad'?1:0):i);});
  }
  // Venn: two overlapping circles (slots 0 and 1) with the shared idea as a card below.
  const radius=Math.min((width-pad*2)/3.2,font*9),circle=(i:number)=>t==='venn' && i<2;
  const {inner,iconSize,blobRadius,labelGap,detailGap}=cardAnatomy(font,crowded),top=font*2.6;
  const funnelInset=(bw:number)=>t==='funnel'?Math.min(14,bw*.06):0;
  const metrics=(labelLines:number,detailLines:number,isMain:boolean)=>{
    const size=labelSize*(isMain?1.25:1),step=labelStep*(isMain?1.25:1);
    // The icon circle spans inner..inner+2*blobRadius; the label starts a clear gap below it.
    const heading=inner+2*blobRadius+labelGap+size*.8;
    const detailY=heading+(labelLines-1)*step+detailGap+detailSize;
    const last=detailLines?detailY+(detailLines-1)*detailStep:heading+(labelLines-1)*step;
    return {heading,detailY,height:last+font*.4+inner};
  };
  const slotWidth=(i:number)=>t==='funnel'?w*Math.max(.6,1-.12*i):t==='hierarchy'&&i>0?w-INDENT:circle(i)?radius*1.1+32:t==='venn'?w*.85:w;
  const lines=(label:string,detail:string,id?:string)=>{
    const bw=id!=null && assigned.has(id)?slotWidth(assigned.get(id)!):w;
    const room=bw-2*(inner+funnelInset(bw));
    return {label:wrapMeasured(label,room,id===main?labelSize*1.25:labelSize,650),detail:wrapMeasured(detail,room,detailSize)};
  };
  // Reserve the largest authored state and every move destination before any reveal.
  const heights=scene.nodes.filter(n=>!circle(assigned.get(n.id)!)).map(n=>Math.max(...[n,...(scene.states??[]).filter(s=>s.target===n.id)].map(s=>{
    const text=lines(s.label,s.detail,n.id);return metrics(text.label.length,text.detail.length,n.id===main).height+(n.value!=null?30:0);
  })));
  const rowHeight=Math.max(...heights,100);
  const slots:Box[]=Array.from({length:8},(_,i)=>({x:pad+w/2+(i%columns)*(w+gap),y:top+rowHeight/2+Math.floor(i/columns)*(rowHeight+gap),w:slotWidth(i),h:rowHeight}));
  if(t==='hierarchy')slots.forEach((s,i)=>{if(i>0)s.x=pad+INDENT+(w-INDENT)/2;});
  if(t==='venn'){
    const cy=top+radius+4;
    slots[0]={x:width/2-radius*.6,y:cy,w:radius*2,h:radius*2};
    slots[1]={x:width/2+radius*.6,y:cy,w:radius*2,h:radius*2};
    slots.slice(2).forEach((s,i)=>Object.assign(s,{x:width/2,y:cy+radius+gap*.6+rowHeight/2+i*(rowHeight+gap)}));
  }
  const used=[...assigned.values(),...scene.actions.filter(a=>a.kind==='move').map(a=>a.to_slot??0)];
  const height=Math.max(...used.map(i=>slots[i].y+slots[i].h/2))+24;
  return {slots,assigned,height,lines,labelSize,detailSize,labelStep,detailStep,main,radius,font,crowded,inner,iconSize,blobRadius,metrics,funnelInset};
}
