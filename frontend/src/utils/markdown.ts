/**
 * A small, safe Markdown renderer for the in-page preview.
 *
 * The preview shows a file the backend stored, so its content is untrusted
 * input. Nothing of it ever reaches the DOM as HTML: every character that
 * carries meaning in HTML is escaped first, and only then the small subset
 * of Markdown listed below is turned into tags this module writes itself.
 * A link is only linked when its target is http(s), an absolute path or a
 * fragment; anything else (`javascript:` and friends) stays plain text.
 *
 * The supported subset covers the generated artifacts: headings, paragraphs,
 * bullet and numbered lists, fenced and inline code, bold, italic, links and
 * horizontal rules.
 */

const ESCAPES: Record<string, string> = {
  '&': '&amp;',
  '<': '&lt;',
  '>': '&gt;',
  '"': '&quot;',
  "'": '&#39;',
}

/** Escape the characters that are special in HTML. */
export function escapeHtml(text: string): string {
  return text.replace(/[&<>"']/g, (char) => ESCAPES[char] ?? char)
}

/**
 * A link target the preview is willing to make clickable.
 *
 * Absolute http(s) URLs, fragments and same-origin paths are kept. A
 * protocol-relative `//host` and every other scheme (`javascript:`, `data:`)
 * stay plain text.
 */
function isSafeUrl(url: string): boolean {
  return /^https?:\/\/[^\s]/i.test(url) || url.startsWith('#') || /^\/[^/]/.test(url)
}

/** Inline markup: code spans, bold, italic and links, on escaped text. */
function renderInline(escaped: string): string {
  let html = escaped.replace(
    /`([^`]+)`/g,
    (_match, code: string) => `<code>${code}</code>`,
  )
  html = html.replace(
    /\[([^\]]+)\]\(([^)\s]+)\)/g,
    (match, text: string, url: string) => {
      if (!isSafeUrl(url)) {
        return match
      }
      return `<a href="${url}" target="_blank" rel="noopener noreferrer">${text}</a>`
    },
  )
  html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
  html = html.replace(/(^|[^*])\*([^*\n]+)\*/g, '$1<em>$2</em>')
  html = html.replace(/(^|\s)_([^_\n]+)_/g, '$1<em>$2</em>')
  return html
}

/** Turn untrusted Markdown into the HTML of this module. */
export function renderMarkdown(source: string): string {
  const lines = source.replace(/\r\n?/g, '\n').split('\n')
  const out: string[] = []
  let paragraph: string[] = []
  let listType: 'ul' | 'ol' | null = null
  let inFence = false
  let fence: string[] = []

  function closeParagraph(): void {
    if (paragraph.length > 0) {
      out.push(`<p>${renderInline(escapeHtml(paragraph.join(' ')))}</p>`)
      paragraph = []
    }
  }

  function closeList(): void {
    if (listType) {
      out.push(`</${listType}>`)
      listType = null
    }
  }

  function openList(type: 'ul' | 'ol'): void {
    if (listType !== type) {
      closeList()
      out.push(`<${type}>`)
      listType = type
    }
  }

  for (const raw of lines) {
    const line = raw.trimEnd()

    if (/^\s*```/.test(line) || /^\s*~~~/.test(line)) {
      if (inFence) {
        out.push(`<pre class="md-code-block"><code>${escapeHtml(fence.join('\n'))}</code></pre>`)
        fence = []
        inFence = false
      } else {
        closeParagraph()
        closeList()
        inFence = true
      }
      continue
    }
    if (inFence) {
      fence.push(raw)
      continue
    }

    if (line.trim() === '') {
      closeParagraph()
      closeList()
      continue
    }

    const heading = /^(#{1,6})\s+(.*)$/.exec(line)
    if (heading) {
      closeParagraph()
      closeList()
      const level = heading[1]?.length ?? 1
      out.push(`<h${level}>${renderInline(escapeHtml(heading[2] ?? ''))}</h${level}>`)
      continue
    }

    if (/^\s*([-*_])\s*\1\s*\1[\s*-]*$/.test(line)) {
      closeParagraph()
      closeList()
      out.push('<hr />')
      continue
    }

    const bullet = /^\s*[-*+]\s+(.*)$/.exec(line)
    if (bullet) {
      closeParagraph()
      openList('ul')
      out.push(`<li>${renderInline(escapeHtml(bullet[1] ?? ''))}</li>`)
      continue
    }

    const numbered = /^\s*\d+[.)]\s+(.*)$/.exec(line)
    if (numbered) {
      closeParagraph()
      openList('ol')
      out.push(`<li>${renderInline(escapeHtml(numbered[1] ?? ''))}</li>`)
      continue
    }

    const quote = /^\s*>\s?(.*)$/.exec(line)
    if (quote) {
      closeParagraph()
      closeList()
      out.push(`<blockquote>${renderInline(escapeHtml(quote[1] ?? ''))}</blockquote>`)
      continue
    }

    paragraph.push(line.trim())
  }

  if (inFence) {
    out.push(`<pre class="md-code-block"><code>${escapeHtml(fence.join('\n'))}</code></pre>`)
  }
  closeParagraph()
  closeList()
  return out.join('\n')
}

/** The HTML of an untrusted plain-text file: escaped, line by line. */
export function renderPlainText(source: string): string {
  return `<pre class="md-plain">${escapeHtml(source)}</pre>`
}
