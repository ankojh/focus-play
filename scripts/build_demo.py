"""Build a standalone Focus Play demo folder that opens from index.html with no server.

The demo replays one saved lesson for any goal. Usage:
    .venv/bin/python scripts/build_demo.py [--lesson LESSON_ID] [--out DIR]
"""
import argparse, json, re, shutil, sqlite3, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND, DATA = ROOT / "frontend", ROOT / ".data"
HASH = re.compile(r"^[0-9a-f]{64}$")

README = """Focus Play demo
================

1. Open the folder and double-click index.html (Chrome or Safari).
2. Type any learning goal and click "Create my lesson".
3. The shorts appear one at a time (about 5 seconds each), then a rating slide.

No internet, installation or server is needed. Keep the media folder next to index.html.
To start over, click Create in the top bar.
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--lesson", help="lesson id; defaults to the only or latest complete lesson")
    parser.add_argument("--out", default=str(ROOT.parent / "focus-play-demo"))
    args = parser.parse_args()
    out = Path(args.out).resolve()

    db = sqlite3.connect(DATA / "records.sqlite3")
    rows = [json.loads(body) for (body,) in db.execute("select body from lessons")]
    lessons = [l for l in rows if (l["id"] == args.lesson if args.lesson else l["job"]["status"] == "complete")]
    if not lessons:
        raise SystemExit("No matching complete lesson found.")
    lesson = max(lessons, key=lambda l: l["job"]["updated_at"])

    subprocess.run(["npx", "vite", "build", "--config", "vite.demo.config.ts"], cwd=FRONTEND, check=True)
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(FRONTEND / "dist-demo", out)

    # file:// pages block module scripts and crossorigin requests, so load the IIFE bundle as a classic script.
    html = (out / "demo.html").read_text()
    html = re.sub(r'<script type="module" crossorigin src="\./app\.js"></script>', "", html)
    html = html.replace(' crossorigin href="./app.css"', ' href="./app.css"')
    html = html.replace("</body>", '<script src="./app.js"></script></body>')
    (out / "index.html").write_text(html)
    (out / "demo.html").unlink()
    (out / "lesson-data.js").write_text("window.FOCUS_PLAY_DEMO_LESSON = " + json.dumps(lesson) + ";\n")

    (out / "media/audio").mkdir(parents=True)
    (out / "media/assets").mkdir(parents=True)
    for short in lesson["shorts"]:
        shutil.copy2(DATA / "audio" / short["audio_path"], out / "media/audio")
    assets = {v for v in re.findall(r'"([0-9a-f]{64})"', json.dumps(lesson)) if (DATA / "assets" / f"{v}.png").exists()}
    for asset in assets:
        shutil.copy2(DATA / "assets" / f"{asset}.png", out / "media/assets")
        (out / "media/assets" / f"{asset}.png").chmod(0o644)
    (out / "README.txt").write_text(README)

    archive = shutil.make_archive(str(out), "zip", out.parent, out.name)
    print(f"Demo: {out}/index.html ({len(lesson['shorts'])} shorts, {len(assets)} images)\nZip:  {archive}")


if __name__ == "__main__":
    main()
