import { test, expect, type Page } from '@playwright/test';
// Explicit fixtures. These are not a live YouTube or model check.
const source={id:'src_test',title:'Index video fixture',channel:'Test channel',source_type:'youtube',video_id:'testvideo01',url:'https://www.youtube.com/watch?v=testvideo01',transcript_provider:'youtube-transcript-api',transcript_status:'available',content_hash:'hash',provenance:'Synthetic YouTube caption fixture.',segments:[{id:'seg_a',source_id:'src_test',text:'An index maps keys to rows.',start_ms:12000,end_ms:16000}]};
const evidence={source_id:source.id,segment_ids:['seg_a'],quote:source.segments[0].text,start_ms:12000,end_ms:16000};
function makeShort(id:string,template:string='process') {return {id,objective:`Understand an index ${id}`,prerequisites:[],status:'ready',measured_duration_ms:30000,audio_path:`${'a'.repeat(64)}.wav`,optional:false,question_required:false,cache_hit:false,timings:{},evidence_references:[evidence],narration_units:[{text:'An index maps keys to rows.',evidence,start_ms:0,end_ms:15000},{text:'The planner can still choose a scan.',evidence,start_ms:15000,end_ms:30000}],scenes:[{template,start_ms:0,end_ms:30000,nodes:[{id:'key',label:'Search key',detail:'Input value',slot:0,shape:template==='chart'?'bar':'box',value:template==='chart'?10:null},{id:'row',label:'Table row',detail:'Matching row',slot:1,shape:template==='chart'?'bar':'box',value:template==='chart'?20:null}],connections:[{id:'edge',source:'key',target:'row'}],actions:[{kind:'appear',target:'key',at_ms:0,to_slot:null},{kind:'appear',target:'row',at_ms:15000,to_slot:null},{kind:'highlight',target:'row',at_ms:15000,to_slot:null},{kind:'draw',target:'edge',at_ms:15000,to_slot:null}]}],question:null,error:null};}
function makeLesson() {const now=Date.now()/1000;return {id:'lesson_test',request:{goal:'Database indexes',prior_knowledge:'beginner',time_budget_seconds:300,language:'en',source_mode:null as string|null,source_ids:[] as string[],request_id:'test-request'},status:'ready',sources:[structuredClone(source)],objectives:[],short_ids:['one','two'],shorts:[makeShort('one'),makeShort('two','comparison')],planned_duration_ms:60000,original_planned_duration_ms:60000,extra_allowance_ms:0,provider_settings:{},metrics:{},job:{id:'job_test',lesson_id:'lesson_test',status:'complete',stage:'ready',event_sequence:4,error:null,created_at:now,updated_at:now,stage_timings:{}}};}
function wav() {const n=24000*30*2,b=Buffer.alloc(44+n);b.write('RIFF',0);b.writeUInt32LE(36+n,4);b.write('WAVEfmt ',8);b.writeUInt32LE(16,16);b.writeUInt16LE(1,20);b.writeUInt16LE(1,22);b.writeUInt32LE(24000,24);b.writeUInt32LE(48000,28);b.writeUInt16LE(2,32);b.writeUInt16LE(16,34);b.write('data',36);b.writeUInt32LE(n,40);return b;}
async function mock(page:Page,lesson=makeLesson(),options:{failure?:boolean;sourceFailure?:boolean;progress?:boolean;emptySources?:boolean;saved?:boolean}={}) {
  let snapshot=0,creates=0,retried=false,body:any;
  const failed={...lesson,status:'failed',shorts:[],short_ids:[],job:{...lesson.job,status:'failed',stage:'Searching YouTube',error:{code:'YOUTUBE_KEY_MISSING',message:'Add YOUTUBE_API_KEY to the server .env file and restart the server. Then retry.'}}};
  await page.route('**/api/**',async route=>{
    const url=new URL(route.request().url()),path=url.pathname;
    const fulfill=(body:unknown,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)});
    if(path==='/api/health')return fulfill({ready:true,model_ready:true,speech_ready:true,youtube_ready:true,youtube_message:'YouTube search configured.',model:'qwen3:8b',digest:'test',speech_provider:'kokoro',voice:'af_heart',message:'Local providers are ready.'});
    if(path==='/api/sources')return fulfill({sources:options.emptySources?[]:lesson.sources});
    if(path==='/api/lessons' && route.request().method()==='GET')return fulfill(options.saved?[lesson]:[]);
    if(path==='/api/lessons' && route.request().method()==='POST') {creates++;body=route.request().postDataJSON();if(options.failure)return fulfill({code:'QUEUE_FULL',message:'The local queue is full. Wait for a lesson to finish, then retry.'},429);return fulfill(options.sourceFailure?failed:options.progress?{...lesson,status:'queued',job:{...lesson.job,status:'running',stage:'Searching YouTube',event_sequence:1},shorts:[],short_ids:[]}:lesson,202);}
    if(path.endsWith('/events')) {snapshot++;return route.fulfill({contentType:'text/event-stream',body:`event: progress\nid: ${snapshot}\ndata: {"stage":"progress"}\n\n`});}
    if(path.endsWith('/cancel'))return fulfill({...lesson,status:'cancelled',job:{...lesson.job,status:'cancelled',stage:'cancelled',event_sequence:6}});
    if(path.endsWith('/retry')){retried=true;return fulfill({...lesson,status:'ready',job:{...lesson.job,event_sequence:7}});}
    if(path.endsWith('/explanations'))return fulfill({...lesson,extra_allowance_ms:40000,planned_duration_ms:100000,job:{...lesson.job,event_sequence:7},shorts:[...lesson.shorts,makeShort('extra','example')],short_ids:[...lesson.short_ids,'extra']});
    if(path.startsWith('/api/lessons/'))return fulfill(options.sourceFailure&&!retried?failed:options.progress && snapshot<2?{...lesson,status:'partially_ready',job:{...lesson.job,status:'running',stage:'Reading video transcripts',event_sequence:2},shorts:[lesson.shorts[0],{...lesson.shorts[1],status:'queued'}]}:lesson);
    if(path.startsWith('/api/audio/')){const b=wav(),range=route.request().headers()['range'];if(range){const m=range.match(/bytes=(\d+)-(\d*)/);const start=Number(m?.[1]??0),end=m?.[2]?Math.min(Number(m[2]),b.length-1):b.length-1;return route.fulfill({status:206,contentType:'audio/wav',headers:{'Accept-Ranges':'bytes','Content-Range':`bytes ${start}-${end}/${b.length}`,'Content-Length':String(end-start+1)},body:b.subarray(start,end+1)});}return route.fulfill({contentType:'audio/wav',headers:{'Accept-Ranges':'bytes','Content-Length':String(b.length)},body:b});}
    return fulfill({code:'NOT_FOUND',message:'Not found.'},404);
  });
  return {creates:()=>creates,connections:()=>snapshot,body:()=>body};
}
async function start(page:Page) {await page.goto('/');await page.getByLabel('Learning goal').fill('Database indexes');await page.getByRole('button',{name:'Create my lesson'}).click();await expect(page.getByRole('button',{name:'Play',exact:true})).toBeVisible();}

