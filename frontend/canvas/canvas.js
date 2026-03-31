window.generateId = () => {
  if (crypto.randomUUID) return crypto.randomUUID();
  return Math.random().toString(36).substring(2, 15);
};

class DrawingCanvas {
  constructor(containerId) {
    this.container = document.getElementById(containerId);
    this.onDraw = null;   // Triggers when a new element is created
    this.onUpdate = null; // Triggers when an element changes (move, resize, styling)
    this.onDelete = null; // Triggers when an element is removed
    this.onClear = null;

    this.elements = [];
    this.redoStack = [];
    
    // Tools
    this.currentTool = 'pen';
    this.currentStrokeColor = 'var(--text)';
    this.currentFillColor = 'transparent';
    this.currentStrokeWidth = 3;
    this.currentOpacity = 1;

    // Legacy aliases kept for compatibility with the rest of the app.
    this.color = this.currentStrokeColor;
    this.fillColor = this.currentFillColor;
    this.lineWidth = this.currentStrokeWidth;
    this.opacity = this.currentOpacity;

    // Interaction state
    this.isDrawing = false;
    this.isDragging = false;
    this.currentElement = null;
    this.selectedElement = null; // Array of selected items or single item ID
    
    // Pen tracking vars
    this.lastVelocity = 0;
    this.lastWidth = this.lineWidth;

    this._init();
  }

  _init() {
    const wrapper = document.createElement('div');
    wrapper.className = 'canvas-wrapper';

    this.canvas = document.createElement('canvas');
    this.canvas.id = 'drawCanvas';
    this.canvas.width = window.innerWidth > 1000 ? window.innerWidth - 300 : window.innerWidth;
    this.canvas.height = window.innerHeight - 80;
    this.ctx = this.canvas.getContext('2d');

    this.coordsEl = document.createElement('div');
    this.coordsEl.className = 'canvas-coords';
    this.coordsEl.textContent = '0, 0';

    this.renderLayer = document.createElement('div');
    this.renderLayer.className = 'canvas-render-layer';

    wrapper.appendChild(this.canvas);
    wrapper.appendChild(this.renderLayer);
    this.container.appendChild(wrapper);
    this.container.appendChild(this.coordsEl);

    this._bindEvents();
    
    // Initial draw to setup bg
    this.redraw();

    // Resize handler
    window.addEventListener('resize', () => {
      this.canvas.width = wrapper.clientWidth;
      this.canvas.height = wrapper.clientHeight;
      this.redraw();
    });
  }

  _bindEvents() {
    this.canvas.addEventListener('mousedown', (e) => this._onDown(e));
    this.canvas.addEventListener('mousemove', (e) => this._onMove(e));
    window.addEventListener('mouseup', (e) => this._onUp(e));
    this.canvas.addEventListener('dblclick', (e) => this._onDoubleClick(e));
    
    // Touch
    this.canvas.addEventListener('touchstart', (e) => {
      e.preventDefault();
      this._onDown(e.touches[0]);
    }, { passive: false });
    this.canvas.addEventListener('touchmove', (e) => {
      e.preventDefault();
      this._onMove(e.touches[0]);
    }, { passive: false });
    window.addEventListener('touchend', (e) => {
      this._onUp();
    });

    // Keyboard (Delete Selection)
    document.addEventListener('keydown', (e) => {
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
      if ((e.key === 'Delete' || e.key === 'Backspace') && this.selectedElement) {
        e.preventDefault();
        this.deleteElement(this.selectedElement);
      }
    });
  }

  _getPos(e) {
    const rect = this.canvas.getBoundingClientRect();
    return {
      x: (e.clientX - rect.left) * (this.canvas.width / rect.width),
      y: (e.clientY - rect.top) * (this.canvas.height / rect.height)
    };
  }

  _cloneElement(el) {
    return {
      ...el,
      points: el.points ? el.points.map(p => ({ ...p })) : undefined
    };
  }

