# Series bible: 걷어차인 회장님 (The Chairman They Kicked Aside)

This is the series bible for a vertical micro-drama (short-drama / 단편 드라마) built with
`shortsfactory`. It defines the premise, the look, the cast, and the hard format rules
that every episode follows. Episode 1 is authored as data in
`src/shortsfactory/story/episodes.py`; this document is the human-readable companion to
that data. Where the two disagree, the code is the source of truth.

## Premise

A chaebol-heir romance, deliberately subverted.

The familiar version of this story has a powerful heir who rescues and reshapes an
ordinary woman. This series inverts every beat of that:

- The heir is the one who is exposed, humiliated, and chasing.
- The ordinary woman is the one who holds the upper hand, and she is hiding her own
  identity and her own agenda.
- The "rescue" is not kindness. She was already there, already watching, already ahead of
  him.

The engine of the series is status reversal plus hidden identity. The audience thinks they
are watching a rags-to-riches meet-cute, and every episode peels that back to show
something colder underneath: she did not stumble into his world, she came for it.

The tone is emotionally intense. There is no sexual content. The heat comes from power,
secrets, recognition, and dread, not from romance-as-fan-service.

## Visual style

Well-drawn, webtoon / anime-style illustrated characters. Not photoreal.

- Characters read as drawn figures with clean lines and strong color blocking, in the
  spirit of a Korean webtoon or a stylized anime key visual.
- Each character has a consistent key visual: the same hair silhouette, palette, and
  wardrobe accent in every scene, so the cast stays recognizable across the episode and
  across the series.
- Framing is moody and cinematic: two-stop mood gradients, a soft focal glow on the staged
  character, a vignette, and directed effects (rain for the rainy hook, a breaking-news
  lower-third band for the news beat, a brief white flash on a twist cut).

Reality note for the shipped sample: the committed `samples/ep01.mp4` was rendered on the
fully offline path, so the on-screen characters are code-generated stylized figures (a
deterministic vector-style bust built from each character's visual spec), not hand-drawn
art. True "well-drawn manga" quality comes from supplying real character art per the
drop-in convention documented in the README, or wiring an image provider. The style target
above is what the series is for; the offline figure is the stand-in that proves the engine
end to end.

## Cast

The three roles below match the `Character` / `VisualSpec` definitions in
`src/shortsfactory/story/episodes.py` exactly.

### 강유진 (Kang Yoo-jin): male lead

- Role: the chaebol heir. The Daeyang Group (대양그룹) heir.
- Character: used to deference, now stripped of it. In Episode 1 he is the one who was
  left in the rain, the one who has to come back and ask why she did not turn him in. He
  reads her reversal as opportunity (he offers her a job) and misreads it completely.
- Visual design: cool-toned corporate palette. Navy-steel suit accent. Dark, swept hair.
  Warm skin tone. A cool navy mood gradient (top around deep navy, bottom near-black). He
  is drawn centered.

### 서하은 (Seo Ha-eun): female lead

- Role: the ordinary convenience-store clerk who secretly holds the upper hand.
- Character: outwardly an unremarkable part-time worker; actually the one in control. She
  watched him fall and did nothing. She knew he was poisoned, not drunk, and she knew it
  from the start. When the news names him a Daeyang heir, she does not feel awe; she feels
  a cold, resigned recognition, because that is the name she came to destroy.
- Visual design: warm-but-muted palette, clearly distinct from the male lead. Deep-crimson
  apron accent. Long dark hair. Warm skin tone. A muted wine mood gradient (top around a
  dusky rose-brown, bottom near-black). She is drawn centered. Her hair shape, placement,
  and wardrobe color are intentionally different from the male lead so the two never blur
  together.

### 뉴스 속보 (Breaking News anchor): supporting

- Role: the broadcast voice for the breaking-news beat that reveals 강유진's identity.
- Character: not a person in the drama so much as the mechanism that detonates Twist 2. A
  neutral news-anchor presence.
- Visual design: neutral broadcast palette (near-black studio gradient), breaking-news red
  accent, short bob hair. Appears with the "속보 BREAKING" lower-third band.

## Format rules

Every episode in this series obeys the same format so the series stays bingeable and the
engine stays simple:

- Vertical 9:16, 1080x1920.
- About 60 seconds per episode. Episode 1 totals roughly 60.5 seconds across 12 scenes.
- A fixed four-beat spine: HOOK, then TWIST 1, then TWIST 2, then CLIFFHANGER. The goal is
  three escalating turns inside a single minute.
- Korean dialogue and narration, burned in as captions, rendered with a Korean-capable
  font.
- Every episode ends on a cliffhanger. No episode resolves cleanly; each one closes on a
  question or a reveal that forces the next episode. Episode 1 ends on the torn job card
  and the old photo bearing the Daeyang family crest slipping from her apron, then
  "다음 화에 계속" (to be continued).

## Logline

빗속에 버려진 재벌 후계자, 그를 구한 평범한 그녀는 사실 그 가문을 무너뜨리러 왔다.

(The chaebol heir abandoned in the rain; the ordinary woman who saved him in fact came to
bring his family down.)
