function escapeHtml(value: string) {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

function renderInline(value: string) {
  return escapeHtml(value)
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/~~([^~]+)~~/g, '<del>$1</del>')
    .replace(/\*([^*]+)\*/g, '<em>$1</em>')
    // Images come from http(s) or from this app's own public folder. Anything
    // else - a data: or javascript: URL - is left as the text it arrived as.
    .replace(/!\[([^\]]*)\]\(([^)\s]+)\)/g, (match: string, alt: string, src: string) => {
      if (!/^(https?:\/\/|\/|\.\/)/.test(src)) return match
      return `<img src="${src}" alt="${alt}" loading="lazy">`
    })
    .replace(/\[([^\]]+)\]\(((?:https?:\/\/|mailto:)[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>')
}

function flushParagraph(lines: string[], out: string[]) {
  if (!lines.length) return
  out.push(`<p>${lines.map(renderInline).join('<br>')}</p>`)
  lines.length = 0
}

function flushList(items: string[], out: string[], ordered: boolean) {
  if (!items.length) return
  const tag = ordered ? 'ol' : 'ul'
  out.push(`<${tag}>${items.map((item) => `<li>${renderInline(item)}</li>`).join('')}</${tag}>`)
  items.length = 0
}

function normalizePythonLiteral(value: string) {
  return value
    .replace(/\bNone\b/g, 'null')
    .replace(/\bTrue\b/g, 'true')
    .replace(/\bFalse\b/g, 'false')
    .replace(/'([^'\\]*(?:\\.[^'\\]*)*)'/g, (_, inner: string) => `"${inner.replace(/"/g, '\\"')}"`)
}

function parseStructuredValue(value: string): unknown {
  const trimmed = value.trim()
  if (!trimmed || !/^[\[{]/.test(trimmed)) return null

  try {
    return JSON.parse(trimmed)
  } catch {
    try {
      return JSON.parse(normalizePythonLiteral(trimmed))
    } catch {
      return null
    }
  }
}

function formatCellValue(value: unknown) {
  if (value === null || value === undefined || value === '') return '<span class="md-muted">-</span>'
  if (typeof value === 'object') return escapeHtml(JSON.stringify(value))
  return renderInline(String(value))
}

function renderDataTable(rows: Record<string, unknown>[]) {
  const headers = Array.from(new Set(rows.flatMap((row) => Object.keys(row))))
  if (!headers.length) return ''
  return [
    '<div class="md-table-wrap"><table class="md-data-table">',
    '<thead><tr>',
    headers.map((header) => `<th>${escapeHtml(header.replace(/_/g, ' '))}</th>`).join(''),
    '</tr></thead><tbody>',
    rows.map((row) => (
      `<tr>${headers.map((header) => `<td>${formatCellValue(row[header])}</td>`).join('')}</tr>`
    )).join(''),
    '</tbody></table></div>',
  ].join('')
}

function renderStructuredValue(value: unknown): string | null {
  if (Array.isArray(value)) {
    if (value.length === 0) return '<p><span class="md-muted">No rows returned.</span></p>'
    if (value.every((item) => item && typeof item === 'object' && !Array.isArray(item))) {
      return renderDataTable(value as Record<string, unknown>[])
    }
    return `<ul>${value.map((item) => `<li>${formatCellValue(item)}</li>`).join('')}</ul>`
  }

  if (value && typeof value === 'object') {
    return renderDataTable([value as Record<string, unknown>])
  }

  return null
}

const TABLE_SEPARATOR_CELL = /^:?-{2,}:?$/

function splitTableRow(line: string) {
  return line
    .trim()
    .replace(/^\|/, '')
    .replace(/\|$/, '')
    .split('|')
    .map((cell) => cell.trim())
}

function isTableSeparator(line: string | undefined) {
  if (!line || !line.includes('-')) return false
  const cells = splitTableRow(line)
  return cells.length > 0 && cells.every((cell) => TABLE_SEPARATOR_CELL.test(cell))
}

function columnAlignments(separator: string) {
  return splitTableRow(separator).map((cell) => {
    const left = cell.startsWith(':')
    const right = cell.endsWith(':')
    if (left && right) return 'center'
    return right ? 'right' : left ? 'left' : ''
  })
}

// A pipe table becomes a real table: without this the rows reached the bubble
// as plain text and every "| cell | cell |" line looked like repeated junk.
// Missing cells are padded so a ragged table keeps its grid.
function renderTable(rows: string[][], aligns: string[], copyLabel?: string) {
  const [header, ...body] = rows
  const columns = header.length
  const align = (index: number) => (aligns[index] ? ` style="text-align: ${aligns[index]}"` : '')
  const renderCells = (row: string[], tag: 'th' | 'td') =>
    Array.from({ length: columns }, (_, index) => {
      return `<${tag}${align(index)}>${renderInline(row[index] ?? '')}</${tag}>`
    }).join('')

  return [
    '<div class="md-table-wrap">',
    copyLabel ? `<button type="button" class="md-copy-btn">${escapeHtml(copyLabel)}</button>` : '',
    '<table class="md-data-table">',
    `<thead><tr>${renderCells(header, 'th')}</tr></thead>`,
    `<tbody>${body.map((row) => `<tr>${renderCells(row, 'td')}</tr>`).join('')}</tbody>`,
    '</table>',
    '</div>',
  ].join('')
}

function parseJsonText(text: string): unknown {
  const candidate = text.trim()
  if (!candidate || !/^[\[{]/.test(candidate)) return null
  try {
    return JSON.parse(candidate)
  } catch {
    return null
  }
}

// Tool payloads are JSON and the interesting part often sits in a string field
// holding a whole HTTP body. Expanding what parses turns that escaped one-liner
// into the indented block a reader expects next to the Input.
function expandJsonStrings(value: unknown, depth = 0): unknown {
  if (depth >= 4) return value
  if (typeof value === 'string') {
    const parsed = parseJsonText(value)
    return parsed === null ? value : expandJsonStrings(parsed, depth + 1)
  }
  if (Array.isArray(value)) return value.map((item) => expandJsonStrings(item, depth + 1))
  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>).map(([key, item]) => [
        key,
        expandJsonStrings(item, depth + 1),
      ]),
    )
  }
  return value
}

// Rows stored before the backend indented tool output are still one endless
// line; re-indenting on render fixes those too. A truncated block does not
// parse, so it is left exactly as stored.
function formatCodeBlock(code: string, language: string) {
  const trimmed = code.trim()
  if (language !== 'json' && !/^[\[{]/.test(trimmed)) return code
  const parsed = parseJsonText(trimmed)
  if (parsed === null) return code
  try {
    return JSON.stringify(expandJsonStrings(parsed), null, 2)
  } catch {
    return code
  }
}

export function renderMarkdown(
  value: string | null | undefined,
  options: { copyLabel?: string } = {},
) {
  const copyLabel = options.copyLabel
  if (!value) return ''

  const structured = renderStructuredValue(parseStructuredValue(value))
  if (structured) return structured

  const out: string[] = []
  const paragraph: string[] = []
  const listItems: string[] = []
  let orderedList = false
  let inCode = false
  let codeLines: string[] = []
  let codeLang = ''

  const closeBlocks = () => {
    flushParagraph(paragraph, out)
    flushList(listItems, out, orderedList)
  }

  const lines = value.replace(/\r\n/g, '\n').split('\n')
  for (let index = 0; index < lines.length; index += 1) {
    const rawLine = lines[index]
    const line = rawLine.trimEnd()

    if (line.startsWith('```')) {
      if (inCode) {
        out.push(`<pre><code>${escapeHtml(formatCodeBlock(codeLines.join('\n'), codeLang))}</code></pre>`)
        codeLines = []
        codeLang = ''
        inCode = false
      } else {
        closeBlocks()
        inCode = true
        codeLang = line.slice(3).trim().toLowerCase()
      }
      continue
    }

    if (inCode) {
      codeLines.push(rawLine)
      continue
    }

    if (!line.trim()) {
      closeBlocks()
      continue
    }

    const heading = /^(#{1,4})\s+(.+)$/.exec(line)
    if (heading) {
      closeBlocks()
      const level = heading[1].length
      out.push(`<h${level}>${renderInline(heading[2])}</h${level}>`)
      continue
    }

    const quote = /^>\s?(.+)$/.exec(line)
    if (quote) {
      closeBlocks()
      out.push(`<blockquote>${renderInline(quote[1])}</blockquote>`)
      continue
    }

    // Pipe table: this line is the header, the next one the separator, and
    // every following line with a pipe is a body row.
    if (line.includes('|') && isTableSeparator(lines[index + 1])) {
      closeBlocks()
      const rows = [splitTableRow(line)]
      const aligns = columnAlignments(lines[index + 1] || '')
      index += 2
      while (index < lines.length && lines[index].trim() && lines[index].includes('|')) {
        rows.push(splitTableRow(lines[index]))
        index += 1
      }
      index -= 1
      out.push(renderTable(rows, aligns, copyLabel))
      continue
    }

    const unordered = /^[-*]\s+(.+)$/.exec(line)
    const ordered = /^\d+\.\s+(.+)$/.exec(line)
    if (unordered || ordered) {
      flushParagraph(paragraph, out)
      const isOrdered = Boolean(ordered)
      if (listItems.length && orderedList !== isOrdered) {
        flushList(listItems, out, orderedList)
      }
      orderedList = isOrdered
      listItems.push((ordered || unordered)?.[1] || '')
      continue
    }

    flushList(listItems, out, orderedList)
    paragraph.push(line)
  }

  if (inCode) out.push(`<pre><code>${escapeHtml(codeLines.join('\n'))}</code></pre>`)
  closeBlocks()
  return out.join('')
}
