/* SA-001: the one Markdown -> HTML boundary for chat bubbles.
 *
 * Model and tool text is untrusted: the model quotes news snippets, and a
 * snippet can carry HTML. The bubble sink is React's dangerouslySetInnerHTML
 * (sphere.jsx). Two independent layers stand in front of it:
 *
 * 1. marked renders raw HTML in the text as visible text, never as markup.
 *    The chat prompt asks for Markdown only, so nothing intended is lost, and
 *    a quoted snippet stays readable instead of silently vanishing. <br> is
 *    the one tag kept, as a constant.
 * 2. DOMPurify sanitizes marked's output right before the sink, with a
 *    restrictive policy that holds even if layer 1 regresses:
 *    - only the tags Markdown produces (no img, svg, math, form, iframe, style);
 *    - no style, class, id or event attributes;
 *    - links only to http(s), opened in a new tab that cannot reach this
 *      window (rel="noopener noreferrer"); any other href is removed;
 *    - images are dropped: a model-written image URL would be fetched with no
 *      click, which can leak data to a third party.
 *
 * Fails closed: if either library is missing (CDN down, SRI mismatch) or
 * throws, the text is shown escaped, never as unsanitized HTML.
 *
 * index.html loads this after the pinned marked and DOMPurify scripts. An
 * inline script there has already moved marked from `window.marked` to
 * `window.saMarkedLib`, so nothing can call the raw parser, including a
 * sphere.jsx still cached by an older service worker: its renderMd then falls
 * back to escaped text for that one load. This file takes the handoff and
 * removes it from `window` too.
 */
(function () {
  const markedLib = window.saMarkedLib;
  try { delete window.saMarkedLib; } catch (e) { window.saMarkedLib = undefined; }

  const SAFE_HREF = /^https?:\/\//i;

  const POLICY = {
    ALLOWED_TAGS: ['p', 'br', 'hr', 'strong', 'em', 'del', 'code', 'pre', 'blockquote',
                   'ul', 'ol', 'li', 'a', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
                   'table', 'thead', 'tbody', 'tr', 'th', 'td'],
    ALLOWED_ATTR: ['href', 'title', 'align', 'start'],
    // Table alignment and list start are plain values; without this DOMPurify
    // would test them against the URL pattern below and drop them.
    ADD_URI_SAFE_ATTR: ['align', 'start'],
    ALLOWED_URI_REGEXP: SAFE_HREF,
    ALLOW_DATA_ATTR: false,
    ALLOW_ARIA_ATTR: false,
    ALLOW_UNKNOWN_PROTOCOLS: false,
  };

  function escapeText(text) {
    return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
               .replace(/"/g, '&quot;').replace(/'/g, '&#39;')
               .replace(/\n/g, '<br>');
  }

  let md = null;
  if (markedLib && typeof markedLib.Marked === 'function') {
    md = new markedLib.Marked({
      breaks: true,
      gfm: true,
      renderer: {
        html(html, block) {          // layer 1: raw HTML becomes text
          if (/^<br\s*\/?>$/i.test(html.trim())) return '<br>';
          const text = escapeText(html.replace(/\n+$/, ''));
          return block ? '<p>' + text + '</p>\n' : text;
        },
      },
    });
  }

  // A private instance, so this hook cannot leak into any other DOMPurify use.
  let purify = typeof window.DOMPurify === 'function' ? window.DOMPurify(window) : null;
  if (purify && purify.isSupported) {
    purify.addHook('afterSanitizeAttributes', function (node) {
      if (node.nodeName !== 'A') return;
      const href = node.getAttribute('href');
      if (href && SAFE_HREF.test(href)) {
        node.setAttribute('target', '_blank');
        node.setAttribute('rel', 'noopener noreferrer nofollow');
      } else {
        node.removeAttribute('href');
      }
    });
  } else {
    purify = null;
  }

  // Layer 2 on its own, exposed so tests can prove it holds without layer 1.
  function sanitizeHtml(html) {
    return purify ? purify.sanitize(html, POLICY) : escapeText(String(html));
  }

  function renderChatMarkdown(text) {
    const src = text == null ? '' : String(text);
    if (!md || !purify) return escapeText(src);
    try {
      return sanitizeHtml(md.parse(src));
    } catch (e) {
      return escapeText(src);
    }
  }
  renderChatMarkdown.sanitizeHtml = sanitizeHtml;
  window.saRenderChatMarkdown = renderChatMarkdown;
})();
