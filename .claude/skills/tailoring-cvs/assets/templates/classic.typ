#let data = json(sys.inputs.at("data", default: "render.json"))
#let presets = json(sys.inputs.at("presets", default: "presets.json"))
#import "common.typ": *

// classic: single column, Libertinus Serif, centered small-caps name, small-caps section titles over a thin
// full-width rule (Jake's Resume hierarchy). Black text; rules use a very dark gray, so `theme.accent` is
// deliberately unused. Strings from the data are inserted as text, never as markup; nothing calls eval.
#let theme = data.theme
#let preset = presets.at(theme.density)
#let serif = "Libertinus Serif"
#let name-size = 2.3em
#let headline-size = 1.05em
#let footer-extra = 0.12in
#let bullet-gap-em = 0.3em
#let item-gap-em = 0.75em
#let subentry-indent = 1.1em
#let rule-weight = 0.5pt
#let section-tracking = 0.04em
#let section-size = 1.12em
#let bold-weight = "bold"

#let sty = (
  accent: rgb("#222222"),
  ink: black,
  muted: rgb("#2B2B2B"),
  heavy: bold-weight,
  section-gap: preset.section_gap_pt * 1pt,
  item-gap: item-gap-em,
  bullet-gap: bullet-gap-em,
  indent: subentry-indent,
  draft: data.meta.draft,
)

#set document(title: data.meta.title, author: data.meta.author, keywords: data.meta.keywords, date: none)
#set text(font: serif, size: preset.body_pt * 1pt, lang: "en", fill: sty.ink, hyphenate: false)
#set par(leading: preset.leading_em * 1em, spacing: 0.5em, justify: false)
#set page(
  paper: theme.paper,
  margin: (x: preset.margin_in * 1in, top: preset.margin_in * 1in, bottom: preset.margin_in * 1in + footer-extra),
  footer: page-footer(sty.draft, sty),
  footer-descent: 40%,
)

#show: body => draft-highlight(sty.draft, body)

// Section heading in small caps with a thin rule beneath. Still a real heading element, so the PDF stays tagged.
#let section-title(title, sty) = {
  show heading: it => block(width: 100%, above: sty.section-gap, below: 0.45em, sticky: true)[
    #stack(
      spacing: 0.22em,
      text(weight: sty.heavy, size: section-size, tracking: section-tracking, smallcaps(it.body)),
      line(length: 100%, stroke: rule-weight + sty.accent),
    )
  ]
  heading(level: 1, outlined: false, title)
}

// Same dispatch as the shared render-section, but with this template's section title.
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

// Header: centered name in small caps, headline, then one contact line with links.
#align(center)[
  #block(below: 0.3em, text(weight: sty.heavy, size: name-size, smallcaps(data.header.name)))
  #if data.header.headline != "" {
    block(below: 0.3em, text(size: headline-size, style: "italic")[#data.header.headline])
  }
  #block(contact-line(data.header.contacts, sty))
]

#for sec in data.sections { render-section(sec, sty) }
