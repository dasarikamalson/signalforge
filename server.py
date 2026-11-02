#!/usr/bin/env python3
"""Signalforge: local-first public website lead discovery prototype."""
import csv, html, http.client, ipaddress, json, os, re, socket, ssl, time
from collections import deque
from html.parser import HTMLParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import BoundedSemaphore
from urllib.parse import urljoin, urlsplit, urlunsplit, unquote
from urllib.robotparser import RobotFileParser

ROOT = Path(__file__).parent / 'public'
UA = 'SignalforgeBot/0.1 (+local research tool)'
MAX_BYTES = 1_000_000
MAX_PAGES = 5
SLOTS = BoundedSemaphore(2)
EMAIL = re.compile(r'(?<![\w.+-])[a-zA-Z0-9.!#$%&\'*+/=?^_`{|}~-]+@[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)+(?![\w.-])')
PHONE = re.compile(r'(?<![\w\d])(?:\+\d{1,3}[ .()-]?)?(?:\(?\d{2,4}\)?[ .-]?)?\d{3,4}[ .-]\d{3,4}(?!\d)')

def normalize(raw):
    p = urlsplit(raw.strip())
    if p.scheme not in ('http', 'https') or not p.hostname or p.username or p.password:
        raise ValueError('Use a public http or https URL without credentials.')
    try: port = p.port
    except ValueError: raise ValueError('Invalid port.')
    if port not in (None, 80 if p.scheme == 'http' else 443): raise ValueError('Only standard HTTP and HTTPS ports are supported.')
    host = p.hostname.lower().rstrip('.')
    if host in ('localhost',) or host.endswith(('.localhost', '.local', '.internal')): raise ValueError('Local and internal hosts are not allowed.')
    if host.startswith('[') or ':' in host: raise ValueError('IP literal URLs are not supported.')
    try: ipaddress.ip_address(host); raise ValueError('IP literal URLs are not supported.')
    except ValueError as e:
        if str(e) == 'IP literal URLs are not supported.': raise
    return urlunsplit((p.scheme, host, p.path or '/', p.query, ''))

def fetch(url):
    p = urlsplit(normalize(url)); port = 443 if p.scheme == 'https' else 80
    # Resolve once and connect to a validated address, preventing DNS rebinding.
    try: addresses = {x[4][0] for x in socket.getaddrinfo(p.hostname, port, type=socket.SOCK_STREAM)}
    except socket.gaierror: raise ValueError('Could not resolve the website.')
    if not addresses or any(not ipaddress.ip_address(a).is_global for a in addresses):
        raise ValueError('The website resolves to a non-public address.')
    address = sorted(addresses)[0]
    conn = http.client.HTTPSConnection(p.hostname, port, timeout=8, context=ssl.create_default_context()) if p.scheme == 'https' else http.client.HTTPConnection(p.hostname, port, timeout=8)
    def connect():
        sock = socket.create_connection((address, port), timeout=8)
        conn.sock = conn._context.wrap_socket(sock, server_hostname=p.hostname) if p.scheme == 'https' else sock
    conn.connect = connect
    path = (p.path or '/') + (('?' + p.query) if p.query else '')
    try:
        conn.request('GET', path, headers={'User-Agent': UA, 'Accept': 'text/html,application/xhtml+xml,text/plain;q=0.9', 'Connection': 'close'})
        response = conn.getresponse()
        if 300 <= response.status < 400: raise ValueError('Redirects are not followed. Enter the final URL directly.')
        data = response.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES: raise ValueError('Page exceeded the 1 MB limit.')
        return response.status, response.getheader('Content-Type', ''), data.decode('utf-8', 'replace')
    finally: conn.close()

class Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True); self.links=[]; self.mail=[]; self.tel=[]; self.text=[]; self.jsonld=[]; self.hidden=0; self.capture=False; self.buf=[]; self.title=''; self.in_title=False
    def handle_starttag(self, tag, attrs):
        a=dict(attrs); tag=tag.lower()
        if tag == 'script':
            self.hidden += 1
            if a.get('type','').lower().split(';')[0].strip() == 'application/ld+json': self.capture=True; self.buf=[]
        elif tag in ('style','noscript','template','svg'): self.hidden += 1
        elif tag == 'title': self.in_title=True
        elif tag == 'a':
            href=a.get('href','').strip()
            if href.lower().startswith('mailto:'): self.mail.append(unquote(href[7:].split('?')[0]))
            elif href.lower().startswith('tel:'): self.tel.append(unquote(href[4:].split('?')[0]))
            elif href: self.links.append(href)
    def handle_endtag(self, tag):
        if tag == 'script':
            if self.capture: self.jsonld.append(''.join(self.buf)); self.capture=False
            self.hidden=max(0,self.hidden-1)
        elif tag in ('style','noscript','template','svg'): self.hidden=max(0,self.hidden-1)
        elif tag == 'title': self.in_title=False
    def handle_data(self, data):
        if self.capture: self.buf.append(data)
        elif self.in_title: self.title += data
        elif not self.hidden: self.text.append(data)

def people_json(obj, url):
    out=[]
    if isinstance(obj,list):
        for x in obj: out += people_json(x,url)
    elif isinstance(obj,dict):
        types=obj.get('@type',[]); types=[types] if isinstance(types,str) else types
        if isinstance(types,list) and 'Person' in types:
            def val(k):
                v=obj.get(k,''); return str(v).strip()[:200] if isinstance(v,(str,int)) else ''
            name=val('name'); email=val('email').removeprefix('mailto:'); phone=val('telephone'); role=val('jobTitle'); org=obj.get('worksFor',''); org=org.get('name','') if isinstance(org,dict) else org if isinstance(org,str) else ''
            if name and (email or phone): out.append({'name':name,'role':role,'company':str(org)[:200], 'email':email if EMAIL.fullmatch(email) else '', 'phone':phone[:80], 'source':url,'kind':'Person (structured data)'})
        for value in obj.values():
            if isinstance(value,(list,dict)): out += people_json(value,url)
    return out

def conservative_disallows(body, url):
    # Treat any matching Disallow as binding, regardless of agent group or Allow.
    # This is deliberately stricter than the standard, not a full RFC parser.
    p = urlsplit(url); path = unquote((p.path or '/') + (('?' + p.query) if p.query else ''))
    for line in body.splitlines():
        line = line.split('#', 1)[0]
        if ':' not in line: continue
        key, value = line.split(':', 1); value = unquote(value.strip())
        if key.strip().lower() != 'disallow' or not value: continue
        anchored = value.endswith('$'); value = value[:-1] if anchored else value
        pattern = '^' + re.escape(value).replace(r'\*', '.*') + ('$' if anchored else '')
        if re.search(pattern, path): return True
    return False

def crawl(raw, limit=3):
    start=normalize(raw); base=urlsplit(start); origin=f'{base.scheme}://{base.netloc}'; robots=origin+'/robots.txt'
    status, _, body=fetch(robots)
    if status == 404: rp=RobotFileParser(); rp.parse([])
    elif status == 200:
        rp=RobotFileParser(); rp.parse(body.splitlines())
    else: raise ValueError(f'Cannot verify robots.txt (HTTP {status}); crawl stopped.')
    delay=rp.crawl_delay(UA) or rp.crawl_delay('*') or 0
    if delay > 10: raise ValueError('Site requests a crawl delay over 10 seconds; crawl stopped.')
    wait=max(1.0, float(delay)); queue=deque([start]); seen=set(); rows=[]; warnings=[]; last=time.monotonic()
    while queue and len(seen) < max(1,min(MAX_PAGES,limit)):
        u=queue.popleft()
        if u in seen: continue
        if not rp.can_fetch(UA,u) or conservative_disallows(body, u): warnings.append('Skipped a URL disallowed by robots.txt.'); continue
        seen.add(u)
        if last: time.sleep(max(0,wait-(time.monotonic()-last)))
        try:
            last=time.monotonic(); st,typ,body=fetch(u)
            if st != 200 or not any(t in typ.lower() for t in ('text/html','application/xhtml+xml')):
                warnings.append(f'Skipped {u}: HTTP {st} or non-HTML content.'); continue
            p=Page(); p.feed(body); text=' '.join(p.text)
            for ld in p.jsonld:
                try: rows += people_json(json.loads(ld),u)
                except (ValueError, RecursionError): pass
            emails=set(p.mail) | set(EMAIL.findall(text)); phones=set(p.tel) | set(PHONE.findall(text))
            for e in sorted(emails):
                e=e.strip()
                if EMAIL.fullmatch(e) and not e.lower().endswith(('.png','.jpg','.jpeg','.gif','.webp','.svg')): rows.append({'name':'','role':'','company':'','email':e,'phone':'','source':u,'kind':'Public contact'})
            for phone in sorted(phones):
                ph=phone.strip()[:80]
                if 7 <= len(re.sub(r'\D','',ph)) <= 15: rows.append({'name':'','role':'','company':'','email':'','phone':ph,'source':u,'kind':'Public contact'})
            for h in p.links:
                try:
                    v=normalize(urljoin(u,h)); q=urlsplit(v)
                    if (q.scheme,q.netloc)==(base.scheme,base.netloc) and v not in seen and len(queue)<40: queue.append(v)
                except ValueError: pass
        except (ValueError, OSError, http.client.HTTPException) as e: warnings.append(f'Skipped {u}: {str(e)[:140]}')
    unique=[]; keys=set()
    for r in rows:
        key=(r['name'].lower(),r['email'].lower(),re.sub(r'\D','',r['phone']))
        if key not in keys: keys.add(key); unique.append(r)
    return {'results':unique[:300], 'pagesScanned':len(seen), 'warnings':warnings[:10], 'origin':origin}

