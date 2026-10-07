import { test, expect, type Page } from '@playwright/test';
import { readFileSync } from 'node:fs';
const fixture=JSON.parse(readFileSync(new URL('../../fixtures/mixed-visuals.json',import.meta.url),'utf8'));
const image=readFileSync(new URL('../../fixtures/assets/lookup-illustration.png',import.meta.url));
function lesson(){const now=Date.now()/1000;return {id:'mixed_lesson',request:{goal:'Mixed visual diagnostic',prior_knowledge:'beginner',time_budget_seconds:120,language:'en',request_id:'visual-test'},status:'ready',sources:[{id:'src_visual',title:'Original illustrative test passages',source_type:'original_sample',transcript_status:'available',provenance:fixture.notice,content_hash:'fixture',segments:fixture.segments}],objectives:[],short_ids:fixture.shorts.map((s:any)=>s.id),shorts:structuredClone(fixture.shorts),planned_duration_ms:90000,original_planned_duration_ms:90000,extra_allowance_ms:0,provider_settings:{},metrics:{},job:{id:'visual_job',lesson_id:'mixed_lesson',status:'complete',stage:'ready',event_sequence:1,created_at:now,updated_at:now}};}
function wav(){const n=24000*30*2,b=Buffer.alloc(44+n);b.write('RIFF',0);b.writeUInt32LE(36+n,4);b.write('WAVEfmt ',8);b.writeUInt32LE(16,16);b.writeUInt16LE(1,20);b.writeUInt16LE(1,22);b.writeUInt32LE(24000,24);b.writeUInt32LE(48000,28);b.writeUInt16LE(2,32);b.writeUInt16LE(16,34);b.write('data',36);b.writeUInt32LE(n,40);return b;}
async function mock(page:Page,body=lesson(),missing=false){
  await page.route('**/api/**',async route=>{
    const path=new URL(route.request().url()).pathname;
    const json=(value:unknown,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(value)});
    if(path==='/api/health')return json({ready:true,model_ready:true,speech_ready:true,youtube_ready:true,model:'fixture',speech_provider:'fixture',voice:'fixture',message:'Deterministic diagnostic only.'});
    if(path==='/api/sources')return json({sources:body.sources});
    if(path==='/api/lessons')return json(route.request().method()==='GET'?[]:body);
    if(path.endsWith('/events'))return route.fulfill({contentType:'text/event-stream',body:`event: done\ndata: ${JSON.stringify(body)}\n\n`});
    if(path.startsWith('/api/lessons/'))return json(body);
    if(path.startsWith('/api/assets/'))return missing?json({code:'ASSET_MISSING',message:'Missing'},404):route.fulfill({contentType:'image/png',body:image});
    if(path.startsWith('/api/audio/')){
      const b=wav(),range=route.request().headers()['range'];
      if(range){const m=range.match(/bytes=(\d+)-(\d*)/),start=Number(m?.[1]??0),end=m?.[2]?Math.min(Number(m[2]),b.length-1):b.length-1;return route.fulfill({status:206,contentType:'audio/wav',headers:{'Accept-Ranges':'bytes','Content-Range':`bytes ${start}-${end}/${b.length}`},body:b.subarray(start,end+1)});}
      return route.fulfill({contentType:'audio/wav',body:b});
    }
    return json({message:'Not found'},404);
  });
}
async function start(page:Page){await page.goto('/');await page.getByLabel('Learning goal').fill('Mixed visual diagnostic');await page.getByRole('button',{name:'Create my lesson'}).click();await expect(page.locator('.player')).toBeVisible();await expect.poll(()=>page.locator('audio').evaluate((a:HTMLAudioElement)=>a.readyState)).toBeGreaterThanOrEqual(1);await page.locator('audio').evaluate((a:HTMLAudioElement)=>a.pause());}
async function seek(page:Page,ms:number){await expect.poll(()=>page.locator('audio').evaluate((a:HTMLAudioElement)=>a.readyState)).toBeGreaterThanOrEqual(1);await page.locator('audio').evaluate((a:HTMLAudioElement)=>a.pause());if(ms%100===0)await page.getByLabel('Seek within short').fill(String(ms));else await page.locator('audio').evaluate((a:HTMLAudioElement,ms)=>{a.pause();a.currentTime=ms/1000;},ms);await expect.poll(()=>page.locator('audio').evaluate((a:HTMLAudioElement)=>a.currentTime)).toBeCloseTo(ms/1000,1);}

