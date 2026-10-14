/* Immutable links: editing the builder NEVER changes a link already sent to a lead. */
(() => {
  const fields=['name','logo','niche','layout','theme','demo'];
  const input=id=>document.getElementById('pv-'+id);
  let serial=0,timer,active,lastConfig='',readyPath='',scheduledConfig='';
  const status=document.getElementById('pv-status'),copyBtn=document.getElementById('pv-copy');
  function read(){return {brand:input('name').value.trim(),logo:input('logo').value.trim(),niche:input('niche').value,layout:input('layout').value,theme:input('theme').value,demo:input('demo').checked};}
  async function persist(config,version){
    try{
      const data=await Outreach.api('/api/admin/demo-links',config,active.signal);
      if(version!==serial)return;
      readyPath=data.path;input('url').value=location.origin+readyPath;
      const open=document.getElementById('pv-open');open.href=input('url').value+'?inspect=1';
      open.removeAttribute('aria-disabled');open.style.pointerEvents='';
      copyBtn.disabled=false;status.textContent='Ready · changes are saved automatically';lastConfig=JSON.stringify(config);
    }catch(e){if(e.name!=='AbortError'&&version===serial){status.textContent=e.message;input('url').value='';scheduledConfig='';}}
  }
  function changed(){
    const config=read();const signature=JSON.stringify(config);if(signature===scheduledConfig)return;scheduledConfig=signature;Outreach.save('preview-builder-v5',config);
    const version=++serial;clearTimeout(timer);active?.abort();active=new AbortController();
    copyBtn.disabled=true;readyPath='';input('url').value='';
    const open=document.getElementById('pv-open');open.removeAttribute('href');open.setAttribute('aria-disabled','true');open.style.pointerEvents='none';
    status.textContent='Saving your short link…';
    timer=setTimeout(()=>persist(config,version),180);
  }
  const draft=Outreach.load('preview-builder-v5',null);
  if(draft){for(const field of fields){if(field==='demo')input(field).checked=draft.demo??true;else input(field).value=draft[field==='name'?'brand':field]??'';}}
  fields.forEach(field=>{input(field).addEventListener('input',changed);input(field).addEventListener('change',changed);});
  copyBtn.addEventListener('click',async()=>{
    if(!readyPath)return;
    try{await Outreach.copy(input('url').value);const text=copyBtn.textContent;copyBtn.textContent='Copied';setTimeout(()=>copyBtn.textContent=text,1300);}catch(e){status.textContent=e.message;}
  });
  window.initPreviewLinks=()=>{if(!readyPath)changed();};
  window.addEventListener('online',()=>{if(!readyPath){scheduledConfig='';changed();}});
})();
