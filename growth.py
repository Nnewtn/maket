"""v7: signed package pricing, private feedback and persistent daily reporting.
One installation = one business. SQLite connections are per operation; no shared Session.
"""
from __future__ import annotations
import asyncio, base64, hashlib, hmac, html, json, logging, re, secrets, time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo
from fastapi import BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, UniqueConstraint, text
from sqlalchemy.dialects.sqlite import insert
from database import Base, SessionLocal, Booking, Service, Staff, Setting, engine
from services import telegram
from services.fx import get_rates

log = logging.getLogger('growth')
ROOT = Path(__file__).parent
DEFAULTS = {'google_maps_url':'', 'daily_summary_enabled':'0', 'daily_summary_time':'21:00', 'business_timezone':'Europe/Warsaw', 'site_niche':'barber'}

class Feedback(Base):
    __tablename__ = 'feedback'
    id = Column(Integer, primary_key=True)
    booking_id = Column(Integer, ForeignKey('bookings.id'), nullable=True, unique=True)
    stars = Column(Integer, nullable=False)
    comment = Column(String(1200), default='')
    contact = Column(String(200), default='')
    needs_attention = Column(Boolean, default=False)
    resolved = Column(Boolean, default=False)
    is_demo = Column(Boolean, default=False)
    notification_status = Column(String(20), default='not_needed')
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow)

class SummaryDelivery(Base):
    __tablename__ = 'summary_deliveries'
    id = Column(Integer, primary_key=True)
    day = Column(String(10), unique=True)
    status = Column(String(20), default='pending')
    attempts = Column(Integer, default=0)
    error = Column(String(300), default='')
    updated_at = Column(DateTime, default=datetime.utcnow)

class QuoteIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    niche: Literal['beauty','barber','auto','detailing']
    size: int = Field(ge=0, le=2)
    goal: int = Field(ge=0, le=2)
    addons: list[Literal['spa','rain','ozone']] = Field(default_factory=list, max_length=3)
    currency: Literal['PLN','EUR','USD'] = 'PLN'
    demo: bool = False
    service_id: int | None = None

class FeedbackIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    booking_id: int | None = None
    token: str = Field(default='', max_length=128)
    stars: int = Field(ge=1, le=5)
    comment: str = Field(default='', max_length=1200)
    contact: str = Field(default='', max_length=200)
    is_demo: bool = False

# name key, PLN price, duration; used only by isolated demos.
CATALOG = {
 'barber': [('svc_hair',80,45),('svc_beard',50,30),('svc_makeover',120,75)],
 'beauty': [('svc_color',220,90),('svc_pedicure',160,75),('svc_makeover',350,150)],
 'auto': [('svc_protection',350,90),('svc_interior',300,120),('svc_presale',600,180)],
 'detailing': [('svc_correction',1200,360),('svc_interior',600,180),('svc_presale',1800,480)],
}
ADDONS = {'spa': ('addon_spa',75,60,20), 'rain': ('addon_rain',100,80,15), 'ozone': ('addon_ozone',150,120,30)}

def settings():
    with SessionLocal() as s:
        return {r.key:r.value for r in s.query(Setting).all()}

def local_now(st=None):
    return datetime.now(ZoneInfo((st or settings()).get('business_timezone') or 'Europe/Warsaw'))

def sign_data(value, secret):
    raw = base64.urlsafe_b64encode(json.dumps(value, separators=(',',':')).encode()).decode().rstrip('=')
    sig = hmac.new(secret.encode(), raw.encode(), hashlib.sha256).hexdigest()
    return raw+'.'+sig

def read_quote(token, secret):
    try:
        raw,sig=token.rsplit('.',1)
        expected=hmac.new(secret.encode(),raw.encode(),hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig,expected): raise ValueError()
        cfg=json.loads(base64.urlsafe_b64decode(raw+'='*(-len(raw)%4)))
        if cfg['exp'] < time.time(): raise ValueError()
        return cfg
    except Exception:
        raise HTTPException(422, 'Package expired or invalid. Please calculate again.')

