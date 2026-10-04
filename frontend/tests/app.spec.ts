import { test, expect, type Page } from '@playwright/test';
import { readFileSync, writeFileSync } from 'node:fs';
const compiledStoryboard=JSON.parse(readFileSync(new URL('../../fixtures/storyboard-lookup-playback.json',import.meta.url),'utf8'));
function storyboardLesson(){const lesson=makeLesson();lesson.shorts[0]={...structuredClone(compiledStoryboard),id:'one'};return lesson;}
async function seekAudio(page:Page,ms:number){
  await page.locator('audio').evaluate((a:HTMLAudioElement)=>a.pause());
  await page.locator('audio').evaluate((a:HTMLAudioElement,ms)=>new Promise<void>(resolve=>{
    a.addEventListener('seeked',()=>resolve(),{once:true});a.currentTime=ms/1000;
  }),ms);
}
// Explicit fixtures. These are not a live YouTube or model check.
const source={id:'src_test',title:'Index video fixture',channel:'Test channel',source_type:'youtube',video_id:'testvideo01',url:'https://www.youtube.com/watch?v=testvideo01',transcript_provider:'youtube-transcript-api',transcript_status:'available',content_hash:'hash',provenance:'Synthetic YouTube caption fixture.',segments:[{id:'seg_a',source_id:'src_test',text:'An index maps keys to rows.',start_ms:12000,end_ms:16000}]};
const evidence={source_id:source.id,segment_ids:['seg_a'],quote:source.segments[0].text,start_ms:12000,end_ms:16000};
function makeShort(id:string,template:string='process') {return {id,objective:`Understand an index ${id}`,prerequisites:[],status:'ready',measured_duration_ms:30000,audio_path:`${'a'.repeat(64)}.wav`,optional:false,question_required:false,cache_hit:false,timings:{},evidence_references:[evidence],narration_units:[{text:'An index maps keys to rows.',evidence,start_ms:0,end_ms:15000},{text:'The planner can still choose a scan.',evidence,start_ms:15000,end_ms:30000}],scenes:[{template,start_ms:0,end_ms:30000,nodes:[{id:'key',label:'Search key',detail:'The value you look up',slot:0,icon:'key',role:template==='dos_donts'?'good':'start',shape:template==='chart'?'bar':'box',value:template==='chart'?10:null},{id:'row',label:'Table row',detail:'Where the matching data lives',slot:1,icon:'table',role:template==='dos_donts'?'bad':'result',shape:template==='chart'?'bar':'box',value:template==='chart'?20:null},...(['cycle','key_fact','steps','dos_donts'].includes(template)?[{id:'plan',label:'Query planner',detail:'Picks an index or a full scan',slot:2,icon:'route',role:template==='dos_donts'?'good':'step',shape:'box',value:null}]:[])],connections:[{id:'edge',source:'key',target:'row'}],actions:[{kind:'appear',target:'key',at_ms:0,to_slot:null},{kind:'appear',target:'row',at_ms:15000,to_slot:null},{kind:'highlight',target:'row',at_ms:15000,to_slot:null},{kind:'draw',target:'edge',at_ms:15000,to_slot:null}]}],question:null,error:null};}
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
async function start(page:Page) {await page.goto('/');await page.getByLabel('Learning goal').fill('Database indexes');await page.getByRole('button',{name:'Create my lesson'}).click();await expect(page.locator('.player')).toBeVisible();await expect.poll(()=>page.locator('audio').evaluate((a:HTMLAudioElement)=>a.readyState)).toBeGreaterThanOrEqual(1);await page.locator('audio').evaluate((a:HTMLAudioElement)=>a.pause());await expect(page.getByRole('button',{name:'Play',exact:true})).toBeVisible();}

test('teaching outcomes and planned practice allowances are visible without a timer',async({page})=>{
  const lesson=makeLesson() as any;
  lesson.teaching_plan_version=2;lesson.plan_diagnostics=['This source supports lookup and maintenance, not a complete database course.'];
  lesson.shorts[0].learning_outcome='Trace a search key to a matching row';lesson.shorts[0].question_required=true;
  lesson.shorts[0].question={prompt:'What does the matching key locate?',options:['A row','A server'],answer_index:0,explanation:'The index maps a key to a row location.',evidence,allowance_ms:20000};
  await mock(page,lesson);await start(page);await expect(page.getByRole('complementary',{name:'Lesson details'})).toBeVisible();
  await expect(page.locator('.learning-point')).toContainText('You’ll be able to: Trace a search key to a matching row');
  await expect(page.locator('.outline')).toContainText('practice allowance 20 sec');
  await expect(page.locator('.outline')).toContainText(lesson.plan_diagnostics[0]);
  await page.getByRole('slider',{name:'Seek within short'}).focus();await page.keyboard.press('End');await expect(page.locator('.question')).toBeVisible();
  await expect(page.locator('.question')).toContainText('20 SEC ALLOWANCE');
  await expect(page.locator('.question')).toContainText('answers are not timed');
  await expect(page.locator('audio')).toHaveAttribute('loop','');
  await expect(page.getByRole('button',{name:'A row',exact:true})).not.toHaveClass(/selected/);
  await page.getByRole('button',{name:'A row',exact:true}).click();await expect(page.locator('.question [role="status"]')).toContainText('Correct.');
});

test('final session copy explains measured videos, practice and coverage shortfall',async({page})=>{
  const lesson=makeLesson() as any;
  lesson.planning={version:2,completion_reason:'coverage_exhausted',completion_detail:'Available sources support only lookup and scans.'};
  lesson.duration_ledger={version:2,measured_ready_media_ms:60000,reserved_practice_ms:20000,estimated_unready_media_ms:0,reserved_closing_ms:0,forecast_total_ms:80000,final_content_ms:80000,original_content_ms:80000,extra_content_ms:0,utilisation:80000/300000,shortfall_ms:190000};
  lesson.planned_duration_ms=80000;
  await mock(page,lesson);await start(page);
  await expect(page.getByTestId('session-duration')).toHaveText('About 1:20 of videos and practice for your 5:00 session');
  await expect(page.locator('.lesson-heading')).toContainText('Measured ready video 1:00');
  await expect(page.locator('.lesson-heading')).toContainText('Scheduled practice allowance 0:20');
  await expect(page.getByTestId('session-shortfall')).toContainText('27% of the original budget');
  await expect(page.getByTestId('session-shortfall')).toContainText(lesson.planning.completion_detail);
  await expect(page.getByTestId('session-shortfall')).toContainText('No repeated loops or generation wait counted');
  await expect(page.locator('audio')).toHaveAttribute('loop','');
});

