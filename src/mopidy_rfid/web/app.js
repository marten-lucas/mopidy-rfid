// State
let ws = null;
let wsReconnectTimer = null;
let waitingForScan = false;
let searchTimeout = null;
let scanPollTimer = null;
let currentSoundKey = null;

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

// Robust toast helper: use M.toast when available, else fallback to a simple DOM toast
function showToast(html, classes = '') {
  try {
    if (window.M && M.toast) {
      M.toast({html, classes});
      return;
    }
  } catch (e) {
    // fall back
  }

  // Fallback custom toast
  try {
    let container = document.getElementById('custom-toast-container');
    if (!container) {
      container = document.createElement('div');
      container.id = 'custom-toast-container';
      Object.assign(container.style, {
        position: 'fixed',
        top: '16px',
        right: '16px',
        zIndex: '2147483647',
        display: 'flex',
        flexDirection: 'column',
        gap: '8px',
        pointerEvents: 'none'
      });
      // append directly to <body> to avoid modal scoping
      (document.body || document.documentElement).appendChild(container);
    }
    const el = document.createElement('div');
    el.className = 'custom-toast ' + classes;
    el.textContent = typeof html === 'string' ? html : JSON.stringify(html);
    Object.assign(el.style, {
      background: '#323232',
      color: 'white',
      padding: '10px 14px',
      borderRadius: '4px',
      boxShadow: '0 2px 6px rgba(0,0,0,0.2)',
      opacity: '0',
      transition: 'opacity 0.25s ease',
      pointerEvents: 'auto'
    });
    container.appendChild(el);
    // Force reflow
    void el.offsetWidth;
    el.style.opacity = '1';
    setTimeout(() => {
      el.style.opacity = '0';
      setTimeout(() => {
        try { container.removeChild(el); } catch (e) {}
      }, 300);
    }, 3500);
  } catch (e) {
    console.log('Toast:', html);
  }
}