for(const width of [1280,390])test(`mixed diagrams/table/chart share the audio clock at width ${width}`,async({page})=>{
  await page.setViewportSize({width,height:1000});await page.emulateMedia({reducedMotion:'reduce'});await mock(page);await start(page);
  await expect(page.locator('.diagram')).toBeVisible();await seek(page,9999);await expect(page.locator('.diagram')).toBeVisible();
  await seek(page,10000);await expect(page.locator('[data-visual-kind=table]')).toBeVisible();await expect(page.getByTestId('visual-row_0')).toContainText('Alpha');await expect(page.getByTestId('visual-row_0').locator('td').nth(1)).toHaveAttribute('data-focused','true');
  await page.screenshot({path:`test-results/visual-table-${width}.png`,fullPage:true});
  await seek(page,20000);await expect(page.locator('[data-visual-kind=chart]')).toBeVisible();await expect(page.locator('.player-kicker')).toHaveText(new RegExp(`^03 / ${String(fixture.shorts[0].narration_units.length).padStart(2,'0')}`));
  await expect(page.locator('.chart-visual')).toContainText('illustrative data, not measurements');await expect(page.getByTestId('visual-point_0')).toContainText('-12 units');await expect(page.getByTestId('visual-point_2')).toContainText('1500 units');await expect(page.getByTestId('visual-point_1').locator('.chart-zero-value')).toHaveCount(1);
  const bars=await page.locator('.chart-bar').evaluateAll(nodes=>nodes.map(n=>(n as HTMLElement).style.width));expect(parseFloat(bars[2])).toBeGreaterThan(99);expect(parseFloat(bars[0])).toBeLessThan(1);expect(parseFloat(bars[1])).toBe(0);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);await page.screenshot({path:`test-results/visual-chart-${width}.png`,fullPage:true});
  await seek(page,30000);await expect(page.locator('[data-visual-kind=chart]')).toBeVisible();await seek(page,10000);await expect(page.getByTestId('visual-row_0')).toContainText('Alpha');await seek(page,0);await expect(page.locator('.diagram')).toBeVisible();
});

for(const width of [1280,390])test(`code reveal, focus, seek and escaped source text at width ${width}`,async({page})=>{
  const body=lesson(),s=body.shorts[1];
  s.scenes[0].payload.text='<script>window.injected=true</script>\n<img src=x onerror="window.injected=true">';
  await page.setViewportSize({width,height:1000});await mock(page,body);await start(page);await page.getByRole('button',{name:'Next short'}).click();await page.locator('audio').evaluate((a:HTMLAudioElement)=>a.pause());await seek(page,0);
  await expect(page.locator('pre')).toContainText('<script>window.injected=true</script>');await expect(page.getByTestId('visual-line_2')).toHaveCount(0);await expect(page.locator('.data-visual script,.data-visual img')).toHaveCount(0);
  await seek(page,15000);await expect(page.getByTestId('visual-line_2')).toHaveAttribute('data-focused','true');expect(await page.evaluate(()=>('injected' in window))).toBe(false);
  await page.screenshot({path:`test-results/visual-code-escaped-${width}.png`,fullPage:true});await seek(page,0);await expect(page.getByTestId('visual-line_2')).toHaveCount(0);expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
});

for(const width of [1280,390])test(`original source code fixture screenshot at width ${width}`,async({page})=>{
  await page.setViewportSize({width,height:1000});await mock(page);await start(page);await page.getByRole('button',{name:'Next short'}).click();await page.locator('audio').evaluate((a:HTMLAudioElement)=>a.pause());await seek(page,15000);
  await expect(page.locator('pre')).toContainText('SELECT name');await expect(page.getByTestId('visual-line_2')).toHaveAttribute('data-focused','true');await expect(page.locator('.code-visual')).toContainText('display only');await page.screenshot({path:`test-results/visual-code-${width}.png`,fullPage:true});
});

test('all-zero chart uses a visible zero marker and long labels do not overflow',async({page})=>{
  await page.setViewportSize({width:390,height:1000});const body=lesson(),p=body.shorts[0].scenes[2].payload;
  p.points.forEach((p:any)=>{p.value=0;p.label='Long label for a zero source value, shown without truncation';});
  await mock(page,body);await start(page);await seek(page,20000);await expect(page.locator('.chart-visual')).toContainText('All values are zero');await expect(page.locator('.chart-zero-value')).toHaveCount(3);expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});