  _normalizeElement(el) {
    const normalized = this._cloneElement(el);
    normalized.strokeColor = this._materializeColor(
      normalized.strokeColor || normalized.color || getComputedStyle(document.documentElement).getPropertyValue('--text').trim() || '#4A3728'
    );
    normalized.fillColor = normalized.fillColor !== undefined ? normalized.fillColor : (normalized.fill !== undefined ? normalized.fill : 'transparent');
    normalized.fillColor = normalized.fillColor === 'transparent' ? 'transparent' : this._materializeColor(normalized.fillColor, 'transparent');
    normalized.strokeWidth = normalized.strokeWidth !== undefined ? normalized.strokeWidth : 3;
    normalized.opacity = normalized.opacity !== undefined ? normalized.opacity : 1;
    if (normalized.type === 'sticky' && normalized.fillColor === 'transparent') {
      normalized.fillColor = this._materializeColor('var(--sticky-yellow)');
    }
    return normalized;
  }

  _getDefaultStrokeColor() {
    return this._materializeColor(this.currentStrokeColor);
  }

  _getDefaultFillColor() {
    if (this.currentFillColor === 'transparent') return 'transparent';
    return this._materializeColor(this.currentFillColor, 'transparent');
  }

  _getStrokeColor(el) {
    return el.strokeColor || el.color || this.currentStrokeColor;
  }

  _getFillColor(el) {
    return el.fillColor !== undefined ? el.fillColor : (el.fill !== undefined ? el.fill : 'transparent');
  }

  _resolveCanvasColor(value, fallback = this.currentStrokeColor) {
    if (!value) return fallback;
    if (value.startsWith('var(')) {
      const variableName = value.slice(4, -1).trim();
      return getComputedStyle(document.documentElement).getPropertyValue(variableName).trim() || fallback;
    }
    return value;
  }

  _materializeColor(value, fallback = this.currentStrokeColor) {
    if (!value) return fallback;
    if (value === 'transparent') return value;
    return this._resolveCanvasColor(value, fallback);
  }

  _getElementBounds(el) {
    if (el.type === 'pen') {
      let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
      (el.points || []).forEach(p => {
        if (p.x < minX) minX = p.x;
        if (p.y < minY) minY = p.y;
        if (p.x > maxX) maxX = p.x;
        if (p.y > maxY) maxY = p.y;
      });
      return { x: minX, y: minY, width: maxX - minX, height: maxY - minY };
    }

    if (el.type === 'line' || el.type === 'arrow') {
      const x = Math.min(el.x, el.x2);
      const y = Math.min(el.y, el.y2);
      return {
        x,
        y,
        width: Math.max(el.x, el.x2) - x,
        height: Math.max(el.y, el.y2) - y
      };
    }

    return {
      x: el.x,
      y: el.y,
      width: el.width,
      height: el.height
    };
  }

  _moveElement(el, dx, dy) {
    const moved = this._cloneElement(el);
    if (moved.x !== undefined) moved.x += dx;
    if (moved.y !== undefined) moved.y += dy;
    if (moved.x2 !== undefined) moved.x2 += dx;
    if (moved.y2 !== undefined) moved.y2 += dy;
    if (moved.points) {
      moved.points = moved.points.map(p => ({ x: p.x + dx, y: p.y + dy }));
    }
    return moved;
  }

  // Element Management
  setTool(tool) {
    this.currentTool = tool;
    this.selectedElement = null; // Deselect when switching tools
    this.updateCursor();
    this.redraw();
  }

  updateCursor() {
    const c = this.canvas;
    if (this.currentTool === 'select') c.style.cursor = 'default';
    else if (this.currentTool === 'pen') c.style.cursor = 'crosshair';
    else if (this.currentTool === 'text' || this.currentTool === 'sticky') c.style.cursor = 'text';
    else c.style.cursor = 'crosshair';
  }

