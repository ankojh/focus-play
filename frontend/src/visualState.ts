import type { VisualScene } from './api';
export type DataScene = Exclude<VisualScene, {nodes:unknown}>;
const idPattern=/^[a-z][a-z0-9_]{0,19}$/;
const hashPattern=/^[a-f0-9]{64}$/;
const text=(v:unknown,max:number,min=1):v is string=>typeof v==='string' && v.length>=min && v.length<=max;

export function visualTargets(scene:DataScene):string[] {
  switch(scene.kind){
    case 'table':return scene.payload.rows.flatMap(r=>[r.id,...r.cells.map((_,i)=>`${r.id}_c${i}`)]);
    case 'code':return scene.payload.text.split(/\r?\n/).map((_,i)=>`line_${i+1}`);
    case 'chart':return scene.payload.points.map(p=>p.id);
    case 'image':return ['image',...scene.payload.annotations!.map(a=>a.id)];
  }
}
export function primaryTargets(scene:DataScene):string[] {
  return scene.kind==='table'?scene.payload.rows.map(r=>r.id):visualTargets(scene);
}
// Snap semantic changes at measured beat boundaries. Reduced motion never exposes future items.
export function visualFrame(scene:DataScene,time:number){
  const visible=new Set<string>();let focused:string|null=null;
  for(const a of scene.actions){
    if(a.at_ms>time)break;
    if(a.kind==='appear')visible.add(a.target);
    if(a.kind==='disappear'){visible.delete(a.target);if(focused===a.target || (scene.kind==='table' && focused?.startsWith(`${a.target}_c`)) || (scene.kind==='image' && a.target==='image'))focused=null;}
    if(a.kind==='highlight')focused=a.target;
  }
  return {visible,focused};
}

// Defense against corrupt saved snapshots; the server remains the schema authority.
export function visualError(scene:DataScene):boolean {
  try {
    const p=scene.payload;
    if(scene.visual_version!==1 || !p)return true;
    switch(scene.kind){
      case 'table': {
        const t=scene.payload;
        if(!Array.isArray(t.columns)||t.columns.length<1||t.columns.length>4||t.columns.some(c=>!text(c,120))||!Array.isArray(t.rows)||t.rows.length<1||t.rows.length>8||t.rows.some(r=>!idPattern.test(r.id)||!Array.isArray(r.cells)||r.cells.length!==t.columns.length||r.cells.some(c=>!text(c,120))))return true;
        break;
      }
      case 'code': {
        const c=scene.payload;
        if(!text(c.text,6000)||!['text','python','sql','javascript','shell'].includes(c.language)||c.text.split(/\r?\n/).length>30||c.text.split(/\r?\n/).some(l=>l.length>200))return true;
        break;
      }
      case 'chart': {
        const c=scene.payload;
        if(c.chart_kind!=='bar'||c.scale_policy!=='zero_inclusive'||!text(c.unit,40)||!text(c.axis_label,80)||!Array.isArray(c.points)||c.points.length<1||c.points.length>8||c.points.some(p=>!idPattern.test(p.id)||!text(p.label,60)||!Number.isFinite(p.value)||Math.abs(p.value)>1e12))return true;
        break;
      }
      case 'image': {
        const i=scene.payload,a=scene.asset;
        if(!hashPattern.test(i.asset_id)||!text(i.alt,240,5)||!text(i.caption,240)||!a||a.id!==i.asset_id||a.content_hash!==a.id||a.status!=='ready'||a.width!==i.width||a.height!==i.height||!['image/png','image/jpeg'].includes(a.mime_type)||!text(a.attribution,300,5)||!text(a.permission_basis,500,5)||!Array.isArray(i.annotations)||i.annotations.length>6||i.annotations.some(n=>!idPattern.test(n.id)||!text(n.label,100)||!Number.isFinite(n.x)||!Number.isFinite(n.y)||n.x<0||n.x>1||n.y<0||n.y>1))return true;
        break;
      }
      default:return true;
    }
    const all=visualTargets(scene),primary=primaryTargets(scene),known=new Set(all);
    if(known.size!==all.length)return true;
    const visible=new Set<string>(),revealed=new Set<string>();let previous=scene.start_ms;
    for(const a of scene.actions){
      if(!['appear','disappear','highlight'].includes(a.kind)||!known.has(a.target)||a.to_slot!=null||a.state_id!=null||a.at_ms<previous||a.at_ms<scene.start_ms||a.at_ms>=scene.end_ms)return true;
      const row=scene.kind==='table'&&!primary.includes(a.target)?a.target.replace(/_c\d+$/,''):null;
      if(row&&(!visible.has(row)||a.kind!=='highlight'))return true;
      if(scene.kind==='image'&&a.target!=='image'&&!visible.has('image'))return true;
      if(a.kind==='appear'){if(visible.has(a.target))return true;visible.add(a.target);revealed.add(a.target);}
      else if(a.kind==='disappear'){if(!visible.has(a.target))return true;visible.delete(a.target);}
      else if(!visible.has(a.target)&&!row)return true;
      previous=a.at_ms;
    }
    return primary.some(t=>!revealed.has(t));
  }catch{return true;}
}
