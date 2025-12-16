// State
let ws = null;
let wsReconnectTimer = null;
let waitingForScan = false;
let searchTimeout = null;

// WebSocket connection
function connectWebSocket() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${protocol}//${window.location.host}/rfid/ws`;
  
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
    if (waitingForScan) {
      // Modal is open and waiting for scan
      handleScannedTag(data.tag_id);
    } else {
      M.toast({html: `Tag scanned: ${data.tag_id}`, classes: 'blue'});
    }
    fetchMappings(); // Refresh table
  } else if (data.event === 'mappings_updated') {
    fetchMappings();
  }
}

// API calls
function fetchMappings() {
  fetch('/rfid/api/mappings')
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
    tbody.innerHTML = '<tr><td colspan="4" class="center grey-text">No mappings yet</td></tr>';
    updateSettings(map);
    return;
  }
  
  updateSettings(map);
  
  tags.forEach(tag => {
    const mapping = map[tag];
    const tr = document.createElement('tr');
    tr.className = 'mapping-row pointer';
    
    const tdTag = document.createElement('td');
    tdTag.textContent = tag;
    
    const tdDesc = document.createElement('td');
    tdDesc.textContent = mapping.description || '-';
    
    const tdUri = document.createElement('td');
    const uri = mapping.uri || mapping; // Support old format
    tdUri.innerHTML = `<code>${escapeHtml(formatAction(uri))}</code>`;
    
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
    tr.appendChild(tdDesc);
    tr.appendChild(tdUri);
    tr.appendChild(tdDel);
    
    tr.addEventListener('click', () => openEditModal(tag, mapping));
    tbody.appendChild(tr);
  });
}

