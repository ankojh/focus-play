import type { TableScene } from './api';
import { visualFrame } from './visualState';
export function TableVisual({scene,time}:{scene:TableScene;time:number}) {
  const {visible,focused}=visualFrame(scene,time),p=scene.payload;
  return <div className="table-scroll"><table><caption>{p.illustrative?'Illustrative table · not measured data':'Source-derived table'}</caption><thead><tr>{p.columns.map((c,i)=><th key={i} scope="col">{c}</th>)}</tr></thead><tbody>{p.rows.filter(r=>visible.has(r.id)).map(r=><tr key={r.id} data-testid={`visual-${r.id}`} data-focused={focused===r.id}>{r.cells.map((c,i)=><td key={i} data-focused={focused===`${r.id}_c${i}`}>{c}</td>)}</tr>)}</tbody></table></div>;
}
