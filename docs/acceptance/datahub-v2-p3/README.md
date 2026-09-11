# DataHub V2 P3 status-patch replay

The original low-Beta strategy was replayed locally for 2023-09-01 through
2023-09-28 against the old release `Rb60ab5f94b2a612b` and the new status-patch
release `R6c4d2b9c79fc882d`.

Both completed successfully and produced the identical result hash
`e24bd0d3d892ddc26c5aeafcd2b78c343e380432ebef251caa6aef1f8e07a745`.
The old run took 36.503 seconds; the new run took 35.803 seconds. Full machine
output is in `status-patch-replay.json`.

The result does not imply the patch is unused. It means the three patched
securities were not part of this strategy's effective state-dependent path in
this window. A separate `get_extras` replay proves the new release reads all
three records. Old release replay remains fixed and unchanged.
