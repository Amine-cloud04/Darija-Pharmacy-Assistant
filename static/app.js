const $ = s => document.querySelector(s);
let page = 1, total = 0;
const chatHistory = [];
const state = () => new URLSearchParams({q: $('#query').value.trim(), form: $('#form').value, status: $('#status').value, page, per_page: 12});
const esc = s => String(s || '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

async function load() {
  const res = await fetch(`/api/medications?${state()}`); const data = await res.json(); total = data.total;
  $('#count').textContent = `${total.toLocaleString('fr-FR')} résultat${total !== 1 ? 's' : ''}`;
  $('#page-label').textContent = total ? `Page ${data.page} · ${Math.ceil(total/data.per_page)}` : '';
  $('#previous').disabled = page === 1; $('#next').disabled = page * data.per_page >= total;
  $('#result-list').innerHTML = data.items.length ? data.items.map(card).join('') : '<div class="empty">Aucun médicament ne correspond à cette recherche.</div>';
}
function card(m) { return `<article class="medicine" data-id="${esc(m.id)}"><div><h3>${esc(m.specialite)}</h3><p>${esc(m.substance_active || 'Substance active non renseignée')}</p></div><div class="meta"><span>${esc(m.dosage)}</span><span>${esc(m.forme)}</span></div><div class="price">${esc(m.ppv || 'Prix non renseigné')}</div><button class="details">Voir fiche →</button></article>`; }
$('#search-form').addEventListener('submit', e => { e.preventDefault(); page = 1; load(); });
$('#previous').onclick = () => { if(page > 1) { page--; load(); window.scrollTo({top: 300, behavior:'smooth'}); } };
$('#next').onclick = () => { page++; load(); window.scrollTo({top: 300, behavior:'smooth'}); };
$('#export').onclick = () => location.href = `/api/export?${state()}`;
$('#result-list').onclick = async e => { const card = e.target.closest('.medicine'); if (!card) return; const m = await fetch(`/api/medications/${card.dataset.id}`).then(r => r.json()); $('#detail-content').innerHTML = `<p class="eyebrow">Fiche catalogue</p><h2>${esc(m.specialite)}</h2>${[['Substance active',m.substance_active],['Dosage',m.dosage],['Forme',m.forme],['Présentation',m.presentation],['Statut',m.statut],['PPV',m.ppv],['PH',m.ph]].filter(x=>x[1]).map(([k,v])=>`<div class="fact"><span>${k}</span><b>${esc(v)}</b></div>`).join('')}<p class="warning">Données informatives issues du fichier catalogue local. Confirme la disponibilité, le prix et l’usage auprès d’une pharmacie.</p>`; $('#details').showModal(); };
$('#close-dialog').onclick = () => $('#details').close();
function bubble(text, who) { const el=document.createElement('div'); el.className=`bubble ${who}`; el.textContent=text; $('#chat').append(el); $('#chat').scrollTop=99999; return el; }
$('#chat-form').addEventListener('submit', async e => { e.preventDefault(); const input=$('#chat-input'), message=input.value.trim(); if(!message) return; bubble(message,'user'); input.value=''; const pending=bubble('Je réfléchis et je consulte le catalogue…','bot'); try { const r=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message,messages:chatHistory})}); const data=await r.json(); const answer=data.answer || data.error || 'Réponse indisponible.'; pending.textContent=answer; if(r.ok && data.answer) { chatHistory.push({role:'user',content:message},{role:'assistant',content:answer}); if(chatHistory.length>12) chatHistory.splice(0,chatHistory.length-12); } } catch { pending.textContent='Impossible de joindre le service local. Réessaie dans un instant.'; } });
fetch('/api/health').then(r=>r.json()).then(x => { $('#catalogue-status').textContent = `${x.records.toLocaleString('fr-FR')} médicaments indexés`; if(!x.chat_configured) { $('#chat-input').placeholder='Chat à configurer côté serveur'; $('#chat-input').disabled=true; $('#chat-form button').disabled=true; bubble('Le vrai chatbot nécessite une clé OPENAI_API_KEY sur le serveur. La recherche catalogue reste disponible.', 'bot'); } }).catch(()=>$('#catalogue-status').textContent='Catalogue hors ligne');
load();
