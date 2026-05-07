import assert from 'node:assert/strict';
import test from 'node:test';
import vm from 'node:vm';
import { readFileSync } from 'node:fs';

function extractInlineEditorSource() {
  const html = readFileSync(new URL('../index.html', import.meta.url), 'utf8');
  const match = html.match(
    /function readInlineEditorMeta\(name\) \{[\s\S]*?\n\n        class InlineEditor \{[\s\S]*?\n        \}\n\n        \/\* Initialize \*\//,
  );

  if (!match) {
    throw new Error('Could not find inline editor source in index.html');
  }

  return `${match[0].replace(/\n\n        \/\* Initialize \*\/$/, '')}\nthis.InlineEditor = InlineEditor;\nthis.buildUnifiedDiff = buildUnifiedDiff;\nthis.getInlineEditorConfig = getInlineEditorConfig;`;
}

class MockClassList {
  constructor() {
    this.classes = new Set();
  }

  add(name) {
    this.classes.add(name);
  }

  remove(name) {
    this.classes.delete(name);
  }

  toggle(name, force) {
    if (force === undefined) {
      if (this.classes.has(name)) {
        this.classes.delete(name);
        return false;
      }
      this.classes.add(name);
      return true;
    }

    if (force) {
      this.classes.add(name);
      return true;
    }

    this.classes.delete(name);
    return false;
  }

  contains(name) {
    return this.classes.has(name);
  }
}

class MockElement {
  constructor(tagName, innerHTML = '') {
    this.tagName = tagName.toUpperCase();
    this.innerHTML = innerHTML;
    this.textContent = innerHTML;
    this.style = {};
    this.attributes = {};
    this.classList = new MockClassList();
    this.listeners = new Map();
    this.clickCount = 0;
    this.removeCount = 0;
    this.parentNode = null;
    this._contentEditable = 'inherit';
    this.value = '';
  }

  addEventListener(type, handler) {
    this.listeners.set(type, handler);
  }

  dispatch(type, event = {}) {
    const handler = this.listeners.get(type);
    if (handler) {
      handler(event);
    }
  }

  set contentEditable(value) {
    this._contentEditable = value;
    this.attributes.contenteditable = value;
  }

  get contentEditable() {
    return this._contentEditable;
  }

  get isContentEditable() {
    return this._contentEditable === 'true';
  }

  getAttribute(name) {
    return this.attributes[name] ?? null;
  }

  setAttribute(name, value) {
    this.attributes[name] = value;
  }

  removeAttribute(name) {
    delete this.attributes[name];
  }

  closest() {
    return null;
  }

  click() {
    this.clickCount += 1;
  }

  select() {
    this.selected = true;
  }

  remove() {
    this.removeCount += 1;
    if (this.parentNode?.children) {
      this.parentNode.children = this.parentNode.children.filter((child) => child !== this);
    }
  }
}

function createDocumentClone(snapshotHtml) {
  const clonedToggle = new MockElement('button', 'Editing (Ctrl+S to save)');
  clonedToggle.classList.add('active');
  clonedToggle.classList.add('show');

  return {
    outerHTML: snapshotHtml,
    querySelector(selector) {
      if (selector === '#editToggle') {
        return clonedToggle;
      }
      return null;
    },
    querySelectorAll() {
      return [new MockElement('h1'), new MockElement('p')];
    },
  };
}

function createEnvironment({
  meta = {},
  savedEdits,
  snapshotHtml = '<html><body>snapshot</body></html>',
  windowPathname = '/internal-agents/index.html',
} = {}) {
  const editableElements = [
    new MockElement('h1', 'Title'),
    new MockElement('p', 'Body copy'),
  ];
  const editToggle = new MockElement('button', 'Edit');
  const editHotzone = new MockElement('div');
  const createdElements = [];
  const body = {
    children: [],
    appendChild(element) {
      element.parentNode = this;
      this.children.push(element);
    },
  };
  const keydownHandlers = [];
  const clipboardWrites = [];
  const derivedStorageKey = meta['inline-editor-storage-key'] || `inline-editor:${meta['inline-editor-file-path'] || windowPathname}`;
  const localStorage = {
    store: new Map(savedEdits ? [[derivedStorageKey, savedEdits]] : []),
    getItem(key) {
      return this.store.has(key) ? this.store.get(key) : null;
    },
    setItem(key, value) {
      this.store.set(key, value);
    },
  };
  const context = {
    console,
    localStorage,
    window: {
      location: {
        pathname: windowPathname,
      },
    },
    navigator: {
      clipboard: {
        async writeText(text) {
          clipboardWrites.push(text);
        },
      },
    },
    Blob: class MockBlob {
      constructor(parts, options) {
        this.parts = parts;
        this.options = options;
      }
    },
    URL: {
      createObjectURL() {
        return 'blob:mock';
      },
      revokeObjectURL() {},
    },
    setTimeout(fn) {
      fn();
      return 1;
    },
    clearTimeout() {},
    document: {
      body,
      documentElement: {
        outerHTML: snapshotHtml,
        cloneNode() {
          return createDocumentClone(snapshotHtml);
        },
      },
      getElementById(id) {
        if (id === 'editToggle') return editToggle;
        if (id === 'editHotzone') return editHotzone;
        return null;
      },
      querySelector(selector) {
        const match = selector.match(/meta\[name="([^"]+)"\]/);
        if (!match) {
          return null;
        }

        const content = meta[match[1]];
        if (!content) {
          return null;
        }

        const element = new MockElement('meta');
        element.setAttribute('content', content);
        return element;
      },
      querySelectorAll(selector) {
        if (!selector.includes('h1')) {
          return [];
        }
        return editableElements;
      },
      addEventListener(type, handler) {
        if (type === 'keydown') {
          keydownHandlers.push(handler);
        }
      },
      createElement(tagName) {
        const element = new MockElement(tagName);
        createdElements.push(element);
        return element;
      },
    },
  };

  vm.runInNewContext(extractInlineEditorSource(), context);
  const editor = new context.InlineEditor();

  return {
    body,
    clipboardWrites,
    createdElements,
    editHotzone,
    editToggle,
    editableElements,
    editor,
    keydownHandlers,
    localStorage,
  };
}

test('restores saved edits on startup', () => {
  const savedEdits = JSON.stringify([
    { index: 0, html: 'Updated title' },
    { index: 1, html: 'Updated body' },
  ]);
  const { editableElements } = createEnvironment({ savedEdits });

  assert.equal(editableElements[0].innerHTML, 'Updated title');
  assert.equal(editableElements[1].innerHTML, 'Updated body');
});

test('pressing E works when focus is on a contenteditable=false element', () => {
  const { editToggle, editor, keydownHandlers } = createEnvironment();
  editor.toggleEditMode();
  editor.toggleEditMode();

  const target = new MockElement('p', 'Body copy');
  target.contentEditable = 'false';

  const event = {
    key: 'E',
    target,
    preventDefaultCalled: false,
    preventDefault() {
      this.preventDefaultCalled = true;
    },
  };

  keydownHandlers[0](event);

  assert.equal(editor.isActive, true);
  assert.equal(editToggle.textContent, 'Editing (Ctrl+S to save)');
  assert.equal(event.preventDefaultCalled, true);
});

test('config auto-detects from the current path', () => {
  const { editor } = createEnvironment({ windowPathname: '/talks/demo/index.html' });

  assert.equal(editor.filePath, '/talks/demo/index.html');
  assert.equal(editor.storageKey, 'inline-editor:/talks/demo/index.html');
  assert.equal(editor.downloadName, 'index-edited.html');
});

test('meta tags override auto-detected editor config', () => {
  const { editor } = createEnvironment({
    meta: {
      'inline-editor-file-path': '/repo/slides/custom-deck.html',
      'inline-editor-storage-key': 'slides-custom:v2',
      'inline-editor-download-name': 'custom-export.html',
    },
  });

  assert.equal(editor.filePath, '/repo/slides/custom-deck.html');
  assert.equal(editor.storageKey, 'slides-custom:v2');
  assert.equal(editor.downloadName, 'custom-export.html');
});

test('clipboard prompt includes the file path and a unified diff', () => {
  const { editor } = createEnvironment({ snapshotHtml: '<html><body>before</body></html>' });
  editor.originalDocumentHtml = '<!DOCTYPE html>\n<html><body>before</body></html>';

  const prompt = editor.buildClipboardPrompt('<!DOCTYPE html>\n<html><body>after</body></html>');

  assert.match(prompt, /Apply this unified diff to \/internal-agents\/index\.html/);
  assert.match(prompt, /```diff/);
  assert.match(prompt, /--- \/internal-agents\/index\.html/);
  assert.match(prompt, /\+\+\+ \/internal-agents\/index\.html/);
  assert.match(prompt, /-<html><body>before<\/body><\/html>/);
  assert.match(prompt, /\+<html><body>after<\/body><\/html>/);
});

test('save persists editable content and copies the diff prompt to clipboard', async () => {
  const { clipboardWrites, createdElements, editToggle, editableElements, editor, localStorage } = createEnvironment();
  editor.toggleEditMode();
  editableElements[0].innerHTML = 'Saved title';
  editableElements[1].innerHTML = 'Saved paragraph';
  editor.serializeDocument = () => '<!DOCTYPE html>\n<html><body>after</body></html>';
  editor.originalDocumentHtml = '<!DOCTYPE html>\n<html><body>before</body></html>';

  await editor.save();

  const saved = JSON.parse(localStorage.getItem('inline-editor:/internal-agents/index.html'));
  assert.deepEqual(saved, [
    { index: 0, html: 'Saved title' },
    { index: 1, html: 'Saved paragraph' },
  ]);
  assert.equal(clipboardWrites.length, 1);
  assert.match(clipboardWrites[0], /Apply this unified diff to/);
  assert.match(clipboardWrites[0], /\+<html><body>after<\/body><\/html>/);
  assert.equal(createdElements.some((child) => child.tagName === 'A' && child.clickCount === 1), true);
  assert.equal(editToggle.classList.contains('active'), true);
});
