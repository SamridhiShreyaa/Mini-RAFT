class ClusterDashboard {
  constructor(containerId, gatewayUrl) {
    this.container = document.getElementById(containerId);
    this.gatewayUrl = gatewayUrl;
    this.refreshInterval = null;
    this.data = null;

    this._render();
  }

  _render() {
    this.container.innerHTML = `
      <div class="dashboard">
        <h2>
          <span class="refresh-dot"></span>
          Cluster Status
        </h2>
        <div id="dashboardContent">
          <div class="info-card">
            <div class="label">Status</div>
            <div class="value value-muted">Loading...</div>
          </div>
        </div>
      </div>
    `;
    this.content = document.getElementById('dashboardContent');
  }

  startAutoRefresh(intervalMs = 3000) {
    this.fetchStatus();
    this.refreshInterval = setInterval(() => this.fetchStatus(), intervalMs);
  }

  stopAutoRefresh() {
    if (this.refreshInterval) {
      clearInterval(this.refreshInterval);
      this.refreshInterval = null;
    }
  }

  async fetchStatus() {
    try {
      const res = await fetch(`${this.gatewayUrl}/cluster-status`, {
        signal: AbortSignal.timeout(5000)
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      this.data = await res.json();
      this.lastUpdated = new Date();
      this._updateUI();
    } catch (err) {
      this._showError(err.message);
    }
  }

  _updateUI() {
    if (!this.data) return;

    const leaderName = this._extractName(this.data.leader);
    const totalNodes = this.data.totalNodes || 0;
    const aliveCount = (this.data.replicas || []).filter(r => r.status === 'UP').length;

    const timeStr = this.lastUpdated
      ? this.lastUpdated.toLocaleTimeString()
      : '—';

    this.content.innerHTML = `
      <div class="info-card">
        <div class="label">Leader</div>
        <div class="value leader">${leaderName}</div>
      </div>
      <div class="info-card">
        <div class="label">Nodes Online</div>
        <div class="value">${aliveCount} / ${totalNodes}</div>
      </div>
      <div class="replica-list">
        <h3>Replicas</h3>
        ${this._renderReplicas()}
      </div>
      <div class="dashboard-updated-at">
        Updated ${timeStr}
      </div>
    `;
    if (window.lucide) window.lucide.createIcons();
  }

  _renderReplicas() {
    if (!this.data || !this.data.replicas) return '';

    return this.data.replicas.map(r => {
      const name = this._extractName(r.replica);
      const isDown = r.status !== 'UP';
      const role = isDown ? 'down' : (r.state || 'follower');
      const roleClass = role.toLowerCase();

      return `
        <div class="replica-item">
          <span class="replica-name"><i data-lucide="server" class="server-icon"></i> ${name}</span>
          <span class="replica-role ${roleClass}">${role}</span>
        </div>
      `;
    }).join('');
  }

  _extractName(url) {
    if (!url) return 'unknown';
    try {
      const u = new URL(url);
      return u.hostname;
    } catch {
      return url.replace(/https?:\/\//, '').split(':')[0];
    }
  }

  _showError(msg) {
    this.content.innerHTML = `
      <div class="info-card">
        <div class="label">Status</div>
        <div class="value value-muted">Offline</div>
      </div>
      <div class="dashboard-error">
        <i data-lucide="triangle-alert"></i> Could not reach gateway: ${msg}
      </div>
    `;
    if (window.lucide) window.lucide.createIcons();
  }

  destroy() {
    this.stopAutoRefresh();
  }
}
