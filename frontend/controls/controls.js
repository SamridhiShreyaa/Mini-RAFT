class ControlsBar {
  constructor(containerId) {
    this.container = document.getElementById(containerId);
    this.onToolChange = null;
    this.onAction = null;
    this.activeTool = 'pen';
    this._render();
    this._bind();
  }

  _render() {
    this.container.innerHTML = `
      <div class="controls-bar">
        <button class="btn" id="btnSelect" data-tool="select" title="Select (V)"><i data-lucide="mouse-pointer-2"></i></button>
        <div class="separator"></div>
        <button class="btn active" id="btnPen" data-tool="pen" title="Pen (P)"><i data-lucide="pen-tool"></i></button>
        <button class="btn" id="btnLine" data-tool="line" title="Line (L)"><i data-lucide="minus"></i></button>
        <button class="btn" id="btnArrow" data-tool="arrow" title="Arrow (A)"><i data-lucide="arrow-up-right"></i></button>
        <button class="btn" id="btnRect" data-tool="rect" title="Rectangle (R)"><i data-lucide="square"></i></button>
        <button class="btn" id="btnCircle" data-tool="circle" title="Circle (C)"><i data-lucide="circle"></i></button>
        <div class="separator"></div>
        <button class="btn" id="btnText" data-tool="text" title="Text (T)"><i data-lucide="type"></i></button>
        <button class="btn" id="btnSticky" data-tool="sticky" title="Sticky Note (S)"><i data-lucide="sticky-note"></i></button>
        <div class="separator"></div>
        <button class="btn" id="btnUndo" title="Undo (Ctrl+Z)"><i data-lucide="corner-up-left"></i></button>
        <button class="btn" id="btnRedo" title="Redo (Ctrl+Y)"><i data-lucide="corner-up-right"></i></button>
        <button class="btn danger" id="btnClear" title="Clear All"><i data-lucide="trash-2"></i></button>
      </div>
    `;
    this.toolButtons = this.container.querySelectorAll('[data-tool]');
    if (window.lucide) window.lucide.createIcons();
  }

  _bind() {
    this.toolButtons.forEach(btn => {
      btn.addEventListener('click', () => {
        const tool = btn.getAttribute('data-tool');
        this.setTool(tool);
        if (this.onToolChange) this.onToolChange(tool);
      });
    });

    document.getElementById('btnUndo').addEventListener('click', () => {
      this._pulse(document.getElementById('btnUndo'));
      if (this.onAction) this.onAction('undo');
    });

    document.getElementById('btnRedo').addEventListener('click', () => {
      this._pulse(document.getElementById('btnRedo'));
      if (this.onAction) this.onAction('redo');
    });

    document.getElementById('btnClear').addEventListener('click', () => {
      if (this.onAction) this.onAction('clear');
    });

    document.addEventListener('keydown', (e) => {
      // Don't trigger if typing in input/textarea
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
      if (e.ctrlKey || e.metaKey) return; // Allow app.js to handle keyboard shortcuts for undo/redo

      const keyMap = {
        'v': 'select', 'p': 'pen', 'l': 'line', 'a': 'arrow',
        'r': 'rect', 'c': 'circle', 't': 'text', 's': 'sticky'
      };

      const tool = keyMap[e.key.toLowerCase()];
      if (tool) {
        this.setTool(tool);
        if (this.onToolChange) this.onToolChange(tool);
      }
    });
  }

  setTool(tool) {
    this.activeTool = tool;
    this.toolButtons.forEach(btn => {
      if (btn.getAttribute('data-tool') === tool) {
        btn.classList.add('active');
      } else {
        btn.classList.remove('active');
      }
    });
  }

  _pulse(btn) {
    btn.style.borderColor = 'var(--accent)';
    btn.style.background = 'var(--accent-glow)';
    setTimeout(() => {
      btn.style.borderColor = '';
      btn.style.background = '';
    }, 200);
  }
}
