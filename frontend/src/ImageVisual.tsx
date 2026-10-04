import { useState } from 'react';
import type { ImageScene } from './api';
import { visualFrame } from './visualState';
export function ImageVisual({scene,time}:{scene:ImageScene;time:number}) {
  const [state,setState]=useState<'loading'|'loaded'|'failed'>('loading'),[retry,setRetry]=useState(0);
  const {visible,focused}=visualFrame(scene,time),p=scene.payload;
  if(!visible.has('image'))return null;
  return <figure className="image-visual">
    {state==='loading'&&<p role="status">Loading managed image…</p>}
    {state==='failed'?<div className="error" role="alert">This essential image could not load. Restart the local server to repair bundled assets, then retry.<button onClick={()=>{setState('loading');setRetry(r=>r+1);}}>Retry image</button></div>:<div className="annotated-image" style={{aspectRatio:`${p.width}/${p.height}`}} data-focused={focused==='image'}><img key={retry} src={`/api/assets/${p.asset_id}${retry?`?retry=${retry}`:''}`} width={p.width} height={p.height} alt={p.alt} onLoad={()=>setState('loaded')} onError={()=>setState('failed')}/>{state==='loaded'&&p.annotations!.filter(a=>visible.has(a.id)).map(a=><span className="image-annotation" data-testid={`visual-${a.id}`} data-focused={focused===a.id} key={a.id} style={{left:`${a.x*100}%`,top:`${a.y*100}%`}}>{a.label}</span>)}</div>}
    <figcaption>{p.caption}<span className="visual-credit">{scene.asset.illustrative?'Illustrative image · ':''}{scene.asset.attribution}</span><details><summary>Asset provenance and permission</summary><p>{scene.asset.creator} · {scene.asset.permission_basis}</p><p>{scene.asset.source_context}</p><p>Original source: {scene.asset.original_source}</p><p>Acquired: {new Date(scene.asset.acquired_at*1000).toISOString().slice(0,10)} · {scene.asset.mime_type} · {scene.asset.byte_size.toLocaleString()} bytes</p><p>Image rights are separate from lesson evidence.</p></details></figcaption>
  </figure>;
}