  _onDown(e) {
    if (e.button !== 0 && e.type !== 'touchstart') return; // only left click
    const pos = this._getPos(e);
    
    if (this.currentTool === 'select') {
      // Find element to select/drag
      const hit = this._hitTest(pos);
      if (hit) {
        this.selectedElement = hit.id;
        this.isDragging = true;
        const bounds = this._getElementBounds(hit);
        this.dragOffset = {
          x: pos.x - bounds.x,
          y: pos.y - bounds.y
        };
        // Bring to front
        this.elements = [...this.elements.filter(el => el.id !== hit.id), this._cloneElement(hit)];
        if (this.onSelect) this.onSelect(hit);
      } else {
        this.selectedElement = null; // Clicked on empty space
        if (this.onSelect) this.onSelect(null);
      }
      this.redraw();
      return;
    }

    if (this.currentTool === 'text' || this.currentTool === 'sticky') {
      this._spawnTextInput(pos, this.currentTool);
      this.selectedElement = null; // deselect
      this.redraw();
      return;
    }

    // Start drawing a new element
    this.isDrawing = true;
    this.startPos = pos;
    this.lastWidth = this.lineWidth;
    this.lastVelocity = 0;
    
    const newEl = {
      id: generateId(),
      type: this.currentTool,
      strokeColor: this._getDefaultStrokeColor(),
      fillColor: this._getDefaultFillColor(),
      strokeWidth: this.currentStrokeWidth,
      opacity: this.currentOpacity,
    };

    if (this.currentTool === 'sticky' && newEl.fillColor === 'transparent') {
      newEl.fillColor = this._materializeColor('var(--sticky-yellow)');
    }

    if (this.currentTool === 'pen') {
      newEl.points = [pos];
    } else {
      newEl.x = pos.x;
      newEl.y = pos.y;
      newEl.width = 0;
      newEl.height = 0;
      if (this.currentTool === 'line' || this.currentTool === 'arrow') {
        newEl.x2 = pos.x;
        newEl.y2 = pos.y;
      }
    }

    this.currentElement = newEl;
  }

  _onMove(e) {
    const pos = this._getPos(e);
    this.coordsEl.textContent = `${Math.round(pos.x)}, ${Math.round(pos.y)}`;

    if (this.isDragging && this.selectedElement) {
      const el = this.elements.find(e => e.id === this.selectedElement);
      if (el) {
        const dx = pos.x - this.dragOffset.x - el.x;
        const dy = pos.y - this.dragOffset.y - el.y;

        this.elements = this.elements.map(item => (
          item.id === this.selectedElement ? this._moveElement(item, dx, dy) : item
        ));
        this.redraw();
      }
      return;
    }

    if (!this.isDrawing || !this.currentElement) return;

    if (this.currentTool === 'pen') {
      this.currentElement.points.push(pos);
    } else if (this.currentTool === 'line' || this.currentTool === 'arrow') {
      this.currentElement.x2 = pos.x;
      this.currentElement.y2 = pos.y;
    } else {
      this.currentElement.width = pos.x - this.startPos.x;
      this.currentElement.height = pos.y - this.startPos.y;
    }

    this.redraw();
    this._renderElement(this.currentElement); // draw active element on top
  }

  _onUp(e) {
    if (this.isDragging) {
      this.isDragging = false;
      const el = this.elements.find(el => el.id === this.selectedElement);
      if (el && this.onUpdate) this.onUpdate(el);
      return;
    }

    if (!this.isDrawing || !this.currentElement) return;
    this.isDrawing = false;

    // Validate if it's not too small (unless it's text/sticky which don't need drag)
    const el = this.currentElement;
    if (this._isValidElement(el)) {
      // Normalize rect/circle width/height
      if (el.width < 0) { el.x += el.width; el.width = Math.abs(el.width); }
      if (el.height < 0) { el.y += el.height; el.height = Math.abs(el.height); }

      this.elements = [...this.elements, this._normalizeElement(el)];
      this.redoStack = []; // clear future redo
      
      if (this.currentTool !== 'select') {
        this.selectedElement = el.id; // auto select after drawing
        if (this.onSelect) this.onSelect(el);
      }

      if (this.onDraw) this.onDraw(el);
    }

    this.currentElement = null;
    this.redraw();
  }

