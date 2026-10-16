# Contributing to spacetope

spacetope is dual-licensed: AGPL-3.0-or-later (see `LICENSE`) or a commercial licence from Adventurous
Systems, the copyright holder (see `COMMERCIAL.md`). It is also used in a commercial product, so every contribution must come with
clear provenance and with permission to relicense; without that, the commercial licence could not include it.
Two things are required for a change to be merged: a **DCO sign-off** on each commit, and a
one-time **CLA** acceptance.

## 1. Developer Certificate of Origin (per commit)

Sign every commit with `git commit -s`, which appends:

```
Signed-off-by: Your Name <your.email@example.com>
```

By doing that you certify the Developer Certificate of Origin 1.1:

> By making a contribution to this project, I certify that:
>
> (a) The contribution was created in whole or in part by me and I have the right to submit it under
> the open source license indicated in the file; or
>
> (b) The contribution is based upon previous work that, to the best of my knowledge, is covered under
> an appropriate open source license and I have the right under that license to submit that work with
> modifications, whether created in whole or in part by me, under the same open source license (unless
> I am permitted to submit under a different license), as indicated in the file; or
>
> (c) The contribution was provided directly to me by some other person who certified (a), (b) or (c)
> and I have not modified it.
>
> (d) I understand and agree that this project and the contribution are public and that a record of the
> contribution (including all personal information I submit with it, including my sign-off) is maintained
> indefinitely and may be redistributed consistent with this project or the open source license(s) involved.

Use your real name and a reachable email address.

## 2. Contributor License Agreement (once per contributor)

Open a pull request that adds a line to `CONTRIBUTORS.md`:

```
Your Name <your.email@example.com> — CLA accepted YYYY-MM-DD
```

By adding that line you agree that, for every contribution you make to spacetope:

1. **You keep your copyright.** You grant Adventurous Systems a perpetual, worldwide, non-exclusive,
   royalty-free, irrevocable licence to use, reproduce, modify, prepare derivative works of, publicly
   display, sublicense and distribute your contribution.
2. **You allow relicensing.** You grant Adventurous Systems the right to license your contribution under
   other terms, including proprietary and commercial terms, and to include it in commercial products.
3. **You grant patent rights** on the same terms as Apache-2.0 section 3 (as the project was licensed when
   this CLA was written), for any patent claims you can
   licence that your contribution necessarily infringes.
4. **You have the right to contribute.** The work is yours to give. If your employer or institution holds
   rights in it, you have their permission, or they sign on your behalf.
5. **No warranty.** The contribution is provided as is, without warranties of any kind.

If you cannot agree to point 2, say so in the pull request. The change can still be discussed, but it
cannot be merged.

## 3. Third-party code and dependencies

- **Do not paste code from another project** unless its licence permits it and you say where it came from.
  Apache-2.0, MIT, BSD and ISC are fine with attribution; GPL, AGPL and LGPL code must not be copied into
  this repository even though the public release is AGPL, because Adventurous Systems could not then offer
  it under a commercial licence. Add every new dependency and its licence to
  `NOTICE`.
- **Generated code.** State in the pull request if a change was written with an AI assistant, and review
  it as your own work; the sign-off covers it either way.

## 4. Working agreements

Read `CLAUDE.md` first: vocabulary, the integer-millimetre rule, and the topologicpy gotchas. Then
`docs/PLAN.md` for the milestones and their gates. A change is ready when:

- the gate for the milestone it touches passes, and earlier gates still pass:
  `.venv/bin/python -m pytest -m "gate_m0 or gate_m1 or gate_m2 or gate_m3 or gate_m4 or gate_m5 or gate_m7"`;
- browser changes pass `cd e2e && npx playwright test` (mocked) and, for anything touching the API,
  `REAL_BACKEND=1 npx playwright test`;
- new library behaviour you relied on is recorded in `docs/TOPOLOGICPY_NOTES.md`, marked `[RUN]` when you
  verified it yourself;
- decisions with a reason land in `docs/PLAN.md` §5, including the ones that did not work.

This file is not legal advice; the CLA wording deserves a lawyer's review before the project takes
outside contributions.
