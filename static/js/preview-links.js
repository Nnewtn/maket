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
  // Logo: Ctrl+V / drag-and-drop / file picker -> uploaded, field filled with the stored path
  const thumb=document.getElementById('pv-logo-thumb');
  function showThumb(){const v=input('logo').value.trim();if(v&&Outreach.validLogo(v)){thumb.src=v;thumb.referrerPolicy='no-referrer';thumb.classList.remove('hidden');}else thumb.classList.add('hidden');}
  async function setLogoFile(file){
    status.textContent='Uploading logo…';
    try{input('logo').value=await Outreach.uploadLogo(file);showThumb();changed();}
    catch(e){status.textContent=e.message;}
  }
  input('logo').addEventListener('paste',e=>{const f=Outreach.imageFromClipboard(e);if(f){e.preventDefault();setLogoFile(f);}});
  // pasting anywhere inside this section (outside other text fields) also works
  document.addEventListener('paste',e=>{
    const sec=document.getElementById('sec-preview');if(!sec||sec.classList.contains('hidden')||e.target===input('logo'))return;
    if(['INPUT','TEXTAREA','SELECT'].includes(e.target.tagName))return;
    const f=Outreach.imageFromClipboard(e);if(f){e.preventDefault();setLogoFile(f);}
  });
  input('logo').addEventListener('dragover',e=>e.preventDefault());
  input('logo').addEventListener('drop',e=>{const f=[...(e.dataTransfer?.files||[])].find(x=>x.type.startsWith('image/'));if(f){e.preventDefault();setLogoFile(f);}});
  document.getElementById('pv-logo-file').addEventListener('change',e=>{const f=e.target.files[0];e.target.value='';if(f)setLogoFile(f);});
  input('logo').addEventListener('input',showThumb);
  const draft=Outreach.load('preview-builder-v5',null);
  if(draft){for(const field of fields){if(field==='demo')input(field).checked=draft.demo??true;else input(field).value=draft[field==='name'?'brand':field]??'';}}
  showThumb();
  fields.forEach(field=>{input(field).addEventListener('input',changed);input(field).addEventListener('change',changed);});
  copyBtn.addEventListener('click',async()=>{
    if(!readyPath)return;
    try{await Outreach.copy(input('url').value);const text=copyBtn.textContent;copyBtn.textContent='Copied';setTimeout(()=>copyBtn.textContent=text,1300);}catch(e){status.textContent=e.message;}
  });
  window.initPreviewLinks=()=>{if(!readyPath)changed();};
  window.addEventListener('online',()=>{if(!readyPath){scheduledConfig='';changed();}});
})();
