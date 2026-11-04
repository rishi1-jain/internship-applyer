/* Serialized by chrome.scripting; deliberately self-contained. Never submits, clicks, or accepts consent. */
function fillApprovedPacket(packet) {
  function canonical(url) { const u=new URL(url); return u.origin+u.pathname.replace(/\/+$/,'').replace(/\/apply$/,''); }
  const target=new URL(packet.url), here=new URL(location.href);
  // Greenhouse's older boards URL redirects to job-boards.greenhouse.io. Preserve board and job identity.
  const green=h=>['boards.greenhouse.io','job-boards.greenhouse.io'].includes(h);
  const same=canonical(target.href)===canonical(here.href) || (green(target.hostname)&&green(here.hostname)&&target.pathname.replace(/\/+$/,'')===here.pathname.replace(/\/+$/,''));
  if(!same) return {error:'This page does not match the approved job URL. Open that job’s application form first.'};
  // Embedded Greenhouse forms can use gh_jid or other job identifiers; do not relax URL matching to the host.
  const ids=['gh_jid','jobId','job_id','gh_src'];
  for(const key of ids.filter(k=>k!=='gh_src')) if(target.searchParams.has(key)&&target.searchParams.get(key)!==here.searchParams.get(key)) return {error:'Job identifier does not match the approved packet.'};
  if(target.search&&!ids.some(k=>target.searchParams.has(k))&&target.search!==here.search) return {error:'Job URL query differs. Verify and import the final application URL.'};
  const norm=s=>String(s||'').toLowerCase().replace(/[\s_*:]+/g,' ').replace(/[^a-z0-9 +#?.-]/g,'').trim();
  const labelText=l=>{const copy=l.cloneNode(true);copy.querySelectorAll('input,select,textarea,button').forEach(c=>c.remove());return copy.textContent;};
  const labels=el=>[...(el.labels||[])].map(labelText).join(' ') || el.getAttribute('aria-label') || (el.getAttribute('aria-labelledby')||'').split(' ').map(id=>document.getElementById(id)?.textContent||'').join(' ').trim() || el.placeholder || el.name || el.id;
  const aliases={first_name:['first name','given name','firstname','first-name'],last_name:['last name','family name','surname','lastname','last-name'],full_name:['full name','name','your name'],email:['email','email address','e-mail'],phone:['phone','phone number','mobile','mobile phone'],location:['location','city','current location','city / location'],linkedin:['linkedin','linkedin profile','linkedin url','linkedin profile url'],github:['github','github url','github profile'],website:['website','portfolio','personal website','portfolio url'],school:['school','university','college','school name'],graduation:['graduation','expected graduation','graduation date','expected graduation date']};
  const filled=[],skipped=[];
  const fields=packet.fields;
  const controls=[...document.querySelectorAll('input,textarea,select')];
  for(const el of controls){
    if(el.disabled||el.readOnly||el.type==='hidden'||el.getClientRects().length===0)continue;
    const label=labels(el),n=norm(label),name=norm(el.name||el.id);
    if(['submit','button','reset','password','checkbox','radio'].includes(el.type)){if(el.required&&!el.checked&&['checkbox','radio'].includes(el.type))skipped.push(label+' (manual choice)');continue;}
    if(el.type==='file'){
      if(el.files?.length){skipped.push(label+' (already has a file)');continue;}
      if(!/resume|résumé|\bcv\b/i.test(label+' '+el.name+' '+el.id)){skipped.push(label+' (upload manually)');continue;}
      if(el.accept&&!/pdf|application\/\*|\*/i.test(el.accept)){skipped.push(label+' (this input may not accept PDF; upload manually)');continue;}
      try{const bytes=Uint8Array.from(atob(packet.pdf),c=>c.charCodeAt(0));const dt=new DataTransfer();dt.items.add(new File([bytes],`resume-${packet.id}.pdf`,{type:'application/pdf'}));el.files=dt.files;el.dispatchEvent(new Event('change',{bubbles:true}));filled.push(label+' (review PDF upload)');}catch{skipped.push(label+' (upload PDF manually)');}continue;
    }
    const selectedPlaceholder=el.tagName==='SELECT'&&el.selectedOptions?.[0]&&(el.value===''||/^(select|choose|please select|--)/i.test(el.selectedOptions[0].textContent.trim()));
    if(el.value&&!selectedPlaceholder){skipped.push(label+' (existing answer preserved)');continue;}
    const custom=(fields.custom||[]).find(a=>norm(a.label)===n);
    let value=custom?.value;
    // Standard mappings exclude questions asking for disclosures, consent, authorization, or sensitive facts.
    const sensitive=/authoriz|sponsor|citizen|visa|disabil|veteran|gender|race|ethnic|agree|consent|legal|eligible|18 years|criminal|salary|compensation/i.test(label);
    if(value===undefined&&!sensitive){const key=Object.keys(aliases).find(k=>aliases[k].includes(n)||aliases[k].includes(name));if(key)value=fields[key];}
    if(!value){if(el.required||el.getAttribute('aria-required')==='true')skipped.push(label+' (needs your answer)');continue;}
    if(el.tagName==='SELECT'){
      const option=[...el.options].find(o=>norm(o.textContent)===norm(value)||norm(o.value)===norm(value));
      if(!option){skipped.push(label+' (no exact option; select manually)');continue;}
      el.value=option.value;
    } else {
      const proto=el.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype;
      Object.getOwnPropertyDescriptor(proto,'value').set.call(el,value);
    }
    el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));
    el.style.outline='2px solid #91ad88';filled.push(label);
  }
  if(document.querySelector('iframe'))skipped.push('Embedded forms may need manual entry.');
  return {filled,skipped};
}
if(typeof module!=='undefined')module.exports={fillApprovedPacket};
