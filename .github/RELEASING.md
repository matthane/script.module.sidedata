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

Nothing validates those contents automatically. Two things to check by
hand before tagging:

- `lib/sidedata/native_libs/aarch64/libdovi.so` must stay non-executable
  in git, so `git ls-files -s` reports mode `100644` for it. A shared
  library needs no execute permission to be opened through `ctypes.CDLL`.
- Anything added outside the `.gitattributes` export-ignore rules reaches
  the zip. `git archive --format=tar HEAD | tar -t` lists what ships.

## Where this ships

Through CoreELEC. Their distro repo carries a `package.mk` that pulls a
tarball of this repo pinned by release tag; the source itself is never
copied into their tree. GitHub's archive endpoint honours `export-ignore`,
so what they receive is the same file set as the release zip above.

Nothing is agreed with CoreELEC yet, so the path below is our proposal, not
a settled fact. Best fit is
`projects/Amlogic-ce/packages/addons/script/sidedata/package.mk`, with
`PKG_NAME="sidedata"` and `PKG_SECTION="script.module"`. That project
directory is where their Amlogic-only addons live, which this is, and the
addon id is built as `${PKG_SECTION}.${PKG_NAME}`, so those two values are
what keeps it `script.module.sidedata`. `packages/addons/script/steamlink`
is the same shape one level up, section `script.program` and name
`steamlink`. The `script` directory rather than `service` follows the addon
id, not the extension point order, so the addon presenting as a service in
Kodi does not move it.

`PKG_ADDON_TYPE` only picks a template `addon.xml` for packages that ship
none. This one ships its own, so the value is inert here and CoreELEC's
build edits nothing in it but the version.

Publishing a new version takes two steps: tag here, then open a pull
request against `CoreELEC/CoreELEC` titled `sidedata: bump package to
X.Y.Z`. Pin `PKG_VERSION` to the new release tag, for example `1.4.2`,
not the raw commit SHA, and set `PKG_SHA256` to the hash of
`archive/vX.Y.Z.tar.gz`. `PKG_URL` needs the `v` prefix in front of
`${PKG_VERSION}` for that archive path to resolve. Pin to the tag rather
than the commit SHA: hashing a commit-pinned download is redundant once
the SHA already pins the content, while hashing a tagged download is a
real integrity check. There is no self-service path and no way to
hotfix, so their review and release cadence sets how fast a fix reaches
anyone.

CoreELEC's build appends its own `PKG_REV` to whatever version `addon.xml`
declares, rewriting the file in place, so `1.3.0` reaches users as
`1.3.0.0`. Keep three components here and let them add the fourth. Addons
depending on this one should import the version tagged here, since Kodi
treats `<import>` as a minimum and the four-part version satisfies it.

Release notes live in the `<news>` element of `addon.xml`. CoreELEC's
packaging can fold a `changelog.txt` into that field instead, but only by
substituting `@PKG_ADDON_NEWS@` into the `addon.xml` it builds, and this
addon ships its own, so that route does nothing here.

The GitHub Release is the direct-install route for anyone sideloading
(Add-ons, install from zip file).