  _isValidElement(el) {
    if (el.type === 'pen') return el.points && el.points.length > 1;
    if (el.type === 'text' || el.type === 'sticky') return !!el.text;
    if (el.type === 'line' || el.type === 'arrow') {
      return Math.abs(el.x2 - el.x) > 2 || Math.abs(el.y2 - el.y) > 2;
    }
    return Math.abs(el.width) > 5 || Math.abs(el.height) > 5;
  }

  _hitTest(pos) {
    // Traverse backwards to pick top elements first
    for (let i = this.elements.length - 1; i >= 0; i--) {
      const el = this.elements[i];
      if (el.type === 'pen') {
        // Simple bounding box for pen
        let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
        el.points.forEach(p => {
          if (p.x < minX) minX = p.x; if (p.y < minY) minY = p.y;
          if (p.x > maxX) maxX = p.x; if (p.y > maxY) maxY = p.y;
        });
        if (pos.x >= minX - 5 && pos.x <= maxX + 5 && pos.y >= minY - 5 && pos.y <= maxY + 5) return el;
      } 
      else if (el.type === 'line' || el.type === 'arrow') {
        const minX = Math.min(el.x, el.x2) - 5;
        const maxX = Math.max(el.x, el.x2) + 5;
        const minY = Math.min(el.y, el.y2) - 5;
        const maxY = Math.max(el.y, el.y2) + 5;
        if (pos.x >= minX && pos.x <= maxX && pos.y >= minY && pos.y <= maxY) return el;
      }
      else {
        // Rect, circle, text, sticky
        if (pos.x >= el.x && pos.x <= el.x + el.width && pos.y >= el.y && pos.y <= el.y + el.height) {
          return el;
        }
      }
    }
    return null;
  }

  // -------------------------------------------------------------
  // Rendering
  // -------------------------------------------------------------
  
  redraw() {
    this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
    
    for (const el of this.elements) {
      this._renderElement(el);
    }

    if (this.selectedElement && this.currentTool === 'select') {
      const el = this.elements.find(e => e.id === this.selectedElement);
      if (el) this._drawSelectionBox(el);
    }
  }

  _onDoubleClick(e) {
    if (this.currentTool === 'select' && this.selectedElement) {
      const el = this.elements.find(x => x.id === this.selectedElement);
      if (el && (el.type === 'text' || el.type === 'sticky')) {
        this._spawnTextInput(el, el.type, true);
      }
    }
  }

