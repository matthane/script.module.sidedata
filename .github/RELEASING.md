# Cutting a release

Checklist for publishing a new version of this addon.

1. Bump the version in `addon.xml`. Kodi addon versions must increase for
   Kodi to offer an update, so this has to happen even for small changes.
   Update the `<news>` element in the same file while you are there; that
   is what Kodi shows in the add-on information dialog.
2. Update the version notes in `NOTICE.md` and `README.md` if the change
   touches the bundled library or its pinned versions (see UPDATING.md).
3. Run the local test suite: `python3 -m unittest discover tests`. On a
   host without a matching native libdovi build, or without the external
   fixture directory, the golden tests skip; that is expected, see
   UPDATING.md for where the fixtures live.
4. Commit the version bump.
5. Tag the commit `vX.Y.Z`, matching the `addon.xml` version exactly. For
   example, if `addon.xml` says version `1.3.0`, tag `v1.3.0`.
6. Push the tag. `.github/workflows/release.yml` picks it up, checks the
   tag matches `addon.xml`, builds `script.module.sidedata-X.Y.Z.zip` from
   a plain `git archive` of the tagged commit, and attaches it to a new
   GitHub Release.
7. Open the CoreELEC pull request, without which nothing reaches users
   through the add-on repository. See "Where this ships" below.

The release zip is exactly what `git archive` produces once
`.gitattributes` export-ignore rules are applied: `tests/`, `tools/` and
the whole `.github/` tree, which holds this file, `UPDATING.md` and the
GitHub Actions configuration, are all dropped. `addon.xml`, `FIELDS.md`,
`README.md`, `NOTICE.md`, `LICENSE.txt`, `LICENSES/`, `resources/` and the
bundled `lib/` tree, including `native_libs/`, all ship.

Nothing validates those contents automatically. `kodi-addon-checker` used
to run here, but it enforces Kodi add-on repository policy, and this addon
ships through CoreELEC, which uses neither that repository nor that tool.
Its rules were never ours to satisfy, and its icon size rule actively
conflicts with CoreELEC's own convention.

Two things it did catch, worth checking by hand before tagging:

- `lib/sidedata/native_libs/aarch64/libdovi.so` must stay non-executable
  in git, so `git ls-files -s` reports mode `100644` for it. A shared
  library needs no execute permission to be opened through `ctypes.CDLL`.
- Anything added outside the `.gitattributes` export-ignore rules reaches
  the zip. `git archive --format=tar HEAD | tar -t` lists what ships.

## Where this ships

Through CoreELEC. Their distro repo carries a `package.mk` under
`packages/addons/script/`, which pulls a tarball of this repo pinned by
commit SHA; the source itself is never copied into their tree. GitHub's
archive endpoint honours `export-ignore`, so what they receive is the same
file set as the release zip above.

Publishing a new version is therefore two steps, not one: tag here, then
open a pull request against `CoreELEC/CoreELEC` bumping `PKG_VERSION` to
the new commit SHA and `PKG_SHA256` to its hash. There is no self-service
path and no way to hotfix, so their review and release cadence sets how
fast a fix reaches anyone.

CoreELEC's build appends its own `PKG_REV` to whatever version `addon.xml`
declares, rewriting the file in place, so `1.2.2` reaches users as
`1.2.2.0`. Keep three components here and let them add the fourth. Addons
depending on this one should import the version tagged here, since Kodi
treats `<import>` as a minimum and the four-part version satisfies it.

Their packaging can also fold a `changelog.txt` into the addon's news
field, but it does so by substituting `@PKG_ADDON_NEWS@` in the `addon.xml`
being built. This addon ships its own `addon.xml`, which carries no such
placeholder, so that step is a no-op here. Anything worth showing in
Kodi's add-on information dialog has to be a `<news>` element maintained
in `addon.xml` directly, which is what this addon does, and why there is
no `changelog.txt` in this repo.

The GitHub Release remains the direct-install route for anyone sideloading
(Add-ons, install from zip file).