test('forecast and expanding outline update without moving the selected ready short',async({page})=>{
  const lesson=makeLesson() as any;
  lesson.job.status='running';lesson.status='partially_ready';lesson.job.stage='expanding the lesson outline';
  lesson.planning={version:2,revision:1,completion_reason:null};
  lesson.duration_ledger={version:2,measured_ready_media_ms:60000,reserved_practice_ms:0,estimated_unready_media_ms:0,reserved_closing_ms:0,forecast_total_ms:60000,final_content_ms:null,original_content_ms:60000,extra_content_ms:0,utilisation:.2,shortfall_ms:210000};
  await mock(page,lesson);await start(page);
  await page.getByRole('button',{name:'Next short'}).click();
  await expect(page.locator('.player h2')).toHaveText('Understand an index two');
  const audio=await page.locator('audio').elementHandle();
  await expect(page.getByTestId('session-duration')).toContainText('Current estimate: about 1:00');
  await expect(page.locator('.lesson-heading')).toContainText('Outline may expand');
  lesson.shorts.push({...makeShort('extension'),status:'queued',curriculum_role:'extension',measured_duration_ms:0});
  lesson.short_ids.push('extension');lesson.job.event_sequence=5;lesson.planning.revision=2;
  lesson.duration_ledger.forecast_total_ms=90000;lesson.duration_ledger.estimated_unready_media_ms=30000;
  await expect(page.locator('.outline-item')).toHaveCount(3,{timeout:10000});
  await expect(page.getByTestId('session-duration')).toContainText('Current estimate: about 1:30');
  await expect(page.locator('.outline-item.current')).toContainText('Understand an index two');
  await expect(page.locator('.player h2')).toHaveText('Understand an index two');
  expect(await audio!.evaluate((a:HTMLAudioElement)=>a.isConnected)).toBe(true);
  await expect(page.getByTestId('session-shortfall')).toHaveCount(0);
});

test('library replaces sidebar sources and create, and branding has no Local labels',async({page})=>{
  await mock(page,makeLesson(),{saved:true});await page.goto('/');
  const nav=page.getByRole('navigation',{name:'Main navigation'});
  await expect(nav.getByRole('button')).toHaveCount(2);await expect(nav.getByRole('button',{name:'Sources'})).toHaveCount(0);await expect(nav.getByRole('button',{name:'Create'})).toHaveCount(0);
  await expect(page.locator('.brand')).toHaveText('FocusPlay');await expect(page.locator('.local-status')).toHaveCount(0);
  await nav.getByRole('button',{name:'Library',exact:true}).click();await expect(page.getByRole('heading',{name:'Your library'})).toBeVisible();await expect(page.locator('.library-short')).toHaveCount(2);
  await page.locator('.library-short').nth(1).click();await expect(page.locator('.player h2')).toHaveText('Understand an index two');await expect.poll(()=>page.locator('audio').evaluate((a:HTMLAudioElement)=>a.paused)).toBe(false);
  await page.getByRole('button',{name:'Library',exact:true}).click();await page.reload();await page.getByRole('button',{name:'Library',exact:true}).click();await expect(page.locator('.library-short')).toHaveCount(2);
});
for(const width of [1280,390])test(`Sources toggles the entire details pane without interrupting playback at width ${width}`,async({page})=>{
  await page.setViewportSize({width,height:844});await mock(page);await start(page);
  await page.getByRole('button',{name:'Play',exact:true}).click();await expect(page.getByRole('button',{name:'Pause',exact:true})).toBeVisible();
  const audio=await page.locator('audio').elementHandle();
  const pane=page.getByRole('complementary',{name:'Lesson details'});
  await expect(pane).toBeVisible();await expect(page.getByRole('button',{name:'Hide sources pane'})).toHaveAttribute('aria-expanded','true');
  await page.getByRole('button',{name:'Hide sources pane'}).click();await expect(page.locator('#lesson-details')).toBeHidden();await expect(page.getByRole('heading',{name:'Lesson outline'})).toBeHidden();await expect(page.locator('.evidence-list')).toBeHidden();await expect(page.locator('.lesson-grid')).toHaveClass(/pane-hidden/);
  await expect(page.getByRole('button',{name:'Show sources pane'})).toHaveAttribute('aria-expanded','false');await expect(page.getByRole('button',{name:'Show sources pane'})).toHaveAttribute('aria-controls','lesson-details');expect(await audio!.evaluate((a:HTMLAudioElement)=>!a.paused && a.isConnected)).toBe(true);
  await page.getByRole('button',{name:'Show sources pane'}).click();await expect(pane).toBeVisible();await expect(page.getByRole('heading',{name:'Lesson outline'})).toBeVisible();await expect(page.locator('.evidence-list')).toBeVisible();await expect(page.locator('.lesson-grid')).not.toHaveClass(/pane-hidden/);expect(await audio!.evaluate((a:HTMLAudioElement)=>!a.paused && a.isConnected)).toBe(true);
  await page.getByRole('button',{name:'Hide sources pane'}).click();await page.getByRole('button',{name:'Next short'}).click();await expect(page.locator('.player h2')).toHaveText('Understand an index two');await expect(page.locator('#lesson-details')).toBeHidden();await page.getByRole('button',{name:'Show sources pane'}).click();await expect(page.locator('.learning-point h3')).toHaveText('Understand an index two');
});

