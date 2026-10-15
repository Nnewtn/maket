"""Integration suite; isolated DB, Telegram mocked (never contacts real customers)."""
import os, tempfile, sys, asyncio
from datetime import datetime, timedelta
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
os.environ['DATA_DIR']=tempfile.mkdtemp(prefix='crm-v7-test-')
os.environ['SESSION_SECRET']='test-only-key-v7'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pytest
from fastapi.testclient import TestClient
import main, growth
from database import SessionLocal, Booking, Setting, Service, engine
from services import fx
fx._mem_cache={'base':'PLN','rates':{'PLN':1,'EUR':.23,'USD':.25},'date':'TEST','ts':__import__('time').time()}

@pytest.fixture(scope='module')
def client():
    # Reproduce an existing v6 database: only legacy tables exist at startup.
    from database import Staff, Waitlist, DemoLink, OutboundLead, OutboundTemplate, OutboundSend
    for model in [Service, Staff, Booking, Setting, Waitlist, DemoLink, OutboundLead, OutboundTemplate, OutboundSend]:
        model.__table__.create(engine, checkfirst=True)
    with SessionLocal() as s:
        s.add(Setting(key='legacy_sentinel',value='preserve-v6-data')); s.commit()
    with TestClient(main.app) as c:
        assert c.post('/api/admin/login',json={'password':'admin123'}).status_code==200
        yield c

def future(hour=10): return (growth.local_now().replace(tzinfo=None)+timedelta(days=3)).replace(hour=hour,minute=0,second=0,microsecond=0).isoformat()
def payload(hour=10): return {'client_name':'V7 Tester','phone':'+48500100200','service_id':1,'staff_id':1,'starts_at':future(hour)}
def setval(key,value):
    with SessionLocal() as s:
        x=s.get(Setting,key)
        if not x: s.add(Setting(key=key,value=value))
        else: x.value=value
        s.commit()

def test_wal(client):
    with engine.connect() as c: assert c.exec_driver_sql('PRAGMA journal_mode').scalar()=='wal'

def test_existing_v6_database_is_preserved(client):
    with SessionLocal() as s:
        assert s.get(Setting,'legacy_sentinel').value=='preserve-v6-data'
        assert s.get(Setting,'daily_summary_time').value=='21:00'
        assert s.get(Setting,'daily_summary_enabled').value=='0'
    assert client.get('/api/admin/feedback').status_code==200

def test_server_sessions_expire(client):
    import time
    token=main._sign(f'admin:{int(time.time())-9*3600}')
    assert not main._check(token)
def test_all_pages(client):
    for path in ['/','/admin','/admin/outbound','/feedback/demo']:
        assert client.get(path).status_code==200

def test_session_scope(client):
    from starlette.testclient import TestClient
    with TestClient(main.app) as c:
        assert c.post('/api/outbound/login',json={'password':'123123'}).status_code==200
        token=c.cookies['outbound_token'];c.cookies.set('admin_token',token)
        assert c.get('/api/admin/settings').status_code==401
        assert c.get('/api/admin/feedback').status_code==401
        assert c.post('/api/admin/daily-summary/test').status_code==401

def test_no_logo(client):
    links=[]
    for logo in [None,'']:
        data={'brand':'Luna Beauty Warsaw','niche':'beauty'}
        if logo is not None:data['logo']=logo
        r=client.post('/api/admin/demo-links',json=data);assert r.status_code==200
        assert 'logo' not in r.json()['config'];links.append(r.json()['path'])
        page=client.get(links[-1]);assert 'Luna Beauty Warsaw' in page.text
    assert links[0]==links[1]

@pytest.mark.parametrize('niche',['beauty','barber','auto','detailing'])
def test_quiz_demo_all_niches(client,niche):
    car=niche in ('auto','detailing')
    small=client.post('/api/quiz/quote',json={'niche':niche,'goal':0,'size':0,'addons':[],'demo':True}).json()
    large=client.post('/api/quiz/quote',json={'niche':niche,'goal':0,'size':2,'addons':['rain','ozone'] if car else ['spa'],'currency':'EUR','demo':True})
    assert large.status_code==200
    q=large.json();assert q['currency']=='EUR' and q['duration_min']>small['duration_min']
    assert q['price_pln']>small['price_pln'];assert q['addons'][0]['discount_percent']==20
    with SessionLocal() as s: before=s.query(Booking).count()
    r=client.post('/api/bookings',json={**payload(11),'is_demo':True,'quote_token':q['quote_token']})
    assert r.status_code==200 and r.json()['demo']
    with SessionLocal() as s: assert s.query(Booking).count()==before

def test_real_quote_and_booking_price_duration(client):
    q=client.post('/api/quiz/quote',json={'niche':'barber','size':1,'goal':0,'service_id':1,'addons':['spa'],'demo':False,'currency':'USD'}).json()
    assert q['price']==39 and q['duration_min']==74 # 80*1.2 +60 =156 PLN; 45*1.2+20=74
    r=client.post('/api/bookings',json={**payload(),'quote_token':q['quote_token']});assert r.status_code==200,r.text
    bid=r.json()['id']
    with SessionLocal() as s:
        b=s.get(Booking,bid);assert b.price==q['price'] and b.currency=='USD' and b.duration_min==74
    assert client.post('/api/bookings',json={**payload(11),'phone':'+48500100201'}).status_code==409

def test_tampered_expired_quotes(client):
    q=client.post('/api/quiz/quote',json={'niche':'barber','size':0,'goal':0,'addons':[],'demo':True}).json()
    assert client.post('/api/bookings',json={**payload(15),'quote_token':q['quote_token']+'x'}).status_code==422
    q['exp']=0
    assert client.post('/api/bookings',json={**payload(15),'quote_token':growth.sign_data(q,main.SESSION_SECRET)}).status_code==422

