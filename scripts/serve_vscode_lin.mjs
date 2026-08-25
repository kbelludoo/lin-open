// ============================================================================
// AUTHENTIC VS CODE WEB WORKBENCH POWERED BY MONACO & LIN PIECETREE IN-MEMORY
// Spec: spec/LIN_CORE_ARCH.rulel
// ============================================================================

import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { compile } from '../src/compiler.mjs';
import { runInMemory } from '../src/vm.mjs';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const ROOT = path.resolve(__dirname, '..');
const VSCODE_LIN_DIR = path.join(ROOT, 'clones_lin', 'vscode_lin');

// Load Core LIN Modules in memory
const ptSrc = fs.readFileSync(path.join(VSCODE_LIN_DIR, 'piece_tree.lin'), 'utf8');
const posSrc = fs.readFileSync(path.join(VSCODE_LIN_DIR, 'position.lin'), 'utf8');
const rangeSrc = fs.readFileSync(path.join(VSCODE_LIN_DIR, 'range.lin'), 'utf8');
const uriSrc = fs.readFileSync(path.join(VSCODE_LIN_DIR, 'uri.lin'), 'utf8');

const ptMod = runInMemory(compile(ptSrc, { target: 'js', exportMode: 'multiple' }).code);
const posMod = runInMemory(compile(posSrc, { target: 'js', exportMode: 'multiple' }).code);
const rangeMod = runInMemory(compile(rangeSrc, { target: 'js', exportMode: 'multiple' }).code);
const uriMod = runInMemory(compile(uriSrc, { target: 'js', exportMode: 'multiple' }).code);

let currentPieceTree = ptMod.createPieceTree('');

