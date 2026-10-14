const assert=require('node:assert/strict');
const O=require('../static/js/outreach-core.js');
assert.equal(O.parse('Luna | beauty | +48 500 100 200').items.length,1);
assert.equal(O.parse('name,niche,contact\r\n"Salon, Gold",barber,@gold').items[0].name,'Salon, Gold');
assert.equal(O.parse('Nazwa;nisza;kontakt\nLuna;beauty;@luna').items.length,1);
assert.equal(O.parse('Luna\tbeauty\t@luna').items.length,1);
assert.equal(O.parse('Luna | beauty | +48500100200\nLuna | beauty | +48 500 100 200').duplicates,1);
assert.equal(O.parse('Broken | unsupported | @user').errors.length,1);
assert.throws(()=>O.parse('"Never closed,barber,@user'));
assert.equal(O.message('Hi {name}! {link} {name}',{name:'A & B'},'https://example.com/d/abc'),'Hi A & B! https://example.com/d/abc A & B');
assert.equal(O.message('Hi {name}! {link}',{name:'$&'},'https://example.com'),'Hi $&! https://example.com');
const wa=O.wa('+48 500 100 200','Hi Luna! https://example.com/d/abc');
assert.equal(new URL(wa).searchParams.get('text'),'Hi Luna! https://example.com/d/abc');
assert.equal(O.wa('@luna','Hello'),'');
assert.equal(O.escape('<img onerror="x">'),'&lt;img onerror=&quot;x&quot;&gt;');
assert.equal(O.parse('\uFEFFLuna | beauty | @luna').items.length,1);
console.log('13 parser, template, escaping and WhatsApp assertions passed.');
{
  const r=O.parse('Luna | beauty | @luna | https://example.com/logo.png');
  assert.equal(r.items[0].logo,'https://example.com/logo.png');
  assert.equal(O.parse('Luna | beauty | @luna | javascript:alert(1)').errors.length,1);
  assert.equal(O.parse('Luna | beauty | @luna').items[0].logo,'');
  assert.equal(O.matchLead('Studio Luna.png',[{name:'Studio Luna'},{name:'Other'}]).name,'Studio Luna');
  assert.equal(O.matchLead('north-barber (2).jpg',[{name:'North Barber'}]).name,'North Barber');
  assert.equal(O.matchLead('random.png',[{name:'North Barber'}]),null);
  console.log('logo parsing and filename matching passed.');
}