test('empty library offers a way to create a lesson',async({page})=>{
  await mock(page);await page.goto('/');await page.getByRole('button',{name:'Library',exact:true}).click();await expect(page.getByText('Your learning library is empty')).toBeVisible();await page.getByRole('button',{name:'Create a lesson',exact:true}).click();await expect(page.getByLabel('Learning goal')).toBeVisible();
});
test('wheel gestures switch shorts once, start narration, and respect feed boundaries',async({page})=>{
  const l=makeLesson();l.shorts.push(makeShort('three'));l.short_ids.push('three');await mock(page,l);await start(page);
  const wheel=async(deltaY:number)=>page.locator('.shorts-view').dispatchEvent('wheel',{deltaY,bubbles:true,cancelable:true});
  await wheel(15);await expect(page.locator('.player h2')).toHaveText('Understand an index one');await wheel(30);await wheel(80);await expect(page.locator('.player h2')).toHaveText('Understand an index two');
  await expect.poll(()=>page.locator('audio').evaluate((a:HTMLAudioElement)=>a.paused)).toBe(false);await expect.poll(()=>page.locator('audio').evaluate((a:HTMLAudioElement)=>a.currentTime)).toBeGreaterThan(0);
  await wheel(-60);await expect(page.locator('.player h2')).toHaveText('Understand an index one');await wheel(-60);await expect(page.locator('.player h2')).toHaveText('Understand an index one');
  await page.locator('.player').focus();await page.keyboard.press('ArrowDown');await expect(page.locator('.player h2')).toHaveText('Understand an index two');await page.keyboard.press('ArrowDown');await expect(page.locator('.player h2')).toHaveText('Understand an index three');await page.keyboard.press('ArrowDown');await expect(page.locator('.player h2')).toHaveText('Understand an index three');
});
test('vertical swipes navigate on mobile and horizontal gestures do not',async({page})=>{
  await page.setViewportSize({width:390,height:844});await mock(page);await start(page);
  const swipe=async(x:number,y:number)=>page.locator('.shorts-view').evaluate((view,{x,y})=>{view.dispatchEvent(new TouchEvent('touchstart',{bubbles:true,touches:[new Touch({identifier:1,target:view,clientX:200,clientY:500})]}));view.dispatchEvent(new TouchEvent('touchend',{bubbles:true,changedTouches:[new Touch({identifier:1,target:view,clientX:x,clientY:y})]}));},{x,y});
  await swipe(80,480);await expect(page.locator('.player h2')).toHaveText('Understand an index one');await swipe(200,300);await expect(page.locator('.player h2')).toHaveText('Understand an index two');await expect.poll(()=>page.locator('audio').evaluate((a:HTMLAudioElement)=>a.paused)).toBe(false);await swipe(200,700);await expect(page.locator('.player h2')).toHaveText('Understand an index one');
});
test('audio automatically loops the current short rather than advancing',async({page})=>{
  await mock(page);await start(page);await page.locator('audio').evaluate(async(a:HTMLAudioElement)=>{a.currentTime=29.8;a.playbackRate=4;await a.play();});
  await expect.poll(()=>page.locator('audio').evaluate((a:HTMLAudioElement)=>a.currentTime)).toBeLessThan(5);await expect(page.locator('.player h2')).toHaveText('Understand an index one');expect(await page.locator('audio').evaluate((a:HTMLAudioElement)=>a.loop && !a.paused)).toBe(true);
});
test('like and dislike are mutually exclusive, toggleable and saved per short',async({page})=>{
  await mock(page);await start(page);const like=page.getByRole('button',{name:'Like short',exact:true}),dislike=page.getByRole('button',{name:'Dislike short',exact:true});
  await like.click();await expect(like).toHaveAttribute('aria-pressed','true');await dislike.click();await expect(like).toHaveAttribute('aria-pressed','false');await expect(dislike).toHaveAttribute('aria-pressed','true');await dislike.click();await expect(dislike).toHaveAttribute('aria-pressed','false');await like.click();
  await page.getByRole('button',{name:'Next short'}).click();await expect(like).toHaveAttribute('aria-pressed','false');await dislike.click();await page.getByRole('button',{name:'Previous short'}).click();await expect(like).toHaveAttribute('aria-pressed','true');await page.reload();await expect(like).toHaveAttribute('aria-pressed','true');
});

