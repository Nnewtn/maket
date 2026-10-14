/* Shared by the live link builder and outbound conveyor. No external JS dependencies. */
(function(root){
  const niches=['beauty','barber','auto','detailing'];
  function escape(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
  function phone(s){const raw=String(s).replace(/^tel:/i,'').trim();return /^\+?[\d\s().-]+$/.test(raw)&&raw.replace(/\D/g,'').length>=8&&raw.replace(/\D/g,'').length<=15?raw.replace(/\D/g,''):'';}
  function message(template,row,link){return String(template).replace(/\{(name|niche|link)\}/g,(_,k)=>k==='link'?link:String(row[k]??''));}
  function wa(contact,text){const p=phone(contact);return p?`https://wa.me/${p}?text=${encodeURIComponent(text)}`:'';}
  function delimiter(text){let quote=false;const counts={'|':0,'\t':0,';':0,',':0};for(let i=0;i<text.length;i++){const c=text[i];if(c==='"'){if(quote&&text[i+1]==='"'){i++;continue;}quote=!quote;}else if(!quote&&(c==='\n'||c==='\r')){if(Object.values(counts).some(Boolean))break;}else if(!quote&&Object.hasOwn(counts,c))counts[c]++;}return Object.keys(counts).reduce((best,d)=>counts[d]>counts[best]?d:best,'|');}
  function csv(text,delim){
    const rows=[];let cells=[],cell='',quote=false;
    for(let i=0;i<text.length;i++){
      const c=text[i];
      if(c==='"'){if(quote&&text[i+1]==='"'){cell+='"';i++;}else if(quote||!cell.trim()){quote=!quote;}else cell+=c;}
      else if(!quote&&c===delim){cells.push(cell.trim());cell='';}
      else if(!quote&&(c==='\n'||c==='\r')){if(c==='\r'&&text[i+1]==='\n')i++;cells.push(cell.trim());if(cells.some(Boolean))rows.push(cells);cells=[];cell='';}
      else cell+=c;
    }
    if(quote)throw new Error('Unclosed quote in CSV. Close the quoted field and retry.');
    cells.push(cell.trim());if(cells.some(Boolean))rows.push(cells);return rows;
  }
  function parse(text){
    if(text.length>500000)throw new Error('Import is too large. Maximum 500 KB.');
    const rows=csv(text.replace(/^\uFEFF/,''),delimiter(text)),items=[],errors=[],seen=new Set();let duplicates=0;
    rows.forEach((r,i)=>{
      if(i===0&&/^(name|salon|company|название|nazwa)/i.test(r[0])&&!niches.includes((r[1]||'').toLowerCase()))return;
      const [name,niche0,contact]=r,niche=(niche0||'').toLowerCase();
      if(r.length!==3||!name||name.length>120||!niches.includes(niche)||!contact||contact.length>300){errors.push(`Row ${i+1}: expected Name | beauty/barber/auto/detailing | contact (name ≤120 characters).`);return;}
      const signature=`${name.toLowerCase()}|${niche}|${phone(contact)||contact.toLowerCase()}`;
      if(seen.has(signature)){duplicates++;return;}seen.add(signature);items.push({name,niche,contact,signature});
    });
    if(items.length>500)throw new Error('Maximum 500 valid contacts per browser workspace.');
    return {items,errors,duplicates};
  }
  async function api(path,body,signal){
    const token=localStorage.getItem('admin-token')||'';
    const controller=new AbortController();const relay=()=>controller.abort();
    if(signal){if(signal.aborted)relay();else signal.addEventListener('abort',relay,{once:true});}
    const timer=setTimeout(()=>controller.abort(new DOMException('Request timed out. Check your connection and retry.','TimeoutError')),15000);
    try{
      const response=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json','X-Admin-Token':token},body:JSON.stringify(body),signal:controller.signal});
      const data=await response.json().catch(()=>({}));
      if(response.status===401)throw new Error('Sign in to the CRM first. Your local draft has not been deleted.');
      if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:'Invalid data or request failed. Check the fields.');
      return data;
    }finally{clearTimeout(timer);signal?.removeEventListener('abort',relay);}
  }
  async function copy(text){
    if(navigator.clipboard&&window.isSecureContext){await navigator.clipboard.writeText(text);return;}
    const area=document.createElement('textarea');area.value=text;area.style.position='fixed';area.style.opacity='0';document.body.append(area);area.select();
    const ok=document.execCommand('copy');area.remove();if(!ok)throw new Error('Clipboard blocked. Select and copy the text manually.');
  }
  function save(key,value){try{localStorage.setItem(key,JSON.stringify(value));return true;}catch{return false;}}
  function load(key,fallback){try{return JSON.parse(localStorage.getItem(key))??fallback;}catch{return fallback;}}
  root.Outreach={niches,escape,phone,message,wa,csv,parse,api,copy,save,load};
  if(typeof module!=='undefined')module.exports=root.Outreach;
})(typeof window==='undefined'?globalThis:window);
