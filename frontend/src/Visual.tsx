import type { VisualScene } from './api';
import './visuals.css';
import { Diagram } from './Diagram';
import { TableVisual } from './TableVisual';
import { CodeVisual } from './CodeVisual';
import { ChartVisual } from './ChartVisual';
import { ImageVisual } from './ImageVisual';
import { visualError } from './visualState';
export function Visual({scene,time,overview=false,pan=0}:{scene:VisualScene;time:number;overview?:boolean;pan?:number}) {
  if(!scene.kind || scene.kind==='diagram')return <Diagram scene={scene} time={time} overview={overview} pan={pan}/>;
  if(visualError(scene))return <p role="alert" className="error">This visual has invalid renderer data. Retry lesson preparation.</p>;
  const content=scene.kind==='table'?<TableVisual scene={scene} time={time}/>:scene.kind==='code'?<CodeVisual scene={scene} time={time}/>:scene.kind==='chart'?<ChartVisual scene={scene} time={time}/>:scene.kind==='image'?<ImageVisual key={scene.payload.asset_id} scene={scene} time={time}/>:null;
  return <section className="data-visual visual-reader" tabIndex={0} data-scene-id={scene.id} data-visual-kind={scene.kind} aria-label={`${scene.summary}. Scroll within the visual to read all content.`}><span className="visual-kind">{scene.kind.toUpperCase()}</span><h3>{scene.summary}</h3>{content}</section>;
}
