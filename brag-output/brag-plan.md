# Antibody — brag plan

**What it is:** An autonomous repair agent that fixes a SQL injection in a live web app, then proves search still works before the fix is allowed to ship.
**For:** Teams who want security fixes from an agent without the agent "fixing" things by breaking the product.
**What sets it apart:** The agent doesn't grade its own work. An independent check suite it never sees decides, and the host refuses to deploy anything that didn't pass.
**Most impressive claim:** One query (`xyz')) OR 1=1--`) against our public Juice Shop deployment returns 24 credential-shaped rows (recorded external probe). After the patch, the same probe returns 0, and apple/banana/lemon/raspberry/juice still return 3/1/1/2/35 products.
**Funniest claim:** A patch that "fixes" the injection by making search return nothing passes the injection check and still gets rejected. Its own pitch line: *closes a security hole without closing the business.*
**Visual hook:** A typed attack URL, then a wall of redacted credential rows pouring out.
**Real UI/flow:** Request → leaked rows → Semgrep finding at `routes/search.ts:23` → the parameterized `replacements` diff → check rows with pass pills (the dashboard's own style) → REJECTED mutant.
**Tone:** `default`, leaning dark and technical. Punchy, clean, with one dry joke.
**Share caption:** see share-copy.txt.

## Honesty guardrails
- Leak count: 24, from B's public probe (B-checklist B2). Check numbers come from `artifacts/*.json`.
- The public deploy of the *fixed* candidate hasn't run yet, so the video never says "now live". It states the host rule instead: only a passing patch ships.
- Leaked rows are fully redacted on screen.

## Visual identity
Taken from the evidence dashboard (`src/web/src/index.css`, dark tokens): bg #141517 → deeper #0e0f11, panel #1c1e21, line #2c2f33, text #e8e9ea, muted #9a9ea4, accent #8aa9ff, ok #8fd9a8/#173323, bad #f3a197/#3a1c19. System UI sans plus ui-monospace, as in the dashboard. Pill style reused verbatim.

## Storyboard (22.0s, 30fps, 1920×1080, 120 bpm so cuts land on beats)
| # | Time | Scene | On screen |
|---|---|---|---|
| 1 Hook | 0.0–3.5 | The leak | `GET /rest/products/search?q=` types `xyz')) OR 1=1--`; "200 OK · 24 rows" counts up; redacted rows flood. Headline: **One search query. 24 leaked credentials.** |
| 2 Reveal | 3.5–7.5 | Antibody | Glyph and wordmark. Line: **Closes a security hole without closing the business.** |
| 3 Find & fix | 7.5–11.5 | Semgrep + Guild | Finding card (`routes/search.ts:23`, express-sequelize-injection, CWE-89); the diff's red lines, then green `replacements` lines. Caption: **Semgrep finds it. A Guild agent writes the patch.** |
| 4 Prove | 11.5–15.5 | Independent checks | 7 rows tick to pass: 5 ordinary searches with real counts, injection 24→0 rows, /api/Users 401. Caption: **Search still works. The attack returns nothing.** |
| 5 Reject | 15.5–19.0 | The joke | Candidate `WHERE 1=0`: injection 0 rows ✓, "apple" 0 of 3 ✗, then a REJECTED stamp. Caption: **Closed the hole by closing the business? Rejected.** |
| 6 Outro | 19.0–22.0 | Ship rule | Wordmark, **Only a verified patch ships.**, sponsors, github.com/hackathon-corner/antibody |

Transitions: old content fades out over 0.2s, then a dip through the background, then new content staggers in. No crossfades.

## Sound
A minor, 120 bpm. Hook: low A drone, a filtered noise riser, quiet key clicks, and a low sub hit when the rows flood. The drop at 3.5s brings in a soft four-on-the-floor kick, hats, and an Am–F–C–G pad with a pluck arpeggio. Check ticks are A-minor pentatonic plucks rising under the music. The reject is a muffled low thud on F→E. The outro resolves to Am with a bell, and the tail fades.
