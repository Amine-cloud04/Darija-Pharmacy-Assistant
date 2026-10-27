const $=s=>document.querySelector(s);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const chatLog=$('#chat-log');
let conversation=[], page=1, perPage=8, total=0, candidatesById=new Map(), selected=null, currentSlots=null;

async function api(url,options){
  const response=await fetch(url,options);let body;
  try{body=await response.json()}catch{body={error:'Réponse illisible du serveur.'}}
  if(!response.ok)throw new Error(body.error||`Erreur ${response.status}`);
  return body;
}
function addBubble(role,text,meta=''){
  const article=document.createElement('article');article.className=`bubble ${role==='user'?'user-bubble':'assistant-bubble'}`;
  const avatar=role==='user'?'Vous':'D';
  article.innerHTML=`<span class="bubble-avatar">${avatar}</span><div class="bubble-content"><p>${esc(text).replace(/\n/g,'<br>')}</p>${meta?`<small>${esc(meta)}</small>`:''}</div>`;
  chatLog.appendChild(article);article.scrollIntoView({block:'nearest',behavior:'smooth'});return article;
}
function candidateMarkup(m,related=false){
  const price=m.ppv&& !['DH','SANS PPV'].includes(m.ppv.trim().toUpperCase())?`<span class="catalogue-price">Prix catalogue · à confirmer · ${esc(m.ppv)}</span>`:`<span class="catalogue-price">Prix non indiqué</span>`;
  const score=related?`<small class="related-note">Fiche liée · le dosage ou la forme diffère</small>`:m.matching_score!=null?`<small class="match-note">Correspondance textuelle · à confirmer</small>`:'';
  const choose=related?'':`<button type="button" class="choose-product" data-id="${esc(m.id)}">C’est bien ce produit <span>→</span></button>`;
  return `<article class="candidate-card${related?' related-card':''}"><div class="candidate-top"><span class="candidate-kind">FICHE DU CATALOGUE</span><span class="candidate-id">#${esc(m.id)}</span></div><h3>${esc(m.specialite)}</h3><p>${esc(m.substance_active||'Substance active non indiquée')}</p><div class="candidate-details"><span>${esc(m.dosage||'Dosage non indiqué')}</span><span>${esc(m.forme||'Forme non indiquée')}</span></div>${m.presentation?`<span class="package-detail">${esc(m.presentation)}</span>`:''}${price}${score}${choose}</article>`;
}
function showCandidates(items,host){
  items.forEach(item=>candidatesById.set(String(item.id),item));
  const container=document.createElement('div');container.className='candidate-list';
  if(items.length)container.innerHTML=items.map(candidateMarkup).join('');
  else container.innerHTML='<div class="no-results"><strong>Pas de correspondance assez fiable</strong><span>Vérifiez l’orthographe ou envoyez une photo plus nette.</span></div>';
  const parent=host.classList?.contains('bubble')?host.querySelector('.bubble-content'):host;
  parent.appendChild(container);
}
function showRelatedCandidates(items,host,previewItems=[]){
  const parent=host.classList?.contains('bubble')?host.querySelector('.bubble-content'):host;
  const section=document.createElement('section');section.className='related-results';
  const preview=previewItems.length?previewItems:items.slice(0,6), previewIds=new Set(preview.map(item=>String(item.id))), remaining=items.filter(item=>!previewIds.has(String(item.id)));
  section.innerHTML=`<h3>${items.length} fiches liées dans le catalogue</h3><p>Le dosage lu ne figure pas dans le catalogue. Ces fiches partagent la substance, mais ne sont pas des correspondances exactes.</p><div class="candidate-list">${preview.map(item=>candidateMarkup(item,true)).join('')}</div>${remaining.length?`<details class="related-more"><summary>Afficher les ${remaining.length} autres fiches</summary><div class="candidate-list">${remaining.map(item=>candidateMarkup(item,true)).join('')}</div></details>`:''}`;
  parent.appendChild(section);
}
function setBusy(busy){
  const button=$('#chat-form button[type="submit"]');
  button.disabled=busy;button.querySelector('span').textContent=busy?'Je comprends…':'Envoyer';
  $('#chat-input').disabled=busy;
}
function setNeed(slots){
  currentSlots=slots;const firstStep=document.querySelector('.request-steps .step:first-child');firstStep.classList.remove('active');firstStep.classList.add('done');$('#product-step').classList.add('active');const names={availability:'Disponibilité',price:'Prix',find_pharmacy:'Trouver une pharmacie',product_info:'Information sur le produit',identify:'Identifier un médicament',medical_advice:'Question de santé',other:'Votre demande'};
  $('#need-summary').textContent=`${names[slots.intent]||'Votre demande'}${slots.city?` · ${slots.city}`:''}`;
  if(slots.quantity)$('#quantity').value=slots.quantity;
  if(slots.city)$('#location').value=slots.city;
  const type=slots.intent==='availability'?'availability':slots.intent==='price'?'price':'both';
  $('#question-type').value=type;
  if(['fr','darija_latn','darija_ar'].includes(slots.language))$('#message-language').value=slots.language;
}
function clearSelection(){selected=null;const firstStep=document.querySelector('.request-steps .step:first-child');firstStep.classList.add('active');firstStep.classList.remove('done');$('#prepare-message').disabled=true;$('#selected-product').classList.add('empty-product');$('#selected-product').innerHTML='<span class="product-symbol">Rx</span><div><strong>Aucun produit confirmé</strong><p>Choisissez la fiche qui correspond à la boîte.</p></div>';$('#product-summary').textContent='À confirmer dans le catalogue';$('#product-step').classList.remove('done','active');$('#message-step').classList.remove('done','active');$('#message-result').classList.add('hidden');$('#step-state').textContent='À compléter';}
function setSelected(m,announce=true){
  selected=m;$('#prepare-message').disabled=false;
  $('#selected-product').classList.remove('empty-product');
  $('#selected-product').innerHTML=`<span class="product-symbol">✓</span><div><strong>${esc(m.specialite)}</strong><p>${esc(m.dosage||'Dosage non indiqué')} · ${esc(m.forme||'Forme non indiquée')}</p><small>${esc(m.presentation||'Présentation non indiquée')} · fiche #${esc(m.id)} · vérifiez avec l’emballage</small></div>`;
  $('#product-summary').textContent=`${m.specialite} · ${m.dosage||'dosage à confirmer'}`;
  $('#product-step').classList.add('done');$('#product-step').classList.remove('active');$('#message-step').classList.add('active');$('#step-state').textContent='Produit confirmé';
  $('#message-result').classList.add('hidden');
  if(announce){addBubble('assistant',`D’accord, j’ai noté ${m.specialite} ${m.dosage||''}. Vérifiez que le dosage et la forme correspondent bien à votre boîte. Vous pouvez préparer votre question dans le panneau « Votre demande ».`,'Fiche tirée du catalogue local · stock non vérifié');}
}
document.addEventListener('click',e=>{
  const prompt=e.target.closest('[data-prompt]');if(prompt){sendMessage(prompt.dataset.prompt);return;}
  const button=e.target.closest('.choose-product');if(!button)return;
  const record=candidatesById.get(button.dataset.id);if(record)setSelected(record);
});

