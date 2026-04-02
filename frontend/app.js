const GATEWAY_URL = 'http://localhost:3000';

const canvas = new DrawingCanvas('canvasContainer');
const controls = new ControlsBar('controlsBar');
const stylePanel = new StylePanel('stylePanelContainer');
const dashboard = new ClusterDashboard('dashboardContainer', GATEWAY_URL);
const conn = createConnection(GATEWAY_URL, { enableWebSocket: false });
const tabSync = new TabSync();

const DELETE_EVENT_TYPES = new Set(['delete', 'DELETE']);

function saveStrokes() {
  try {
    localStorage.setItem('raft-strokes', JSON.stringify(canvas.getStrokes()));
  } catch (e) { /* storage full, ignore */ }
}

function loadStrokes() {
  try {
    const saved = localStorage.getItem('raft-strokes');
    if (saved) {
      const strokes = JSON.parse(saved);
      canvas.setStrokes(strokes);
    }
  } catch (e) { /* corrupt data, ignore */ }
}

// status pill
const statusPill = document.getElementById('connectionStatus');
function updateConnectionUI(connected) {
  const pill = statusPill;
  const label = pill.querySelector('span');

  if (connected) {
    pill.classList.add('connected');
    label.textContent = 'Connected';
  } else {
    pill.classList.remove('connected');
    label.textContent = 'Disconnected';
  }
}

// -------------------------------------------------------------
// Controls & Styles
// -------------------------------------------------------------

controls.onToolChange = (tool) => {
  canvas.setTool(tool);
  if (tool === 'select') {
    stylePanel.hide();
  } else {
    stylePanel.show();
  }
};

controls.onAction = (act) => {
  let changed = false;
  if (act === 'undo') {
    if (canvas.undo()) { conn.sendUndo(); changed = true; }
  } else if (act === 'redo') {
    if (canvas.redo()) { conn.sendRedo(); changed = true; }
  } else if (act === 'clear') {
    if (confirm('Clear the whole board?')) {
      canvas.clear();
      conn.sendClear();
      tabSync.broadcast({ type: 'clear' });
      changed = true;
    }
  }
  if (changed) saveStrokes();
};

const styleChangeHandlers = {
  strokeColor: (value) => canvas.setColor(value),
  fillColor: (value) => canvas.setFillColor(value),
  strokeWidth: (value) => canvas.setLineWidth(value),
  opacity: (value) => canvas.setOpacity(value)
};

stylePanel.onStyleChange = (key, value) => {
  const handler = styleChangeHandlers[key];
  if (handler) handler(value);
};

// -------------------------------------------------------------
// Canvas → Network
// -------------------------------------------------------------

canvas.onDraw = (el) => {
  conn.sendDraw(el);
  tabSync.broadcast({ type: 'draw', stroke: el });
  saveStrokes();
};

canvas.onUpdate = (el) => {
  conn.sendUpdate(el);
  tabSync.broadcast({ type: 'update', stroke: el });
  saveStrokes();
};

canvas.onSelect = (el) => {
  if (el) {
    stylePanel.syncWithElement(el);
    stylePanel.show();
  } else if (canvas.currentTool === 'select') {
    stylePanel.hide();
  }
};

canvas.onDelete = (id) => {
  conn.sendDelete(id);
  tabSync.broadcast({ type: 'DELETE', id });
  saveStrokes();
};

// -------------------------------------------------------------
// Network → Canvas
// -------------------------------------------------------------

conn.on('draw', (data) => {
  if (!data.stroke) return;
  canvas.drawFromRemote(data.stroke);
  saveStrokes();
});

conn.on('update', (data) => {
  if (!data.stroke) return;
  canvas.drawFromRemote(data.stroke); // overwrites via ID
  saveStrokes();
});

conn.on('delete', (data) => {
  if (!data.id) return;
  canvas.deleteFromRemote(data.id);
  saveStrokes();
});

conn.on('clear', () => {
  canvas.clear();
  saveStrokes();
});

conn.on('connection', () => {
  updateConnectionUI(conn.connected);
});

// -------------------------------------------------------------
// Tab Sync → Canvas
// -------------------------------------------------------------

tabSync.onReceive = (data) => {
  if (!data || !data.type) return;

  if (data.type === 'draw' && data.stroke) {
    canvas.drawFromRemote(data.stroke);
    saveStrokes();
  } else if (data.type === 'update' && data.stroke) {
    canvas.drawFromRemote(data.stroke);
    saveStrokes();
  } else if (DELETE_EVENT_TYPES.has(data.type) && data.id) {
    canvas.deleteFromRemote(data.id);
    saveStrokes();
  } else if (data.type === 'clear') {
    canvas.clear();
    saveStrokes();
  }
};

// -------------------------------------------------------------
// Initialization
// -------------------------------------------------------------

async function checkGatewayHealth() {
  try {
    const res = await fetch(`${GATEWAY_URL}/health`, {
      signal: AbortSignal.timeout(3000)
    });
    if (res.ok) {
      updateConnectionUI(true);
      return;
    }
  } catch (e) { /* unreachable */ }
  updateConnectionUI(false);
}

loadStrokes();
conn.connect();
dashboard.startAutoRefresh(3000);
checkGatewayHealth();
setInterval(checkGatewayHealth, 5000);