class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args): pass
    def headers_safe(self, code, content_type, length):
        self.send_response(code); self.send_header('Content-Type',content_type); self.send_header('Content-Length',str(length)); self.send_header('X-Content-Type-Options','nosniff'); self.send_header('Referrer-Policy','no-referrer'); self.send_header('Content-Security-Policy',"default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'"); self.end_headers()
    def respond(self, code, obj):
        data=json.dumps(obj).encode(); self.headers_safe(code,'application/json; charset=utf-8',len(data)); self.wfile.write(data)
    def local_host(self): return self.headers.get('Host','').lower() in (f'localhost:{PORT}', f'127.0.0.1:{PORT}')
    def do_GET(self):
        if not self.local_host(): return self.respond(403,{'error':'Invalid host.'})
        paths={'/':('index.html','text/html; charset=utf-8'),'/style.css':('style.css','text/css; charset=utf-8'),'/app.js':('app.js','text/javascript; charset=utf-8')}
        item=paths.get(urlsplit(self.path).path)
        if not item: return self.respond(404,{'error':'Not found.'})
        data=(ROOT/item[0]).read_bytes(); self.headers_safe(200,item[1],len(data)); self.wfile.write(data)
    def do_POST(self):
        if not self.local_host(): return self.respond(403,{'error':'Invalid host.'})
        if self.path != '/api/scan': return self.respond(404,{'error':'Not found.'})
        origin=self.headers.get('Origin','')
        if origin not in (f'http://localhost:{PORT}',f'http://127.0.0.1:{PORT}'): return self.respond(403,{'error':'Invalid origin.'})
        if self.headers.get('Content-Type','').split(';')[0] != 'application/json': return self.respond(415,{'error':'JSON required.'})
        try:
            length=int(self.headers.get('Content-Length','0'))
            if length<=0 or length>4096: raise ValueError('Invalid request size.')
            payload=json.loads(self.rfile.read(length)); raw=payload.get('url',''); limit=payload.get('limit',3)
            if not isinstance(raw,str) or len(raw)>2048 or not isinstance(limit,int): raise ValueError('Invalid input.')
            if not SLOTS.acquire(blocking=False): return self.respond(429,{'error':'Too many scans running; try again later.'})
            try: result=crawl(raw,limit)
            finally: SLOTS.release()
            self.respond(200,result)
        except (ValueError, OSError, http.client.HTTPException, json.JSONDecodeError) as e: self.respond(400,{'error':str(e)[:200]})

if __name__ == '__main__':
    PORT=int(os.getenv('PORT','8765')); server=ThreadingHTTPServer(('127.0.0.1',PORT),Handler); print(f'Signalforge running at http://localhost:{PORT}',flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: server.server_close()
else: PORT=int(os.getenv('PORT','8765'))