  _spawnTextInput(posOrEl, type, isEdit = false) {
    const el = document.createElement('textarea');
    el.className = 'text-input-overlay';
    const originalText = isEdit ? (posOrEl.text || '') : '';
    
    // Position
    const rect = this.canvas.getBoundingClientRect();
    const x = isEdit ? posOrEl.x : posOrEl.x;
    const y = isEdit ? posOrEl.y : posOrEl.y;
    
    el.style.left = `${x}px`;
    el.style.top = `${y}px`;
    el.style.color = isEdit ? (posOrEl.strokeColor || posOrEl.color || this.currentStrokeColor) : this.currentStrokeColor;
    
    if (type === 'sticky') {
      el.style.width = isEdit ? `${posOrEl.width}px` : '150px';
      el.style.height = isEdit ? `${posOrEl.height}px` : '150px';
      el.style.background = isEdit
        ? (posOrEl.fillColor || posOrEl.fill || 'var(--sticky-yellow)')
        : (this.currentFillColor === 'transparent' ? 'var(--sticky-yellow)' : this.currentFillColor);
      el.style.padding = '12px';
      el.style.boxShadow = 'var(--shadow-md)';
      el.style.border = 'none';
      el.style.fontSize = '1.2rem';
    } else {
      el.style.minWidth = '100px';
      el.style.minHeight = '30px';
      el.style.fontSize = '1.5rem';
    }
    
    if (isEdit) {
      el.value = posOrEl.text || '';
    }

    this.renderLayer.style.pointerEvents = 'auto'; // allow clicking textarea
    this.renderLayer.appendChild(el);
    
    // Auto resize text
    if (type === 'text') {
      el.addEventListener('input', () => {
        el.style.height = 'auto';
        el.style.height = el.scrollHeight + 'px';
        el.style.width = 'auto';
        el.style.width = el.scrollWidth + 'px';
      });
    }

    // Delay focus slightly so double click doesn't blur
    setTimeout(() => {
      el.focus();
      if (isEdit) el.setSelectionRange(el.value.length, el.value.length);
    }, 10);

    el.addEventListener('blur', () => {
      const text = el.value.trim();
      if (text) {
        if (isEdit) {
          posOrEl.text = text;
          if (type === 'text') {
            posOrEl.width = el.offsetWidth;
            posOrEl.height = el.offsetHeight;
          }
          posOrEl.strokeColor = this._materializeColor(posOrEl.strokeColor || posOrEl.color || this.currentStrokeColor);
          if (posOrEl.fillColor && posOrEl.fillColor !== 'transparent') {
            posOrEl.fillColor = this._materializeColor(posOrEl.fillColor, 'transparent');
          }
          if (this.onUpdate) this.onUpdate(posOrEl);
        } else {
          const newEl = {
            id: generateId(),
            type,
            x, y,
            width: el.offsetWidth,
            height: el.offsetHeight,
            text,
            strokeColor: this._materializeColor(el.style.color),
            fillColor: type === 'sticky' ? this._materializeColor(el.style.background, 'transparent') : 'transparent',
            strokeWidth: this.currentStrokeWidth,
            opacity: this.currentOpacity
          };
          this.elements = [...this.elements, this._normalizeElement(newEl)];
          this.redoStack = [];
          if (this.currentTool !== 'select') {
            this.setTool('select');
            this.selectedElement = newEl.id;
          }
          if (this.onDraw) this.onDraw(newEl);
        }
      } else if (isEdit) {
        // Keep the element instead of deleting on empty blur to avoid accidental loss.
        posOrEl.text = originalText;
        if (this.onUpdate) this.onUpdate(posOrEl);
      }
      
      this.renderLayer.removeChild(el);
      this.renderLayer.style.pointerEvents = 'none';
      this.redraw();
    });
  }

  _renderElement(el) {
    this.ctx.beginPath();
    this.ctx.globalAlpha = el.opacity || 1;
    this.ctx.strokeStyle = this._resolveCanvasColor(this._getStrokeColor(el));
    const fillColor = this._getFillColor(el);
    this.ctx.fillStyle = fillColor === 'transparent' ? 'transparent' : this._resolveCanvasColor(fillColor, 'transparent');
    this.ctx.lineWidth = el.strokeWidth;
    this.ctx.lineCap = 'round';
    this.ctx.lineJoin = 'round';

    switch (el.type) {
      case 'pen':
        this._drawPen(el);
        break;
      case 'line':
        this._drawLine(el.x, el.y, el.x2, el.y2);
        break;
      case 'arrow':
        this._drawArrow(el.x, el.y, el.x2, el.y2, el.strokeWidth);
        break;
      case 'rect':
        this._drawRect(el.x, el.y, el.width, el.height);
        break;
      case 'circle':
        this._drawCircle(el.x, el.y, el.width, el.height);
        break;
      case 'text':
        this._drawText(el);
        break;
      case 'sticky':
        this._drawSticky(el);
        break;
    }
    this.ctx.globalAlpha = 1; // reset alpha
  }

