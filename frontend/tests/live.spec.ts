import { test, expect } from '@playwright/test';
// Explicit live test: actual YouTube search, captions, local model and local voice.
test('real YouTube lesson: incremental playback, refresh, source links and time budget',async({page,request})=>{
  test.skip(process.env.FOCUS_LIVE!=='1','Set FOCUS_LIVE=1 with YOUTUBE_API_KEY and local providers ready.');
  test.setTimeout(180000);
  const health=await request.get('/api/health');expect((await health.json()).ready).toBe(true);
  await page.goto('/');
  await page.getByLabel('Learning goal').fill('Explain database indexes: compare an index lookup with a table scan, then give a SQL lookup example.');
  await page.getByLabel('What do you already know?').selectOption('custom');await page.getByLabel('Describe current knowledge').fill('I know basic SQL SELECT queries.');
  const created=page.waitForResponse(r=>r.url().endsWith('/api/lessons') && r.request().method()==='POST');
  await page.getByRole('button',{name:'Create my lesson'}).click();const response=await created;expect(response.status()).toBe(202);const accepted=await response.json();const lid=accepted.id;
  await expect(page.locator('.player')).toBeVisible({timeout:150000});
  await expect.poll(()=>page.locator('audio').evaluate((a:HTMLAudioElement)=>a.readyState)).toBeGreaterThanOrEqual(1);
  const first=await(await request.get(`/api/lessons/${lid}`)).json();expect(first.shorts[0].status).toBe('ready');
  if(first.shorts.length>1&&!first.shorts[0].cache_hit)expect(first.shorts.slice(1).some((s:any)=>s.status!=='ready')).toBe(true);
  if(await page.locator('audio').evaluate((a:HTMLAudioElement)=>a.paused))await page.getByRole('button',{name:'Play',exact:true}).click();await expect.poll(()=>page.locator('audio').evaluate((a:HTMLAudioElement)=>a.currentTime)).toBeGreaterThan(.25);await page.getByRole('button',{name:'Pause',exact:true}).click();await page.getByLabel('Seek within short').fill('5000');
  await expect.poll(()=>page.locator('audio').evaluate((a:HTMLAudioElement)=>a.currentTime)).toBeCloseTo(5,0);await page.reload();await expect(page.getByRole('button',{name:'Play',exact:true})).toBeVisible();await expect.poll(()=>page.locator('audio').evaluate((a:HTMLAudioElement)=>a.currentTime)).toBeCloseTo(5,0);
  await expect.poll(async()=>{const r=await request.get(`/api/lessons/${lid}`);return (await r.json()).job.status;},{timeout:150000,intervals:[1000]}).toBe('complete');
  const final=await(await request.get(`/api/lessons/${lid}`)).json();expect(final.planned_duration_ms).toBeLessThanOrEqual(300000);expect(final.shorts.every((s:any)=>s.audio_path && s.evidence_references.length)).toBe(true);
  expect(final.sources.length).toBeGreaterThan(0);
  for(const source of final.sources){expect(source.source_type).toBe('youtube');expect(source.video_id).toMatch(/^[A-Za-z0-9_-]{11}$/);expect(source.url).toBe(`https://www.youtube.com/watch?v=${source.video_id}`);expect(source.channel).toBeTruthy();expect(source.transcript_provider).toBe('youtube-transcript-api');}
  const ids=new Set(final.sources.map((s:any)=>s.id));for(const short of final.shorts){expect(short.evidence_references.every((e:any)=>ids.has(e.source_id))).toBe(true);if(short.question)expect(ids.has(short.question.evidence.source_id)).toBe(true);}
  await expect(page.locator('.evidence-list').getByRole('link',{name:'Open source'}).first()).toHaveAttribute('href',/^https:\/\/www.youtube.com\/watch\?v=[A-Za-z0-9_-]{11}&t=\d+s$/);await page.screenshot({path:'test-results/live-youtube-desktop.png',fullPage:true});
  // A reused request ID returns this same lesson, even after completion.
  const repeat=await request.post('/api/lessons',{data:response.request().postDataJSON()});expect((await repeat.json()).id).toBe(lid);
});
