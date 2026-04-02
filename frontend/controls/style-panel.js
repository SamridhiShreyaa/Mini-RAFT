class StylePanel {
  constructor(containerId) {
    this.container = document.getElementById(containerId);
    this.onStyleChange = null;
    
    // Default theme colors
    this.strokeColors = [
      '#4A3728',            // deep brown
      '#8B7355',            // muted brown
      '#C97070',            // red
      '#CCA855',            // orange
      '#7BAE7F',            // green
      '#7BA0C4',            // blue
      '#C4886B',            // accent
      '#ffffff'             // white
    ];

    this.fillColors = [
      'transparent',
      '#FFF3C4',
      '#FFE0E0',
      '#D4F0D4',
      '#D4E8F7',
      '#E8D4F0',
      '#FFE4CC',
      '#4A3728'
    ];

    this.state = {
      strokeColor: '#4A3728',
      fillColor: 'transparent',
      strokeWidth: 3,
      opacity: 1
    };

    this.strokePickerValue = '#4A3728';
    this.fillPickerValue = '#FFF3C4';

    this._render();
    this._bind();
  }

  _render() {
    this.container.innerHTML = `
      <div class="style-panel" id="stylePanelBody">
        <div class="style-section">
          <span class="style-label">Stroke</span>
          <div class="color-grid" id="strokeGrid">
            ${this.strokeColors.map((c) => `
              <div class="color-btn stroke-color ${c === this.state.strokeColor ? 'active' : ''}" 
                   style="background: ${c}" data-color="${c}"></div>
            `).join('')}
          </div>
          <div class="color-wheel-row">
            <label class="color-wheel-label" for="strokePicker">Custom</label>
            <input type="color" id="strokePicker" class="color-wheel" value="${this.strokePickerValue}" />
          </div>
        </div>

        <div class="style-section">
          <span class="style-label">Background</span>
          <div class="color-grid" id="fillGrid">
            ${this.fillColors.map((c) => `
              <div class="color-btn fill-color ${c === 'transparent' ? 'transparent' : ''} ${c === this.state.fillColor ? 'active' : ''}" 
                   style="${c !== 'transparent' ? `background: ${c}` : ''}" data-color="${c}"></div>
            `).join('')}
          </div>
          <div class="color-wheel-row">
            <label class="color-wheel-label" for="fillPicker">Custom</label>
            <input type="color" id="fillPicker" class="color-wheel" value="${this.fillPickerValue}" />
          </div>
        </div>

        <div class="style-section">
          <span class="style-label">Thickness</span>
          <div class="stroke-width-grid">
            <div class="stroke-btn width-btn" data-width="2"><div class="stroke-line thin"></div></div>
            <div class="stroke-btn width-btn active" data-width="4"><div class="stroke-line med"></div></div>
            <div class="stroke-btn width-btn" data-width="8"><div class="stroke-line bold"></div></div>
          </div>
        </div>

        <div class="style-section">
          <span class="style-label">Opacity</span>
          <input type="range" class="opacity-slider" id="opacitySlider" min="0.1" max="1" step="0.1" value="1" />
        </div>
      </div>
    `;

    this.panelBody = document.getElementById('stylePanelBody');
  }

  _bind() {
    this.container.querySelectorAll('.stroke-color').forEach(btn => {
      btn.addEventListener('click', () => {
        this._setActive('.stroke-color', null);
        btn.classList.add('active');
        this.state.strokeColor = btn.getAttribute('data-color');
        this._emit('strokeColor', this.state.strokeColor);
      });
    });

    document.getElementById('strokePicker').addEventListener('input', (e) => {
      this._setActive('.stroke-color', null);
      this.state.strokeColor = e.target.value;
      this.strokePickerValue = e.target.value;
      this._emit('strokeColor', this.state.strokeColor);
    });

    this.container.querySelectorAll('.fill-color').forEach(btn => {
      btn.addEventListener('click', () => {
        this._setActive('.fill-color', null);
        btn.classList.add('active');
        this.state.fillColor = btn.getAttribute('data-color');
        this._emit('fillColor', this.state.fillColor);
      });
    });

    document.getElementById('fillPicker').addEventListener('input', (e) => {
      this._setActive('.fill-color', null);
      this.state.fillColor = e.target.value;
      this.fillPickerValue = e.target.value;
      this._emit('fillColor', this.state.fillColor);
    });

    this.container.querySelectorAll('.width-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        this.container.querySelectorAll('.width-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        this.state.strokeWidth = parseInt(btn.getAttribute('data-width'));
        this._emit('strokeWidth', this.state.strokeWidth);
      });
    });

    document.getElementById('opacitySlider').addEventListener('input', (e) => {
      this.state.opacity = parseFloat(e.target.value);
      this._emit('opacity', this.state.opacity);
    });
  }

  _emit(key, value) {
    if (this.onStyleChange) {
      this.onStyleChange(key, value);
    }
  }

  _setActive(selector, activeValue) {
    this.container.querySelectorAll(selector).forEach((node) => {
      const shouldBeActive = activeValue !== null && node.getAttribute('data-color') === activeValue;
      node.classList.toggle('active', shouldBeActive);
    });
  }

  show() {
    this.panelBody.classList.remove('hidden');
  }

  hide() {
    this.panelBody.classList.add('hidden');
  }

  // Sync panel to currently selected element's styles
  syncWithElement(el) {
    if (!el) return;
    const strokeColor = el.strokeColor || el.color;
    const fillColor = el.fillColor || el.fill;
    const resolvedStrokeColor = this._resolveUiColor(strokeColor);
    const resolvedFillColor = this._resolveUiColor(fillColor);
    
    // Try to match colors, if they are custom hex will just unselect
    this._setActive('.stroke-color', strokeColor);
    this._setActive('.fill-color', fillColor);

    if (resolvedStrokeColor && resolvedStrokeColor.startsWith('#')) {
      this.strokePickerValue = resolvedStrokeColor;
      document.getElementById('strokePicker').value = resolvedStrokeColor;
    }

    if (resolvedFillColor && resolvedFillColor.startsWith('#')) {
      this.fillPickerValue = resolvedFillColor;
      document.getElementById('fillPicker').value = resolvedFillColor;
    }

    this.container.querySelectorAll('.width-btn').forEach(b => {
      b.classList.toggle('active', parseInt(b.getAttribute('data-width')) === el.strokeWidth);
    });

    document.getElementById('opacitySlider').value = el.opacity !== undefined ? el.opacity : 1;
  }

  _resolveUiColor(color) {
    if (!color || color === 'transparent') return color;
    if (!color.startsWith('var(')) return color;
    const variableName = color.slice(4, -1).trim();
    return getComputedStyle(document.documentElement).getPropertyValue(variableName).trim() || color;
  }
}