  _drawPen(el) {
    const pts = el.points;
    if (!pts || pts.length < 2) return;
    
    this.ctx.beginPath();
    this.ctx.moveTo(pts[0].x, pts[0].y);
    for (let i = 1; i < pts.length - 1; i++) {
        const midX = (pts[i].x + pts[i + 1].x) / 2;
        const midY = (pts[i].y + pts[i + 1].y) / 2;
        this.ctx.quadraticCurveTo(pts[i].x, pts[i].y, midX, midY);
    }
    const last = pts[pts.length - 1];
    this.ctx.lineTo(last.x, last.y);
    this.ctx.stroke();
  }

  _drawRect(x, y, w, h) {
    // Emulate hand-drawn "cozy" rects with slight wobbly line
    this.ctx.beginPath();
    this.ctx.rect(x, y, w, h);
    if (this.ctx.fillStyle !== 'transparent') this.ctx.fill();
    this.ctx.stroke();
  }

  _drawCircle(x, y, w, h) {
    this.ctx.beginPath();
    this.ctx.ellipse(x + w/2, y + h/2, Math.abs(w/2), Math.abs(h/2), 0, 0, 2 * Math.PI);
    if (this.ctx.fillStyle !== 'transparent') this.ctx.fill();
    this.ctx.stroke();
  }

  _drawText(el) {
    this.ctx.fillStyle = this._resolveCanvasColor(this._getStrokeColor(el));
    this.ctx.font = "24px 'Caveat', cursive";
    this.ctx.textBaseline = 'top';
    const lines = (el.text || '').split('\n');
    lines.forEach((line, i) => {
      this.ctx.fillText(line, el.x + 2, el.y + 2 + (i * 24));
    });
  }

  _drawSticky(el) {
    // Fill background
    const fillColor = this._getFillColor(el) === 'transparent' ? 'var(--sticky-yellow)' : this._getFillColor(el);
    this.ctx.fillStyle = this._resolveCanvasColor(fillColor, '#F9E27D');
    this.ctx.shadowColor = 'rgba(0,0,0,0.1)';
    this.ctx.shadowBlur = 10;
    this.ctx.shadowOffsetY = 4;
    this.ctx.fillRect(el.x, el.y, el.width, el.height);
    
    // Reset shadow
    this.ctx.shadowColor = 'transparent';
    this.ctx.shadowBlur = 0;
    this.ctx.shadowOffsetY = 0;

    // Draw text
    this.ctx.fillStyle = this._resolveCanvasColor(this._getStrokeColor(el));
    this.ctx.font = "20px 'Caveat', cursive";
    this.ctx.textBaseline = 'top';
    const lines = (el.text || '').split('\n');
    lines.forEach((line, i) => {
      this.ctx.fillText(line, el.x + 12, el.y + 12 + (i * 20));
    });
  }

  _drawLine(x1, y1, x2, y2) {
    this.ctx.beginPath();
    this.ctx.moveTo(x1, y1);
    this.ctx.lineTo(x2, y2);
    this.ctx.stroke();
  }

  _drawArrow(x1, y1, x2, y2, strokeWidth) {
    this._drawLine(x1, y1, x2, y2);
    const angle = Math.atan2(y2 - y1, x2 - x1);
    const headLen = 15;
    this.ctx.beginPath();
    this.ctx.moveTo(x2, y2);
    this.ctx.lineTo(x2 - headLen * Math.cos(angle - Math.PI / 6), y2 - headLen * Math.sin(angle - Math.PI / 6));
    this.ctx.moveTo(x2, y2);
    this.ctx.lineTo(x2 - headLen * Math.cos(angle + Math.PI / 6), y2 - headLen * Math.sin(angle + Math.PI / 6));
    this.ctx.stroke();
  }

