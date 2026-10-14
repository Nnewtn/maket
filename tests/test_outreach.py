"""Run with: python -m pytest -q (isolated SQLite; never uses salon.db)."""
import os
import tempfile
os.environ['DATA_DIR'] = tempfile.mkdtemp(prefix='booking-tests-')

import pytest
from concurrent.futures import ThreadPoolExecutor
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from main import app
from database import Booking, SessionLocal, get_setting
from outreach import DemoLink

@pytest.fixture(scope='module')
def client():
    with TestClient(app) as c:
        yield c

@pytest.fixture(scope='module')
def headers(client):
    token = client.post('/api/admin/login', json={'password':'admin123'}).json()['token']
    return {'X-Admin-Token':token}

def create(client, headers, **config):
    response=client.post('/api/admin/demo-links',json={'brand':'Luna Studio',**config},headers=headers)
    assert response.status_code==200,response.text
    return response.json()

def test_creation_requires_login(client):
    assert client.post('/api/admin/demo-links',json={'brand':'X'}).status_code==401

def test_stable_creation_is_idempotent(client,headers):
    a=create(client,headers);b=create(client,headers)
    assert a['code']==b['code'] and a['path'].startswith('/d/') and a['views']==0

def test_edit_creates_new_immutable_link(client,headers):
    a=create(client,headers,brand='First');b=create(client,headers,brand='Second')
    assert a['code']!=b['code']
    assert '"brand": "First"' in client.get(a['path']).text

def test_contact_keys_produce_distinct_links(client,headers):
    assert create(client,headers,key='lead_a')['code']!=create(client,headers,key='lead_b')['code']

@pytest.mark.parametrize('bad',[{'niche':'medical'},{'theme':'hacked'},{'logo':'javascript:alert(1)'},{'brand':'x'*121}])
def test_invalid_config(client,headers,bad):
    assert client.post('/api/admin/demo-links',json=bad,headers=headers).status_code==422

def test_batch_preserves_order(client,headers):
    response=client.post('/api/admin/demo-links/batch',json={'items':[{'brand':'A','niche':'auto','key':'a'},{'brand':'B','niche':'barber','key':'b'}]},headers=headers)
    assert response.status_code==200
    a,b=response.json()['items'];assert a['code']!=b['code']
    assert '"brand": "A"' in client.get(a['path']).text

def test_script_injection_escaped(client,headers):
    result=create(client,headers,brand='</script><script>window.PWNED=1</script>')
    text=client.get(result['path']).text
    assert '</script><script>window.PWNED=1' not in text
    assert '\\u003c/script\\u003e' in text

def test_get_and_head_dont_count(client,headers):
    result=create(client,headers,key='crawler')
    client.get(result['path']);client.head(result['path'])
    stats=client.post('/api/admin/demo-links/stats',json={'codes':[result['code']]},headers=headers).json()
    assert stats['items'][0]['views']==0

def test_visit_dedup_and_stats(client,headers):
    result=create(client,headers,key='dedup');path=f"/api/demo-links/{result['code']}/view"
    for _ in range(2):assert client.post(path,json={'visit_id':'a'*32}).status_code==204
    client.post(path,json={'visit_id':'b'*32})
    stats=client.post('/api/admin/demo-links/stats',json={'codes':[result['code']]},headers=headers).json()['items'][0]
    assert stats['views']==2 and stats['first_view_at'] and stats['last_view_at']
    assert client.post('/api/admin/demo-links/stats',json={'codes':[result['code']]}).status_code==401

def test_cross_origin_tracking_blocked(client,headers):
    result=create(client,headers,key='origin')
    assert client.post(f"/api/demo-links/{result['code']}/view",json={'visit_id':'a'*32},headers={'Origin':'https://unrelated.invalid'}).status_code==403

def test_concurrent_creation_and_views(client,headers):
    def operation(i):return create(client,headers,key='concurrent')
    with ThreadPoolExecutor(max_workers=6) as pool:rows=list(pool.map(operation,range(12)))
    assert len({r['code'] for r in rows})==1
    code=rows[0]['code']
    def view(i):return client.post(f'/api/demo-links/{code}/view',json={'visit_id':f'{i:032d}'}).status_code
    with ThreadPoolExecutor(max_workers=6) as pool:assert set(pool.map(view,range(12)))=={204}
    with SessionLocal() as db:assert db.get(DemoLink,code).views==12

def test_preview_does_not_rewrite_business_settings(client,headers):
    before=client.get('/api/settings/public').json()
    a=create(client,headers,brand='Salon A',niche='auto');b=create(client,headers,brand='Salon B',niche='beauty')
    client.get(a['path']);client.get(b['path'])
    assert before==client.get('/api/settings/public').json()

def test_missing_code_and_validation(client):
    assert client.get('/d/does-not-exist').status_code==404
    assert client.post('/api/demo-links/missing/view',json={'visit_id':'a'*32}).status_code==404
    assert client.post('/api/demo-links/missing/view',json={'visit_id':'x'}).status_code==422

def test_static_and_outbound(client):
    for path in ['/','/admin','/admin/outbound','/static/js/niches.js','/static/js/outbound.js']:
        assert client.get(path).status_code==200
    admin=client.get('/admin').text
    assert 'Generate link</button>' not in admin and 'Copy Link' in admin and 'preview-links.js' in admin


def _png():
    import io
    from PIL import Image
    b = io.BytesIO(); Image.new("RGBA", (40, 20), (200, 30, 30, 255)).save(b, "PNG"); return b.getvalue()

def test_demo_logo_upload_requires_login(client):
    assert client.post('/api/admin/demo-logo', files={'file': ('a.png', _png(), 'image/png')}).status_code == 401

def test_pasted_logo_upload_and_use_in_link(client, headers):
    r = client.post('/api/admin/demo-logo', headers=headers, files={'file': ('clip.png', _png(), 'image/png')})
    assert r.status_code == 200
    logo = r.json()['logo']
    assert logo.startswith('/static/uploads/demo_')
    link = client.post('/api/admin/demo-links', headers=headers, json={'brand': 'Luna', 'logo': logo})
    assert link.status_code == 200
    assert client.get(logo).status_code == 200
    assert logo in client.get(link.json()['path']).text

def test_demo_logo_rejects_non_image_and_foreign_paths(client, headers):
    assert client.post('/api/admin/demo-logo', headers=headers, files={'file': ('x.png', b'nope', 'image/png')}).status_code == 400
    for bad in ['/static/uploads/../../etc/passwd', '/other/x.png', '//evil.com/x.png']:
        assert client.post('/api/admin/demo-links', headers=headers, json={'brand': 'x', 'logo': bad}).status_code == 422
