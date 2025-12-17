// State
let ws = null;
let wsReconnectTimer = null;
let waitingForScan = false;
let searchTimeout = null;
let scanPollTimer = null;

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
      // Tag scanned while not in add mode - highlight and show edit option
      M.toast({html: `Tag ${data.tag_id} scanned`, classes: 'blue'});
      highlightAndEditTag(data.tag_id);
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
    tbody.innerHTML = '<tr><td colspan="5" class="center grey-text">No mappings yet</td></tr>';
    updateSettings(map);
    return;
  }
  
  updateSettings(map);
  
  tags.forEach(tag => {
    const mapping = map[tag];
    const tr = document.createElement('tr');
    tr.className = 'mapping-row';
    tr.setAttribute('data-tag', tag);
    
    const tdTag = document.createElement('td');
    tdTag.textContent = tag;
    
    const tdDesc = document.createElement('td');
    tdDesc.textContent = mapping.description || '-';
    
    const tdUri = document.createElement('td');
    const uri = mapping.uri || mapping; // Support old format
    tdUri.innerHTML = `<code>${escapeHtml(formatAction(uri))}</code>`;
    
    const tdActions = document.createElement('td');
    tdActions.style.whiteSpace = 'nowrap';
    
    const editBtn = document.createElement('a');
    editBtn.className = 'waves-effect waves-light btn-small blue';
    editBtn.innerHTML = '<i class="material-icons">edit</i>';
    editBtn.style.marginRight = '5px';
    editBtn.addEventListener('click', (ev) => {
      ev.stopPropagation();
      openEditModal(tag, mapping);
    });
    
    const delBtn = document.createElement('a');
    delBtn.className = 'waves-effect waves-light btn-small red';
    delBtn.innerHTML = '<i class="material-icons">delete</i>';
    delBtn.addEventListener('click', (ev) => {
      ev.stopPropagation();
      if (confirm(`Delete mapping for tag ${tag}?`)) {
        deleteMapping(tag);
      }
    });
    
    tdActions.appendChild(editBtn);
    tdActions.appendChild(delBtn);
    
    tr.appendChild(tdTag);
    tr.appendChild(tdDesc);
    tr.appendChild(tdUri);
    tr.appendChild(tdActions);
    
    tbody.appendChild(tr);
  });
}