test('play, pause, seek, replay, captions and diagrams share the audio clock',async({page})=>{
  await mock(page);await start(page);await expect(page.getByTestId('node-row')).toHaveCount(0);
  await page.getByRole('button',{name:'Play',exact:true}).click();await expect(page.getByRole('button',{name:'Pause',exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Pause',exact:true}).click();const audio=page.locator('audio');expect(await audio.evaluate((a:HTMLAudioElement)=>a.paused)).toBe(true);
  const seek=page.getByLabel('Seek within short');await seek.fill('20000');await expect(page.getByTestId('captions')).toHaveText('The planner can still choose a scan.');await expect(page.getByTestId('node-row')).toBeVisible();await expect(page.getByTestId('connection-edge')).toHaveCount(1);
  expect(await audio.evaluate((a:HTMLAudioElement)=>a.currentTime)).toBeCloseTo(20,0);
  await page.getByRole('button',{name:'Replay short'}).click();await expect(page.getByTestId('captions')).toHaveText('An index maps keys to rows.');await expect(page.getByTestId('node-row')).toHaveCount(0);
  await page.getByRole('button',{name:'Next short'}).click();await expect(page.locator('.player h2')).toHaveText('Understand an index two');await page.getByRole('button',{name:'Previous short'}).click();await expect(page.locator('.player h2')).toHaveText('Understand an index one');
});
test('refresh restores selected short and seek position without starting audio',async({page})=>{
  await mock(page);await start(page);await page.getByRole('button',{name:'Next short'}).click();await page.getByLabel('Seek within short').fill('18000');await page.reload();await expect(page.locator('.player h2')).toHaveText('Understand an index two');await expect(page.getByTestId('captions')).toHaveText('The planner can still choose a scan.');expect(await page.locator('audio').evaluate((a:HTMLAudioElement)=>a.paused)).toBe(true);
});
test('progress and reconnection recover snapshots without a second create request',async({page})=>{
  const state=await mock(page,makeLesson(),{progress:true});await start(page);await expect(page.getByTestId('job-stage')).toHaveText('ready',{timeout:10000});expect(state.connections()).toBeGreaterThanOrEqual(2);await page.reload();await expect(page.getByRole('button',{name:'Play',exact:true})).toBeVisible();expect(state.creates()).toBe(1);
});
test('three-field form submits without sources or manual entry',async({page})=>{
  const state=await mock(page,makeLesson(),{emptySources:true});await page.goto('/');
  await expect(page.getByText('Where should the lesson start?')).toHaveCount(0);
  await expect(page.getByRole('button',{name:'Create my lesson'})).toBeEnabled();
  await page.getByLabel('Learning goal').fill('Database indexes');await page.getByLabel('What do you already know?').selectOption('custom');await page.getByLabel('Describe current knowledge').fill('I know SQL');await page.getByLabel('How much time do you have?').selectOption('120');
  await page.getByRole('button',{name:'Create my lesson'}).click();await expect(page.getByRole('button',{name:'Play',exact:true})).toBeVisible();
  expect(Object.keys(state.body()).sort()).toEqual(['goal','language','prior_knowledge','request_id','time_budget_seconds']);expect(state.body()).toMatchObject({goal:'Database indexes',prior_knowledge:'I know SQL',time_budget_seconds:120});
  await expect(page.getByRole('link',{name:'Open source',exact:true})).toHaveAttribute('href','https://www.youtube.com/watch?v=testvideo01&t=12s');
  await page.getByRole('button',{name:/Sources/}).click();await expect(page.getByRole('checkbox')).toHaveCount(0);await expect(page.getByRole('button',{name:/Import|Search YouTube/})).toHaveCount(0);await expect(page.getByLabel('Transcript text')).toHaveCount(0);
});
test('source setup failure keeps retry and offers no source fallback',async({page})=>{
  await mock(page,makeLesson(),{sourceFailure:true});await page.goto('/');await page.getByLabel('Learning goal').fill('Database indexes');await page.getByRole('button',{name:'Create my lesson'}).click();await expect(page.getByRole('alert')).toContainText('YOUTUBE_API_KEY');await expect(page.getByTestId('job-stage')).toHaveText('Searching YouTube');await expect(page.getByRole('button',{name:'Import source',exact:true})).toHaveCount(0);await page.getByRole('button',{name:'Retry',exact:true}).click();await expect(page.getByRole('button',{name:'Play',exact:true})).toBeVisible();
});
test('saved imported lesson opens without creating a lesson or changing its source label',async({page})=>{
  const lesson=makeLesson();lesson.request.source_mode='import';lesson.request.source_ids=['src_test'];Object.assign(lesson.sources[0],{source_type:'import',title:'Saved manual transcript',transcript_provider:null,channel:null,video_id:null,url:null});
  const state=await mock(page,lesson,{saved:true});await page.goto('/');await page.locator('.recent').getByRole('button').click();await expect(page.getByRole('button',{name:'Play',exact:true})).toBeVisible();await expect(page.locator('.evidence-list')).toContainText('Saved manual transcript');expect(state.creates()).toBe(0);
  await page.getByRole('button',{name:/Sources/}).click();await expect(page.locator('.source-type')).toHaveText('IMPORTED TRANSCRIPT');await expect(page.getByRole('checkbox')).toHaveCount(0);
});
test('request errors do not erase the form',async({page})=>{
  await mock(page,makeLesson(),{failure:true});await page.goto('/');await page.getByLabel('Learning goal').fill('Database indexes');await page.getByRole('button',{name:'Create my lesson'}).click();await expect(page.getByRole('alert')).toContainText('queue is full');await expect(page.getByLabel('Learning goal')).toHaveValue('Database indexes');
});
test('questions explain the answer and extra shorts need a visible time decision',async({page})=>{
  const l=makeLesson();(l.shorts[0] as any).question={prompt:'What does the index point to?',options:['A row','A server'],answer_index:0,explanation:'The index maps a key to a row location.',evidence,allowance_ms:20000};
  await mock(page,l);await start(page);await page.locator('audio').evaluate((a:HTMLAudioElement)=>{a.currentTime=30;a.dispatchEvent(new Event('ended'));});await page.getByRole('button',{name:'A server',exact:true}).click();await expect(page.getByRole('status')).toContainText('The index maps a key');await page.getByRole('button',{name:'Show an example'}).click();await expect(page.getByRole('dialog')).toContainText('adds up to 40 seconds');await page.getByRole('button',{name:'Add up to 40 seconds'}).click();await expect(page.locator('.lesson-heading')).toContainText('Extra allowance +40 sec');
});
test('narrow viewport and keyboard seek remain usable with reduced motion',async({page})=>{
  await page.setViewportSize({width:390,height:844});await page.emulateMedia({reducedMotion:'reduce'});await mock(page);await start(page);expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);await page.locator('.player').focus();await page.keyboard.press('ArrowRight');await expect.poll(()=>page.locator('audio').evaluate((a:HTMLAudioElement)=>a.currentTime)).toBeCloseTo(5,0);await page.keyboard.press('Space');await expect(page.getByRole('button',{name:'Pause',exact:true})).toBeVisible();await page.screenshot({path:'test-results/mobile.png',fullPage:true});
});
test('scene text is escaped and all five templates are safe to render',async({page})=>{
  const l=makeLesson();l.shorts=['process','comparison','example','timeline','chart'].map(t=>makeShort(t,t));l.short_ids=l.shorts.map(s=>s.id);l.shorts[0].scenes[0].nodes[0].label='<script>alert(1)</script>';
  await mock(page,l);await start(page);await expect(page.locator('script').filter({hasText:'alert(1)'})).toHaveCount(0);for(const template of ['comparison','example','timeline','chart']){await page.getByRole('button',{name:'Next short'}).click();await expect(page.getByRole('img',{name:new RegExp(template+' diagram')})).toBeVisible();}
});