async function sendMessage(text){
  text=(text||'').trim();if(!text)return;
  clearSelection();
  conversation.push({role:'user',content:text});addBubble('user',text);const quick=$('#quick-start');if(quick)quick.classList.add('hidden');setBusy(true);
  const pending=addBubble('assistant','Je regarde ce que vous voulez faire…',window.dawalinkDeployment==='vercel'?'Recherche du catalogue':'Modèle local');pending.classList.add('thinking');
  try{
    let data, fallback=window.dawalinkDeployment==='vercel';
    if(fallback)data=await api('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:text})});
    else try{data=await api('/api/assistant/message',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({messages:conversation})});}
    catch(error){
      const health=await api('/api/health');
      if(health.deployment!=='vercel')throw error;
      window.dawalinkDeployment='vercel';fallback=true;
      data=await api('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:text})});
    }
    pending.remove();if(!fallback)setNeed(data.slots);
    if(fallback){
      const host=addBubble('assistant',data.answer,'Version en ligne · interprétation déterministe et catalogue local; Qwen/Ollama est disponible seulement dans la version locale.');
      if(data.candidates?.length)showCandidates(data.candidates,host);
      return;
    }
    const host=addBubble('assistant',data.reply,`Compris avec ${data.model} · résultats du catalogue local`);
    if(data.candidates?.length)showCandidates(data.candidates,host);
    if(data.next_step==='clinical_safety')host.classList.add('safety-bubble');
  }catch(error){pending.remove();addBubble('assistant',error.message,'Le service de chat n’a pas répondu.');}
  finally{setBusy(false);$('#chat-input').focus();}
}
$('#chat-form').addEventListener('submit',event=>{event.preventDefault();const input=$('#chat-input');const text=input.value;input.value='';input.style.height='auto';sendMessage(text)});
$('#chat-input').addEventListener('input',event=>{event.target.style.height='auto';event.target.style.height=`${Math.min(event.target.scrollHeight,150)}px`;event.target.dir=/[\u0600-\u06ff]/.test(event.target.value)?'rtl':'auto'});
$('#chat-input').addEventListener('keydown',event=>{if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();$('#chat-form').requestSubmit()}});