function highlightAndEditTag(tagId) {
  // Remove previous highlights
  document.querySelectorAll('.mapping-row').forEach(row => {
    row.classList.remove('teal', 'lighten-3');
  });
  
  // Find and highlight the row with this tag
  const row = document.querySelector(`.mapping-row[data-tag="${tagId}"]`);
  if (row) {
    row.classList.add('teal', 'lighten-3');
    row.scrollIntoView({ behavior: 'smooth', block: 'center' });
    
    // Show a toast with edit option
    setTimeout(() => {
      const editBtn = row.querySelector('.btn-small.blue');
      if (editBtn) {
        editBtn.classList.add('pulse');
        setTimeout(() => editBtn.classList.remove('pulse'), 2000);
      }
    }, 300);
  }
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

let allItems = [];
let filteredItems = [];

function loadItemsByType(type) {
  const container = document.getElementById('items-list');
  const loader = document.getElementById('loading-indicator');
  
  container.innerHTML = '';
  loader.style.display = 'block';
  
  console.log('Loading items of type:', type);
  
  fetch(`/rfid/api/browse?type=${type}`)
    .then(r => r.json())
    .then(data => {
      loader.style.display = 'none';
      allItems = data.items || [];
      filteredItems = allItems;
      console.log('Loaded items:', allItems.length);
      renderItems(filteredItems);
    })
    .catch(e => {
      loader.style.display = 'none';
      console.error('Browse error:', e);
      M.toast({html: 'Failed to load items', classes: 'red'});
    });
}

function renderItems(items) {
  const container = document.getElementById('items-list');
  container.innerHTML = '';
  
  if (!items || items.length === 0) {
    container.innerHTML = '<tr><td colspan="2" class="grey-text center-align">No items found</td></tr>';
    return;
  }
  
  items.forEach(item => {
    const tr = document.createElement('tr');
    tr.style.cursor = 'pointer';
    
    const tdName = document.createElement('td');
    tdName.textContent = item.name || item.uri;
    
    const tdSource = document.createElement('td');
    tdSource.textContent = item.source || 'unknown';
    tdSource.className = 'grey-text';
    
    tr.appendChild(tdName);
    tr.appendChild(tdSource);
    
    tr.addEventListener('click', () => {
      document.getElementById('selected-uri').value = item.uri;
      document.querySelectorAll('#items-list tr').forEach(el => el.classList.remove('teal', 'lighten-5'));
      tr.classList.add('teal', 'lighten-5');
      document.getElementById('save-mapping').classList.remove('disabled');
    });
    
    container.appendChild(tr);
  });
}

function filterItems(query) {
  if (!query) {
    filteredItems = allItems;
  } else {
    const lowerQuery = query.toLowerCase();
    filteredItems = allItems.filter(item => 
      (item.name || '').toLowerCase().includes(lowerQuery)
    );
  }
  renderItems(filteredItems);
}

// Modal handlers
function openAddModal() {
  resetModal();
  document.getElementById('modal-title').textContent = 'Add Mapping';
  document.getElementById('tag-helper').textContent = 'Please scan a tag to continue';
  waitingForScan = true;
  startScanPolling();
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
  document.getElementById('filter-query').value = '';
  document.getElementById('selected-uri').value = '';
  document.getElementById('items-list').innerHTML = '';
  document.getElementById('items-container').style.display = 'none';
  document.getElementById('save-mapping').classList.add('disabled');
  document.getElementById('tag-input').setAttribute('disabled', 'disabled');
  allItems = [];
  filteredItems = [];
  M.updateTextFields();
  M.FormSelect.init(document.querySelectorAll('select'));
}

function startScanPolling() {
  stopScanPolling();
  scanPollTimer = setInterval(() => {
    if (!waitingForScan) return;
    fetch('/rfid/api/last-scan')
      .then(r => r.json())
      .then(data => {
        if (data && data.tag_id) {
          handleScannedTag(String(data.tag_id));
        }
      })
      .catch(() => {});
  }, 1000);
}

function stopScanPolling() {
  if (scanPollTimer) {
    clearInterval(scanPollTimer);
    scanPollTimer = null;
  }
}

function handleScannedTag(tagId) {
  document.getElementById('tag-input').value = tagId;
  document.getElementById('tag-input').removeAttribute('disabled');
  document.getElementById('tag-helper').textContent = 'Tag scanned successfully';
  waitingForScan = false;
  stopScanPolling();
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
  const itemsContainer = document.getElementById('items-container');
  const selectedUri = document.getElementById('selected-uri').value;
  
  if (['STOP', 'TOGGLE_PLAY'].includes(type)) {
    itemsContainer.style.display = 'none';
    document.getElementById('selected-uri').value = type;
    document.getElementById('save-mapping').classList.remove('disabled');
  } else if (type) {
    itemsContainer.style.display = 'block';
    document.getElementById('filter-query').value = '';
    if (!selectedUri || ['STOP', 'TOGGLE_PLAY'].includes(selectedUri)) {
      document.getElementById('selected-uri').value = '';
      document.getElementById('save-mapping').classList.add('disabled');
    }
    // Load items for this type
    loadItemsByType(type);
  } else {
    itemsContainer.style.display = 'none';
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
  const modalElems = document.querySelectorAll('.modal');
  M.Modal.init(modalElems, {
    onCloseEnd: () => {
      waitingForScan = false;
      stopScanPolling();
    }
  });
  M.FormSelect.init(document.querySelectorAll('select'));
  const tabs = M.Tabs.init(document.querySelectorAll('.tabs'), {
    onShow: (tab) => {
      // Show FAB only on mappings tab
      const fab = document.querySelector('.fixed-action-btn');
      if (tab.id === 'mappings-tab') {
        fab.style.display = 'block';
      } else {
        fab.style.display = 'none';
      }
    }
  });
  
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
  
  document.getElementById('filter-query').addEventListener('input', (e) => {
    const query = e.target.value.trim();
    filterItems(query);
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
