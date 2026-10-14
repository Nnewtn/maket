"""Real Chromium end-to-end smoke suite. Start uvicorn before running this script.
BASE_URL defaults to http://127.0.0.1:8075; uses a separate disposable data directory.
"""
import os
from datetime import date, timedelta
from pathlib import Path
import httpx
from playwright.sync_api import sync_playwright, expect

BASE=os.environ.get('BASE_URL','http://127.0.0.1:8075')
api=httpx.Client(base_url=BASE)
token=api.post('/api/admin/login',json={'password':'admin123'}).json()['token']
headers={'X-Admin-Token':token}
errors=[]
with sync_playwright() as pw:
    browser=pw.chromium.launch(args=['--no-sandbox'])
    context=browser.new_context(viewport={'width':1440,'height':1000},permissions=['clipboard-read','clipboard-write'])
    context.add_init_script("localStorage.setItem('admin-token',"+repr(token)+");localStorage.setItem('site-lang','en');")
    # Tests are independent of third-party image/font/CDN availability.
    context.route('https://images.unsplash.com/**',lambda r:r.abort())
    context.route('https://fonts.googleapis.com/**',lambda r:r.abort())
    context.route('https://fonts.gstatic.com/**',lambda r:r.abort())
    context.route('**/api/fx',lambda r:r.fulfill(json={'rates':{'PLN':1,'EUR':.23,'USD':.25}}))
    page=context.new_page();page.on('pageerror',lambda error:errors.append(str(error)))
    page.goto(BASE+'/admin');page.get_by_role('button',name='Preview links',exact=False).click()
    page.locator('#pv-name').fill('Luna Beauty');page.locator('#pv-niche').select_option('beauty')
    expect(page.locator('#pv-copy')).to_be_enabled()
    first=page.locator('#pv-url').input_value();assert '/d/' in first
    page.locator('#pv-name').fill('City Motors');page.locator('#pv-niche').select_option('auto')
    expect(page.locator('#pv-copy')).to_be_enabled()
    second=page.locator('#pv-url').input_value();assert first!=second
    page.locator('#pv-copy').click();expect(page.locator('#pv-copy')).to_have_text('Copied');assert page.evaluate('navigator.clipboard.readText()')==second
    page.reload();page.get_by_role('button',name='Preview links',exact=False).click();expect(page.locator('#pv-copy')).to_be_enabled();assert page.locator('#pv-name').input_value()=='City Motors'
    print('PASS live generator, immutable links, clipboard, restored builder')

    demo=page.context.new_page();demo.on('pageerror',lambda error:errors.append(str(error)))
    before=api.get('/api/admin/bookings',headers=headers).json()
    for niche,english,polish in [('beauty','Gel manicure','Manicure hybrydowy'),('barber','Beard trim & shape','Strzyżenie i modelowanie brody'),('auto','Oil & filter change','Wymiana oleju i filtra'),('detailing','One-step paint correction','Jednoetapowa korekta lakieru')]:
        link=api.post('/api/admin/demo-links',headers=headers,json={'brand':'Brand '+niche,'niche':niche}).json()['path']
        demo.goto(BASE+link);expect(demo.locator('#brand-name')).to_have_text('Brand '+niche);expect(demo.locator('#services-grid')).to_contain_text(english)
        demo.locator('#lang-btn').click();demo.locator('[data-lang-opt=pl]').click();expect(demo.locator('#services-grid')).to_contain_text(polish)
        demo.locator('#lang-btn').click();demo.locator('[data-lang-opt=en]').click()
    demo.goto(second);expect(demo.locator('#services-grid')).to_contain_text('Oil & filter change')
    demo.locator('#name').fill('Test Visitor');demo.locator('#phone').fill('+48500100200');demo.locator('#date').fill((date.today()+timedelta(days=2)).isoformat());demo.locator('.slot').first.click();demo.locator('#submit-btn').click();expect(demo.locator('#booking-success')).to_contain_text('Demo booking complete')
    assert before==api.get('/api/admin/bookings',headers=headers).json()
    demo.goto(first);expect(demo.locator('#brand-name')).to_have_text('Luna Beauty')
    print('PASS four niche catalogs, Polish translations, brand isolation and no real demo bookings')

    page.goto(BASE+'/admin/outbound')
    page.locator('#import-text').fill('North Barber | barber | +48 500 100 200\nAuto Center | auto | @autocenter\nNorth Barber | barber | +48500100200\nWrong | fake | @wrong')
    page.locator('#parse-btn').click();expect(page.locator('#lead-rows tr')).to_have_count(2)
    expect(page.locator('#lead-rows tr').first.locator('a[data-action=wa]')).to_be_visible()
    expect(page.locator('#import-status')).to_contain_text('duplicates skipped')
    page.locator('#offer-template').fill('Hi {name}! Here is your preview: {link}')
    expect(page.locator('#lead-rows tr').first.locator('a[data-action=wa]')).to_have_attribute('href',__import__('re').compile('https://wa.me/48500100200\\?text=Hi%20North%20Barber'))
    page.locator('#lead-rows tr').first.locator('[data-action=copy]').click()
    expect(page.locator('#ob-toast')).to_have_text('Personalized offer copied');copied=page.evaluate('navigator.clipboard.readText()');assert 'Hi North Barber!' in copied and '/d/' in copied
    page.reload();expect(page.locator('#lead-rows tr')).to_have_count(2);assert page.locator('#offer-template').input_value()=='Hi {name}! Here is your preview: {link}'
    lead_link=page.locator('#lead-rows tr').first.locator('td:nth-child(3) a').get_attribute('href').replace('?inspect=1','')
    demo.goto(lead_link);expect(demo.locator('#brand-name')).to_have_text('North Barber')
    page.locator('#refresh-btn').click();expect(page.locator('#lead-rows tr').first.locator('td:nth-child(4)')).to_contain_text('1 opens')
    page.locator('#lead-rows tr').first.locator('[data-action=optout]').click();expect(page.locator('#lead-rows tr').first.locator('[data-action=copy]')).to_be_disabled();assert page.locator('#lead-rows tr').first.locator('a[data-action=wa]').count()==0
    page.locator('#search').fill('Auto');expect(page.locator('#lead-rows tr')).to_have_count(1)
    page.locator('#search').fill('')
    page.screenshot(path=os.environ.get('OUTBOUND_SCREENSHOT','/tmp/outbound-desktop.png'),full_page=True)
    print('PASS import, dedup, template substitution, WA URL, copying, persistence, view polling, opt-out and search')

    mobile=browser.new_context(viewport={'width':390,'height':844},is_mobile=True,has_touch=True)
    mobile.add_init_script("localStorage.setItem('admin-token',"+repr(token)+");localStorage.setItem('site-lang','en');")
    mobile.route('https://images.unsplash.com/**',lambda r:r.abort())
    mobile.route('https://fonts.googleapis.com/**',lambda r:r.abort())
    mobile.route('https://fonts.gstatic.com/**',lambda r:r.abort())
    mobile.route('**/api/fx',lambda r:r.fulfill(json={'rates':{'PLN':1,'EUR':.23,'USD':.25}}))
    m=mobile.new_page();m.on('pageerror',lambda error:errors.append(str(error)))
    m.goto(BASE+'/admin/outbound');m.locator('#sample-btn').click();m.locator('#parse-btn').click();expect(m.locator('#lead-rows tr')).to_have_count(4);assert m.evaluate('document.documentElement.scrollWidth<=innerWidth'), 'Outbound overflow'
    m.goto(first);expect(m.locator('#brand-name')).to_have_text('Luna Beauty');assert m.evaluate('document.documentElement.scrollWidth<=innerWidth'), 'Preview overflow'
    m.locator('#lang-btn').click();expect(m.locator('#lang-menu')).to_be_visible();m.locator('[data-lang-opt=pl]').click()
    m.screenshot(path=os.environ.get('MOBILE_SCREENSHOT','/tmp/preview-mobile.png'),full_page=True)
    print('PASS mobile 390px layout and language dropdown')
    assert not errors,errors
    print('PASS no uncaught browser JS exceptions')
    browser.close()