def review_token(bid, secret):
    return hmac.new(secret.encode(),f'review:{bid}'.encode(),hashlib.sha256).hexdigest()

def valid_review(bid, token, secret):
    return bool(bid and hmac.compare_digest(review_token(bid,secret),token))

def quote_package(p, secret):
    allowed={'rain','ozone'} if p.niche in ('auto','detailing') else {'spa'}
    if len(set(p.addons)) != len(p.addons) or not set(p.addons) <= allowed:
        raise HTTPException(422,'Add-ons do not match this business.')
    name,base,duration=CATALOG[p.niche][p.goal]
    sid=9000+p.goal
    if not p.demo:
        with SessionLocal() as s:
            sv=s.get(Service,p.service_id) if p.service_id else None
            if not p.service_id:
                services=s.query(Service).filter(Service.is_active==True,Service.niche.in_([p.niche,'all'])).order_by(Service.id).all()
                patterns={'barber':['haircut|strzy|cut','beard|brod|shave','makeover|metamor|combo'], 'beauty':['hair|color|kolor|strzy','pedicure|manicure|care|piel','makeover|metamor|color'], 'auto':['protect|paint|lakier','interior|clean|wnętrz','sale|sprzeda|prep'], 'detailing':['correct|coating|korekt|ceram','interior|wnętrz','sale|sprzeda|prep']}
                sv=next((v for v in services if re.search(patterns[p.niche][p.goal],v.name,re.I)), None)
                if sv is None and services: sv=services[min(p.goal,len(services)-1)]
            if not sv:
                raise HTTPException(409,'Configure services for this niche in CRM first.')
            if not sv.is_active or sv.niche not in (p.niche,'all'):
                raise HTTPException(422,'Service does not match this niche.')
            sid=sv.id; base=sv.price; duration=sv.duration_min; name=sv.name
    multiplier=(1,1.25,1.5)[p.size] if p.niche in ('auto','detailing') else (1,1.2,1.4)[p.size]
    items=[]; total=round(base*multiplier,2); duration=round(duration*multiplier)
    for code in p.addons:
        key,regular,discount,mins=ADDONS[code]
        items.append({'code':code,'name_key':key,'regular_pln':regular,'price_pln':discount,'minutes':mins,'discount_percent':20})
        total+=discount; duration+=mins
    rates=get_rates('PLN'); rate=rates['rates'].get(p.currency,1)
    cfg={'service_id':sid,'name':name,'niche':p.niche,'demo':p.demo,'price':round(total*rate,2),'base_price':round(base*multiplier*rate,2),'price_pln':total,'currency':p.currency,'duration_min':duration,'addons':items,'exp':int(time.time())+1800,'fx_date':rates.get('date','fallback')}
    return {**cfg,'quote_token':sign_data(cfg,secret)}

def active_masters(s, start, duration, staff_id=None):
    masters=s.query(Staff).filter(Staff.is_active==True).all()
    end=start+timedelta(minutes=duration)
    existing=s.query(Booking).filter(Booking.status.notin_(['Cancelled','NoShow']),Booking.starts_at < end,Booking.starts_at > start-timedelta(days=2)).all()
    available=[]
    for m in masters:
        if staff_id and m.id != staff_id: continue
        try:
            a,b=m.work_hours.split('-'); lo=datetime.strptime(a,'%H:%M').time(); hi=datetime.strptime(b,'%H:%M').time()
            if start.time()<lo or end.date()!=start.date() or end.time()>hi: continue
        except (ValueError,AttributeError): continue
        if any(b.staff_id==m.id and b.starts_at < end and b.starts_at+timedelta(minutes=b.duration_min)>start for b in existing): continue
        load=sum(b.staff_id==m.id for b in existing)
        available.append((load,m))
    return [m for _,m in sorted(available,key=lambda v:(v[0],v[1].id))]

