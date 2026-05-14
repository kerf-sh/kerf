# License

Kerf is open-source software. You can read, modify, and redistribute the entire
codebase — including the bits that power our hosted service — under the MIT
license.

## TL;DR

You can:

- **Use Kerf for anything**, including commercial work, with no fee.
- **Modify it.** Fork the repo, change what you want, ship your version.
- **Redistribute it.** Bundle Kerf into your own product, or run it as a
  service for your customers.
- **Sell it.** You don't owe us a cut. Charge whatever you like.
- **Self-host the cloud.** The code that runs `kerf.app` is in the same public
  repo, under the same license. If you want to operate your own hosted Kerf,
  you can.

You have to:

- **Keep the copyright notice and license text** in any copy or substantial
  portion of the software you distribute.

That's it.

## The full text

Verbatim from the [`LICENSE`](https://github.com/kerf-sh/kerf/blob/main/LICENSE)
file at the repository root:

```
MIT License

Copyright (c) 2026 Imran Paruk

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## Third-party components

Kerf depends on a number of open-source libraries — three.js, JSCAD, OpenCascade
(via opencascade.js), planegcs, tscircuit, React, Tailwind, and others. Each
ships under its own license (mostly MIT, Apache 2.0, or LGPL). Their license
texts travel with the source in `node_modules/` and the compiled bundles. Run
`npm ls` in a checkout to see the full list.

## A note on intent

The MIT license is short on purpose. We picked it because we want Kerf to be
useful — to hobbyists, to small shops, to companies, to other tools that want
to embed parametric CAD. If you find yourself wishing the license said more,
chances are MIT already lets you do the thing.

If you're unsure whether a particular use is allowed: it almost certainly is.
If you'd like to talk anyway, drop us a line at the contact address in
[Privacy](/docs/privacy) or [Terms](/docs/terms).
