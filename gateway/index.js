const http       = require('http');
const express    = require('express');
const axios      = require('axios');
const cors       = require('cors');
const { WebSocketServer, WebSocket } = require('ws');

const PORT = parseInt(process.env.PORT, 10) || 3000;

const REPLICAS = (
  process.env.REPLICAS ||
  'http://host.docker.internal:3001,http://host.docker.internal:3002,http://host.docker.internal:3003,http://host.docker.internal:3004,http://host.docker.internal:3005'
).split(',').map(r => r.trim()).filter(Boolean);

const POLL_INTERVAL_MS    = 2000;
const REQUEST_TIMEOUT_MS  = 1500;
const MAX_SEND_RETRIES    = 3;

let currentLeader  = null;
let currentTerm    = -1;
let clusterState   = [];
let failoverCount  = 0;

const app = express();
app.use(cors());
app.use(express.json());

const server = http.createServer(app);

const wss = new WebSocketServer({ server, path: '/ws' });
const wsClients = new Set();

wss.on('connection', (ws) => {
  wsClients.add(ws);
  log(`[WS] Client connected (total: ${wsClients.size})`);

  ws.send(JSON.stringify({
    type: 'leader_info',
    leader: currentLeader,
    term: currentTerm,
  }));

  ws.on('message', async (raw) => {
    let data;
    try {
      data = JSON.parse(raw);
    } catch {
      ws.send(JSON.stringify({ type: 'error', message: 'Invalid JSON' }));
      return;
    }

    const result = await forwardToLeader(data);

    if (result.success) {
      broadcastToClients(data, ws);
    } else {
      ws.send(JSON.stringify({ type: 'error', message: result.error }));
    }
  });

  ws.on('close', () => {
    wsClients.delete(ws);
    log(`[WS] Client disconnected (total: ${wsClients.size})`);
  });

  ws.on('error', () => {
    wsClients.delete(ws);
  });
});

function broadcastToClients(data, excludeWs = null) {
  const msg = JSON.stringify(data);
  for (const client of wsClients) {
    if (client !== excludeWs && client.readyState === WebSocket.OPEN) {
      try {
        client.send(msg);
      } catch { /* client gone */ }
    }
  }
}

async function discoverLeader() {
  const results = await Promise.allSettled(
    REPLICAS.map(async (replica) => {
      try {
        const res = await axios.get(`${replica}/state`, {
          timeout: REQUEST_TIMEOUT_MS,
        });
        return { replica, ...res.data };
      } catch (err) {
        return { replica, error: err.message };
      }
    })
  );

  const newClusterState = [];
  let foundLeader = null;
  let foundTerm   = -1;

  for (const r of results) {
    const val = r.status === 'fulfilled' ? r.value : { replica: '?', error: 'promise rejected' };
    newClusterState.push(val);

    if (val.state === 'leader') {
      foundLeader = val.replica;
      foundTerm   = val.term ?? foundTerm;
    }
  }

  clusterState = newClusterState;

  if (foundLeader && foundLeader !== currentLeader) {
    const wasFailover = currentLeader !== null;
    log(`[LEADER] ${wasFailover ? 'Changed' : 'Discovered'}: ${foundLeader} (term ${foundTerm})`);

    if (wasFailover) {
      failoverCount++;
      log(`[FAILOVER] #${failoverCount} ${currentLeader} -> ${foundLeader}`);

      broadcastToClients({
        type: 'leader_change',
        oldLeader: currentLeader,
        newLeader: foundLeader,
        term: foundTerm,
      });
    }

    currentLeader = foundLeader;
    currentTerm   = foundTerm;
  } else if (!foundLeader && currentLeader) {
    log('[WARNING] Leader lost! Cluster may be electing...');
    currentLeader = null;
  }

  return currentLeader;
}

let pollTimer = setInterval(discoverLeader, POLL_INTERVAL_MS);

discoverLeader().then(() => {
  log(`[INIT] Initial leader: ${currentLeader || 'none yet'}`);
});

async function forwardToLeader(data) {
  let attempts = MAX_SEND_RETRIES;
  let lastError = 'No leader available';

  while (attempts > 0) {
    if (!currentLeader) {
      log('[ROUTE] No leader cached, rediscovering...');
      await discoverLeader();
      if (!currentLeader) {
        attempts--;
        await sleep(500);
        continue;
      }
    }

    try {
      const endpoint = resolveEndpoint(data);
      log(`[ROUTE] Forwarding ${data.type || 'unknown'} -> ${currentLeader}${endpoint}`);

      const res = await axios.post(`${currentLeader}${endpoint}`, data, {
        timeout: REQUEST_TIMEOUT_MS,
      });

      return { success: true, data: res.data };
    } catch (err) {
      const status = err.response?.status;
      log(`[ERROR] Leader ${currentLeader} failed (${status || err.code || err.message}), rediscovering...`);

      currentLeader = null;
      await discoverLeader();
      attempts--;
      lastError = err.message;
    }
  }

  log(`[ERROR] All ${MAX_SEND_RETRIES} attempts exhausted: ${lastError}`);
  return { success: false, error: lastError };
}

function resolveEndpoint(data) {
  switch (data.type) {
    case 'draw':
    case 'update':
      return '/submit-stroke';
    case 'undo':
      return '/undo';
    case 'redo':
      return '/redo';
    case 'DELETE':
    case 'delete':
    case 'clear':
      return '/client_request';
    default:
      return '/client_request';
  }
}

app.get('/cluster-status', async (_req, res) => {
  await discoverLeader();

  const status = [];

  for (const replica of REPLICAS) {
    try {
      const r = await axios.get(`${replica}/status`, {
        timeout: REQUEST_TIMEOUT_MS,
      });
      status.push({ replica, status: 'UP', ...r.data });
    } catch {
      status.push({ replica, status: 'DOWN' });
    }
  }

  res.json({
    timestamp: new Date().toISOString(),
    leader: currentLeader,
    term: currentTerm,
    totalNodes: REPLICAS.length,
    failoverCount,
    wsClients: wsClients.size,
    replicas: status,
  });
});

app.get('/leader', async (_req, res) => {
  if (!currentLeader) await discoverLeader();

  res.json({
    leader: currentLeader,
    term: currentTerm,
    failoverCount,
  });
});

app.post('/send', async (req, res) => {
  const result = await forwardToLeader(req.body);

  if (result.success) {
    broadcastToClients(req.body);
    res.json({ success: true, message: 'Sent to leader' });
  } else {
    res.status(503).json({ success: false, error: result.error });
  }
});

app.get('/health', (_req, res) => {
  res.json({
    status: 'ok',
    leader: currentLeader,
    term: currentTerm,
    uptime: process.uptime(),
    wsClients: wsClients.size,
  });
});

function log(...args) {
  const ts = new Date().toISOString().slice(11, 23);
  console.log(`[${ts}]`, ...args);
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

server.listen(PORT, () => {
  log(`[INIT] Gateway running on :${PORT}`);
  log(`[INIT] Replicas: ${REPLICAS.join(', ')}`);
  log(`[INIT] WebSocket endpoint: ws://localhost:${PORT}/ws`);
});

process.on('SIGTERM', () => {
  log('[SHUTDOWN] Shutting down...');
  clearInterval(pollTimer);
  wss.close();
  server.close();
});

process.on('SIGINT', () => {
  log('[SHUTDOWN] Interrupted, shutting down...');
  clearInterval(pollTimer);
  wss.close();
  server.close();
  process.exit(0);
});