test('play, pause, seek, captions and diagrams share the audio clock',async({page})=>{
  await mock(page);await start(page);await expect(page.getByTestId('node-row')).toHaveCount(0);
  await page.getByRole('button',{name:'Play',exact:true}).click();await expect(page.getByRole('button',{name:'Pause',exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Pause',exact:true}).click();const audio=page.locator('audio');expect(await audio.evaluate((a:HTMLAudioElement)=>a.paused)).toBe(true);
  const seek=page.getByLabel('Seek within short');await seek.fill('20000');await expect(page.getByTestId('captions')).toHaveText('The planner can still choose a scan.');await expect(page.getByTestId('node-row')).toBeVisible();await expect(page.getByTestId('connection-edge')).toHaveCount(1);
  expect(await audio.evaluate((a:HTMLAudioElement)=>a.currentTime)).toBeCloseTo(20,0);
  await seek.fill('0');await expect(page.getByTestId('captions')).toHaveText('An index maps keys to rows.');await expect(page.getByTestId('node-row')).toHaveCount(0);
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
  await page.getByRole('button',{name:'Hide sources pane'}).click();await expect(page.getByRole('checkbox')).toHaveCount(0);await expect(page.getByRole('button',{name:/Import|Search YouTube/})).toHaveCount(0);await expect(page.getByLabel('Transcript text')).toHaveCount(0);
});
test('source setup failure keeps retry and offers no source fallback',async({page})=>{
  await mock(page,makeLesson(),{sourceFailure:true});await page.goto('/');await page.getByLabel('Learning goal').fill('Database indexes');await page.getByRole('button',{name:'Create my lesson'}).click();await expect(page.getByRole('alert')).toContainText('YOUTUBE_API_KEY');await expect(page.getByTestId('job-stage')).toHaveText('Searching YouTube');await expect(page.getByRole('button',{name:'Import source',exact:true})).toHaveCount(0);await page.getByRole('button',{name:'Retry',exact:true}).click();await expect(page.getByRole('button',{name:'Play',exact:true})).toBeVisible();
});
test('saved imported lesson opens without creating a lesson or changing its source label',async({page})=>{
  const lesson=makeLesson();lesson.request.source_mode='import';lesson.request.source_ids=['src_test'];Object.assign(lesson.sources[0],{source_type:'import',title:'Saved manual transcript',transcript_provider:null,channel:null,video_id:null,url:null});
  const state=await mock(page,lesson,{saved:true});await page.goto('/');await page.locator('.recent').getByRole('button').click();await expect(page.locator('.player h2')).toHaveText('Understand an index one');await expect(page.locator('.evidence-list')).toContainText('Saved manual transcript');expect(state.creates()).toBe(0);
  await page.getByRole('button',{name:'Library',exact:true}).click();await expect(page.locator('.library-lesson')).toContainText('Database indexes');await expect(page.locator('.library-short')).toHaveCount(2);await page.locator('.library-short').nth(1).click();await expect(page.locator('.player h2')).toHaveText('Understand an index two');await expect(page.locator('.evidence-list')).toContainText('Saved manual transcript');expect(state.creates()).toBe(0);
});
test('request errors do not erase the form',async({page})=>{
  await mock(page,makeLesson(),{failure:true});await page.goto('/');await page.getByLabel('Learning goal').fill('Database indexes');await page.getByRole('button',{name:'Create my lesson'}).click();await expect(page.getByRole('alert')).toContainText('queue is full');await expect(page.getByLabel('Learning goal')).toHaveValue('Database indexes');
});
test('questions remain answerable while shorts loop and extra actions are removed',async({page})=>{
  const l=makeLesson();(l.shorts[0] as any).question={prompt:'What does the index point to?',options:['A row','A server'],answer_index:0,explanation:'The index maps a key to a row location.',evidence,allowance_ms:20000};
  await mock(page,l);await start(page);await page.locator('audio').evaluate((a:HTMLAudioElement)=>{a.currentTime=30;a.dispatchEvent(new Event('ended'));});await page.getByRole('button',{name:'A server',exact:true}).click();await expect(page.getByRole('status')).toContainText('The index maps a key');await expect(page.getByRole('button',{name:'Show an example'})).toHaveCount(0);await expect(page.getByRole('button',{name:'Explain again'})).toHaveCount(0);await expect(page.getByRole('button',{name:'Replay short'})).toHaveCount(0);await expect(page.locator('.player h2')).toHaveText('Understand an index one');
});
test('narrow viewport and keyboard seek remain usable with reduced motion',async({page})=>{
  await page.setViewportSize({width:390,height:844});await page.emulateMedia({reducedMotion:'reduce'});await mock(page);await start(page);expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);await page.locator('.player').focus();await page.keyboard.press('ArrowRight');await expect.poll(()=>page.locator('audio').evaluate((a:HTMLAudioElement)=>a.currentTime)).toBeCloseTo(5,0);await page.keyboard.press('Space');await expect(page.getByRole('button',{name:'Pause',exact:true})).toBeVisible();await page.screenshot({path:'test-results/mobile.png',fullPage:true});
});
for(const reduced of [false,true])test(`compiled storyboard boundaries, state changes, backwards seek and final frame (reduced=${reduced})`,async({page})=>{
  await page.emulateMedia({reducedMotion:reduced?'reduce':'no-preference'});await mock(page,storyboardLesson());await start(page);
  await expect(page.locator('.diagram')).toHaveAttribute('data-scene-id','scene_0');await expect(page.getByTestId('node-node_1')).toContainText('Candidate row');
  await expect(page.locator('.diagram')).not.toHaveAttribute('aria-label',/Storage and updates/);
  await seekAudio(page,5999);await expect(page.getByTestId('node-node_1')).toContainText('Candidate row');
  await seekAudio(page,6000);await expect(page.getByTestId('node-node_1')).toContainText('Matching row');await expect(page.getByTestId('node-node_1')).toHaveAttribute('data-focused','true');
  await seekAudio(page,13999);await expect(page.locator('.diagram')).toHaveAttribute('data-scene-id','scene_0');
  await seekAudio(page,14000);await expect(page.locator('.diagram')).toHaveAttribute('data-scene-id','scene_1');await expect(page.getByTestId('captions')).toHaveText(compiledStoryboard.narration_units[2].text);await expect(page.getByTestId('node-node_0')).toContainText('Index key');await expect(page.getByTestId('connection-conn_0')).toHaveCount(1);
  await seekAudio(page,22000);await expect(page.getByTestId('node-node_0')).toContainText('Storage and updates');
  await seekAudio(page,30000);await expect(page.locator('.diagram')).toHaveAttribute('data-scene-id','scene_1');await expect(page.getByTestId('captions')).toHaveText(compiledStoryboard.narration_units[3].text);
  await seekAudio(page,1000);await expect(page.locator('.diagram')).toHaveAttribute('data-scene-id','scene_0');await expect(page.getByTestId('node-node_1')).toContainText('Candidate row');await expect(page.getByTestId('node-node_0')).toHaveAttribute('data-focused','true');await expect(page.getByTestId('connection-conn_0')).toHaveCount(0);
});

test('reduced motion does not reveal future storyboard nodes or accessibility labels',async({page})=>{
  const lesson=storyboardLesson(),scene=lesson.shorts[0].scenes[0];
  const reveal=scene.actions.splice(1,1)[0];reveal.at_ms=6000;reveal.beat_id='beat_1';scene.actions.splice(2,0,reveal);
  await page.emulateMedia({reducedMotion:'reduce'});await mock(page,lesson);await start(page);await expect(page.getByTestId('node-node_1')).toHaveCount(0);await expect(page.locator('.diagram')).not.toHaveAttribute('aria-label',/Candidate row|Matching row/);
  await seekAudio(page,5999);await expect(page.getByTestId('node-node_1')).toHaveCount(0);await seekAudio(page,6000);await expect(page.getByTestId('node-node_1')).toContainText('Matching row');await seekAudio(page,1000);await expect(page.getByTestId('node-node_1')).toHaveCount(0);
});

test('explicit move and hide states recompute correctly when seeking backward',async({page})=>{
  const lesson=storyboardLesson(),scene=lesson.shorts[0].scenes[0];
  scene.actions[3]={kind:'move',target:'node_1',at_ms:6000,to_slot:2,beat_id:'beat_1'} as any;
  scene.actions.push({kind:'disappear',target:'node_0',at_ms:6000,beat_id:'beat_1'} as any);
  await mock(page,lesson);await start(page);const before=await page.getByTestId('node-node_1').getAttribute('transform');
  await seekAudio(page,7000);await expect(page.getByTestId('node-node_0')).toHaveCount(0);expect(await page.getByTestId('node-node_1').getAttribute('transform')).not.toBe(before);
  await seekAudio(page,1000);await expect(page.getByTestId('node-node_0')).toBeVisible();await expect(page.getByTestId('node-node_1')).toHaveAttribute('transform',before!);
});

test('legacy scene gaps do not silently fall back to the first scene',async({page})=>{
  const lesson=makeLesson(),first=lesson.shorts[0].scenes[0],second=structuredClone(first);first.end_ms=10000;first.actions=first.actions.filter(a=>a.at_ms<10000);second.start_ms=20000;second.actions=second.actions.map(a=>({...a,at_ms:20000}));lesson.shorts[0].scenes.push(second);
  await mock(page,lesson);await start(page);await seekAudio(page,15000);await expect(page.getByRole('alert')).toContainText('No scene covers this audio position');await expect(page.locator('.diagram')).toHaveCount(0);await seekAudio(page,20000);await expect(page.locator('.diagram')).toBeVisible();
});

test('same audio time gives the same storyboard frame after playback and direct seek',async({page})=>{
  await mock(page,storyboardLesson());await start(page);
  await page.locator('audio').evaluate(async(a:HTMLAudioElement)=>{a.playbackRate=8;await a.play();});
  await expect(page.getByTestId('node-node_1')).toContainText('Matching row',{timeout:10000});
  await page.locator('audio').evaluate((a:HTMLAudioElement)=>a.pause());
  const ms=await page.locator('audio').evaluate((a:HTMLAudioElement)=>a.currentTime*1000);
  await expect(page.getByRole('button',{name:'Play',exact:true})).toBeVisible();
  const frame=await page.locator('.diagram').evaluate(el=>el.outerHTML);
  await seekAudio(page,1000);await expect(page.getByTestId('node-node_1')).toContainText('Candidate row');
  await seekAudio(page,ms);await expect.poll(()=>page.locator('.diagram').evaluate(el=>el.outerHTML)).toBe(frame);
});

test('storyboard loops reset visuals and refresh restores the active scene while paused',async({page})=>{
  await mock(page,storyboardLesson());await start(page);await seekAudio(page,23000);await expect(page.getByTestId('node-node_0')).toContainText('Storage and updates');
  // Native audio seeks and the visible control both persist the audio clock.
  await page.reload();await expect(page.locator('.diagram')).toHaveAttribute('data-scene-id','scene_1');await expect(page.getByTestId('node-node_0')).toContainText('Storage and updates');expect(await page.locator('audio').evaluate((a:HTMLAudioElement)=>a.paused)).toBe(true);
  await page.locator('audio').evaluate(async(a:HTMLAudioElement)=>{a.currentTime=29.8;a.playbackRate=4;await a.play();});await expect(page.locator('.diagram')).toHaveAttribute('data-scene-id','scene_0');await expect(page.getByTestId('node-node_1')).toContainText('Candidate row');await expect(page.getByTestId('captions')).toHaveText(compiledStoryboard.narration_units[0].text);
});

for(const width of [1280,390])test(`storyboard screenshots at meaningful beats, width ${width}`,async({page})=>{
  await page.setViewportSize({width,height:844});await mock(page,storyboardLesson());await start(page);
  for(const [beat,ms] of [1000,7000,15000,23000].entries()){
    await seekAudio(page,ms);await expect(page.locator('.diagram')).toHaveAttribute('data-scene-id',beat<2?'scene_0':'scene_1');
    await page.locator('.player').screenshot({path:`test-results/storyboard-${width}-beat-${beat}.png`,style:'.topbar{visibility:hidden}'});
  }
});

test('invalid new storyboard shows an actionable error instead of scene-zero fallback',async({page})=>{
  const lesson=storyboardLesson();lesson.shorts[0].scenes[1].start_ms=15000;
  await mock(page,lesson);await start(page);await expect(page.getByRole('alert')).toContainText('invalid storyboard timing');await expect(page.locator('.diagram')).toHaveCount(0);await expect(page.getByRole('button',{name:'Play',exact:true})).toBeDisabled();
});

test('scene text is escaped and all nine templates are safe to render',async({page})=>{
  const templates=['process','comparison','example','timeline','chart','steps','cycle','dos_donts','key_fact'];
  const l=makeLesson();l.shorts=templates.map(t=>makeShort(t,t));l.short_ids=l.shorts.map(s=>s.id);l.shorts[0].scenes[0].nodes[0].label='<script>alert(1)</script>';
  // Saved lessons predate icons and roles and must still render.
  for(const node of l.shorts[0].scenes[0].nodes as any[]){delete node.icon;delete node.role;}
  await mock(page,l);await start(page);await expect(page.locator('script').filter({hasText:'alert(1)'})).toHaveCount(0);
  for(const [i,template] of templates.entries()){
    if(i)await page.getByRole('button',{name:'Next short'}).click();
    const diagram=page.getByRole('img',{name:new RegExp(`${template} diagram`)});
    await expect(diagram).toBeVisible();
    // Seek past the second narration unit so every node, icon, and arrow is drawn.
    // Wait for metadata first; loading restores the saved position and would undo the seek.
    await page.locator('audio').evaluate((a:HTMLAudioElement)=>new Promise(r=>a.readyState>=1?r(0):a.addEventListener('loadedmetadata',()=>setTimeout(r,0),{once:true})));
    await page.locator('audio').evaluate((a:HTMLAudioElement)=>{a.pause();a.currentTime=20;a.dispatchEvent(new Event('seeked'));});
    await expect(page.locator('.time-readout')).toContainText('0:20');
    if(i)await expect(diagram.locator('svg').first()).toBeVisible();
    else await expect(page.getByTestId('node-row')).toBeVisible();
    await page.locator('.player').screenshot({path:`test-results/template-${template}.png`,style:'.topbar{visibility:hidden}'});
  }
});

for(const width of [320,390,1280])for(const zoom of [1,2])test(`long presentation content stays readable, width ${width}, text scale ${zoom}`,async({page})=>{
  await page.setViewportSize({width,height:900});await page.emulateMedia({reducedMotion:'reduce'});
  const lesson=makeLesson(),s=lesson.shorts[0];
  s.objective='Understand why an INDEX lookup is not always faster than scanning, especially when the search condition matches most rows';
  const node=s.scenes[0].nodes[0];node.label='WWW INDEX lookup — not always faster';node.detail='Only when selective; a scan may win if most rows match the condition.';
  s.narration_units[0].text='An INDEX can map a search key to a row, but the planner may choose a scan when the search condition matches most rows. '.repeat(5).trim();
  await mock(page,lesson);await start(page);
  await page.evaluate(zoom=>document.documentElement.style.fontSize=`${zoom*100}%`,zoom);
  const geometry=async()=>page.getByTestId('node-key').evaluate(g=>{
    const card=g.querySelector('rect')!.getBBox();const texts=[...g.querySelectorAll('text')];
    return {minSize:Math.min(...texts.map(t=>parseFloat(getComputedStyle(t).fontSize)*t.getScreenCTM()!.a)),fits:texts.every(t=>{const b=t.getBBox();return b.x>=card.x && b.x+b.width<=card.x+card.width+.5 && b.y>=card.y && b.y+b.height<=card.y+card.height+.5;}),label:texts.filter(t=>t.classList.contains('node-label')).map(t=>t.textContent).join('').replace(/\s/g,''),detail:texts.filter(t=>t.classList.contains('node-detail')).map(t=>t.textContent).join('').replace(/\s/g,'')};
  });
  await expect.poll(async()=> (await geometry()).minSize).toBeGreaterThanOrEqual(14*zoom-.1);
  const measured=await geometry();writeFileSync(`test-results/presentation-long-${width}-${zoom}.json`,JSON.stringify({width,zoom,...measured},null,2));expect(measured.fits).toBe(true);expect(measured.label).toBe(node.label.replace(/\s/g,''));expect(measured.detail).toBe(node.detail.replace(/\s/g,''));
  expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
  const captions=page.getByTestId('captions');await expect(captions).toHaveText(s.narration_units[0].text);
  expect(await captions.evaluate(e=>e.scrollHeight>e.clientHeight)).toBe(true);
  await captions.hover();await page.mouse.wheel(0,160);await expect.poll(()=>captions.evaluate(e=>e.scrollTop)).toBeGreaterThan(0);await expect(page.locator('.player h2')).toHaveText(s.objective);
  await page.getByRole('button',{name:'Hide captions'}).click();await expect(captions).toBeHidden();await page.getByText('Full transcript',{exact:true}).click();await expect(page.locator('.short-transcript')).toContainText(s.narration_units[0].text);
  await page.getByRole('button',{name:'Seek to narration beat 2'}).click();await expect.poll(()=>page.locator('audio').evaluate((a:HTMLAudioElement)=>a.currentTime)).toBe(15);
  await page.getByRole('button',{name:'Show captions'}).click();await expect(captions).toHaveText(s.narration_units[1].text);
  await page.locator('.player').screenshot({path:`test-results/presentation-long-${width}-${zoom}.png`,style:'.topbar{visibility:hidden}'});
});

for(const template of ['comparison','key_fact'])for(const width of [320,390,1280])test(`dense ${template} preserves qualifiers at width ${width}`,async({page})=>{
  await page.setViewportSize({width,height:900});await page.emulateMedia({reducedMotion:'reduce'});
  const lesson=makeLesson(),scene=lesson.shorts[0].scenes[0];scene.template=template;
  scene.nodes=Array.from({length:4},(_,i)=>({...scene.nodes[0],id:i===0?'key':i===1?'row':`support_${i}`,slot:i,label:'WWW INDEX lookup — not always faster',detail:'Only if selective; most matching rows may favour a full scan.'}));
  await mock(page,lesson);await start(page);await seekAudio(page,20000);
  const measured=await page.locator('[data-testid^="node-"]').evaluateAll(nodes=>nodes.map(g=>{
    const rect=(g.querySelector('rect') as SVGRectElement).getBBox();const labels=[...g.querySelectorAll('.node-label')] as SVGTextElement[],details=[...g.querySelectorAll('.node-detail')] as SVGTextElement[];
    return {label:labels.map(t=>t.textContent).join('').replace(/\s/g,''),detail:details.map(t=>t.textContent).join('').replace(/\s/g,''),fits:[...labels,...details].every(t=>{const b=t.getBBox();return b.x>=rect.x && b.x+b.width<=rect.x+rect.width+.5 && b.y+b.height<=rect.y+rect.height+.5;}),min:Math.min(...details.map(t=>parseFloat(getComputedStyle(t).fontSize)*t.getScreenCTM()!.a))};
  }));expect(measured).toHaveLength(4);
  for(const node of measured){expect(node.label).toBe(scene.nodes[0].label.replace(/\s/g,''));expect(node.detail).toBe(scene.nodes[0].detail.replace(/\s/g,''));expect(node.min).toBeGreaterThanOrEqual(13.99);expect(node.fits).toBe(true);}
  writeFileSync(`test-results/presentation-dense-${template}-${width}.json`,JSON.stringify({width,template,nodes:measured},null,2));
  await page.locator('.player').screenshot({path:`test-results/presentation-dense-${template}-${width}.png`,style:'.topbar{visibility:hidden}'});
});

test('caption and transcript text are escaped without live announcements',async({page})=>{
  const lesson=makeLesson();lesson.shorts[0].narration_units[0].text='<img src=x onerror="window.injected=true"> A safe spoken phrase.';
  lesson.sources[0].title='<svg onload="window.injected=true">Source label</svg>';
  lesson.shorts[0].scenes[0].nodes[0].detail='<img src=x onerror="window.injected=true">';
  await mock(page,lesson);await start(page);await page.getByText('Full transcript',{exact:true}).click();
  await expect(page.locator('.evidence-list')).toContainText(lesson.sources[0].title);
  await expect(page.locator('.diagram')).toHaveAttribute('aria-label',/onerror/);
  await expect(page.locator('.evidence-list svg[onload],.diagram img')).toHaveCount(0);
  await expect(page.getByTestId('captions')).toHaveAttribute('aria-live','off');await expect(page.locator('.captions img,.short-transcript img')).toHaveCount(0);
  await expect(page.locator('.short-transcript')).toContainText('<img src=x');expect(await page.evaluate(()=>('injected' in window))).toBe(false);
});

test('settled arrows and paused instructional states do not move; role changes retain entity identity',async({page})=>{
  await mock(page,storyboardLesson());await start(page);await seekAudio(page,1000);
  const before=await page.getByTestId('node-node_1').getAttribute('data-entity-color');
  const bounds=await page.locator('.diagram').getAttribute('viewBox');await seekAudio(page,7000);
  await expect(page.getByTestId('node-node_1')).toHaveAttribute('data-entity-color',before!);await expect(page.locator('.diagram')).toHaveAttribute('viewBox',bounds!);
  await seekAudio(page,15000);
  await expect(page.getByTestId('connection-conn_0').locator('path')).not.toHaveAttribute('stroke-dasharray');
  const markup=await page.locator('.diagram').evaluate(e=>e.outerHTML);
  await page.waitForTimeout(250);expect(await page.locator('.diagram').evaluate(e=>e.outerHTML)).toBe(markup);
});

test('ready-ahead is contiguous, excludes practice, and updates on seek and jumps',async({page})=>{
  const lesson=makeLesson();lesson.shorts.push(makeShort('three'));lesson.short_ids.push('three');lesson.shorts[1].status='queued';lesson.shorts[0].question_required=true;
  await mock(page,lesson);await start(page);
  await expect(page.getByTestId('ready-ahead')).toContainText('Next 0 shorts ready');await expect(page.getByTestId('ready-ahead')).toContainText('0:30 contiguous');
  await expect(page.getByTestId('client-preload')).toContainText('browser: 0');await expect(page.getByRole('button',{name:'Next short',exact:true})).toBeDisabled();
  await seekAudio(page,20000);await expect(page.getByTestId('ready-ahead')).toContainText('0:10 contiguous');
  await page.locator('.outline-item').nth(2).click();await expect(page.locator('.player h2')).toHaveText('Understand an index three');await expect(page.getByTestId('ready-ahead')).toContainText('0:30 contiguous');
  await expect(page.getByRole('button',{name:'Previous short',exact:true})).toBeDisabled();
});

test('preload window is bounded to two ready shorts and releases blobs on selection and exit',async({page})=>{
  await page.addInitScript(()=>{
    const original=URL.createObjectURL,release=URL.revokeObjectURL,fetchOriginal=window.fetch;
    const stats={created:0,released:0,requests:[] as string[]};(window as any).preloadStats=stats;
    URL.createObjectURL=blob=>{stats.created++;return original(blob);};URL.revokeObjectURL=url=>{stats.released++;release(url);};
    window.fetch=(input,init)=>{if(String(input).includes('/api/audio/'))stats.requests.push(String(input));return fetchOriginal(input,init);};
  });
  const lesson=makeLesson();lesson.shorts.push(makeShort('three'),makeShort('four'));lesson.short_ids.push('three','four');lesson.shorts.forEach((s,i)=>s.audio_path=`${'abcd'[i].repeat(64)}.wav`);
  await mock(page,lesson);await start(page);await expect(page.getByTestId('client-preload')).toContainText('browser: 2');
  let stats=await page.evaluate(()=>(window as any).preloadStats);expect(stats.requests).toHaveLength(2);expect(stats.requests.some((s:string)=>s.includes('d'.repeat(64)))).toBe(false);
  await page.getByRole('button',{name:'Next short',exact:true}).click();await expect(page.getByTestId('client-preload')).toContainText('browser: 2');
  await expect.poll(()=>page.evaluate(()=>(window as any).preloadStats.released)).toBeGreaterThanOrEqual(2);
  await page.getByRole('button',{name:'Library',exact:true}).click();await expect.poll(()=>page.evaluate(()=>{const s=(window as any).preloadStats;return s.created-s.released;})).toBe(0);
});

test('explicit unready selection waits for that short without skipping and records only local observed wait',async({page})=>{
  const lesson=makeLesson();lesson.shorts[1].status='queued';lesson.job.status='running';lesson.status='partially_ready';
  const state=await mock(page,lesson);await start(page);await page.locator('.outline-item').nth(1).click();
  await expect(page.locator('.preparing-player h2')).toHaveText('Preparing the short you selected.');await expect(page.locator('.outline-item.current')).toContainText('Understand an index two');
  lesson.shorts[1].status='ready';lesson.job.event_sequence=5;
  await expect(page.locator('.player h2')).toHaveText('Understand an index two',{timeout:10000});expect(state.creates()).toBe(1);
  const waits=await page.evaluate(()=>JSON.parse(localStorage.getItem('focusplay:requested-waits:v1')||'[]'));
  expect(waits).toHaveLength(1);expect(waits[0].outcome).toBe('ready');expect(waits[0].seconds).toBeGreaterThan(0);expect(waits[0]).not.toHaveProperty('goal');
  await expect(page.locator('audio')).toHaveAttribute('loop','');
});

test('stale and duplicate snapshots cannot downgrade ready content or reset selection',async({page})=>{
  const lesson=makeLesson();lesson.job.status='running';lesson.status='partially_ready';await mock(page,lesson);await start(page);
  await page.getByRole('button',{name:'Next short',exact:true}).click();await expect(page.locator('.player h2')).toHaveText('Understand an index two');
  const handle=await page.locator('audio').elementHandle();lesson.shorts[1].status='queued';lesson.job.event_sequence=3;
  const snapshot=async(sequence:number)=>{await page.waitForResponse(async response=>response.url().endsWith('/api/lessons/lesson_test') && (await response.json()).job.event_sequence===sequence);await page.evaluate(()=>new Promise<void>(resolve=>requestAnimationFrame(()=>requestAnimationFrame(()=>resolve()))));};
  await snapshot(3);await expect(page.locator('.player h2')).toHaveText('Understand an index two');
  lesson.job.event_sequence=4;await snapshot(4);expect(await handle!.evaluate(a=>a.isConnected)).toBe(true);await expect(page.locator('.player h2')).toHaveText('Understand an index two');
});

test('essential upcoming images must decode before client preload is reported ready',async({page})=>{
  const lesson=makeLesson();const mixed=JSON.parse(readFileSync(new URL('../../fixtures/mixed-visuals.json',import.meta.url),'utf8'));
  lesson.shorts[1]={...mixed.shorts[2],id:'two',audio_path:'b'.repeat(64)+'.wav'};
  await mock(page,lesson);await start(page);
  await expect(page.getByTestId('ready-ahead')).toContainText('Next 1 short ready');
  // The mock deliberately has no asset route: missing image must not be hidden by ready audio.
  await expect(page.getByTestId('client-preload')).toContainText('could not be preloaded');await expect(page.getByTestId('client-preload')).toContainText('browser: 0');
});

test('oversized media is not retained by speculative preload',async({page})=>{
  const lesson=makeLesson();lesson.shorts[1].audio_path='b'.repeat(64)+'.wav';await mock(page,lesson);
  await page.route(`**/api/audio/${'b'.repeat(64)}.wav`,route=>route.fulfill({contentType:'audio/wav',headers:{'Content-Length':'4000000'},body:Buffer.alloc(1)}));
  await start(page);await expect(page.getByTestId('client-preload')).toContainText('could not be preloaded');await expect(page.getByTestId('client-preload')).toContainText('browser: 0');
});

test('server media loss prevents next preload and surfaces repair rather than an infinite wait',async({page})=>{
  const lesson=makeLesson() as any;lesson.readiness={version:1,ready_short_ids:['one'],missing_media_short_ids:['two'],initial_contiguous_media_ms:30000};
  await mock(page,lesson);await start(page);await expect(page.getByTestId('ready-ahead')).toContainText('Next 0 shorts ready');await expect(page.getByTestId('client-preload')).toContainText('browser: 0');
  await expect(page.getByRole('alert')).toContainText('Published media is missing');await expect(page.getByRole('button',{name:'Repair missing media',exact:true})).toBeVisible();
});

test('cancel stops inflight prefetch and preserves completed playback',async({page})=>{
  const lesson=makeLesson();lesson.job.status='running';lesson.status='partially_ready';lesson.shorts[1].audio_path='b'.repeat(64)+'.wav';
  await mock(page,lesson);
  let resolve:(()=>void)|undefined;const pending=new Promise<void>(done=>resolve=done);let requested=false;
  await page.route(`**/api/audio/${'b'.repeat(64)}.wav`,async route=>{requested=true;await pending;await route.abort().catch(()=>{});});
  await start(page);await expect.poll(()=>requested).toBe(true);await page.getByRole('button',{name:'Cancel preparation',exact:true}).click();
  await expect(page.getByTestId('job-stage')).toHaveText('cancelled');resolve!();await expect(page.getByTestId('client-preload')).toContainText('browser: 0');await expect(page.locator('.player h2')).toHaveText('Understand an index one');
});

test('autoplay blocking is actionable and not a corrupt audio error',async({page})=>{
  await page.addInitScript(()=>{HTMLMediaElement.prototype.play=()=>Promise.reject(new DOMException('Blocked','NotAllowedError'));});
  await mock(page);await start(page);await page.getByRole('button',{name:'Play',exact:true}).click();
  await expect(page.getByRole('alert')).toContainText('Your browser blocked autoplay. Click Play');await expect(page.getByRole('alert')).not.toContainText('file');await expect(page.getByRole('button',{name:'Play',exact:true})).toBeEnabled();
});

test('diagram text and captions meet AA contrast; focus is visible and answer stays after backward seek',async({page})=>{
  const lesson=makeLesson();(lesson.shorts[0] as any).question={prompt:'Where does the key lead?',options:['A row','A server'],answer_index:0,explanation:'An index key locates the matching row.',evidence,allowance_ms:20000};
  await mock(page,lesson);await start(page);await page.getByLabel('Seek within short').fill('30000');
  const ratios=await page.locator('.diagram').evaluate(svg=>{
    const rgb=(color:string)=>color.match(/[\d.]+/g)!.slice(0,3).map(Number);
    const lum=(color:string)=>rgb(color).map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4;}).reduce((sum,v,i)=>sum+v*[.2126,.7152,.0722][i],0);
    const contrast=(a:string,b:string)=>(Math.max(lum(a),lum(b))+.05)/(Math.min(lum(a),lum(b))+.05);
    const values=[...svg.querySelectorAll('g[data-testid^="node-"]')].flatMap(g=>[...g.querySelectorAll('text')].map(t=>contrast(getComputedStyle(t).fill,getComputedStyle(g.querySelector('rect')!).fill)));
    const caption=document.querySelector('.captions')!,style=getComputedStyle(caption);values.push(contrast(style.color,style.backgroundColor));return values;
  });writeFileSync('test-results/presentation-contrast.json',JSON.stringify({ratios,minimum:Math.min(...ratios)},null,2));expect(Math.min(...ratios)).toBeGreaterThanOrEqual(4.5);
  await page.keyboard.press('Tab');await page.locator('.diagram-frame').focus();expect(await page.locator('.diagram-frame').evaluate(e=>getComputedStyle(e).outlineStyle)).toBe('solid');
  await page.getByRole('button',{name:'A row',exact:true}).click();await expect(page.getByRole('button',{name:'A row',exact:true})).toHaveAttribute('aria-pressed','true');
  await seekAudio(page,1000);await expect(page.locator('.question')).toBeVisible();await expect(page.locator('.question [role=status]')).toContainText('Correct.');
});