async def notify_feedback(fid):
    with SessionLocal() as s:
        f=s.get(Feedback,fid)
        if not f or f.is_demo: return
        content=f'⚠️ <b>Private feedback needs attention</b>\nRating: {f.stars}/5\nBooking: {f.booking_id}\n{html.escape(f.comment)}\nContact: {html.escape(f.contact)}\nNot posted online by this application.'
    st=await asyncio.to_thread(settings)
    ok,err=await telegram.send(st.get('telegram_bot_token',''),st.get('telegram_chat_id',''),content)
    with SessionLocal() as s:
        f=s.get(Feedback,fid)
        if f:
            f.notification_status='sent' if ok else 'failed'; s.commit()
    return ok,err

def build_summary(st=None, day=None, include_demo=False):
    st=st or settings(); today=day or local_now(st).date()
    start=datetime.combine(today,datetime.min.time()); end=start+timedelta(days=1)
    rates=get_rates('PLN'); currency=st.get('default_currency','PLN'); rr=rates['rates']
    with SessionLocal() as s:
        rows=s.query(Booking).filter(Booking.starts_at>=start,Booking.starts_at<end).all()
        rows=[b for b in rows if include_demo or not b.is_demo]
        complete=[b for b in rows if b.status=='Completed']
        revenue=sum(b.price/max(rr.get(b.currency,1),0.0001)*rr.get(currency,1) for b in complete)
        zone=ZoneInfo(st.get('business_timezone') or 'Europe/Warsaw')
        utc_start=start.replace(tzinfo=zone).astimezone(timezone.utc).replace(tzinfo=None)
        utc_end=end.replace(tzinfo=zone).astimezone(timezone.utc).replace(tzinfo=None)
        fb=s.query(Feedback).filter(Feedback.created_at>=utc_start,Feedback.created_at<utc_end).all()
        fb=[f for f in fb if include_demo or not f.is_demo]
    return {'date':today.isoformat(),'timezone':st.get('business_timezone'),'completed':len(complete),'revenue':round(revenue,2),'currency':currency,'cancelled':sum(b.status=='Cancelled' for b in rows),'no_show':sum(b.status=='NoShow' for b in rows),'positive':sum(f.stars>=4 for f in fb),'private_issues':sum(f.stars<=3 for f in fb),'demo':include_demo,'fx_date':rates.get('date','fallback')}

def report_text(r, st, test=False):
    pl=st.get('default_language')=='pl'
    labels=['Podsumowanie dnia','Zakończone wizyty','Przychód','Odwołane','Nieobecności','Pozytywne oceny','Prywatne zgłoszenia'] if pl else ['Daily summary','Completed bookings','Revenue','Cancelled','No-shows','Positive ratings','Private issues']
    return '\n'.join([f"<b>{'TEST · ' if test else ''}{labels[0]} — {r['date']}</b>",html.escape(st.get('site_name','')),f"{labels[1]}: <b>{r['completed']}</b>",f"{labels[2]}: <b>{r['revenue']:.2f} {r['currency']}</b>",f"{labels[3]}: {r['cancelled']} · {labels[4]}: {r['no_show']}",f"{labels[5]}: {r['positive']} · {labels[6]}: {r['private_issues']}",f"{r['timezone']} · FX: {r['fx_date']}"])

async def send_report(test=False, include_demo=False):
    st=await asyncio.to_thread(settings)
    if not st.get('telegram_bot_token') or not st.get('telegram_chat_id'):
        raise HTTPException(409,'Configure Telegram bot token and owner Chat ID in Settings first.')
    report=await asyncio.to_thread(build_summary,st,None,include_demo)
    ok,err=await telegram.send(st['telegram_bot_token'],st['telegram_chat_id'],report_text(report,st,test))
    return {'ok':ok,'detail':'sent' if ok else 'Telegram rejected or timed out; check token, Chat ID and /start.','report':report}