async function checkModel(){
  try{
    const [status,health]=await Promise.all([api('/api/assistant/status'),api('/api/health')]);const badge=$('#model-status');window.dawalinkDeployment=health.deployment;
    if(status.available&&status.model_ready){badge.innerHTML='<i></i> Qwen local prêt';badge.className='model-status ready';$('#llm-setup').classList.add('hidden');}
    else{
      const hosted=health.deployment==='vercel';
      badge.innerHTML=hosted?'<i></i> Catalogue en ligne':'<i></i> Modèle à configurer';badge.className=hosted?'model-status ready':'model-status offline';
      const message=hosted?'Sur la version Vercel, le catalogue et la recherche de pharmacies fonctionnent. Le chat répond avec des règles de recherche; le modèle Qwen local et la reconnaissance Tesseract restent disponibles dans l’installation locale.':!status.available?'Démarrez Ollama puis relancez l’application.':`Installez le modèle local avec : ollama pull ${status.model}`;
      $('#llm-setup').innerHTML=`<strong>${hosted?'Version hébergée':'Le modèle de conversation n’est pas prêt.'}</strong><span>${esc(message)}</span>`;$('#llm-setup').classList.remove('hidden');
      if(hosted){$('.local-pill').innerHTML='<i></i> Catalogue hébergé';$('.model-footnote').textContent='Version Vercel : les recherches sont traitées par le serveur hébergé. Le Qwen local et Tesseract sont disponibles dans la version installée sur votre ordinateur.';}
    }
  }catch{ $('#model-status').textContent='Modèle local indisponible'; }
}

$('#medicine-image').addEventListener('change',async event=>{
  const file=event.target.files[0];if(!file)return;
  clearSelection();const user=addBubble('user',`J’ajoute une photo de boîte : ${file.name}`,'Photo conservée sur cet appareil');const quick=$('#quick-start');if(quick)quick.classList.add('hidden');
  const pending=addBubble('assistant','Je lis le texte visible sur la boîte…','OCR local');const fd=new FormData();fd.append('image',file);
  try{
    const data=await api('/api/recognize',{method:'POST',body:fd});pending.remove();
    const reply=data.ocr_available?data.message:'La reconnaissance photo demande Tesseract, qui n’est pas installé dans ce déploiement. Vous pouvez rechercher le nom dans le catalogue ou écrire votre demande.';
    const host=addBubble('assistant',reply,data.extracted_text?`Texte lu : ${data.extracted_text}`:'Résultat de la reconnaissance locale');
    if(data.candidates?.length){currentSlots={intent:'availability',language:'fr',quantity:null,city:null};setNeed(currentSlots);showCandidates(data.candidates,host);}
    else if(data.related_candidates?.length)showRelatedCandidates(data.related_candidates,host,data.related_preview||[]);
    else if(data.extracted_text){const note=document.createElement('div');note.className='extracted-text';note.textContent=`Texte lu sur l’image : ${data.extracted_text}`;host.appendChild(note);}
  }catch(error){pending.remove();addBubble('assistant',error.message,'Réessayez avec une photo nette, bien éclairée et cadrée sur le nom.');}
  finally{event.target.value='';}
});