def test_addons_validation(client):
    assert client.post('/api/quiz/quote',json={'niche':'auto','size':0,'goal':0,'addons':['spa']}).status_code==422
    assert client.post('/api/quiz/quote',json={'niche':'barber','size':0,'goal':0,'addons':['spa','spa']}).status_code==422

def test_atomic_concurrent_booking(client):
    def send(_):return client.post('/api/bookings',json=payload(15)).status_code
    with ThreadPoolExecutor(max_workers=4) as ex: codes=list(ex.map(send,range(4)))
    assert sorted(codes)==[200,409,409,409],codes

def completed(client,hour=13):
    r=client.post('/api/bookings',json=payload(hour));assert r.status_code==200,r.text
    bid=r.json()['id'];assert client.patch('/api/admin/bookings/'+str(bid),json={'status':'Completed'}).status_code==200
    path=client.get(f'/api/admin/bookings/{bid}/review-link').json()['path'];return bid,path

def test_feedback_secure_private_and_notification(client,monkeypatch):
    sent=[]
    async def fake(token,chat,text):sent.append(text);return True,'ok'
    monkeypatch.setattr(growth.telegram,'send',fake)
    bid,path=completed(client);assert client.get('/feedback/'+str(bid)).status_code==404
    page=client.get(path);assert page.status_code==200
    token=path.split('token=')[1]
    assert client.post('/api/feedback',json={'booking_id':bid,'stars':2,'comment':'Too long'}).status_code==404
    data={'booking_id':bid,'token':token,'stars':2,'comment':'Waited <b>25 minutes</b>','contact':'+48500100200'}
    assert client.post('/api/feedback',json=data).status_code==200
    assert sent and '&lt;b&gt;' in sent[0]
    assert client.post('/api/feedback',json=data).status_code==409
    f=client.get('/api/admin/feedback').json()[0];assert f['needs_attention'] and f['notification_status']=='sent'
    assert client.patch('/api/admin/feedback/'+str(f['id'])).status_code==200

def test_positive_feedback(client,monkeypatch):
    async def forbidden(*a):raise AssertionError('Positive feedback should not send negative alert')
    monkeypatch.setattr(growth.telegram,'send',forbidden)
    bid,path=completed(client,17);token=path.split('token=')[1]
    assert client.post('/api/feedback',json={'booking_id':bid,'token':token,'stars':5,'comment':'My own words'}).status_code==200

def test_sandbox_feedback_does_not_write(client):
    before=client.get('/api/admin/feedback').json()
    for stars in (2,5):assert client.post('/api/feedback',json={'stars':stars,'is_demo':True,'comment':'Demo'}).json()['demo']
    assert client.get('/api/admin/feedback').json()==before

def test_settings_validation(client):
    for data in [{'daily_summary_time':'25:00'},{'business_timezone':'Not/AZone'},{'google_maps_url':'https://evil.example/review'},{'daily_summary_enabled':'yes'}]:
        assert client.patch('/api/admin/settings',json=data).status_code==422
    assert client.patch('/api/admin/settings',json={'google_maps_url':'https://g.page/r/test/review','daily_summary_time':'21:00','business_timezone':'Europe/Warsaw'}).status_code==200

def test_seed_idempotent_and_demo_exclusion(client):
    before=growth.build_summary()
    first=client.post('/api/admin/seed-sample');assert first.json()['feedback']==4
    assert client.post('/api/admin/seed-sample').json()['already_loaded']
    assert growth.build_summary()==before
    report=growth.build_summary(include_demo=True)
    assert report['completed']>=4 and report['positive']>=2 and report['private_issues']>=2

def test_summary_currency_no_show(client):
    setval('default_currency','EUR');today=growth.local_now().replace(tzinfo=None,hour=9,minute=0,second=0,microsecond=0)
    with SessionLocal() as s:
        s.add_all([Booking(client_name='Report',phone='+48500100991',service_id=1,staff_id=1,starts_at=today,duration_min=30,price=100,currency='USD',status='Completed',is_demo=False),Booking(client_name='NoShow',phone='+48500100992',service_id=1,staff_id=1,starts_at=today,duration_min=30,price=50,currency='PLN',status='NoShow',is_demo=False)]);s.commit()
    r=growth.build_summary();assert r['completed']==1 and r['revenue']==92 and r['no_show']==1
    setval('default_currency','PLN')

def test_summary_live_mock_and_persistent_dedup(client,monkeypatch):
    calls=[]
    async def fake(token,chat,text):calls.append((chat,text));return True,'ok'
    monkeypatch.setattr(growth.telegram,'send',fake)
    setval('telegram_bot_token','fake-token');setval('telegram_chat_id','123');setval('daily_summary_time','00:00');setval('daily_summary_enabled','1')
    r=client.post('/api/admin/daily-summary/test');assert r.status_code==200 and r.json()['ok'];assert len(calls)==1
    asyncio.run(growth.summary_tick());asyncio.run(growth.summary_tick());assert len(calls)==2
    assert '<b>' in calls[0][1] and 'TEST' in calls[0][1]
    setval('daily_summary_enabled','0');setval('telegram_bot_token','');setval('telegram_chat_id','')

def test_summary_requires_configuration(client):
    r=client.post('/api/admin/daily-summary/test');assert r.status_code==409

def test_presentation_report_public_is_fictional(client):
    r=client.get('/api/demo/daily-summary');assert r.status_code==200 and r.json()['demo']
