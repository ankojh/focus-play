import type { ChartScene } from './api';
import { visualFrame } from './visualState';
export function chartDomain(values:number[]):[number,number] {
  const low=Math.min(0,...values),high=Math.max(0,...values);
  return low===high?[0,1]:[low,high];
}
export function ChartVisual({scene,time}:{scene:ChartScene;time:number}) {
  const {visible,focused}=visualFrame(scene,time),p=scene.payload;
  // Domain uses the whole dataset to keep the scale stable across beats; never truncate bars.
  const [low,high]=chartDomain(p.points.map(v=>v.value));
  const x=(v:number)=>(v-low)/(high-low)*100,zero=x(0);
  const number=(v:number)=>v.toLocaleString(undefined,{maximumSignificantDigits:6});
  return <div className="chart-visual"><p className="visual-note">{p.axis_label} ({p.unit}) · linear scale including zero{p.illustrative?' · illustrative data, not measurements':''}</p><div className="chart-axis" aria-label={`Domain ${low} to ${high} ${p.unit}`}><span>{number(low)}</span><span>{number(high)}</span></div><div className="chart-plot">{p.points.filter(v=>visible.has(v.id)).map(v=><div className="chart-point" key={v.id} data-testid={`visual-${v.id}`} data-focused={focused===v.id}><div className="chart-label"><span>{v.label}</span><strong>{v.value} {p.unit}</strong></div><div className="chart-track" role="img" aria-label={`${v.label}: ${v.value} ${p.unit}`}><span className="chart-zero" style={{left:zero===100?undefined:`${zero}%`,right:zero===100?0:undefined}}/><span className="chart-bar" data-negative={v.value<0} style={{left:`${Math.min(zero,x(v.value))}%`,width:`${Math.abs(x(v.value)-zero)}%`}}/>{v.value===0&&<span className="chart-zero-value" style={{left:zero===100?undefined:`${zero}%`,right:zero===100?0:undefined}}/>}</div></div>)}</div>{p.points.every(v=>v.value===0)&&<p className="visual-note">All values are zero · domain 0 to 1 for display only.</p>}</div>;
}