  _drawSelectionBox(el) {
    this.ctx.strokeStyle = '#c4886b'; // accent color
    this.ctx.lineWidth = 1;
    this.ctx.setLineDash([5, 5]);

    let x, y, w, h;
    
    if (el.type === 'pen') {
      let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
      el.points.forEach(p => {
        if (p.x < minX) minX = p.x; if (p.y < minY) minY = p.y;
        if (p.x > maxX) maxX = p.x; if (p.y > maxY) maxY = p.y;
      });
      x = minX; y = minY; w = maxX - minX; h = maxY - minY;
    } else if (el.type === 'line' || el.type === 'arrow') {
      x = Math.min(el.x, el.x2);
      y = Math.min(el.y, el.y2);
      w = Math.max(el.x, el.x2) - x;
      h = Math.max(el.y, el.y2) - y;
    } else {
      x = el.x; y = el.y; w = el.width; h = el.height;
    }
    
    this.ctx.strokeRect(x - 5, y - 5, w + 10, h + 10);
    this.ctx.setLineDash([]);
  }

  // -------------------------------------------------------------
  // Data Flow & Actions
  // -------------------------------------------------------------

  clear() {
    this.elements = [];
    this.redoStack = [];
    this.selectedElement = null;
    this.redraw();
    if (this.onSelect) this.onSelect(null);
    if (this.onClear) this.onClear();
  }

  undo() {
    if (this.elements.length === 0) return null;
    const removed = this.elements[this.elements.length - 1];
    this.elements = this.elements.slice(0, -1);
    this.redoStack.push(removed);
    this.selectedElement = null;
    if (this.onSelect) this.onSelect(null);
    this.redraw();
    return removed;
  }

  redo() {
    if (this.redoStack.length === 0) return null;
    const restored = this.redoStack.pop();
    this.elements = [...this.elements, restored];
    this.selectedElement = null;
    if (this.onSelect) this.onSelect(null);
    this.redraw();
    return restored;
  }

  deleteElement(id) {
    if (this.elements.some(e => e.id === id)) {
      this.elements = this.elements.filter(e => e.id !== id);
      this.selectedElement = null;
      if (this.onSelect) this.onSelect(null);
      this.redraw();
      if (this.onDelete) this.onDelete(id);
    }
  }

  // Called from tab/websocket sync
  drawFromRemote(el) {
    const normalized = this._normalizeElement(el);
    const idx = this.elements.findIndex(e => e.id === normalized.id);
    if (idx > -1) {
      this.elements = this.elements.map(e => e.id === normalized.id ? normalized : e);
    } else {
      this.elements = [...this.elements, normalized];
    }
    this.redraw();
  }

  deleteFromRemote(id) {
    this.elements = this.elements.filter(e => e.id !== id);
    if (this.selectedElement === id) this.selectedElement = null;
    this.redraw();
  }

  getStrokes() {
    return this.elements.map(el => this._cloneElement(el));
  }

  setStrokes(strokes) {
    this.elements = strokes.map(el => this._normalizeElement(el));
    this.selectedElement = null;
    this.redraw();
  }

  setColor(c) { 
    this.currentStrokeColor = c;
    this.color = c;
    this._updateSelectedStyle('strokeColor', c);
  }

  setLineWidth(w) { 
    this.currentStrokeWidth = w;
    this.lineWidth = w;
    this._updateSelectedStyle('strokeWidth', w);
  }

  setFillColor(c) {
    this.currentFillColor = c;
    this.fillColor = c;
    this._updateSelectedStyle('fillColor', c);
  }

  setOpacity(o) {
    this.currentOpacity = o;
    this.opacity = o;
    this._updateSelectedStyle('opacity', o);
  }

  _updateSelectedStyle(prop, val) {
    if (!this.selectedElement) return;

    const index = this.elements.findIndex(el => el.id === this.selectedElement);
    if (index < 0) return;

    const updated = this._cloneElement(this.elements[index]);
    if (prop === 'strokeColor') {
      updated.strokeColor = this._materializeColor(val);
    } else if (prop === 'fillColor') {
      updated.fillColor = val === 'transparent' ? 'transparent' : this._materializeColor(val, 'transparent');
    } else {
      updated[prop] = val;
    }

    this.elements = this.elements.map(el => el.id === updated.id ? updated : el);
    this.redraw();
    if (this.onUpdate) this.onUpdate(updated);
  }
}
