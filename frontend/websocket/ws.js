class RaftSocket {
  constructor(gatewayUrl) {
    this.url = gatewayUrl;
    this.ws = null;
    this.connected = false;
    this.reconnectTimer = null;
    this.reconnectDelay = 1000;
    this.maxDelay = 8000;
    this.onMessage = null;
    this.onStatusChange = null;
    this.messageQueue = [];
    this.attempts = 0;
    this.maxAttempts = 20;
  }

  connect() {
    try {
      this.ws = new WebSocket(this.url);
    } catch (e) {
      console.warn('WebSocket connection failed, using HTTP fallback');
      this._setStatus(false);
      this._scheduleReconnect();
      return;
    }

    this.ws.onopen = () => {
      console.log('ws connected');
      this._setStatus(true);
      this.reconnectDelay = 1000;

      while (this.messageQueue.length > 0) {
        const msg = this.messageQueue.shift();
        this._doSend(msg);
      }
    };

    this.ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (this.onMessage) this.onMessage(data);
      } catch (e) {
        console.warn('bad ws message', e);
      }
    };

    this.ws.onclose = () => {
      this._setStatus(false);
      this._scheduleReconnect();
    };

    this.ws.onerror = () => {
      this._setStatus(false);
    };
  }

  send(data) {
    const msg = JSON.stringify(data);
    if (this.connected && this.ws && this.ws.readyState === WebSocket.OPEN) {
      this._doSend(msg);
    } else {
      this.messageQueue.push(msg);
    }
  }

  _doSend(msg) {
    try {
      this.ws.send(msg);
    } catch (e) {
      console.warn('send failed', e);
      this.messageQueue.push(msg);
    }
  }

  _setStatus(connected) {
    this.connected = connected;
    if (this.onStatusChange) this.onStatusChange(connected);
  }

  _scheduleReconnect() {
    if (this.reconnectTimer) return;
    this.attempts++;

    if (this.attempts > this.maxAttempts) {
      console.warn('max reconnect attempts reached');
      return;
    }

    console.log(`reconnecting in ${this.reconnectDelay}ms (attempt ${this.attempts})`);

    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.connect();
      this.reconnectDelay = Math.min(this.reconnectDelay * 1.5, this.maxDelay);
    }, this.reconnectDelay);
  }

  disconnect() {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.ws) {
      this.ws.onclose = null;
      this.ws.close();
    }
    this._setStatus(false);
  }
}

class HttpBridge {
  constructor(baseUrl) {
    this.baseUrl = baseUrl;
    this.onMessage = null;
    this.onStatusChange = null;
    this.connected = false;
    this.pollTimer = null;
  }

  connect() {
    this._setStatus(true);
    this._startPolling();
  }

  send(data) {
    fetch(`${this.baseUrl}/send`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    }).catch(err => console.warn('http send failed', err));
  }

  _startPolling() {
    // poll isn't really needed for draw events in http mode
    // but we keep it for cluster status which is separate
    this._setStatus(true);
  }

  _setStatus(connected) {
    this.connected = connected;
    if (this.onStatusChange) this.onStatusChange(connected);
  }

  disconnect() {
    if (this.pollTimer) clearInterval(this.pollTimer);
    this._setStatus(false);
  }
}

function createConnection(gatewayUrl, options = {}) {
  const wsUrl = gatewayUrl.replace(/^http/, 'ws') + '/ws';
  const enableWebSocket = options.enableWebSocket === true;

  const socket = new RaftSocket(wsUrl);
  const http = new HttpBridge(gatewayUrl);

  const conn = {
    socket,
    http,
    handlers: {},

    on(type, handler) {
      if (!this.handlers[type]) this.handlers[type] = [];
      this.handlers[type].push(handler);
    },

    emit(type, data) {
      const h = this.handlers[type];
      if (h) h.forEach(fn => fn(data));
    },

    send(data) {
      if (enableWebSocket && socket.connected) {
        socket.send(data);
      } else {
        http.send(data);
      }
    },

    sendDraw(stroke) {
      this.send({ type: 'draw', stroke });
    },

    sendUpdate(stroke) {
      this.send({ type: 'update', stroke });
    },

    sendDelete(id) {
      this.send({ type: 'DELETE', id });
    },

    sendClear() {
      this.send({ type: 'clear' });
    },

    sendUndo() {
      this.send({ type: 'undo' });
    },

    sendRedo() {
      this.send({ type: 'redo' });
    },

    get connected() {
      return (enableWebSocket && socket.connected) || http.connected;
    }
  };

  socket.onMessage = (data) => {
    if (!data.type) return;
    const normalizedType = data.type === 'DELETE' ? 'delete' : data.type;
    conn.emit(normalizedType, data);
  };

  socket.onStatusChange = (status) => {
    conn.emit('connection', { connected: status });
  };

  http.onStatusChange = (status) => {
    conn.emit('connection', { connected: status });
  };

  conn.connect = () => {
    if (enableWebSocket) socket.connect();
    http.connect();
  };

  conn.disconnect = () => {
    if (enableWebSocket) socket.disconnect();
    http.disconnect();
  };

  return conn;
}

class TabSync {
  constructor() {
    this.channel = null;
    this.onReceive = null;
    try {
      this.channel = new BroadcastChannel('raft-draw-sync');
      this.channel.onmessage = (e) => {
        if (this.onReceive) this.onReceive(e.data);
      };
    } catch (e) {
      console.warn('BroadcastChannel not supported');
    }
  }

  broadcast(data) {
    if (this.channel) {
      try {
        this.channel.postMessage(data);
      } catch (e) { /* ignore */ }
    }
  }

  close() {
    if (this.channel) this.channel.close();
  }
}
