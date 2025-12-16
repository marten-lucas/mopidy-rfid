// WebSocket connection
let ws = null;
let wsReconnectTimer = null;

function connectWebSocket() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${protocol}//${window.location.host}/ws`;
  
  ws = new WebSocket(wsUrl);
  
  ws.onopen = () => {
    console.log('WebSocket connected');
    updateStatus(true);
    if (wsReconnectTimer) {
      clearTimeout(wsReconnectTimer);
      wsReconnectTimer = null;
    }
  };
  
  ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    handleWebSocketMessage(data);
  };
  
  ws.onclose = () => {
    console.log('WebSocket disconnected');
    updateStatus(false);
    // Reconnect after 3 seconds
    wsReconnectTimer = setTimeout(connectWebSocket, 3000);
  };
  
  ws.onerror = (error) => {
    console.error('WebSocket error:', error);
  };
}

function updateStatus(connected) {
  const badge = document.getElementById('status-badge');
  const text = document.getElementById('status-text');
  const icon = badge.querySelector('i');
  
  badge.classList.remove('hide');
  if (connected) {
    text.textContent = 'Connected';
    icon.style.color = '#4caf50';
  } else {
    text.textContent = 'Disconnected';
    icon.style.color = '#f44336';
  }
}

function handleWebSocketMessage(data) {
  if (data.event === 'tag_scanned') {
    M.toast({html: `Tag scanned: ${data.tag_id}`, classes: 'blue'});
    fetchMappings(); // Refresh table
  } else if (data.event === 'mappings_updated') {
    fetchMappings();
  }
}

// API calls
function fetchMappings() {
  fetch('/api/mappings')
    .then(r => r.json())
    .then(renderMappings)
    .catch(e => {
      console.error('Failed to fetch mappings:', e);
      M.toast({html: 'Failed to load mappings', classes: 'red'});
    });
}

function renderMappings(map) {
  const tbody = document.getElementById('mappings-tbody');
  tbody.innerHTML = '';
  
  const tags = Object.keys(map);
  if (tags.length === 0) {
    tbody.innerHTML = '<tr><td colspan="3" class="center grey-text">No mappings yet</td></tr>';
    return;
  }
  
  tags.forEach(tag => {
    const tr = document.createElement('tr');
    tr.className = 'mapping-row';
    
    const tdTag = document.createElement('td');
    tdTag.textContent = tag;
    tdTag.className = 'pointer';
    
    const tdUri = document.createElement('td');
    tdUri.innerHTML = `<code>${escapeHtml(map[tag])}</code>`;
    
    const tdDel = document.createElement('td');
    const delBtn = document.createElement('a');
    delBtn.className = 'waves-effect waves-light btn-small red';
    delBtn.innerHTML = '<i class="material-icons">delete</i>';
    delBtn.addEventListener('click', (ev) => {
      ev.stopPropagation();
      if (confirm(`Delete mapping for tag ${tag}?`)) {
        deleteMapping(tag);
      }
    });
    tdDel.appendChild(delBtn);
    
    tr.appendChild(tdTag);
    tr.appendChild(tdUri);
    tr.appendChild(tdDel);
    
    tr.addEventListener('click', () => openEditModal(tag, map[tag]));
    tbody.appendChild(tr);
  });
}

function saveMapping(tag, uri) {
  fetch('/api/mappings', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({tag, uri})
  })
  .then(r => {
    if (r.ok) {
      M.toast({html: 'Mapping saved', classes: 'green'});
      fetchMappings();
    } else {
      throw new Error('Save failed');
    }
  })
  .catch(e => {
    console.error(e);
    M.toast({html: 'Failed to save mapping', classes: 'red'});
  });
}

function deleteMapping(tag) {
  fetch(`/api/mappings/${encodeURIComponent(tag)}`, {method: 'DELETE'})
    .then(r => {
      if (r.ok) {
        M.toast({html: 'Mapping deleted', classes: 'green'});
        fetchMappings();
      } else {
        throw new Error('Delete failed');
      }
    })
    .catch(e => {
      console.error(e);
      M.toast({html: 'Failed to delete mapping', classes: 'red'});
    });
}