function handleWebSocketMessage(data) {
  if (data.event === 'tag_scanned') {
    const tagId = String(data.tag_id);
    const action = data.action;
    // Always show toast so user sees scans even outside the add-modal
    let actionLabel = '';
    if (action) {
      if (action === 'play') actionLabel = ' — Play';
      else if (action === 'toggle') actionLabel = ' — Toggle Play/Pause';
      else if (action === 'stop') actionLabel = ' — Stop';
      else actionLabel = ` — ${action}`;
    }
    showToast(`Tag ${tagId} scanned${actionLabel}`, 'green');

    // Check if add modal is open
    const modal = M.Modal.getInstance(document.getElementById('mapping-modal'));
    const isModalOpen = modal && modal.isOpen;

    if (waitingForScan || isModalOpen) {
      // Modal is open or we're waiting for a scan - handle the tag
      handleScannedTag(tagId, action);
    } else {
      // Check if auto-add mode is enabled and tag is unknown
      const autoAddEnabled = document.getElementById('auto-add-checkbox')?.checked;
      if (autoAddEnabled) {
        // Check if tag exists in mappings
        fetch('/rfid/api/mappings')
          .then(r => r.json())
          .then(mappings => {
            if (!mappings[tagId]) {
              showToast(`Unknown tag detected - opening add form`, 'blue');
              openAddModal();
              // Immediately set the tag
              setTimeout(() => {
                document.getElementById('tag-input').value = tagId;
                document.getElementById('tag-input').removeAttribute('disabled');
                document.getElementById('tag-helper').textContent = 'Tag scanned successfully';
                waitingForScan = false;
                stopScanPolling();
                M.updateTextFields();
              }, 100);
            }
          });
      }
    }
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
  const scanNext = document.getElementById('scan-next-checkbox').checked;
  fetch('/rfid/api/mappings', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({tag, uri, description})
  })
  .then(r => {
    if (!r.ok) {
      throw new Error('Save failed');
    }
    // Close modal and refresh mappings before parsing JSON
    try {
      const modal = M.Modal.getInstance(document.getElementById('mapping-modal'));
      if (modal) modal.close();
    } catch (e) {}
    fetchMappings();
    // attempt to parse JSON if present
    return r.json ? r.json() : Promise.resolve({});
  })
  .then(() => {
    M.toast({html:'Saved', classes:'green'});
    if (scanNext) {
      document.getElementById('tag-input').value='';
      waitingForScan = true;
      startScanPolling();
      // Re-open modal for next tag
      setTimeout(() => openAddModal(), 100);
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
let itemsLoaded = false;

function loadItemsByType(type) {
  const container = document.getElementById('items-list');
  const loader = document.getElementById('loading-indicator');
  const loadBtn = document.getElementById('load-items-btn');
  
  container.innerHTML = '';
  loader.style.display = 'block';
  loadBtn.style.display = 'none';
  itemsLoaded = false;
  
  console.log('Loading items of type:', type);
  
  fetch(`/rfid/api/browse?type=${type}`)
    .then(r => r.json())
    .then(data => {
      loader.style.display = 'none';
      allItems = data.items || [];
      filteredItems = allItems;
      itemsLoaded = true;
      console.log('Loaded items:', allItems.length);
      renderItems(filteredItems);
    })
    .catch(e => {
      loader.style.display = 'none';
      loadBtn.style.display = 'block';
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
  const tagInput = document.getElementById('tag-input');
  tagInput.value = '';
  tagInput.setAttribute('placeholder', 'Scan a tag...');
  tagInput.setAttribute('disabled', 'disabled');
  tagInput.setAttribute('readonly', 'readonly');
  document.getElementById('tag-helper').textContent = 'Please scan a tag to continue';
  waitingForScan = true;
  startScanPolling();
  M.updateTextFields();
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
  document.getElementById('tag-input').removeAttribute('readonly');
  document.getElementById('tag-helper').textContent = '';
  document.getElementById('scan-next-checkbox').checked = false;
  waitingForScan = false;
  stopScanPolling();
  
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
  document.getElementById('paste-uri-input').value = '';
  document.getElementById('paste-mode-toggle').checked = false;
  document.getElementById('paste-uri-field').style.display = 'none';
  document.getElementById('items-list').innerHTML = '';
  document.getElementById('items-container').style.display = 'none';
  document.getElementById('save-mapping').classList.add('disabled');
  document.getElementById('tag-input').setAttribute('disabled', 'disabled');
  document.getElementById('scan-next-checkbox').checked = true;
  allItems = [];
  filteredItems = [];
  itemsLoaded = false;
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

function handleScannedTag(tagId, action) {
  document.getElementById('tag-input').value = tagId;
  document.getElementById('tag-input').removeAttribute('disabled');
  document.getElementById('tag-helper').textContent = 'Tag scanned successfully';
  
  // Don't stop scanning when modal is open - allow rescanning
  const modal = M.Modal.getInstance(document.getElementById('mapping-modal'));
  if (!modal || !modal.isOpen) {
    waitingForScan = false;
    stopScanPolling();
  }
  
  M.updateTextFields();
  
  // Check if tag already exists
  fetch('/rfid/api/mappings')
    .then(r => r.json())
    .then(mappings => {
      if (mappings[tagId]) {
        document.getElementById('tag-helper').textContent = 'Tag already exists - editing existing mapping';
        // Only open edit modal if we're not already in the add modal
        const modalTitle = document.getElementById('modal-title').textContent;
        if (modalTitle !== 'Add Mapping') {
          openEditModal(tagId, mappings[tagId]);
        } else {
          // Show warning in add modal that tag exists
          document.getElementById('tag-helper').textContent = 'Warning: Tag already exists! Saving will overwrite.';
          document.getElementById('tag-helper').style.color = '#ff9800';
        }
      } else {
        document.getElementById('tag-helper').textContent = 'Tag scanned successfully';
        document.getElementById('tag-helper').style.color = '';
      }
    });
}

function updateActionTypeUI() {
  const type = document.getElementById('type-select').value;
  const itemsContainer = document.getElementById('items-container');
  const selectedUri = document.getElementById('selected-uri').value;
  const pasteMode = document.getElementById('paste-mode-toggle').checked;
  
  if (pasteMode) {
    itemsContainer.style.display = 'none';
    return;
  }
  
  if (type) {
    itemsContainer.style.display = 'block';
    document.getElementById('filter-query').value = '';
    if (!selectedUri || ['STOP', 'TOGGLE_PLAY'].includes(selectedUri)) {
      document.getElementById('selected-uri').value = '';
      document.getElementById('save-mapping').classList.add('disabled');
    }
    // Show load button instead of auto-loading
    const loadBtn = document.getElementById('load-items-btn');
    const loader = document.getElementById('loading-indicator');
    if (!itemsLoaded) {
      loadBtn.style.display = 'block';
      loader.style.display = 'none';
      document.getElementById('items-list').innerHTML = '<tr><td colspan="2" class="center grey-text">Click "Load Items" to browse</td></tr>';
    }
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

// Sounds functions
function loadSounds() {
  fetch('/rfid/api/sounds').then(r=>r.json()).then(data=>{
    document.getElementById('sound-welcome-uri').textContent = data.welcome || '-';
    document.getElementById('sound-farewell-uri').textContent = data.farewell || '-';
    document.getElementById('sound-detected-uri').textContent = data.detected || '-';
  }).catch(()=>{});
}

function openSoundsModal(key) {
  currentSoundKey = key;
  document.getElementById('sounds-type-select').value = 'track';
  M.FormSelect.init(document.querySelectorAll('select'));
  // Load initial items
  loadSoundsItems('track');
  M.Modal.getInstance(document.getElementById('sounds-modal')).open();
}

function loadSoundsItems(type) {
  const tbody = document.getElementById('sounds-items-list');
  tbody.innerHTML = '<tr><td colspan="2" class="center">Loading...</td></tr>';
  fetch(`/rfid/api/browse?type=${type}`).then(r=>r.json()).then(data=>{
    const items = data.items || [];
    tbody.innerHTML = '';
    items.forEach(item=>{
      const tr = document.createElement('tr');
      tr.style.cursor = 'pointer';
      const tdName = document.createElement('td'); tdName.textContent = item.name || item.uri;
      const tdSource = document.createElement('td'); tdSource.textContent = item.source || 'unknown'; tdSource.className='grey-text';
      tr.appendChild(tdName); tr.appendChild(tdSource);
      tr.addEventListener('click', ()=>{
        // save selection
        fetch('/rfid/api/sounds', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({key: currentSoundKey, uri: item.uri})})
          .then(r=>{ if(r.ok){ M.toast({html:'Sound saved', classes:'green'}); loadSounds(); M.Modal.getInstance(document.getElementById('sounds-modal')).close(); } else { M.toast({html:'Save failed', classes:'red'});} });
      });
      tbody.appendChild(tr);
    });
  }).catch(()=>{
    tbody.innerHTML = '<tr><td colspan="2" class="center red-text">Failed to load items</td></tr>';
  });
}

// LED settings
function loadLedSettings() {
  fetch('/rfid/api/led-settings').then(r=>r.json()).then(data=>{
    document.getElementById('led-welcome').checked = !!data.welcome;
    document.getElementById('led-farewell').checked = !!data.farewell;
    document.getElementById('led-remaining').checked = !!data.remaining;
  }).catch(()=>{});
}

function saveLedSettings() {
  const pairs = [
    {key:'welcome', value: document.getElementById('led-welcome').checked},
    {key:'farewell', value: document.getElementById('led-farewell').checked},
    {key:'remaining', value: document.getElementById('led-remaining').checked},
  ];
  Promise.all(pairs.map(p=> fetch('/rfid/api/led-settings', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(p)})))
    .then(()=> M.toast({html:'LED settings saved', classes:'green'}))
    .catch(()=> M.toast({html:'Save failed', classes:'red'}));
}

// Status functions
function loadStatus() {
  fetch('/rfid/api/status').then(r=>r.json()).then(data=>{
    const el = document.getElementById('rfid-status');
    if (!el) return;
    const val = data.reader || 'unknown';
    el.textContent = val;
    el.className = '';
    if (val === 'available') el.classList.add('green-text');
    else if (val === 'unavailable') el.classList.add('red-text');
    else el.classList.add('grey-text');
  }).catch(()=>{
    const el = document.getElementById('rfid-status');
    if (el) { el.textContent = 'unknown'; el.className = 'grey-text'; }
  });
}

// Init
document.addEventListener('DOMContentLoaded', () => {
  // Init Materialize components
  const modalElems = document.querySelectorAll('.modal');
  M.Modal.init(modalElems, {
    onCloseEnd: () => {
      waitingForScan = false;
      stopScanPolling();
      document.getElementById('tag-input').value='';
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
  
  // Paste mode toggle
  document.getElementById('paste-mode-toggle').addEventListener('change', (e) => {
    const pasteField = document.getElementById('paste-uri-field');
    const typeSelect = document.getElementById('type-select');
    const itemsContainer = document.getElementById('items-container');
    
    if (e.target.checked) {
      pasteField.style.display = 'block';
      itemsContainer.style.display = 'none';
      typeSelect.disabled = true;
    } else {
      pasteField.style.display = 'none';
      typeSelect.disabled = false;
      updateActionTypeUI();
    }
    M.updateTextFields();
  });
  
  // Paste URI input
  document.getElementById('paste-uri-input').addEventListener('input', (e) => {
    const uri = e.target.value.trim();
    document.getElementById('selected-uri').value = uri;
    if (uri) {
      document.getElementById('save-mapping').classList.remove('disabled');
    } else {
      document.getElementById('save-mapping').classList.add('disabled');
    }
  });
  
  // Load items button
  document.getElementById('load-items-btn').addEventListener('click', () => {
    const type = document.getElementById('type-select').value;
    if (type) {
      loadItemsByType(type);
    }
  });
  
  // Common action buttons
  document.querySelectorAll('.common-action-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      const action = e.target.getAttribute('data-action');
      document.getElementById('selected-uri').value = action;
      document.getElementById('save-mapping').classList.remove('disabled');
      // Highlight the selected button
      document.querySelectorAll('.common-action-btn').forEach(b => b.classList.remove('teal'));
      e.target.classList.add('teal');
      M.toast({html: `Selected: ${action}`, classes: 'blue'});
    });
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
  
  // Sounds modal listeners
  M.Modal.init(document.querySelectorAll('#sounds-modal'));
  M.FormSelect.init(document.querySelectorAll('#sounds-type-select'));
  loadSounds();
  document.getElementById('btn-sel-welcome').addEventListener('click', ()=>openSoundsModal('welcome'));
  document.getElementById('btn-sel-farewell').addEventListener('click', ()=>openSoundsModal('farewell'));
  document.getElementById('btn-sel-detected').addEventListener('click', ()=>openSoundsModal('detected'));
  document.getElementById('sounds-type-select').addEventListener('change', (e)=> loadSoundsItems(e.target.value));
  
  // LED settings
  loadLedSettings();
  document.getElementById('led-save').addEventListener('click', saveLedSettings);
  
  // Status
  loadStatus();
  setInterval(loadStatus, 10000);
  
  // Initial load
  fetchMappings();
  connectWebSocket();
});