$('#enquiry-form').addEventListener('submit',async event=>{
  event.preventDefault();if(!selected)return;
  const button=$('#prepare-message');button.disabled=true;button.textContent='Préparation…';
  try{
    const data=await api('/api/pharmacy-request',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({catalog_id:selected.id,strength:selected.dosage,form:selected.forme,presentation:selected.presentation||'',requested_quantity:$('#quantity').value,location:$('#location').value,language:$('#message-language').value,question_type:$('#question-type').value})});
    $('#generated-message').value=data.message;$('#nearby-status').textContent='';$('#nearby-results').innerHTML='';$('#message-result').classList.remove('hidden');$('#message-step').classList.add('done');$('#message-step').classList.remove('active');$('#step-state').textContent='Question prête';
    $('#message-result').scrollIntoView({block:'nearest',behavior:'smooth'});
  }catch(error){addBubble('assistant',error.message,'La question n’a pas été générée.');}
  finally{button.disabled=false;button.innerHTML='Préparer ma question <span aria-hidden="true">→</span>';}
});
$('#copy-message').addEventListener('click',async()=>{
  try{await navigator.clipboard.writeText($('#generated-message').value);$('#copy-message').textContent='Copié';setTimeout(()=>$('#copy-message').textContent='Copier le message',1500);}
  catch{$('#generated-message').select();document.execCommand('copy');}
});
$('#find-nearby').addEventListener('click',()=>{
  const status=$('#nearby-status'), button=$('#find-nearby'), results=$('#nearby-results');
  if(!navigator.geolocation){status.textContent='La géolocalisation n’est pas disponible sur cet appareil.';return;}
  button.disabled=true;status.textContent='Recherche des pharmacies à proximité…';results.innerHTML='';
  navigator.geolocation.getCurrentPosition(async position=>{
    try{
      const data=await api('/api/pharmacies/nearby',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({latitude:position.coords.latitude,longitude:position.coords.longitude,radius_m:$('#nearby-radius').value,message:$('#generated-message').value})});
      if(!data.pharmacies.length){status.innerHTML=`Aucune pharmacie OpenStreetMap trouvée dans ce rayon. <a href="${esc(data.map_search_url)}" target="_blank" rel="noopener noreferrer">Ouvrir la recherche sur la carte</a>`;return;}
      status.textContent=`${data.pharmacies.length} pharmacie${data.pharmacies.length>1?'s':''} trouvée${data.pharmacies.length>1?'s':''} · ${data.source}`;
      results.innerHTML=data.pharmacies.map((p,index)=>{
        const encoded=encodeURIComponent(p.message), wa=p.whatsapp?`<a class="contact-link" href="https://wa.me/${encodeURIComponent(p.whatsapp.replace(/\D/g,''))}?text=${encoded}" target="_blank" rel="noopener noreferrer">WhatsApp</a>`:'', sms=p.phone?`<a class="contact-link" href="sms:${encodeURIComponent(p.phone)}?body=${encoded}">SMS</a>`:'', call=p.phone?`<a class="contact-link secondary" href="tel:${encodeURIComponent(p.phone)}">Appeler</a>`:'', mail=p.email?`<a class="contact-link" href="mailto:${encodeURIComponent(p.email)}?body=${encoded}">E-mail</a>`:'';
        return `<article class="nearby-card"><div class="nearby-card-head"><span class="nearby-rank">${index+1}</span><div><strong>${esc(p.name)}</strong><small>${p.distance_km.toLocaleString('fr-FR')} km${p.address?` · ${esc(p.address)}`:''}</small></div></div><div class="nearby-actions">${wa}${sms}${call}${mail}<a class="contact-link secondary" href="${esc(p.directions_url)}" target="_blank" rel="noopener noreferrer">Itinéraire</a><a class="osm-attribution" href="${esc(p.osm_url)}" target="_blank" rel="noopener noreferrer">Fiche OSM</a></div>${!wa&&!sms&&!mail?'<small class="contact-missing">Aucun contact enregistré; utilisez l’itinéraire ou la fiche cartographique.</small>':''}</article>`;
      }).join('');
    }catch(error){status.textContent=`${error.message} `;const link=document.createElement('a');link.href=`https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(`pharmacy near ${position.coords.latitude},${position.coords.longitude}`)}`;link.target='_blank';link.rel='noopener noreferrer';link.textContent='Ouvrir la carte';status.appendChild(link);}
    finally{button.disabled=false;}
  },error=>{button.disabled=false;status.textContent=error.code===1?'Position refusée. Autorisez l’accès pour trouver les pharmacies les plus proches.':'Position indisponible. Vérifiez le GPS ou ouvrez directement la carte.';},{enableHighAccuracy:true,timeout:12000,maximumAge:120000});
});
$('#edit-request').addEventListener('click',()=>{$('#message-result').classList.add('hidden');$('#message-step').classList.remove('done');$('#message-step').classList.add('active');$('#step-state').textContent='À compléter';});
$('#new-conversation').addEventListener('click',()=>{conversation=[];chatLog.innerHTML='<article class="bubble assistant-bubble"><span class="bubble-avatar">D</span><div class="bubble-content"><p>Salam ! Vous voulez vérifier si un médicament est disponible, demander son prix, ou identifier une boîte ? Dites-moi avec vos mots. Vous pouvez aussi envoyer une photo.</p><small>Assistant local · informations du catalogue à confirmer</small></div></article>';$('<div>');const quick=document.createElement('div');quick.id='quick-start';quick.className='quick-start';quick.setAttribute('aria-label','Exemples de demandes');quick.innerHTML='<button type="button" data-prompt="Je veux vérifier si un médicament est disponible."><span>↗</span> Vérifier la disponibilité</button><button type="button" data-prompt="Je voudrais connaître le prix d’un médicament."><span>◌</span> Demander un prix</button><button type="button" data-prompt="Je ne connais pas le nom du médicament, je veux identifier ma boîte."><span>▧</span> Identifier une boîte</button>';chatLog.appendChild(quick);clearSelection();currentSlots=null;$('#need-summary').textContent='En attente de votre message';$('#quantity').value='';$('#location').value='';$('#medicine-image').value='';$('#chat-input').value='';$('#catalogue-query').value='';$('#message-step').classList.remove('done','active');$('#product-step').classList.remove('done','active');const first=document.querySelector('.request-steps .step:first-child');first.classList.remove('done');first.classList.add('active');$('#step-state').textContent='À compléter';$('#photo-result').classList.add('hidden');$('#catalogue-results').innerHTML='';$('#catalogue-count').textContent='Catalogue local';window.scrollTo({top:0,behavior:'smooth'});});

async function loadCatalogue(){
  const query=$('#catalogue-query').value.trim();const params=new URLSearchParams({q:query,page,per_page:perPage});
  try{const data=await api(`/api/medications?${params}`);total=data.total;$('#catalogue-count').textContent=`${total.toLocaleString('fr-FR')} fiches`;$('#previous').disabled=page<=1;$('#next').disabled=page*perPage>=total;
    const host=$('#catalogue-results');host.innerHTML='';if(data.items.length){data.items.forEach(x=>candidatesById.set(String(x.id),x));showCandidates(data.items,host);}else host.innerHTML='<p class="no-results">Aucune fiche trouvée.</p>';
  }catch(error){$('#catalogue-results').textContent=error.message;}
}
$('#search-catalogue').addEventListener('click',()=>{page=1;loadCatalogue()});$('#catalogue-query').addEventListener('keydown',event=>{if(event.key==='Enter'){event.preventDefault();page=1;loadCatalogue()}});$('#previous').addEventListener('click',()=>{if(page>1){page--;loadCatalogue()}});$('#next').addEventListener('click',()=>{if(page*perPage<total){page++;loadCatalogue()}});
checkModel();
