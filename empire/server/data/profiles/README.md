# Malleable C2 Profiles

A collection of profiles used in [Cobalt Strike](https://www.cobaltstrike.com/) and
Empire's Malleable C2 listener. All have been tested and work with Empire.

Vendored from [BC-SECURITY/Malleable-C2-Profiles](https://github.com/BC-SECURITY/Malleable-C2-Profiles)
at commit `70becbd070547cb0057db37b4a3af90ef895d795`. These files are maintained here
now; changes go in this repository, not upstream.
Profiles live at `<Category>/<name>.profile` —
the loader derives the category from the directory name, so new profiles must go in
a category directory, not at the root.

## Licensing

These are third-party files and are not covered by Empire's own BSD-3-Clause
license. See [NOTICE.md](NOTICE.md) for provenance, the licenses that
apply, and what is known about the sources that offer none.

## Acknowledgements

Thank you to the following repos for generating and publishing many of these.

- [rsmudge](https://github.com/rsmudge/Malleable-C2-Profiles)
- [xx0hcd](https://github.com/xx0hcd/Malleable-C2-Profiles)
- [threatexpress](https://github.com/threatexpress/malleable-c2)
- [yeyintminthuhtut](https://github.com/yeyintminthuhtut/Malleable-C2-Profiles-Collection)
- [bluscreenofjeff](https://github.com/bluscreenofjeff/MalleableC2Profiles)
- [mhaskar](https://github.com/mhaskar/MalleableC2-Profiles)
- [kphongagsorn](https://github.com/kphongagsorn/c2-profiles)

## Documentation

- [A Deep Dive into Cobalt Strike Malleable C2](https://posts.specterops.io/a-deep-dive-into-cobalt-strike-malleable-c2-6660e33b0e0b)
- [Malleable C2 Documentation](https://www.cobaltstrike.com/help-malleable-c2)
- [Empire: Malleable C2 Profiles](https://www.bc-security.org/post/empire-malleable-c2-profiles/)
