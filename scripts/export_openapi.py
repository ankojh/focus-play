import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.main import app
path = Path(__file__).resolve().parents[1] / "backend" / "openapi.json"
path.write_text(json.dumps(app.openapi(), indent=2) + "\n")
app.state.store.close()
print(path)
