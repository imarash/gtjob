#let data = json(sys.inputs.at("data", default: "render.json"))
#let presets = json(sys.inputs.at("presets", default: "presets.json"))
#import "common.typ": *

// modern: single column, Source Sans 3, accent on the name and the section rules only.
#let theme = data.theme
#let preset = presets.at(theme.density)
#let sans = "Source Sans 3"
#let name-size = 24pt
#let headline-size = 1.1em
#let footer-extra = 0.12in
#let bullet-gap-em = 0.34em
#let item-gap-em = 0.8em
#let subentry-indent = 0.9em

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

#set document(title: data.meta.title, author: data.meta.author, keywords: data.meta.keywords, date: none)
#set text(font: sans, size: preset.body_pt * 1pt, lang: "en", fill: sty.ink, hyphenate: false)
#set par(leading: preset.leading_em * 1em, spacing: 0.5em, justify: false)
#set page(
  paper: theme.paper,
  margin: (x: preset.margin_in * 1in, top: preset.margin_in * 1in, bottom: preset.margin_in * 1in + footer-extra),
  footer: page-footer(sty.draft, sty),
  footer-descent: 40%,
)

#show: body => draft-highlight(sty.draft, body)

// Header: name, headline, contacts. Left-aligned so extraction reads name first.
#block(below: 0.3em, text(weight: sty.heavy, size: name-size, fill: sty.accent)[#data.header.name])
#if data.header.headline != "" {
  block(below: 0.35em, text(size: headline-size, fill: sty.muted)[#data.header.headline])
}
#block(contact-line(data.header.contacts, sty))

#for sec in data.sections { render-section(sec, sty) }