for(const width of [1280,390])test(`managed image attribution and timed annotations at width ${width}`,async({page})=>{
  await page.setViewportSize({width,height:1000});await mock(page);await start(page);await page.getByRole('button',{name:'Next short'}).click();await page.getByRole('button',{name:'Next short'}).click();await page.locator('audio').evaluate((a:HTMLAudioElement)=>a.pause());await seek(page,0);
  await expect(page.getByAltText('Illustrative key card pointing to a table row')).toBeVisible();await expect(page.locator('.visual-credit')).toContainText('CC0 1.0');await expect(page.getByTestId('visual-annotation_0')).toHaveCount(0);
  await seek(page,15000);await expect(page.getByTestId('visual-annotation_0')).toHaveAttribute('data-focused','true');await page.getByText('Asset provenance and permission').click();await expect(page.locator('.image-visual')).toContainText('Image rights are separate from lesson evidence.');
  await page.screenshot({path:`test-results/visual-image-${width}.png`,fullPage:true});await seek(page,0);await expect(page.getByTestId('visual-annotation_0')).toHaveCount(0);
});

test('missing essential image fails visibly and offers explicit retry',async({page})=>{
  await mock(page,lesson(),true);await start(page);await page.getByRole('button',{name:'Next short'}).click();await page.getByRole('button',{name:'Next short'}).click();await expect(page.locator('.image-visual [role=alert]')).toContainText('essential image could not load');await page.getByRole('button',{name:'Retry image'}).click();await expect(page.locator('.image-visual [role=alert]')).toBeVisible();
});

test('scrolling an overflowing visual reads its content instead of switching shorts',async({page})=>{
  await page.setViewportSize({width:390,height:844});const body=lesson(),p=body.shorts[0].scenes[2].payload;
  p.points=Array.from({length:8},(_,i)=>({id:`point_${i}`,label:`Source value ${i}`,value:i,segment_id:'seg_chart'}));
  const scene=body.shorts[0].scenes[2];scene.actions=p.points.map((p:any)=>({kind:'appear',target:p.id,at_ms:20000,beat_id:'beat_2'}));
  await mock(page,body);await start(page);await seek(page,20000);const reader=page.locator('.data-visual');
  expect(await reader.evaluate(e=>e.scrollHeight>e.clientHeight)).toBe(true);
  await reader.hover();await page.mouse.wheel(0,180);await expect.poll(()=>reader.evaluate(e=>e.scrollTop)).toBeGreaterThan(0);await expect(reader).toHaveAttribute('data-scene-id','scene_2');
  await reader.focus();await page.keyboard.press('ArrowDown');await expect(reader).toHaveAttribute('data-scene-id','scene_2');
  await page.getByRole('button',{name:'Next short'}).click();await expect(page.locator('[data-visual-kind=code]')).toBeVisible();
});

test('negative-only chart keeps its right-edge zero baseline and zero marker visible',async({page})=>{
  const body=lesson(),p=body.shorts[0].scenes[2].payload;p.points.forEach((p:any,i:number)=>p.value=[-12,-5,0][i]);
  await mock(page,body);await start(page);await seek(page,20000);
  const position=await page.getByTestId('visual-point_2').evaluate(e=>{const track=e.querySelector('.chart-track')!.getBoundingClientRect(),zero=e.querySelector('.chart-zero-value')!.getBoundingClientRect();return {left:zero.left,right:zero.right,edge:track.right};});
  expect(position.left).toBeLessThan(position.edge);expect(position.right).toBeLessThanOrEqual(position.edge);
});

for(const corruption of ['unknown','empty','nonfinite','unsafe-asset'])test(`corrupt renderer ${corruption} cannot produce a blank ready player`,async({page})=>{
  const body=lesson();body.shorts=[body.shorts[0]];body.short_ids=[body.shorts[0].id];const scene=body.shorts[0].scenes[2];
  if(corruption==='unknown')scene.kind='html';if(corruption==='empty')scene.payload.points=[];if(corruption==='nonfinite')scene.payload.points[0].value=null;if(corruption==='unsafe-asset'){body.shorts[0]=lesson().shorts[2];body.shorts[0].scenes[0].payload.asset_id='https://evil.test/image.svg';}
  await mock(page,body);await page.goto('/');await page.getByLabel('Learning goal').fill('Mixed diagnostic');await page.getByRole('button',{name:'Create my lesson'}).click();await expect(page.locator('.player [role=alert]')).toContainText('invalid visual data');await expect(page.getByRole('button',{name:'Play',exact:true})).toBeDisabled();
});