function saveMapping(tag, uri, description) {
  fetch('/rfid/api/mappings', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({tag, uri, description})
  })
  .then(r => {
    if (r.ok) {
      M.toast({html: 'Mapping saved', classes: 'green'});
      fetchMappings();
      M.Modal.getInstance(document.getElementById('mapping-modal')).close();
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
  fetch(`/rfid/api/mappings/${encodeURIComponent(tag)}`, {method: 'DELETE'})
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

function searchLibrary(query, type) {
  const q = encodeURIComponent(query);
  fetch(`/rfid/api/search?q=${q}`)
    .then(r => r.json())
    .then(data => renderSearchResults(data.results || [], type))
    .catch(e => {
      console.error(e);
      M.toast({html: 'Search failed', classes: 'red'});
    });
}

function renderSearchResults(results, filterType) {
  const container = document.getElementById('search-results');
  container.innerHTML = '';
  
  if (!results || results.length === 0) {
    container.innerHTML = '<li class="collection-item grey-text">No results found</li>';
    return;
  }
  
  results.forEach(item => {
    const li = document.createElement('li');
    li.className = 'collection-item';
    
    const title = document.createElement('span');
    title.className = 'title';
    title.textContent = item.name || item.uri;
    
    li.appendChild(title);
    li.style.cursor = 'pointer';
    
    li.addEventListener('click', () => {
      document.getElementById('selected-uri').value = item.uri;
      document.querySelectorAll('#search-results .collection-item').forEach(el => el.classList.remove('active'));
      li.classList.add('active');
      document.getElementById('save-mapping').classList.remove('disabled');
    });
    
    container.appendChild(li);
  });
}

// Modal handlers
function openAddModal() {
  resetModal();
  document.getElementById('modal-title').textContent = 'Add Mapping';
  document.getElementById('tag-helper').textContent = 'Please scan a tag to continue';
  waitingForScan = true;
  M.Modal.getInstance(document.getElementById('mapping-modal')).open();
}

function openEditModal(tag, mapping) {
  resetModal();
  const uri = mapping.uri || mapping; // Support old format
  const description = mapping.description || '';
  
  document.getElementById('modal-title').textContent = 'Edit Mapping';
  document.getElementById('tag-input').value = tag;
  document.getElementById('description-input').value = description;
  document.getElementById('tag-input').removeAttribute('disabled');
  document.getElementById('tag-helper').textContent = '';
  waitingForScan = false;
  
  // Set action type
  if (['TOGGLE_PLAY', 'STOP'].includes(uri)) {
    document.getElementById('type-select').value = uri;
    document.getElementById('selected-uri').value = uri;
  } else if (uri.includes('spotify:track:')) {
    document.getElementById('type-select').value = 'track';
    document.getElementById('selected-uri').value = uri;
  } else if (uri.includes('spotify:album:') || uri.includes(':album:')) {
    document.getElementById('type-select').value = 'album';
    document.getElementById('selected-uri').value = uri;
  } else if (uri.includes('spotify:playlist:') || uri.includes(':playlist:')) {
    document.getElementById('type-select').value = 'playlist';
    document.getElementById('selected-uri').value = uri;
  } else {
    document.getElementById('type-select').value = 'track';
    document.getElementById('selected-uri').value = uri;
  }
  
  M.updateTextFields();
  M.FormSelect.init(document.querySelectorAll('select'));
  updateActionTypeUI();
  document.getElementById('save-mapping').classList.remove('disabled');
  M.Modal.getInstance(document.getElementById('mapping-modal')).open();
}

function resetModal() {
  document.getElementById('tag-input').value = '';
  document.getElementById('description-input').value = '';
  document.getElementById('type-select').value = '';
  document.getElementById('search-query').value = '';
  document.getElementById('selected-uri').value = '';
  document.getElementById('search-results').innerHTML = '';
  document.getElementById('search-field').style.display = 'none';
  document.getElementById('results-container').style.display = 'none';
  document.getElementById('save-mapping').classList.add('disabled');
  document.getElementById('tag-input').setAttribute('disabled', 'disabled');
  M.updateTextFields();
  M.FormSelect.init(document.querySelectorAll('select'));
}

function handleScannedTag(tagId) {
  document.getElementById('tag-input').value = tagId;
  document.getElementById('tag-input').removeAttribute('disabled');
  document.getElementById('tag-helper').textContent = 'Tag scanned successfully';
  waitingForScan = false;
  M.updateTextFields();
  M.toast({html: `Tag ${tagId} scanned`, classes: 'green'});
  
  // Check if tag already exists
  fetch('/rfid/api/mappings')
    .then(r => r.json())
    .then(mappings => {
      if (mappings[tagId]) {
        document.getElementById('tag-helper').textContent = 'Tag already exists - editing existing mapping';
        openEditModal(tagId, mappings[tagId]);
      }
    });
}

function updateActionTypeUI() {
  const type = document.getElementById('type-select').value;
  const searchField = document.getElementById('search-field');
  const resultsContainer = document.getElementById('results-container');
  const selectedUri = document.getElementById('selected-uri').value;
  
  if (['STOP', 'TOGGLE_PLAY'].includes(type)) {
    searchField.style.display = 'none';
    resultsContainer.style.display = 'none';
    document.getElementById('selected-uri').value = type;
    document.getElementById('save-mapping').classList.remove('disabled');
  } else if (type) {
    searchField.style.display = 'block';
    resultsContainer.style.display = 'block';
    if (!selectedUri || ['STOP', 'TOGGLE_PLAY'].includes(selectedUri)) {
      document.getElementById('selected-uri').value = '';
      document.getElementById('save-mapping').classList.add('disabled');
    }
  }
}

function formatAction(uri) {
  if (uri === 'STOP') return 'Stop Playback';
  if (uri === 'TOGGLE_PLAY') return 'Toggle Play/Pause';
  return uri;
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

// Settings functions
function updateSettings(mappings) {
  document.getElementById('total-mappings').textContent = Object.keys(mappings).length;
}

// Init
document.addEventListener('DOMContentLoaded', () => {
  // Init Materialize components
  M.Modal.init(document.querySelectorAll('.modal'));
  M.FormSelect.init(document.querySelectorAll('select'));
  M.Tabs.init(document.querySelectorAll('.tabs'));
  
  // Event listeners
  document.getElementById('open-add').addEventListener('click', openAddModal);
  
  document.getElementById('save-mapping').addEventListener('click', () => {
    const tag = document.getElementById('tag-input').value.trim();
    const uri = document.getElementById('selected-uri').value;
    const description = document.getElementById('description-input').value.trim();
    
    if (!tag || !uri) {
      M.toast({html: 'Tag and action required', classes: 'orange'});
      return;
    }
    
    saveMapping(tag, uri, description);
  });
  
  document.getElementById('type-select').addEventListener('change', updateActionTypeUI);
  
  document.getElementById('search-query').addEventListener('input', (e) => {
    clearTimeout(searchTimeout);
    const query = e.target.value.trim();
    const type = document.getElementById('type-select').value;
    
    if (query.length > 2) {
      searchTimeout = setTimeout(() => {
        searchLibrary(query, type);
      }, 300);
    } else {
      document.getElementById('search-results').innerHTML = '';
    }
  });
  
  // Settings tab event listeners
  document.getElementById('export-db').addEventListener('click', () => {
    fetch('/rfid/api/mappings')
      .then(r => r.json())
      .then(data => {
        const blob = new Blob([JSON.stringify(data, null, 2)], {type: 'application/json'});
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `rfid-mappings-${new Date().toISOString().split('T')[0]}.json`;
        a.click();
        URL.revokeObjectURL(url);
        M.toast({html: 'Mappings exported', classes: 'green'});
      });
  });
  
  document.getElementById('import-db').addEventListener('click', () => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = 'application/json';
    input.onchange = (e) => {
      const file = e.target.files[0];
      const reader = new FileReader();
      reader.onload = (ev) => {
        try {
          const data = JSON.parse(ev.target.result);
          // Import each mapping
          let count = 0;
          Object.keys(data).forEach(tag => {
            const mapping = data[tag];
            const uri = mapping.uri || mapping;
            const description = mapping.description || '';
            fetch('/rfid/api/mappings', {
              method: 'POST',
              headers: {'Content-Type': 'application/json'},
              body: JSON.stringify({tag, uri, description})
            }).then(() => {
              count++;
              if (count === Object.keys(data).length) {
                fetchMappings();
                M.toast({html: `${count} mappings imported`, classes: 'green'});
              }
            });
          });
        } catch (err) {
          M.toast({html: 'Invalid JSON file', classes: 'red'});
        }
      };
      reader.readAsText(file);
    };
    input.click();
  });
  
  // Initial load
  fetchMappings();
  connectWebSocket();
});