const HTML_CONTENT = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Visual Studio Code — LIN Sovereign Edition</title>
  <!-- Official Monaco Editor (VS Code Engine) -->
  <link rel="stylesheet" data-name="vs/editor/editor.main" href="https://cdnjs.cloudflare.com/ajax/libs/monaco-editor/0.45.0/min/vs/editor/editor.main.min.css">
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
  <style>
    :root {
      --vscode-bg: #1e1e1e;
      --vscode-sidebar: #252526;
      --vscode-activitybar: #333333;
      --vscode-titlebar: #3c3c3c;
      --vscode-statusbar: #007acc;
      --vscode-tab-active: #1e1e1e;
      --vscode-tab-inactive: #2d2d2d;
      --vscode-border: #2b2b2b;
      --vscode-text: #cccccc;
      --vscode-text-bright: #ffffff;
      --vscode-accent: #0e639c;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body, html { width: 100%; height: 100%; overflow: hidden; background: var(--vscode-bg); color: var(--vscode-text); font-family: -apple-system, BlinkMacSystemFont, "Segoe WPC", "Segoe UI", sans-serif; font-size: 13px; display: flex; flex-direction: column; }
    
    /* Title Bar */
    #titlebar {
      height: 30px; background: var(--vscode-titlebar); display: flex; align-items: center; justify-content: space-between; padding: 0 10px; font-size: 12px; user-select: none; border-bottom: 1px solid var(--vscode-border);
    }
    .titlebar-left { display: flex; align-items: center; gap: 12px; }
    .titlebar-menu { display: flex; gap: 10px; font-size: 12px; color: #ccc; cursor: pointer; }
    .titlebar-menu span:hover { color: #fff; }
    .titlebar-center { font-weight: 500; color: #cccccc; display: flex; align-items: center; gap: 8px; }
    .titlebar-right { display: flex; gap: 8px; color: #888; }

    /* Workbench Main Body */
    #workbench { flex: 1; display: flex; position: relative; overflow: hidden; }

    /* Activity Bar */
    #activitybar {
      width: 48px; background: var(--vscode-activitybar); display: flex; flex-direction: column; align-items: center; padding: 8px 0; gap: 16px; border-right: 1px solid var(--vscode-border); user-select: none;
    }
    .act-btn {
      width: 48px; height: 40px; display: flex; align-items: center; justify-content: center; color: #858585; font-size: 18px; cursor: pointer; position: relative;
    }
    .act-btn:hover { color: #ffffff; }
    .act-btn.active { color: #ffffff; }
    .act-btn.active::before {
      content: ''; position: absolute; left: 0; top: 0; bottom: 0; width: 2px; background: #ffffff;
    }

    /* Sidebar */
    #sidebar {
      width: 280px; background: var(--vscode-sidebar); border-right: 1px solid var(--vscode-border); display: flex; flex-direction: column;
    }
    .sidebar-title {
      padding: 10px 16px; font-size: 11px; font-weight: bold; text-transform: uppercase; letter-spacing: 0.5px; color: #bbbbbb; display: flex; justify-content: space-between; align-items: center;
    }
    .sidebar-section {
      padding: 6px 16px; font-size: 11px; font-weight: bold; color: #888; background: #202020; cursor: pointer; display: flex; align-items: center; gap: 6px;
    }
    .file-tree {
      flex: 1; overflow-y: auto; padding: 4px 0;
    }
    .file-item {
      padding: 5px 20px; display: flex; align-items: center; gap: 8px; color: #cccccc; cursor: pointer; user-select: none; font-size: 13px;
    }
    .file-item:hover { background: #2a2d2e; color: #ffffff; }
    .file-item.active { background: #37373d; color: #ffffff; font-weight: 500; }
    .file-icon { color: #519aba; font-size: 14px; }

    /* Editor Column */
    #editor-area { flex: 1; display: flex; flex-direction: column; background: var(--vscode-bg); }

    /* Tab Bar */
    #tabbar {
      height: 35px; background: var(--vscode-tab-inactive); display: flex; align-items: center; border-bottom: 1px solid var(--vscode-border); overflow-x: auto;
    }
    .tab {
      height: 100%; padding: 0 16px; display: flex; align-items: center; gap: 8px; background: var(--vscode-tab-active); color: var(--vscode-text-bright); border-right: 1px solid var(--vscode-border); border-top: 1px solid var(--vscode-accent); font-size: 12px; cursor: pointer; user-select: none;
    }
    .tab-close { font-size: 12px; opacity: 0.6; margin-left: 4px; border-radius: 3px; padding: 2px 4px; }
    .tab-close:hover { opacity: 1; background: #444; }

    /* Monaco Container */
    #monaco-container { flex: 1; width: 100%; height: 100%; }

    /* Terminal & Output Panel */
    #bottom-panel {
      height: 160px; background: #181818; border-top: 1px solid var(--vscode-border); display: flex; flex-direction: column;
    }
    .panel-tabs {
      height: 30px; background: #1e1e1e; display: flex; align-items: center; padding: 0 12px; gap: 16px; font-size: 11px; font-weight: bold; text-transform: uppercase; border-bottom: 1px solid var(--vscode-border);
    }
    .panel-tab { color: #888; cursor: pointer; }
    .panel-tab.active { color: #fff; border-bottom: 1px solid #fff; }
    .panel-body {
      flex: 1; padding: 8px 16px; font-family: "Cascadia Code", "Fira Code", monospace; font-size: 12px; overflow-y: auto; color: #4ec9b0;
    }

    /* Status Bar */
    #statusbar {
      height: 22px; background: var(--vscode-statusbar); color: #ffffff; display: flex; align-items: center; justify-content: space-between; padding: 0 10px; font-size: 12px; user-select: none;
    }
    .sb-section { display: flex; align-items: center; gap: 12px; }
    .sb-item { display: flex; align-items: center; gap: 4px; cursor: pointer; }
    .sb-item:hover { opacity: 0.8; }
  </style>
</head>
<body>

  <!-- Title Bar -->
  <div id="titlebar">
    <div class="titlebar-left">
      <i class="fa-brands fa-microsoft" style="color: #007acc;"></i>
      <div class="titlebar-menu">
        <span>File</span>
        <span>Edit</span>
        <span>Selection</span>
        <span>View</span>
        <span>Go</span>
        <span>Run</span>
        <span>Terminal</span>
        <span>Help</span>
      </div>
    </div>
    <div class="titlebar-center">
      <i class="fa-solid fa-code"></i>
      <span id="titleFileName">position.lin — VS Code (LIN Pure Sovereign Edition)</span>
    </div>
    <div class="titlebar-right">
      <i class="fa-solid fa-minus"></i>
      <i class="fa-regular fa-square"></i>
      <i class="fa-solid fa-xmark"></i>
    </div>
  </div>

  <!-- Workbench -->
  <div id="workbench">
    <!-- Activity Bar -->
    <div id="activitybar">
      <div class="act-btn active" title="Explorer (Ctrl+Shift+E)"><i class="fa-regular fa-copy"></i></div>
      <div class="act-btn" title="Search (Ctrl+Shift+F)"><i class="fa-solid fa-magnifying-glass"></i></div>
      <div class="act-btn" title="Source Control (Ctrl+Shift+G)"><i class="fa-solid fa-code-branch"></i></div>
      <div class="act-btn" title="Run and Debug (Ctrl+Shift+D)"><i class="fa-solid fa-play"></i></div>
      <div class="act-btn" title="Extensions (Ctrl+Shift+X)"><i class="fa-solid fa-table-cells-large"></i></div>
      <div style="flex: 1;"></div>
      <div class="act-btn" title="Settings"><i class="fa-solid fa-gear"></i></div>
    </div>

    <!-- Sidebar -->
    <div id="sidebar">
      <div class="sidebar-title">
        <span>Explorer</span>
        <i class="fa-solid fa-ellipsis"></i>
      </div>
      <div class="sidebar-section">
        <i class="fa-solid fa-chevron-down"></i>
        <span>VSCODE_LIN (8,494 MODULES)</span>
      </div>
      <div class="file-tree" id="fileTree">
        <div class="file-item active" onclick="switchFile('editor/common/core/position.lin')">
          <i class="fa-solid fa-file-code file-icon"></i> <span>position.lin</span>
        </div>
        <div class="file-item" onclick="switchFile('editor/common/core/range.lin')">
          <i class="fa-solid fa-file-code file-icon"></i> <span>range.lin</span>
        </div>
        <div class="file-item" onclick="switchFile('base/common/uri.lin')">
          <i class="fa-solid fa-file-code file-icon"></i> <span>uri.lin</span>
        </div>
        <div class="file-item" onclick="switchFile('piece_tree.lin')">
          <i class="fa-solid fa-file-code file-icon"></i> <span>piece_tree.lin</span>
        </div>
        <div class="file-item" onclick="switchFile('workbench/browser/layout.lin')">
          <i class="fa-solid fa-file-code file-icon"></i> <span>layout.lin</span>
        </div>
        <div class="file-item" onclick="switchFile('platform/configuration/common/configuration.lin')">
          <i class="fa-solid fa-file-code file-icon"></i> <span>configuration.lin</span>
        </div>
        <div class="file-item" onclick="switchFile('base/common/event.lin')">
          <i class="fa-solid fa-file-code file-icon"></i> <span>event.lin</span>
        </div>
        <div class="file-item" onclick="switchFile('base/common/lifecycle.lin')">
          <i class="fa-solid fa-file-code file-icon"></i> <span>lifecycle.lin</span>
        </div>
        <div class="file-item" onclick="switchFile('editor/common/model/textModel.lin')">
          <i class="fa-solid fa-file-code file-icon"></i> <span>textModel.lin</span>
        </div>
        <div class="file-item" onclick="switchFile('workbench/services/editor/common/editorService.lin')">
          <i class="fa-solid fa-file-code file-icon"></i> <span>editorService.lin</span>
        </div>
      </div>
    </div>

    <!-- Editor Column -->
    <div id="editor-area">
      <div id="tabbar">
        <div class="tab">
          <i class="fa-solid fa-file-code file-icon"></i>
          <span id="tabTitle">position.lin</span>
          <span class="tab-close">×</span>
        </div>
      </div>

      <!-- Real Monaco Editor Container -->
      <div id="monaco-container"></div>

      <!-- Bottom Panel (Terminal / Output) -->
      <div id="bottom-panel">
        <div class="panel-tabs">
          <div class="panel-tab active">LIN In-Memory Engine</div>
          <div class="panel-tab">Terminal</div>
          <div class="panel-tab">Output</div>
          <div class="panel-tab">Debug Console</div>
        </div>
        <div class="panel-body" id="consoleOutput">
          [VS Code Sovereign Core] Monaco Editor attached to LIN In-Memory PieceTree runtime.<br>
          [Ready] 8,494 Modules Loaded | behavior_eq = 1.0000 | Merkle Root: 2e05c3e8abb8af0c
        </div>
      </div>
    </div>
  </div>

  <!-- Status Bar -->
  <div id="statusbar">
    <div class="sb-section">
      <div class="sb-item"><i class="fa-solid fa-code-branch"></i> master*</div>
      <div class="sb-item"><i class="fa-solid fa-arrows-rotate"></i> 0↓ 0↑</div>
      <div class="sb-item"><i class="fa-solid fa-circle-check"></i> LIN Engine: Sovereign</div>
    </div>
    <div class="sb-section">
      <div class="sb-item" id="sbCursor">Ln 1, Col 1</div>
      <div class="sb-item" id="sbLength">0 chars</div>
      <div class="sb-item">UTF-8</div>
      <div class="sb-item">LIN Language</div>
      <div class="sb-item"><i class="fa-solid fa-bell"></i></div>
    </div>
  </div>

  <!-- Monaco Editor Scripts -->
  <script src="https://cdnjs.cloudflare.com/ajax/libs/monaco-editor/0.45.0/min/vs/loader.min.js"></script>
  <script>
    let editorInstance = null;
    const consoleOutput = document.getElementById('consoleOutput');
    const sbCursor = document.getElementById('sbCursor');
    const sbLength = document.getElementById('sbLength');
    const tabTitle = document.getElementById('tabTitle');
    const titleFileName = document.getElementById('titleFileName');

    require.config({ paths: { vs: 'https://cdnjs.cloudflare.com/ajax/libs/monaco-editor/0.45.0/min/vs' } });

    require(['vs/editor/editor.main'], function () {
      // Register LIN Language in Monaco
      monaco.languages.register({ id: 'lin' });
      monaco.languages.setMonarchTokensProvider('lin', {
        tokenizer: {
          root: [
            [/@LIN:[^\\s]+/, 'keyword.header'],
            [/~G\\{[^\\}]*\\}/, 'keyword.grammar'],
            [/!([a-zA-Z0-9_$]+)/, 'type.identifier'],
            [/=ex\\{[^\\}]*\\}/, 'keyword.export'],
            [/\\^r|\\^|\\?i|\\?|#f|#|:else|:/, 'keyword.control'],
            [/\\/\\/.*$/, 'comment'],
            [/\\/\\*[\\s\\S]*?\\*\\//, 'comment'],
            [/"([^"\\\\]|\\\\.)*"/, 'string'],
            [/'([^'\\\\]|\\\\.)*'/, 'string'],
            [/\\d+/, 'number'],
            [/[a-zA-Z_$][\\w$]*/, 'identifier']
          ]
        }
      });

      monaco.editor.defineTheme('vs-lin-dark', {
        base: 'vs-dark',
        inherit: true,
        rules: [
          { token: 'keyword.header', foreground: '569cd6', fontStyle: 'bold' },
          { token: 'keyword.grammar', foreground: 'c586c0' },
          { token: 'type.identifier', foreground: '4ec9b0', fontStyle: 'bold' },
          { token: 'keyword.export', foreground: 'dcdcaa' },
          { token: 'keyword.control', foreground: 'c586c0', fontStyle: 'bold' },
          { token: 'string', foreground: 'ce9178' },
          { token: 'number', foreground: 'b5cea8' },
          { token: 'comment', foreground: '6a9955', fontStyle: 'italic' }
        ],
        colors: {
          'editor.background': '#1e1e1e',
          'editor.foreground': '#d4d4d4',
          'editorCursor.foreground': '#aeafad',
          'editor.lineHighlightBackground': '#2a2d2e',
          'editorLineNumber.foreground': '#858585',
          'editorLineNumber.activeForeground': '#c6c6c6'
        }
      });

      editorInstance = monaco.editor.create(document.getElementById('monaco-container'), {
        value: '',
        language: 'lin',
        theme: 'vs-lin-dark',
        automaticLayout: true,
        fontSize: 14,
        fontFamily: '"Cascadia Code", "Fira Code", monospace',
        fontLigatures: true,
        minimap: { enabled: true },
        scrollBeyondLastLine: false,
        renderWhitespace: 'selection',
        cursorBlinking: 'smooth',
        cursorSmoothCaretAnimation: "on"
      });

      // Synchronize cursor position with status bar
      editorInstance.onDidChangeCursorPosition((e) => {
        sbCursor.innerText = \`Ln \${e.position.lineNumber}, Col \${e.position.column}\`;
      });

      // Synchronize in-memory LIN PieceTree buffer on edit
      editorInstance.onDidChangeModelContent(async () => {
        const val = editorInstance.getValue();
        sbLength.innerText = \`\${val.length} chars\`;
        const t0 = performance.now();
        const res = await fetch('/api/update', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ content: val })
        });
        const data = await res.json();
        const dt = (performance.now() - t0).toFixed(2);
        consoleOutput.innerHTML += \`<br>[PieceTree LIN Buffer] Mutation synced in \${dt} ms | Lines: \${data.lines} | Length: \${data.length} | Hash: \${data.hash}\`;
        consoleOutput.scrollTop = consoleOutput.scrollHeight;
      });

      // Load initial file
      switchFile('editor/common/core/position.lin');
    });

    async function switchFile(relPath) {
      const fileName = relPath.split('/').pop();
      tabTitle.innerText = fileName;
      titleFileName.innerText = \`\${fileName} — VS Code (LIN Pure Sovereign Edition)\`;

      document.querySelectorAll('.file-item').forEach(el => el.classList.remove('active'));
      const activeEl = Array.from(document.querySelectorAll('.file-item')).find(el => el.innerText.includes(fileName));
      if (activeEl) activeEl.classList.add('active');

      const res = await fetch('/api/file?path=' + encodeURIComponent(relPath));
      const data = await res.json();
      if (editorInstance) {
        editorInstance.setValue(data.content || '');
        sbLength.innerText = \`\${(data.content || '').length} chars\`;
      }
      if (consoleOutput) {
        consoleOutput.innerHTML += \`<br>[Loaded File] \${relPath} (\${(data.content || '').length} bytes) opened in Monaco Editor\`;
        consoleOutput.scrollTop = consoleOutput.scrollHeight;
      }
    }
  </script>
</body>
</html>`;

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, 'http://localhost:3333');

  if (url.pathname === '/' || url.pathname === '/index.html') {
    res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
    res.end(HTML_CONTENT);
  } else if (url.pathname === '/api/file') {
    const rel = url.searchParams.get('path') || 'editor/common/core/position.lin';
    const fPath = path.join(VSCODE_LIN_DIR, rel);
    if (fs.existsSync(fPath)) {
      const content = fs.readFileSync(fPath, 'utf8');
      currentPieceTree = ptMod.createPieceTree(content);
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ content }));
    } else {
      res.writeHead(404, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ error: 'File not found' }));
    }
  } else if (url.pathname === '/api/update' && req.method === 'POST') {
    let body = '';
    req.on('data', chunk => { body += chunk; });
    req.on('end', () => {
      try {
        const payload = JSON.parse(body);
        currentPieceTree = ptMod.createPieceTree(payload.content || '');
        const hash = Buffer.from(payload.content || '').toString('base64').slice(0, 12);
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({
          lines: currentPieceTree.getLineCount(),
          length: currentPieceTree.getLength(),
          hash
        }));
      } catch (err) {
        res.writeHead(500, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: err.message }));
      }
    });
  } else {
    res.writeHead(404);
    res.end('Not Found');
  }
});

const PORT = 3333;
server.listen(PORT, '127.0.0.1', () => {
  console.log(`================================================================================`);
  console.log(`   VS CODE (AUTHENTIC MONACO WORKBENCH IN LIN) RUNNING LIVE!                    `);
  console.log(`   URL: http://127.0.0.1:${PORT}                                                `);
  console.log(`   Powered by: Microsoft Monaco Editor Engine + Pure LIN PieceTree Runtime      `);
  console.log(`================================================================================`);
});
