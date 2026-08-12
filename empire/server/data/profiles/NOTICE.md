# Third-party notices for the bundled Malleable C2 profiles

Empire itself is BSD-3-Clause (see its `LICENSE` file, at the root of a
checkout or source archive and under `.dist-info/licenses/` in an installed
wheel).
The profiles in this directory are third-party content and are **not** covered
by that license. This file records what is known about each one.

These profiles previously reached users through a git submodule, which meant
they were absent from release archives. They are now vendored, so they ship in
release tarballs, "Download ZIP" archives, container images, and — since
`packages` in `pyproject.toml` became a directory include — the Python sdist
and wheel. This file and the texts in `LICENSES/` are carried in all of them.
This file exists because that change is what makes the notices below
obligatory.

Provenance was determined by comparing every bundled profile against fresh
clones of the seven upstream repositories, matching on content rather than on
filename. Content is compared with line endings normalized and trailing
whitespace stripped from each line and from the end of the file, so a file
differing from its upstream only in those respects counts as a match; on raw
bytes some of the counts below would be lower and none would be higher. Where a
file appears in more than one upstream, every match is listed — several of these
collections republish each other, so a single origin cannot be asserted.

Upstreams keep changing, so the counts below describe these commits:

| Upstream | Commit compared against |
| --- | --- |
| threatexpress/malleable-c2 | `a08f7b2c0e9ad70fc5bdbda5acac97b1152d54b8` |
| bluscreenofjeff/MalleableC2Profiles | `5c432bb36ff708056fe014998a933b78ecd0d5d8` |
| rsmudge/Malleable-C2-Profiles | `26323784672913923d20c5a638c6ca79459e8529` |
| yeyintminthuhtut/Malleable-C2-Profiles-Collection | `b1dc3b83c018dcbf6b823f9027c928d07949a063` |
| xx0hcd/Malleable-C2-Profiles | `008b42a9e4c200c1964adc7fa1d5de5e00991a86` |
| kphongagsorn/c2-profiles | `29fe50eaad655ddd0028fca06a9c7785e3ffaf41` |
| mhaskar/MalleableC2-Profiles | `4432c64effce56134bbcc10836b4d813c09049ac` |

## GPL-3.0

`Normal/jquery-c2.4.2.profile` comes from the file of the same name in
[threatexpress/malleable-c2](https://github.com/threatexpress/malleable-c2),
which is licensed GPL-3.0. Authors, per the header the file still carries:
`@joevest`, `@andrewchiles`, `@001SPARTaN`.

Full license text: [`LICENSES/GPL-3.0.txt`](LICENSES/GPL-3.0.txt).

The profile is a configuration file consumed at runtime. Empire is not derived
from it and it is not derived from Empire, so the two are aggregated rather
than combined. It is the only file here traced to a GPL-3.0 source.

## BSD-3-Clause

Seven profiles match
[bluscreenofjeff/MalleableC2Profiles](https://github.com/bluscreenofjeff/MalleableC2Profiles),
which is BSD-3-Clause and requires that its copyright notice be retained:

> Copyright (c) 2016, Jeff Dimmock
> All rights reserved.

Full license text:
[`LICENSES/BSD-3-Clause-bluscreenofjeff.txt`](LICENSES/BSD-3-Clause-bluscreenofjeff.txt).

- `Normal/bingsearch_getonly.profile` — also in rsmudge, yeyintminthuhtut
- `Normal/cnnvideo_getonly.profile` — also in rsmudge
- `Normal/googledrive_getonly.profile` — also in rsmudge
- `Normal/microsoftupdate_getonly.profile` — also in rsmudge
- `Normal/msnbcvideo_getonly.profile` — also in rsmudge
- `Normal/onedrive_getonly.profile` — also in rsmudge
- `Normal/wikipedia_getonly.profile` — also in rsmudge

All seven are also present in `rsmudge/Malleable-C2-Profiles`, which
carries no license. The notice above is retained on the basis that these files
match a BSD-3-Clause distribution; it is not an assertion about which
collection published them first.

## Sources that grant no license

These upstreams carry no `LICENSE` file, so no redistribution terms are
offered and none can be inferred. This is recorded rather than resolved.

| Upstream | Bundled profiles matching it |
| --- | --- |
| [rsmudge/Malleable-C2-Profiles](https://github.com/rsmudge/Malleable-C2-Profiles) | 27 |
| [yeyintminthuhtut/Malleable-C2-Profiles-Collection](https://github.com/yeyintminthuhtut/Malleable-C2-Profiles-Collection) | 26 |
| [xx0hcd/Malleable-C2-Profiles](https://github.com/xx0hcd/Malleable-C2-Profiles) | 1 |
| [kphongagsorn/c2-profiles](https://github.com/kphongagsorn/c2-profiles) | 2 |
| [mhaskar/MalleableC2-Profiles](https://github.com/mhaskar/MalleableC2-Profiles) | 1 |

Counts overlap, because these collections share files with each other.

[BC-SECURITY/Malleable-C2-Profiles](https://github.com/BC-SECURITY/Malleable-C2-Profiles),
the repository these files were vendored from, also carries no `LICENSE` file.

## Files with no upstream match

Thirty-two of the 76 profile files here — the 75 the loader ships plus
`template.profile` — match no upstream under the normalization described above.
Most are not original: twenty-seven are 75% or more similar to an upstream
profile, and twenty-one of those are 90% or more similar, so they are
adaptations rather than new work. The remaining five resemble nothing upstream
closely enough to attribute. Similarity is `difflib.SequenceMatcher` ratio
against the closest normalized upstream file.

No authorship claim is made for these files in either direction. An absent
match means only that no upstream copy is identical today.
