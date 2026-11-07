"""Runs hub and guard together as a Render web service."""
import http.server
import os
import signal
import subprocess
import sys
import threading
import time
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
REQUIRED = ('HUB_BOT_TOKEN','GUARD_BOT_TOKEN','GUARD_PASSWORD','HUB_DB_URL','HUB_DB_TOKEN','GUARD_DB_URL','GUARD_DB_TOKEN','ADMIN_CODE','REPO')
children = {}
stop = threading.Event()

def spawn(name):
    env = dict(os.environ)
    env['PYTHONPATH'] = ROOT + os.pathsep + env.get('PYTHONPATH','')
    env['BOT_TOKEN'] = env['HUB_BOT_TOKEN' if name == 'hub' else 'GUARD_BOT_TOKEN']
    if name == 'guard': env['PASSWORD'] = env['GUARD_PASSWORD']
    return subprocess.Popen([sys.executable, '-u', os.path.join(ROOT, name, 'hub.py' if name == 'hub' else 'guard.py')], cwd=ROOT, env=env)

class Health(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        healthy = set(children) == {'hub','guard'} and all(p.poll() is None for p in children.values())
        self.send_response(200 if healthy else 503); self.send_header('Content-Type','text/plain'); self.end_headers()
        self.wfile.write(b'ok' if healthy else b'not ready')
    def log_message(self, fmt, *args): pass

def keepalive():
    url = os.getenv('RENDER_EXTERNAL_URL','').rstrip('/')
    if not url.startswith('https://'): return
    while not stop.wait(540):
        try:
            with urllib.request.urlopen(url+'/health', timeout=20) as r: r.read()
        except Exception as e: print('keepalive failed:', type(e).__name__, flush=True)

def main():
    missing=[k for k in REQUIRED if not os.environ.get(k)]
    if missing: sys.exit('Missing required configuration: '+', '.join(missing))
    if os.environ['HUB_BOT_TOKEN']==os.environ['GUARD_BOT_TOKEN']: sys.exit('Bots must have different tokens')
    server=http.server.ThreadingHTTPServer(('0.0.0.0',int(os.getenv('PORT','10000'))),Health)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    threading.Thread(target=keepalive,daemon=True).start()
    def terminate(*_): stop.set()
    signal.signal(signal.SIGTERM,terminate); signal.signal(signal.SIGINT,terminate)
    try:
        while not stop.is_set():
            for name in ('hub','guard'):
                p=children.get(name)
                if p is None or p.poll() is not None:
                    if p: print(name,'exited:',p.returncode,'— restarting',flush=True)
                    children[name]=spawn(name)
            stop.wait(10)
    finally:
        for p in children.values():
            if p.poll() is None: p.terminate()
        for p in children.values():
            try: p.wait(timeout=5)
            except subprocess.TimeoutExpired: p.kill(); p.wait()
        server.shutdown()

if __name__ == '__main__': main()
