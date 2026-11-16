# awareness_kb - TriplestarKB Bringup Package

This generated package contains the scenario-specific configuration, queries,
functions, preload data, and insertion templates used to bring up TriplestarKB.
Its launch file delegates to `triplestar_bringup`, selects this package as the
configuration source, and can optionally enable the geometry visualizer.

Launch it with:

```bash
ros2 launch awareness_kb bringup.launch.xml
```

See the [TriplestarKB configuration documentation](https://kas-lab.github.io/triplestar_kb/bringup_package/config-files/)
for configuration fields and package contents.
