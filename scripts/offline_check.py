"""Live one-short check. Python networking is limited to loopback during the run."""
import hashlib
import json
import socket
import sys
import threading
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from app.config import Settings, ROOT
from app.contracts import ImportRequest, ModelShort
from app.providers import Ollama, Speech
from app.sources import parse_transcript, retrieve
from app.validation import attach_evidence, validate_draft, verify_support

connect=socket.socket.connect
blocked=[]
def local_connect(sock,address):
    if isinstance(address,tuple) and address[0] not in {'127.0.0.1','::1','localhost'}:
        blocked.append(str(address));raise OSError('The offline check blocks external network access.')
    return connect(sock,address)
socket.socket.connect=local_connect
settings=Settings();model=Ollama(settings);speech=Speech(settings);cancel=threading.Event()
source=parse_transcript(ImportRequest(title='Offline original sample',text=(ROOT/'fixtures/database-indexes.txt').read_text()))
segments=retrieve([source],'B-tree index lookup')
task={'task':'Teach the B-tree lookup process. Copy exact source excerpts in exactly two narration units. Use 40 to 80 total words and a process diagram. The application derives animation cues. Do not paraphrase.','objective':'Understand a B-tree index lookup','template':'process','question_required':False,'segments':[s.model_dump() for s in segments]}
start=time.monotonic();model.fingerprint();speech.prepare()
def validate(content):
    draft=attach_evidence(content,segments);validate_draft(draft,segments,False)
content=model.generate(ModelShort,task,cancel,validate);draft=attach_evidence(content,segments);verify_support(model,draft,segments,cancel)
key=hashlib.sha256(json.dumps({'draft':draft.model_dump(),'settings':model.fingerprint(),'speech':speech.fingerprint()}).encode()).hexdigest()
name,duration,cached=speech.synthesize(draft.narration_units,key,cancel)
report={'status':'passed','seconds':time.monotonic()-start,'duration_ms':duration,'model':model.fingerprint(),'speech':speech.fingerprint(),'audio_path':name,'blocked_network_attempts':blocked,'offline_boundary':'Python external socket connections blocked. Ollama uses loopback with OLLAMA_NO_CLOUD=1.','draft':draft.model_dump()}
(ROOT/'docs/offline-check.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k!='draft'},indent=2))
