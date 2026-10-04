import type { CodeScene } from './api';
import { visualFrame } from './visualState';
export function CodeVisual({scene,time}:{scene:CodeScene;time:number}) {
  const {visible,focused}=visualFrame(scene,time);
  return <div className="code-visual"><p className="visual-note">{scene.payload.language} · source snippet · display only</p><pre aria-label="Source code listing"><code>{scene.payload.text.split(/\r?\n/).map((line,i)=>visible.has(`line_${i+1}`)?<span className="code-line" key={i} data-testid={`visual-line_${i+1}`} data-focused={focused===`line_${i+1}`}><span className="line-number" aria-hidden="true">{i+1}</span>{line||' '}{'\n'}</span>:null)}</code></pre></div>;
}
