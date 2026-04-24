import re, urllib.request, urllib.error
base = 'http://localhost:3000'
routes = [
    ('NVDA charts', '/company/NVDA/charts', 'html'),
    ('NVDA charts studio', '/company/NVDA/charts?mode=studio', 'studio'),
    ('TTD charts', '/company/TTD/charts', 'ttd'),
    ('NVDA opengraph image', '/company/NVDA/charts/opengraph-image', 'image'),
]

def fetch(path):
    url = base + path
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            status = resp.getcode()
            headers = dict(resp.headers.items())
            body = resp.read()
            return status, headers, body, None
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers.items()), e.read(), None
    except Exception as e:
        return None, {}, b'', str(e)

for name, path, kind in routes:
    status, headers, body, err = fetch(path)
    print(f'=== {name} ===')
    print(f'PATH {path}')
    if err:
        print(f'ERROR {err}')
        print()
        continue
    print(f'STATUS {status}')
    ctype = headers.get('Content-Type', '')
    if kind == 'image':
        print(f'CONTENT_TYPE {ctype}')
        if status and status >= 400:
            text = body.decode('utf-8', 'ignore').replace('\r', ' ').replace('\n', ' ')
            print('EXCERPT ' + text[:300])
    else:
        text = body.decode('utf-8', 'ignore')
        print(f'BODY_LEN {len(text)}')
        if kind == 'html':
            has_og = '/company/NVDA/charts/opengraph-image' in text
            m = re.search(r'(freshness|source|trust)', text, re.I)
            print(f'HAS_OG_IMAGE_ROUTE {has_og}')
            print(f'HAS_FRESHNESS_SOURCE_TRUST {bool(m)}')
            if m:
                print(f'FRESHNESS_SOURCE_TRUST_MATCH {m.group(0)}')
            if (status and status >= 400) or not has_og:
                print('EXCERPT ' + text.replace('\r', ' ').replace('\n', ' ')[:400])
        elif kind == 'studio':
            m = re.search(r'(Interactive Projection Studio is loading|Projection Studio.{0,80}loading)', text, re.I | re.S)
            print(f'HAS_STUDIO_LOADING_MARKER {bool(m)}')
            if m:
                print('STUDIO_MARKER_MATCH ' + m.group(0).replace('\r', ' ').replace('\n', ' ')[:200])
            if (status and status >= 400) or not m:
                print('EXCERPT ' + text.replace('\r', ' ').replace('\n', ' ')[:400])
        elif kind == 'ttd':
            has_ticker = bool(re.search(r'TTD', text, re.I))
            has_title = bool(re.search(r'<title[^>]*>.*?(TTD|Trade Desk|Charts|Company).*?</title>', text, re.I | re.S))
            print(f'HTML_RENDERED {bool(text) and (status is not None and status < 400)}')
            print(f'HAS_TICKER_OR_TITLE {has_ticker or has_title}')
            if (status and status >= 400) or not (has_ticker or has_title):
                print('EXCERPT ' + text.replace('\r', ' ').replace('\n', ' ')[:400])
    print()
