document.addEventListener("DOMContentLoaded", function(){
  var elems = document.querySelectorAll('.modal');
  M.Modal.init(elems);
  M.FormSelect.init(document.querySelectorAll('select'));
  const modal = M.Modal.getInstance(document.getElementById('mapping-modal'));
  document.getElementById('open-add').addEventListener('click', ()=>{
    document.getElementById('modal-title').innerText = 'Add Mapping';
    document.getElementById('tag-input').value = '';
    document.getElementById('uri-input').value = '';
    M.updateTextFields();
    M.FormSelect.init(document.querySelectorAll('select'));
    modal.open();
  });

  function fetchMappings(){
    fetch('/rfid/api/mappings').then(r=>r.json()).then(j=>renderMappings(j)).catch(e=>console.error(e));
  }
  function renderMappings(map){
    const tbody = document.getElementById('mappings-tbody'); tbody.innerHTML = '';
    Object.keys(map).forEach(tag=>{
      const tr = document.createElement('tr');
      const tdTag = document.createElement('td'); tdTag.textContent = tag; tdTag.className = 'pointer';
      const tdUri = document.createElement('td'); tdUri.innerHTML = '<pre>'+map[tag]+'</pre>';
      const tdDel = document.createElement('td');
      const delBtn = document.createElement('a'); delBtn.className = 'waves-effect waves-light btn-small red'; delBtn.textContent = 'Delete';
      delBtn.addEventListener('click', (ev)=>{ ev.stopPropagation(); if(confirm('Delete mapping for ' + tag + '?')){ fetch('/rfid/api/mappings/'+encodeURIComponent(tag), {method: 'DELETE'}).then(()=>fetchMappings()); } });
      tdDel.appendChild(delBtn);
      tr.appendChild(tdTag); tr.appendChild(tdUri); tr.appendChild(tdDel);
      tr.addEventListener('click', ()=>{
        document.getElementById('modal-title').innerText = 'Edit Mapping';
        document.getElementById('tag-input').value = tag;
        document.getElementById('uri-input').value = map[tag];
        M.updateTextFields();
        modal.open();
      });
      tbody.appendChild(tr);
    });
  }

  document.getElementById('save-mapping').addEventListener('click', ()=>{
    const tag = document.getElementById('tag-input').value.trim();
    const type = document.getElementById('type-select').value;
    let uri = document.getElementById('uri-input').value.trim();
    if(type !== 'URI') uri = type;
    if(!tag || !uri){ alert('Tag and action required'); return; }
    fetch('/rfid/api/mappings', {method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({tag: tag, uri: uri})}).then(r=>{ if(r.ok) fetchMappings(); else r.json().then(()=>alert('Failed to save')); });
  });

  // search
  const searchInput = document.getElementById('search-input');
  searchInput.addEventListener('keyup', function(e){
    const q = this.value.trim();
    if(!q) return;
    fetch('/rfid/api/search?q='+encodeURIComponent(q)).then(r=>r.json()).then(j=>{
      // show simple results dialog
      const items = j.results || [];
      if(items.length === 0) return;
      const choice = items[0];
      // autofill uri input with first result
      document.getElementById('uri-input').value = choice.uri;
      M.updateTextFields();
      modal.open();
    });
  });

  // WebSocket for live updates
  try{
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    const ws = new WebSocket(proto+'://'+location.host+'/rfid/ws');
    ws.onmessage = function(ev){
      try{
        const obj = JSON.parse(ev.data);
        if(obj.event === 'tag_detected'){
          // Optionally notify user
          M.toast({html: 'Tag detected: '+obj.tag});
        }
      }catch(e){console.error(e)}
    }
  }catch(e){console.debug('WebSocket not available', e)}

  // init
  document.getElementById('uri-field').style.display = 'block';
  fetchMappings();
});
