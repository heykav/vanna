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

## Reporting a vulnerability

Please [open an issue](https://github.com/heykav/vanna/issues/new) or, for
anything you'd rather not post publicly, use GitHub's private
["Report a vulnerability"](https://github.com/heykav/vanna/security/advisories/new)
flow on this repo. There's no bug bounty - this is a personal project -
but a real report will get read and fixed.
