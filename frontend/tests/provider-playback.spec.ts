import { test, expect } from '@playwright/test';

// Opt-in playback of ACTUAL saved provider output/audio served by an isolated API.
// No fabricated response, audio fixture, inference or source-credit call in this test.
test('real generated storyboard plays, seeks, loops and survives refresh', async ({ page, request }) => {
  const configured = process.env.FOCUS_PROVIDER_API;
  test.skip(!configured, 'Set FOCUS_PROVIDER_API to the isolated saved-provider playback API.');
  const base = new URL(configured!);
  expect(base.protocol).toBe('http:');
  expect(['127.0.0.1', 'localhost']).toContain(base.hostname);
  expect(base.pathname).toBe('/');
  const response = await request.get(new URL('/api/lessons', base).href);
  expect(response.ok()).toBe(true);
  const lessons = await response.json();
  const lessonId = process.env.FOCUS_PROVIDER_LESSON_ID || 'lesson_real_provider_check';
  const lesson = lessons.find((l: any) => l.id === lessonId);
  expect(lesson).toBeTruthy();
  const short = lesson.shorts[0];
  const expectedProvider = process.env.FOCUS_PROVIDER_EXPECTED_PROVIDER || 'turbofieldfare';
  expect(['turbofieldfare', 'ollama']).toContain(expectedProvider);
  expect(short.provider_settings.provider).toBe(expectedProvider);
  expect(short.provider_settings.speech.provider).toBe('kokoro');
  expect(short.status).toBe('ready');
  if (lessonId === 'lesson_real_provider_check') {
    expect(short.scenes.map((s: any) => s.kind)).toEqual(['diagram', 'table', 'chart']);
  } else {
    expect(short.scenes.length).toBeGreaterThan(0);
    expect(short.narration_units.length).toBeGreaterThanOrEqual(2);
  }
  await page.route('**/api/**', async route => {
    // Forward reads only to the REAL isolated API; never create a new lesson.
    expect(route.request().method()).toBe('GET');
    const url = new URL(route.request().url());
    const actual = await route.fetch({ url: new URL(url.pathname + url.search, base).href });
    await route.fulfill({ response: actual });
  });
  await page.setViewportSize({ width: 1280, height: 1000 });
  await page.goto('/');
  await page.getByRole('button', { name: 'Library', exact: true }).click();
  await page.getByRole('button', { name: 'Open lesson', exact: true }).click();
  await expect(page.locator('.player')).toBeVisible();
  await expect.poll(() => page.locator('audio').evaluate((a: HTMLAudioElement) => a.readyState)).toBeGreaterThanOrEqual(1);
  if (await page.locator('audio').evaluate((a: HTMLAudioElement) => a.paused)) {
    await page.getByRole('button', { name: 'Play', exact: true }).click();
  }
  await expect.poll(() => page.locator('audio').evaluate((a: HTMLAudioElement) => a.currentTime)).toBeGreaterThan(.25);
  await page.getByRole('button', { name: 'Pause', exact: true }).click();
  await expect(page.locator('audio')).toHaveAttribute('loop', '');
  expect(await page.locator('audio').evaluate((a: HTMLAudioElement) => Math.round(a.duration * 1000))).toBe(short.measured_duration_ms);
  for (const scene of short.scenes) {
    const ms = scene.start_ms + 100;
    await page.locator('audio').evaluate((a: HTMLAudioElement, ms: number) => { a.pause(); a.currentTime = ms / 1000; }, ms);
    const selector = scene.kind === 'diagram' ? '.diagram' : `[data-visual-kind=${scene.kind}]`;
    await expect(page.locator(selector)).toBeVisible();
    const beat = short.narration_units.find((b: any) => b.scene_id === scene.id);
    await expect(page.getByTestId('captions')).toHaveText(beat.text);
    await page.screenshot({ path: `test-results/real-provider-${scene.kind}.png`, fullPage: true });
  }
  for (const beat of short.narration_units) {
    await page.locator('audio').evaluate((a: HTMLAudioElement, ms: number) => { a.pause(); a.currentTime = ms / 1000; }, beat.start_ms + 100);
    await expect(page.getByTestId('captions')).toHaveText(beat.text);
    const scene = short.scenes.find((s: any) => s.id === beat.scene_id);
    if (scene.kind === 'diagram') {
      const focus = [...scene.actions].reverse().find((a: any) => a.kind === 'highlight' && a.at_ms <= beat.start_ms);
      if (focus) await expect(page.getByTestId(`node-${focus.target}`)).toHaveAttribute('data-focused', 'true');
    }
  }
  await page.screenshot({ path: 'test-results/real-provider-final-beat.png', fullPage: true });
  await page.reload();
  const lastKind = short.scenes[short.scenes.length - 1].kind;
  await expect(page.locator(lastKind === 'diagram' ? '.diagram' : `[data-visual-kind=${lastKind}]`)).toBeVisible();
  await expect(page.getByRole('button', { name: 'Play', exact: true })).toBeVisible();
  // Restoration applies at loadedmetadata; don't race it with a direct seek.
  await expect.poll(() => page.locator('audio').evaluate((a: HTMLAudioElement) => a.readyState)).toBeGreaterThanOrEqual(1);
  await page.getByLabel('Seek within short').fill('0');
  await expect(page.locator('.diagram')).toBeVisible();
  await page.getByText('Full transcript', { exact: true }).click();
  for (const unit of short.narration_units) {
    await expect(page.locator('.short-transcript')).toContainText(unit.text);
  }
});