function searchLibrary(query) {
  fetch(`/api/library/search?q=${encodeURIComponent(query)}`)
    .then(r => r.json())
    .then(renderSearchResults)
    .catch(e => {
      console.error(e);
      M.toast({html: 'Search failed', classes: 'red'});
    });
}

function renderSearchResults(results) {
  const container = document.getElementById('search-results');
  container.innerHTML = '';
  
  if (!results || results.length === 0) {
    container.innerHTML = '<p class="grey-text">No results found</p>';
    return;
  }
  
  const collection = document.createElement('ul');
  collection.className = 'collection';
  
  results.forEach(item => {
    const li = document.createElement('li');
    li.className = 'collection-item avatar';
    
    const icon = document.createElement('i');
    icon.className = 'material-icons circle';
    icon.textContent = item.type === 'track' ? 'music_note' : 
                      item.type === 'album' ? 'album' : 'queue_music';
    
    const title = document.createElement('span');
    title.className = 'title';
    title.textContent = item.name;
    
    const subtitle = document.createElement('p');
    subtitle.textContent = `${item.type} • ${item.artists || item.artist || ''}`;
    
    li.appendChild(icon);
    li.appendChild(title);
    li.appendChild(subtitle);
    
    li.style.cursor = 'pointer';
    li.addEventListener('click', () => {
      document.getElementById('uri-input').value = item.uri;
      M.updateTextFields();
      M.Modal.getInstance(document.getElementById('library-modal')).close();
    });
    
    collection.appendChild(li);
  });
  
  container.appendChild(collection);
}

// Modal handlers
function openAddModal() {
  document.getElementById('modal-title').textContent = 'Add Mapping';
  document.getElementById('tag-input').value = '';
  document.getElementById('uri-input').value = '';
  document.getElementById('type-select').value = 'URI';
  M.updateTextFields();
  M.FormSelect.init(document.querySelectorAll('select'));
  updateUriFieldVisibility();
  M.Modal.getInstance(document.getElementById('mapping-modal')).open();
}

function openEditModal(tag, uri) {
  document.getElementById('modal-title').textContent = 'Edit Mapping';
  document.getElementById('tag-input').value = tag;
  
  if (['TOGGLE_PLAY', 'STOP'].includes(uri)) {
    document.getElementById('type-select').value = uri;
    document.getElementById('uri-input').value = '';
  } else {
    document.getElementById('type-select').value = 'URI';
    document.getElementById('uri-input').value = uri;
  }
  
  M.updateTextFields();
  M.FormSelect.init(document.querySelectorAll('select'));
  updateUriFieldVisibility();
  M.Modal.getInstance(document.getElementById('mapping-modal')).open();
}

function updateUriFieldVisibility() {
  const type = document.getElementById('type-select').value;
  const field = document.getElementById('uri-field');
  field.style.display = type === 'URI' ? 'block' : 'none';
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

// Init
document.addEventListener('DOMContentLoaded', () => {
  // Init Materialize components
  M.Modal.init(document.querySelectorAll('.modal'));
  M.FormSelect.init(document.querySelectorAll('select'));
  
  // Event listeners
  document.getElementById('open-add').addEventListener('click', openAddModal);
  
  document.getElementById('save-mapping').addEventListener('click', () => {
    const tag = document.getElementById('tag-input').value.trim();
    const type = document.getElementById('type-select').value;
    let uri = type === 'URI' ? document.getElementById('uri-input').value.trim() : type;
    
    if (!tag || !uri) {
      M.toast({html: 'Tag and action required', classes: 'orange'});
      return;
    }
    
    saveMapping(tag, uri);
  });
  
  document.getElementById('type-select').addEventListener('change', updateUriFieldVisibility);
  
  document.getElementById('open-library-search').addEventListener('click', (e) => {
    e.preventDefault();
    M.Modal.getInstance(document.getElementById('library-modal')).open();
  });
  
  document.getElementById('search-input').addEventListener('keypress', (e) => {
    if (e.key === 'Enter') {
      const query = e.target.value.trim();
      if (query) searchLibrary(query);
    }
  });
  
  // Initial load
  fetchMappings();
  connectWebSocket();
});
