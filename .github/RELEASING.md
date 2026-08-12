# Cutting a release

Checklist for publishing a new version of this addon.

1. Bump the version in `addon.xml`. Kodi addon versions must increase for
   Kodi to offer an update, so this has to happen even for small changes.
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

The release zip is exactly what `git archive` produces once
`.gitattributes` export-ignore rules are applied: `tests/`, `tools/` and
the whole `.github/` tree, which holds this file, `UPDATING.md` and the
GitHub Actions configuration, are all dropped. `FIELDS.md`, `README.md`,
`NOTICE.md`, `LICENSE.txt`, `LICENSES/`, and the bundled `lib/` tree,
including `native_libs/`, all ship.

`.github/workflows/check.yml` runs the same `git archive` step against
every push and pull request and feeds the result to `kodi-addon-checker`,
so any file that would break the release build is caught before a tag is
ever pushed.

## Where this ships

There is no established CoreELEC addon submission process for third-party
Python addons yet. CoreELEC ships its own repository addon built from
packages in the CoreELEC git tree, which is a different thing from a
community addon repo. Until a CE venue exists, the GitHub Release built
by this workflow is the distribution channel: users install from the zip
directly (Add-ons, install from zip file).

`release.yml` includes a commented-out job for `kodi-addon-submitter`,
shaped after `script.audiooffsetmanager.evolved`'s own submission job, so
the workflow is ready to enable the day a submission venue is confirmed.
