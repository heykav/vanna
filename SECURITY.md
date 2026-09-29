# Security

vanna is a pricing/backtesting library and a static demo page - it doesn't
hold user accounts, doesn't process payments, and the browser demo never
sends anything to a server (it's client-side Pyodide; see the README).
That keeps the realistic attack surface small, but not zero:

- **The core library** takes numeric parameters and does math on them. The
  main class of real bug here is a bad/adversarial input (non-positive
  spot, non-finite rate, etc.) reaching deep into pricing code and either
  crashing with a confusing error or - worse - silently producing a wrong
  number. `vanna.pricing.black_scholes.validate_option_inputs` and the
  checks in `vanna.backtest.engine.run_backtest` exist specifically to
  fail loudly and immediately at the boundary instead.
- **The web demo** (`docs/`) loads Pyodide and Chart.js from jsdelivr with
  Subresource Integrity hashes pinned, and ships a Content-Security-Policy
  restricting script/style/connect sources to `'self'` plus that one CDN
  origin. Two honest limits on that: SRI only covers the top-level
  `pyodide.js`/`chart.js` `<script>` tags - it can't cover the WASM/zip
  files Pyodide fetches internally after that, since those aren't loaded
  via tags the browser can integrity-check. And `frame-ancestors` /
  `X-Frame-Options` aren't set at all, because GitHub Pages doesn't let a
  static site add custom response headers and a `<meta>` CSP can't carry
  `frame-ancestors` - so clickjacking protection genuinely isn't present
  here, rather than quietly assumed.

## Supported versions

There are no tagged releases yet. Only the latest commit on `main` is
supported; fixes are made there and not backported.

## Reporting a vulnerability

Please do not report security problems in a public issue.

1. Preferred: use GitHub's private
   ["Report a vulnerability"](https://github.com/heykav/vanna/security/advisories/new)
   flow on this repo (GitHub private vulnerability reporting).
2. If that is unavailable to you, email the owner at
   heykavofficial@gmail.com.

This is a personal project maintained by one person. Response is
best-effort: there is no guaranteed response time or fix timeline, and no
bug bounty. A real report will be read, and I will say what I plan to do
about it. Please allow reasonable time before disclosing publicly.

Wrong numbers from the pricing or backtest code (a Greek that disagrees
with a reference value, for example) are ordinary bugs, not security
issues; a normal public issue is the right place for those.
