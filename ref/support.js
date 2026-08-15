(function () {
  'use strict';

  // Hide the raw template until the first real render replaces it (avoids a
  // flash of literal "{{ ... }}" text while the page is still parsing).
  var hideStyle = document.createElement('style');
  hideStyle.textContent = 'x-dc{display:block;opacity:0}';
  document.head.appendChild(hideStyle);

  // ---------- expression helpers ----------

  function extractExpr(raw) {
    if (raw == null) return null;
    var m = /^\{\{\s*([\s\S]+?)\s*\}\}$/.exec(raw.trim());
    return m ? m[1] : null;
  }

  function evalPath(expr, scope) {
    if (expr === 'true') return true;
    if (expr === 'false') return false;
    if (expr === 'null') return null;
    var parts = expr.split('.');
    var cur = scope;
    for (var i = 0; i < parts.length; i++) {
      if (cur == null) return undefined;
      cur = cur[parts[i]];
    }
    return cur;
  }

  function stringify(v) {
    return v === undefined || v === null ? '' : String(v);
  }

  function compileTextTemplate(str) {
    var re = /\{\{\s*([\s\S]+?)\s*\}\}/g;
    var segments = [];
    var lastIndex = 0;
    var m;
    while ((m = re.exec(str))) {
      if (m.index > lastIndex) segments.push({ t: str.slice(lastIndex, m.index) });
      segments.push({ e: m[1] });
      lastIndex = re.lastIndex;
    }
    if (lastIndex < str.length) segments.push({ t: str.slice(lastIndex) });
    if (!segments.length) segments.push({ t: '' });
    return function (scope) {
      var out = '';
      for (var i = 0; i < segments.length; i++) {
        var s = segments[i];
        out += s.t !== undefined ? s.t : stringify(evalPath(s.e, scope));
      }
      return out;
    };
  }

  // ---------- template compiler: DOM node -> (scope) => VNode[] ----------

  function compileNode(node) {
    if (node.nodeType === Node.TEXT_NODE) {
      var textFn = compileTextTemplate(node.textContent);
      return function (scope) { return [{ type: 'text', text: textFn(scope) }]; };
    }
    if (node.nodeType !== Node.ELEMENT_NODE) return function () { return []; };

    var tag = node.tagName.toLowerCase();

    if (tag === 'sc-if') {
      var ifExpr = extractExpr(node.getAttribute('value'));
      var ifKids = Array.from(node.childNodes).map(compileNode);
      return function (scope) {
        if (!evalPath(ifExpr, scope)) return [];
        var out = [];
        for (var i = 0; i < ifKids.length; i++) out.push.apply(out, ifKids[i](scope));
        return out;
      };
    }

    if (tag === 'sc-for') {
      var listExpr = extractExpr(node.getAttribute('list'));
      var alias = node.getAttribute('as');
      var forKids = Array.from(node.childNodes).map(compileNode);
      return function (scope) {
        var list = evalPath(listExpr, scope);
        var out = [];
        if (Array.isArray(list)) {
          for (var idx = 0; idx < list.length; idx++) {
            var childScope = Object.create(scope);
            childScope[alias] = list[idx];
            for (var j = 0; j < forKids.length; j++) out.push.apply(out, forKids[j](childScope));
          }
        }
        return out;
      };
    }

    var attrDefs = [];
    Array.from(node.attributes).forEach(function (a) {
      if (a.name.indexOf('hint-placeholder') === 0) return;
      attrDefs.push({ name: a.name, raw: a.value, expr: extractExpr(a.value) });
    });
    var elKids = Array.from(node.childNodes).map(compileNode);

    return function (scope) {
      var attrs = {}, events = {}, props = {}, key;
      for (var i = 0; i < attrDefs.length; i++) {
        var d = attrDefs[i];
        var value;
        if (d.expr !== null) value = evalPath(d.expr, scope);
        else if (d.raw.indexOf('{{') !== -1) value = compileTextTemplate(d.raw)(scope);
        else value = d.raw;

        if (d.name === 'onclick') { events.click = typeof value === 'function' ? value : null; continue; }
        if (d.name === 'onchange') { events.input = typeof value === 'function' ? value : null; continue; }
        if (d.name === 'value' && (tag === 'textarea' || tag === 'input')) { props.value = stringify(value); continue; }
        if (d.name === 'key') { key = stringify(value); continue; }
        attrs[d.name] = stringify(value);
      }
      var children = [];
      for (var k = 0; k < elKids.length; k++) children.push.apply(children, elKids[k](scope));
      return [{ type: 'el', tag: tag, attrs: attrs, events: events, props: props, key: key, children: children }];
    };
  }

  // ---------- vdom mount / diff-patch ----------

  function applyAttrs(el, oldAttrs, newAttrs) {
    for (var name in oldAttrs) if (!(name in newAttrs)) el.removeAttribute(name);
    for (var name2 in newAttrs) if (oldAttrs[name2] !== newAttrs[name2]) el.setAttribute(name2, newAttrs[name2]);
  }

  function applyProps(el, oldProps, newProps) {
    for (var name in newProps) if (oldProps[name] !== newProps[name]) el[name] = newProps[name];
  }

  function applyEvents(el, oldEvents, newEvents) {
    el.__handlers = el.__handlers || {};
    for (var type in oldEvents) if (el.__handlers[type]) el.removeEventListener(type, el.__handlers[type]);
    for (var type2 in newEvents) {
      if (newEvents[type2]) {
        el.addEventListener(type2, newEvents[type2]);
        el.__handlers[type2] = newEvents[type2];
      } else {
        el.__handlers[type2] = null;
      }
    }
  }

  function createDom(vnode) {
    if (vnode.type === 'text') return document.createTextNode(vnode.text);
    var el = document.createElement(vnode.tag);
    applyAttrs(el, {}, vnode.attrs);
    applyProps(el, {}, vnode.props);
    applyEvents(el, {}, vnode.events);
    vnode.children.forEach(function (child) { el.appendChild(createDom(child)); });
    return el;
  }

  function sameNode(a, b) {
    if (!a || !b) return false;
    if (a.type !== b.type) return false;
    if (a.type === 'text') return true;
    if (a.tag !== b.tag) return false;
    if ((a.key || undefined) !== (b.key || undefined)) return false;
    return true;
  }

  function patch(parentDom, oldVList, newVList, domList) {
    var newDomList = [];
    var max = Math.max(oldVList.length, newVList.length);
    for (var i = 0; i < max; i++) {
      var ov = oldVList[i], nv = newVList[i], od = domList[i];
      if (ov && nv && sameNode(ov, nv)) {
        if (nv.type === 'text') {
          if (ov.text !== nv.text) od.textContent = nv.text;
        } else {
          applyAttrs(od, ov.attrs, nv.attrs);
          applyProps(od, ov.props, nv.props);
          applyEvents(od, ov.events, nv.events);
          patch(od, ov.children, nv.children, Array.from(od.childNodes));
        }
        newDomList.push(od);
      } else {
        var refNode = od ? od.nextSibling : null;
        if (od) parentDom.removeChild(od);
        if (nv) {
          var newEl = createDom(nv);
          if (refNode) parentDom.insertBefore(newEl, refNode);
          else parentDom.appendChild(newEl);
          newDomList.push(newEl);
        }
      }
    }
    return newDomList;
  }

  // ---------- DCLogic base class (contract expected by the dc-script) ----------

  function DCLogic(props) {
    this.props = props || {};
  }
  DCLogic.prototype.setState = function (patchObj) {
    var prevState = this.state;
    var next = typeof patchObj === 'function' ? patchObj(this.state) : patchObj;
    this.state = Object.assign({}, this.state, next);
    if (this._onStateChange) this._onStateChange(prevState);
  };

  // ---------- boot ----------

  document.addEventListener('DOMContentLoaded', function () {
    try {
      var xdc = document.querySelector('x-dc');
      if (!xdc) return;

      var helmet = Array.from(xdc.children).find(function (el) { return el.tagName.toLowerCase() === 'helmet'; });
      if (helmet) {
        Array.from(helmet.childNodes).forEach(function (n) { document.head.appendChild(n); });
        helmet.parentNode.removeChild(helmet);
      }

      var templateNodes = Array.from(xdc.childNodes);
      var topCompilers = templateNodes.map(compileNode);
      xdc.innerHTML = '';

      var scriptEl = document.querySelector('script[data-dc-script]');
      if (!scriptEl) throw new Error('script[data-dc-script] not found');
      var scriptSrc = scriptEl.textContent;

      var propsSchema = {};
      try { propsSchema = JSON.parse(scriptEl.getAttribute('data-props') || '{}'); } catch (e) {}
      var defaultProps = {};
      Object.keys(propsSchema).forEach(function (k) { defaultProps[k] = propsSchema[k].default; });

      var Component = new Function('DCLogic', scriptSrc + '\n;return Component;')(DCLogic);
      var inst = new Component(defaultProps);

      var topOldV = [];
      var topOldDom = [];
      function rerender() {
        var scope = inst.renderVals();
        var topNewV = [];
        topCompilers.forEach(function (c) { topNewV.push.apply(topNewV, c(scope)); });
        topOldDom = patch(xdc, topOldV, topNewV, topOldDom);
        topOldV = topNewV;
      }

      inst._onStateChange = function (prevState) {
        var prevProps = inst.props;
        rerender();
        if (inst.componentDidUpdate) inst.componentDidUpdate(prevProps, prevState);
      };

      rerender();
      xdc.style.opacity = '1';
      if (inst.componentDidMount) inst.componentDidMount();
    } catch (err) {
      console.error('support.js failed to render the prototype:', err);
      var pre = document.createElement('pre');
      pre.style.cssText = 'padding:16px;color:#c0392b;background:#fff3f2;font-size:12px;white-space:pre-wrap';
      pre.textContent = 'support.js error: ' + (err && err.stack || err);
      document.body.appendChild(pre);
    }
  });
})();
