import { useLayoutEffect, useRef } from 'react';
import type { Short } from './api';
import { duration } from './api';

// The measured synthesis unit is the only caption clock. In particular, a long
// legacy unit is scrollable, not divided into guessed words/subphrase timestamps.
export function Captions({text,visible}:{text:string|undefined;visible:boolean}){
  const reader=useRef<HTMLDivElement>(null);
  useLayoutEffect(()=>{if(reader.current)reader.current.scrollTop=0;},[text]);
  return <div className="caption-safe-area" hidden={!visible}>
    <div ref={reader} className="captions visual-reader" data-testid="captions" tabIndex={0} aria-label="Current measured narration phrase. Scroll to read longer captions." aria-live="off">{text}</div>
  </div>;
}
export function Transcript({short,seek}:{short:Short;seek:(ms:number)=>void}){
  return <details className="short-transcript visual-reader" key={short.id}>
    <summary>Full transcript</summary>
    <p className="muted">Phrase boundaries are measured from speech. No word-level alignment is available.</p>
    <ol>{short.narration_units.map((unit,i)=><li key={i}><button className="transcript-time" aria-label={`Seek to narration beat ${i+1}`} onClick={()=>seek(unit.start_ms)}>{duration(unit.start_ms)}</button><p>{unit.text}</p></li>)}</ol>
  </details>;
}