async def summary_tick():
    st=await asyncio.to_thread(settings)
    if st.get('daily_summary_enabled')!='1' or not st.get('telegram_bot_token') or not st.get('telegram_chat_id'): return
    now=local_now(st)
    if now.strftime('%H:%M')<st.get('daily_summary_time','21:00'): return
    today=now.date().isoformat()
    def claim():
        with SessionLocal() as s:
            s.execute(text('BEGIN IMMEDIATE'))
            row=s.query(SummaryDelivery).filter_by(day=today).first()
            if row and (row.status=='sent' or row.attempts>=3 or (datetime.utcnow()-row.updated_at).total_seconds()<300): return False
            if not row: row=SummaryDelivery(day=today); s.add(row)
            row.status='sending'; row.attempts=(row.attempts or 0)+1; row.updated_at=datetime.utcnow(); s.commit(); return True
    if not await asyncio.to_thread(claim): return
    try:
        result=await send_report(); ok=result['ok']; err=result['detail']
    except Exception as e: ok=False; err=str(e)
    def finish():
        with SessionLocal() as s:
            row=s.query(SummaryDelivery).filter_by(day=today).one(); row.status='sent' if ok else 'failed'; row.error=err[:300]; row.updated_at=datetime.utcnow(); s.commit()
    await asyncio.to_thread(finish)

async def scheduler():
    while True:
        try: await summary_tick()
        except asyncio.CancelledError: raise
        except Exception: log.exception('summary tick failed')
        await asyncio.sleep(30)


