#let data = json(sys.inputs.at("data", default: "render.json"))
#let presets = json(sys.inputs.at("presets", default: "presets.json"))
#import "common.typ": *

// sidebar: two-column layout — summary and experience in the main column; skills, certifications,
// and education in a shaded right rail. Less ATS-safe than modern and classic. Source Sans 3.
#let theme = data.theme
#let preset = presets.at(theme.density)
#let sans = "Source Sans 3"
#let name-size = 22pt
#let headline-size = 1.05em
#let footer-extra = 0.12in
#let bullet-gap-em = 0.32em
#let item-gap-em = 0.72em
#let subentry-indent = 0.85em
#let sidebar-fill = rgb("#F0F3F7")
#let sidebar-kinds = ("skills", "certifications", "education")

#let sty = (
  accent: rgb(theme.accent),
  ink: rgb("#1A1A1A"),
  muted: rgb("#4A4A4A"),
  heavy: 600,
  section-gap: preset.section_gap_pt * 1pt,
  item-gap: item-gap-em,
  bullet-gap: bullet-gap-em,
  indent: subentry-indent,
  draft: data.meta.draft,
)

#let is-sidebar(sec) = sidebar-kinds.contains(sec.kind)
#let main-sections = data.sections.filter(sec => not is-sidebar(sec))
#let side-sections = data.sections.filter(is-sidebar)

#set document(title: data.meta.title, author: data.meta.author, keywords: data.meta.keywords, date: none)
#set text(font: sans, size: preset.body_pt * 1pt, lang: "en", fill: sty.ink, hyphenate: false)
#set par(leading: preset.leading_em * 1em, spacing: 0.45em, justify: false)
#set page(
  paper: theme.paper,
  margin: (x: preset.margin_in * 1in, top: preset.margin_in * 1in, bottom: preset.margin_in * 1in + footer-extra),
  footer: page-footer(sty.draft, sty),
  footer-descent: 40%,
)

#show: body => draft-highlight(sty.draft, body)

#block(below: 0.35em, text(weight: sty.heavy, size: name-size, fill: sty.accent)[#data.header.name])
#if data.header.headline != "" {
  block(below: 0.4em, text(size: headline-size, fill: sty.muted)[#data.header.headline])
}
#block(below: 0.55em, contact-line(data.header.contacts, sty))

#grid(
  columns: (1.62fr, 1fr),
  column-gutter: 0.55in,
  align: (left, top),
  [
    #for sec in main-sections { render-section(sec, sty) }
  ],
  [
    #block(
      width: 100%,
      fill: sidebar-fill,
      inset: (x: 0.45em, y: 0.5em),
      radius: 3pt,
    )[
      #for sec in side-sections { render-section(sec, sty) }
    ]
  ],
)
