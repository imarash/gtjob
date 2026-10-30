// Shared helpers for the gtjob CV templates. Pure functions: every template defines `data` and `presets`
// itself and passes a style dictionary (`sty`) in. Strings from the data are inserted as text, never as
// markup, and nothing here calls eval.
//
// `sty` keys: accent, ink, muted, heavy (semibold weight), section-gap, item-gap, indent, draft

#let confirm-pattern = regex("\\[\\[CONFIRM:[^\\]]*\\]\\]")
#let draft-red = rgb("#C00000")
#let contact-separator = [ · ]
#let draft-footer-text = "DRAFT: unconfirmed items"

// Highlights [[CONFIRM: ...]] placeholders in red when the render is a draft.
#let draft-highlight(draft, body) = {
  show confirm-pattern: it => if draft { text(fill: draft-red, weight: "bold", it) } else { it }
  body
}

// "n / total" page numbers in text, plus the draft notice when `draft` is true.
#let page-footer(draft, sty) = context {
  let here = counter(page).get().first()
  let total = counter(page).final().first()
  set text(size: 8.5pt, fill: sty.muted)
  grid(
    columns: (1fr, auto, 1fr),
    if draft { text(fill: draft-red, weight: "bold")[#draft-footer-text] } else { [] },
    [#here / #total],
    [],
  )
}

// Section heading: tracked uppercase over a subtle accent rule. A real heading element keeps the PDF tagged.
#let section-title(title, sty) = {
  show heading: it => block(width: 100%, above: sty.section-gap, below: 0.5em, sticky: true)[
    #stack(
      spacing: 0.32em,
      text(weight: sty.heavy, size: 0.9em, tracking: 0.08em, fill: sty.ink, upper(it.body)),
      line(length: 100%, stroke: 0.6pt + sty.accent),
    )
  ]
  heading(level: 1, outlined: false, title)
}

// Employer on the left in bold, dates right-aligned on the same line; title and location on the next line.
// Each line is one paragraph with a flexible gap (`h(1fr)`), so text extraction keeps it on one line.
#let entry-head(heading, subheading, location, dates, sty) = {
  let second = subheading != "" or location != ""
  block(width: 100%, above: sty.item-gap, below: 0.28em, sticky: true, breakable: false)[
    #text(weight: sty.heavy)[#heading]#h(1fr)#text(fill: sty.ink)[#dates]
    #if second [
      #v(0.22em, weak: true)
      #text(fill: sty.muted, style: "italic")[#subheading]#h(1fr)#text(fill: sty.muted)[#location]
    ]
  ]
}

// Tight bullet list with a hanging indent. `indent` shifts the whole list (client subentries).
#let bullets(items, sty, indent: 0pt) = if items.len() > 0 {
  pad(left: indent, list(
    marker: [•],
    indent: 0pt,
    body-indent: 0.6em,
    spacing: sty.bullet-gap,
    ..items.map(t => [#t]),
  ))
}

// Name, headline, and a one-line contact list with real links and a text separator.
#let contact-line(contacts, sty) = {
  show link: set text(fill: sty.ink)
  contacts
    .map(c => if c.url != "" { link(c.url)[#c.text] } else { [#c.text] })
    .join(contact-separator)
}

// One experience or education entry: head, intro, bullets, indented client subentries, collapsed line.
#let render-entry(e, sty) = {
  entry-head(e.heading, e.subheading, e.location, e.dates, sty)
  if e.intro != "" { block(below: 0.4em, text(fill: sty.muted)[#e.intro]) }
  bullets(e.bullets, sty)
  for s in e.subentries {
    block(above: 0.5em, below: 0.25em, sticky: true, breakable: false, pad(left: sty.indent)[
      #text(weight: sty.heavy)[#s.heading]#if s.subheading != "" [ #text(fill: sty.muted)[— #emph[#s.subheading]]]
    ])
    bullets(s.bullets, sty, indent: sty.indent)
  }
  if e.collapsed_line != "" {
    block(above: 0.5em, pad(left: sty.indent, text(fill: sty.muted, style: "italic")[#e.collapsed_line]))
  }
}

#let link-ink = rgb("#1F4E79")

// Certification names as text links. The visible words stay the certificate name.
#let cert-line(sec) = {
  let linked = sec.at("link_lines", default: ())
  if linked.len() > 0 {
    linked
      .map(c => if c.url != "" { underline(text(fill: link-ink)[#link(c.url)[#c.text]]) } else { [#c.text] })
      .join(contact-separator)
  } else {
    sec.lines.join(contact-separator)
  }
}

// One section, dispatched on its kind. Empty sections are skipped by the caller (the data builder omits them).
#let render-section(sec, sty) = {
  section-title(sec.title, sty)
  for p in sec.paragraphs { par(p) }
  for row in sec.skill_rows {
    block(below: 0.3em)[#text(weight: sty.heavy)[#row.label:] #row.items_text]
  }
  for e in sec.entries { render-entry(e, sty) }
  if sec.kind == "certifications" and sec.lines.len() > 0 {
    par(cert-line(sec))
  } else {
    for l in sec.lines { block(below: 0.3em)[#l] }
  }
}
