(() => {
  const $=id=>document.getElementById(id),O=Outreach,KEY='outbound-workspace-v5';
  const defaultTemplate='Hi {name}! I put together a personalized website preview for your business: {link}\nWould you like a quick walkthrough?';
  const restored=O.load(KEY,{});
  let leads=Array.isArray(restored.leads)?restored.leads.slice(0,500):[],busy=false,again=false,activeId=null;
  $('import-text').value=restored.importText||'';$('offer-template').value=restored.template??defaultTemplate;
  if(!localStorage.getItem('admin-token'))$('auth-warning').hidden=false;
  function toast(text){$('ob-toast').textContent=text;$('ob-toast').classList.add('show');setTimeout(()=>$('ob-toast').classList.remove('show'),2600);}
  function save(){const ok=O.save(KEY,{version:5,leads,template:$('offer-template').value,importText:$('import-text').value});$('save-status').textContent=ok?'Saved locally':'Storage full — export a backup';}
  function url(lead){return lead.path?location.origin+lead.path:'';}
  function offer(lead){return O.message($('offer-template').value,lead,url(lead));}
  function selected(){const search=$('search').value.toLowerCase(),filter=$('filter').value;return leads.filter(l=>(l.name+' '+l.contact).toLowerCase().includes(search)&&(filter==='all'||(filter==='opened'&&l.views>0)||(filter==='unopened'&&!l.views&&!l.optout)||(filter==='optout'&&l.optout)));}
  function logoBox(l){
    const img=l.logo&&O.validLogo(l.logo)?`<img src="${O.escape(l.logo)}" alt="" referrerpolicy="no-referrer">`:'<span>Click, then Ctrl+V<br>or drop logo</span>';
    return `<div class="ob-logo${activeId===l.id?' active':''}${l.logo?' has':''}" tabindex="0" data-logo-box title="Click, then press Ctrl+V to paste a logo (image or image URL)">${img}</div><div class="ob-logo-tools"><label class="ob-link">File<input type="file" accept="image/*" data-logo-file hidden></label>${l.logo?'<button class="ob-link" data-logo-clear type="button">Remove</button>':''}</div>`;
  }
  function render(){
    $('total-count').textContent=leads.length;$('viewed-count').textContent=leads.filter(l=>l.views>0).length;$('prepared-count').textContent=leads.filter(l=>l.actedAt).length;
    $('template-warning').hidden=$('offer-template').value.includes('{link}');
    const rows=selected();$('empty-state').hidden=rows.length>0;
    $('lead-rows').innerHTML=rows.map(l=>{
      const link=url(l),ready=!!link&&!l.optout,phone=O.phone(l.contact);
      const wa=ready&&phone?O.wa(l.contact,offer(l)):'';
      return `<tr data-id="${O.escape(l.id)}"><td><strong>${O.escape(l.name)}</strong><small>${O.escape(l.contact)}</small>${l.optout?'<span class="ob-pill optout">Do not contact</span>':''}${l.actedAt?'<div class="ob-sent">Last copy/chat action: '+O.escape(new Date(l.actedAt).toLocaleString())+'</div>':''}</td><td><span class="ob-pill">${O.escape(l.niche)}</span>${logoBox(l)}</td><td>${link?`<a href="${O.escape(link)}?inspect=1" target="_blank" rel="noopener noreferrer">/d/${O.escape(l.code)}</a>`:'<small>Preparing link…</small>'}<button class="ob-secondary" data-action="link" ${link?'':'disabled'}>Copy link</button></td><td><span class="ob-pill ${l.views?'opened':''}">${l.views?`${Number(l.views)} opens`:'Not opened'}</span>${l.last_view_at?'<small>Last: '+O.escape(new Date(l.last_view_at+'Z').toLocaleString())+'</small>':''}</td><td><div class="ob-row-actions">${wa?`<a href="${O.escape(wa)}" target="_blank" rel="noopener noreferrer" class="ob-primary" data-action="wa">Open WhatsApp</a>`:phone?'':'<small>Social contact: use Copy text</small>'}<button class="ob-secondary" data-action="copy" ${ready?'':'disabled'}>Copy text</button><button class="ob-secondary" data-action="optout">${l.optout?'Allow contact':'Do not contact'}</button><button class="ob-danger" data-action="remove">Remove</button></div></td></tr>`;
    }).join('');
  }
  function applyLogo(l,url){
    if((l.logo||'')===url)return;
    l.logo=url;
    if(l.code){l.code='';l.path='';l.views=0;l.last_view_at=null;}  // links are immutable: new logo = new link
  }
  function confirmNewLink(l){return !l.actedAt||confirm('A message for “'+l.name+'” was already prepared. A new logo creates a NEW link (the old one keeps working). Continue?');}
  function nextWithoutLogo(id){const rows=selected(),i=rows.findIndex(x=>x.id===id);return (rows.slice(i+1).concat(rows.slice(0,i))).find(x=>!x.logo)||null;}
  async function setLogo(l,source){
    if(!confirmNewLink(l))return;
    try{
      const url=typeof source==='string'?source:await O.uploadLogo(source);
      applyLogo(l,url);const nxt=nextWithoutLogo(l.id);activeId=nxt?nxt.id:l.id;
      save();render();toast(nxt?'Logo set — now paste the next one':'Logo set');prepare();
      if(nxt)document.querySelector(`tr[data-id="${nxt.id}"] [data-logo-box]`)?.scrollIntoView({block:'nearest'});
    }catch(e){toast(e.message);}
  }
  async function bulkLogos(files){
    files=[...files].filter(f=>f.type.startsWith('image/'));if(!files.length){toast('No image files found.');return;}
    const matched=[],unmatched=[],used=new Set();
    for(const f of files){const l=O.matchLead(f.name,leads);if(l&&!used.has(l.id)){used.add(l.id);matched.push([l,f]);}else unmatched.push(f.name);}
    if(matched.some(([l])=>l.actedAt)&&!confirm('Some matched leads were already messaged. New logos create NEW links for them (old links keep working). Continue?'))return;
    let ok=0,failed=[];
    for(const [l,f] of matched){$('logo-bulk-status').textContent=`Uploading ${ok+failed.length+1}/${matched.length}…`;
      try{applyLogo(l,await O.uploadLogo(f));ok++;}catch(e){failed.push(f.name+': '+e.message);}}
    save();render();
    $('logo-bulk-status').textContent=`${ok} logos matched by file name`+(unmatched.length?` · ${unmatched.length} not matched: ${unmatched.slice(0,8).join(', ')}${unmatched.length>8?'…':''}`:'')+(failed.length?` · errors: ${failed.slice(0,3).join('; ')}`:'');
    prepare();
  }
  function isTyping(t){return t&&(['INPUT','TEXTAREA','SELECT'].includes(t.tagName)&&!t.hasAttribute('data-logo-file'));}
  document.addEventListener('paste',e=>{
    if(isTyping(e.target))return;
    const l=leads.find(x=>x.id===activeId);if(!l){return;}
    const f=O.imageFromClipboard(e);
    if(f){e.preventDefault();setLogo(l,f);return;}
    const text=(e.clipboardData?.getData('text')||'').trim();
    if(text&&/^https?:\/\//.test(text)&&O.validLogo(text)){e.preventDefault();setLogo(l,text);}
  });
  $('lead-rows').addEventListener('click',e=>{
    if(e.target.closest('[data-logo-clear]')){const l=leads.find(x=>x.id===e.target.closest('tr').dataset.id);if(l&&confirmNewLink(l)){applyLogo(l,'');save();render();prepare();}return;}
    const box=e.target.closest('[data-logo-box]');if(!box)return;
    activeId=box.closest('tr').dataset.id;document.querySelectorAll('.ob-logo.active').forEach(x=>x.classList.remove('active'));box.classList.add('active');box.focus();
  });
  $('lead-rows').addEventListener('change',e=>{
    if(!e.target.matches('[data-logo-file]'))return;const f=e.target.files[0];e.target.value='';
    const l=leads.find(x=>x.id===e.target.closest('tr').dataset.id);if(l&&f)setLogo(l,f);
  });
  $('lead-rows').addEventListener('dragover',e=>{if(e.target.closest('[data-logo-box]'))e.preventDefault();});
  $('lead-rows').addEventListener('drop',e=>{
    const box=e.target.closest('[data-logo-box]');if(!box)return;e.preventDefault();
    const l=leads.find(x=>x.id===box.closest('tr').dataset.id),f=[...(e.dataTransfer?.files||[])].find(x=>x.type.startsWith('image/'));
    if(l&&f)setLogo(l,f);
  });
  const zone=$('logo-drop');
  zone.addEventListener('dragover',e=>{e.preventDefault();zone.classList.add('over');});
  zone.addEventListener('dragleave',()=>zone.classList.remove('over'));
  zone.addEventListener('drop',e=>{e.preventDefault();zone.classList.remove('over');bulkLogos(e.dataTransfer.files);});
  $('logo-bulk-file').addEventListener('change',e=>{const f=[...e.target.files];e.target.value='';bulkLogos(f);});
  async function prepare(){
    if(busy){again=true;return;}
    const pending=leads.filter(l=>!l.code);
    if(!pending.length){await refresh();return;}
    busy=true;$('network-status').textContent='Saving personalized short links…';
    try{
      const result=await O.api('/api/admin/demo-links/batch',{items:pending.map(l=>({brand:l.name,niche:l.niche,key:l.id,demo:true,logo:l.logo||''}))});
      result.items.forEach((r,i)=>{const l=leads.find(x=>x.id===pending[i].id);if(l&&(l.logo||'')===(pending[i].logo||''))Object.assign(l,r);});
      save();render();$('network-status').textContent='Links ready. Opens refresh every 15 seconds while this page is visible.';
    }catch(e){$('network-status').textContent=e.message+' Use Refresh views to retry.';}finally{busy=false;if(again){again=false;prepare();}}
  }
  async function refresh(){
    const codes=leads.filter(l=>l.code).map(l=>l.code);if(!codes.length)return;
    try{
      const result=await O.api('/api/admin/demo-links/stats',{codes});const map=new Map(result.items.map(r=>[r.code,r]));
      for(const l of leads){if(map.has(l.code))Object.assign(l,map.get(l.code));}
      save();render();$('network-status').textContent='Updated '+new Date().toLocaleTimeString()+'. Counts reflect visible page opens, not unique people or message reads.';
    }catch(e){$('network-status').textContent=e.message;}
  }
  $('parse-btn').addEventListener('click',async()=>{
    if(busy){toast('Please wait for links to finish saving.');return;}
    try{
      const result=O.parse($('import-text').value);
      if(!result.items.length){$('import-status').textContent='No valid contacts found.';}
      else{
        const existing=$('replace-import').checked?[]:leads;
        const seen=new Set(existing.map(l=>l.signature));let added=0,duplicates=result.duplicates;
        const next=[...existing];
        for(const item of result.items){if(seen.has(item.signature)){duplicates++;continue;}seen.add(item.signature);next.push({...item,logo:item.logo||'',id:crypto.randomUUID().replaceAll('-',''),views:0,path:'',code:'',optout:false});added++;}
        if(next.length>500)throw new Error('Maximum 500 leads. Export or remove older leads before importing more.');
        if($('replace-import').checked&&leads.length&&!confirm('Replace the local list? Previously shared demo links will still work.'))return;
        leads=next;$('import-status').textContent=`${added} added · ${duplicates} duplicates skipped · ${result.errors.length} invalid rows`;
        save();render();
      }
      $('import-errors').textContent=result.errors.slice(0,20).join('\n');$('import-errors').hidden=!result.errors.length;
      await prepare();
    }catch(e){toast(e.message);}
  });
  $('sample-btn').addEventListener('click',()=>{$('import-text').value='Luna Demo Studio | beauty | @luna_demo_studio\nNorth Demo Barber | barber | https://instagram.com/north_demo_barber\nCity Demo Motors | auto | demo-profile\nGloss Demo Lab | detailing | @gloss_demo_lab';save();});
  $('lead-rows').addEventListener('click',async e=>{
    const button=e.target.closest('[data-action]');if(!button)return;const row=button.closest('tr'),l=leads.find(x=>x.id===row.dataset.id);if(!l)return;
    try{
      if(button.dataset.action==='copy'){await O.copy(offer(l));l.actedAt=new Date().toISOString();toast('Personalized offer copied');}
      if(button.dataset.action==='link'){await O.copy(url(l));toast('Link copied');}
      if(button.dataset.action==='wa'){l.actedAt=new Date().toISOString();/* user opens chat; not marked as delivered */}
      if(button.dataset.action==='optout')l.optout=!l.optout;
      if(button.dataset.action==='remove'){if(!confirm('Remove this local lead? The shared demo link remains valid.'))return;leads=leads.filter(x=>x!==l);}
      save();if(button.dataset.action!=='wa')render();
    }catch(error){toast(error.message);}
  });
  for(const id of ['import-text','offer-template'])$(id).addEventListener('input',()=>{save();if(id==='offer-template')render();});
  for(const id of ['search','filter'])$(id).addEventListener('input',render);
  document.querySelectorAll('[data-insert]').forEach(b=>b.addEventListener('click',()=>{const t=$('offer-template');t.setRangeText(b.dataset.insert,t.selectionStart,t.selectionEnd,'end');t.focus();save();render();}));
  $('refresh-btn').addEventListener('click',prepare);
  $('clear-btn').addEventListener('click',()=>{if(busy)return;if(confirm('Delete this browser’s contact list and draft? Export a backup first.')){leads=[];$('import-text').value='';$('offer-template').value=defaultTemplate;save();render();}});
  $('export-btn').addEventListener('click',()=>{const blob=new Blob([JSON.stringify({version:5,leads,template:$('offer-template').value},null,2)],{type:'application/json'}),a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='outbound-backup.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);});
  $('restore-file').addEventListener('change',async e=>{
    try{
      const f=e.target.files[0];if(!f)return;if(busy)throw new Error('Wait for link preparation before restoring.');if(f.size>3000000)throw new Error('Backup exceeds 3 MB.');
      const data=JSON.parse(await f.text());if(data.version!==5||!Array.isArray(data.leads)||data.leads.length>500||typeof data.template!=='string')throw new Error('Invalid backup format.');
      const clean=data.leads.map(l=>{if(typeof l.name!=='string'||l.name.length>120||!O.niches.includes(l.niche)||typeof l.contact!=='string'||l.contact.length>300||typeof l.id!=='string'||!/^[a-zA-Z0-9_-]{1,120}$/.test(l.id))throw new Error('Invalid lead in backup.');return {name:l.name,niche:l.niche,contact:l.contact,id:l.id,signature:l.signature||`${l.name.toLowerCase()}|${l.niche}|${O.phone(l.contact)||l.contact.toLowerCase()}`,logo:O.validLogo(l.logo||'')?l.logo:'',code:'',path:'',views:0,optout:!!l.optout,actedAt:l.actedAt||null};});
      if(!confirm('Replace current local workspace with this backup?'))return;
      leads=clean;$('offer-template').value=data.template;save();render();await prepare();toast('Backup restored');
    }catch(error){toast(error.message);}finally{e.target.value='';}
  });
  render();prepare();setInterval(()=>{if(document.visibilityState==='visible'&&!busy)refresh();},15000);
})();