def install(app, require_admin, secret):
    @app.on_event('startup')
    async def start():
        with SessionLocal() as s:
            for k,v in DEFAULTS.items(): s.execute(insert(Setting).values(key=k,value=v).on_conflict_do_nothing(index_elements=['key']))
            s.commit()
        app.state.summary_task=asyncio.create_task(scheduler())
    @app.on_event('shutdown')
    async def stop():
        task=getattr(app.state,'summary_task',None)
        if task:
            task.cancel()
            try: await task
            except asyncio.CancelledError: pass

    @app.post('/api/quiz/quote')
    def quote(p:QuoteIn): return quote_package(p,secret)

    @app.get('/feedback/{bid}',response_class=HTMLResponse)
    def feedback_page(bid:str, token:str='', code:str=''):
        demo=bid=='demo'; st=settings(); name=''; service=''
        if not demo:
            if not bid.isdigit() or not valid_review(int(bid),token,secret): raise HTTPException(404,'Review link not found')
            with SessionLocal() as s:
                b=s.get(Booking,int(bid))
                if not b or b.status!='Completed' or b.is_demo: raise HTTPException(404,'Review link not found')
                service=b.service.name if b.service else ''
        elif code:
            from database import DemoLink
            with SessionLocal() as s:
                link=s.get(DemoLink,code)
                if link:
                    cfg=json.loads(link.config_json); st={**st,'site_name':cfg.get('brand') or st.get('site_name'),'logo_path':cfg.get('logo') or ''}
        cfg={'booking_id':None if demo else int(bid),'token':token,'is_demo':demo,'site_name':st.get('site_name'),'logo':st.get('logo_path',''),'google_maps_url':st.get('google_maps_url','') if not demo else '', 'service':service}
        safe=json.dumps(cfg,ensure_ascii=False).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
        page=(ROOT/'templates/feedback.html').read_text().replace('<head>','<head><script>window.__FB__='+safe+';</script>',1)
        return HTMLResponse(page,headers={'Cache-Control':'no-store','X-Robots-Tag':'noindex,nofollow','Referrer-Policy':'no-referrer'})

    @app.post('/api/feedback')
    def save_feedback(p:FeedbackIn,bg:BackgroundTasks):
        if p.is_demo: return {'ok':True,'demo':True}
        if not valid_review(p.booking_id,p.token,secret): raise HTTPException(404,'Review link not found')
        if p.stars<=3 and not p.comment.strip(): raise HTTPException(422,'Please describe what went wrong.')
        with SessionLocal() as s:
            s.execute(text('BEGIN IMMEDIATE'))
            b=s.get(Booking,p.booking_id)
            if not b or b.status!='Completed' or b.is_demo: raise HTTPException(404,'Review link not found')
            f=s.query(Feedback).filter_by(booking_id=p.booking_id).first()
            if f: raise HTTPException(409,'Feedback already received. Thank you.')
            f=Feedback(booking_id=b.id,stars=p.stars,comment=p.comment.strip(),contact=p.contact.strip(),needs_attention=p.stars<=3,notification_status='pending' if p.stars<=3 else 'not_needed')
            s.add(f); s.commit(); fid=f.id
        if p.stars<=3: bg.add_task(notify_feedback,fid)
        return {'ok':True,'private':True}

    @app.get('/api/admin/feedback',dependencies=[Depends(require_admin)])
    def list_feedback():
        with SessionLocal() as s:
            rows=s.query(Feedback).order_by(Feedback.created_at.desc()).limit(500).all()
            return [{k:getattr(f,k) for k in ('id','booking_id','stars','comment','contact','needs_attention','resolved','is_demo','notification_status','created_at')} for f in rows]
    @app.patch('/api/admin/feedback/{fid}',dependencies=[Depends(require_admin)])
    def resolve_feedback(fid:int):
        with SessionLocal() as s:
            f=s.get(Feedback,fid)
            if not f: raise HTTPException(404,'Not found')
            f.resolved=not f.resolved; f.updated_at=datetime.utcnow(); s.commit()
        return {'ok':True}
    @app.post('/api/admin/feedback/{fid}/retry',dependencies=[Depends(require_admin)])
    async def retry_feedback(fid:int):
        with SessionLocal() as s:
            f=s.get(Feedback,fid)
            if not f or f.is_demo or not f.needs_attention: raise HTTPException(404,'Not found')
        result=await notify_feedback(fid)
        return {'ok':bool(result and result[0])}
    @app.get('/api/admin/bookings/{bid}/review-link',dependencies=[Depends(require_admin)])
    def review_link(bid:int):
        with SessionLocal() as s:
            b=s.get(Booking,bid)
            if not b or b.status!='Completed' or b.is_demo: raise HTTPException(409,'Complete a real booking first.')
        return {'path':f'/feedback/{bid}?token={review_token(bid,secret)}'}
    @app.get('/api/admin/daily-summary',dependencies=[Depends(require_admin)])
    def report_preview(include_demo:bool=False): return build_summary(include_demo=include_demo)
    @app.post('/api/admin/daily-summary/test',dependencies=[Depends(require_admin)])
    async def test_report(include_demo:bool=False): return await send_report(True,include_demo)
    @app.post('/api/admin/seed-sample',dependencies=[Depends(require_admin)])
    def seed():
        with SessionLocal() as s:
            s.execute(text('BEGIN IMMEDIATE'))
            if s.query(Setting).filter_by(key='growth_sample_v7').first(): return {'ok':True,'already_loaded':True}
            now=local_now().replace(tzinfo=None)
            sv=s.query(Service).first(); master=s.query(Staff).first()
            for i,star in enumerate([2,5,5,3]):
                b=Booking(client_name=['Anna Demo','James Demo','Marta Demo','David Demo'][i],phone='+4855500000'+str(i),service_id=sv.id,staff_id=master.id,starts_at=now.replace(hour=10+i,minute=0,second=0,microsecond=0),duration_min=sv.duration_min,price=sv.price,currency='PLN',status='Completed',is_demo=True,notes='DEMO: fictional sample')
                s.add(b); s.flush()
                s.add(Feedback(booking_id=b.id,stars=star,comment=['Waited 25 minutes beyond my appointment. Please improve scheduling.','Excellent service and very easy booking.','Careful work and a spotless result. I will return.','The final price was not explained before the visit.'][i],contact='Demo customer',needs_attention=star<=3,is_demo=True,notification_status='demo',created_at=datetime.now(timezone.utc).replace(tzinfo=None)))
            s.add(Setting(key='growth_sample_v7',value='1')); s.commit()
        return {'ok':True,'bookings':4,'feedback':4,'demo_only':True}
    @app.get('/api/demo/daily-summary')
    def demo_report():
        return {'date':local_now().date().isoformat(),'completed':12,'revenue':1860,'currency':'PLN','cancelled':1,'no_show':1,'positive':7,'private_issues':1,'demo':True,'timezone':'Europe/Warsaw','fx_date':'DEMO'}
