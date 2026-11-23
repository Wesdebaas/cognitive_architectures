# awareness_kb

The KB's configuration, preload files, queries and insertion templates, for
[TriplestarKB](https://kas-lab.github.io/triplestar_kb/bringup_package/config-files/).

```bash
ros2 launch awareness_kb bringup.launch.xml
ros2 triplestar query call count_triples
```

## SOMA

`soma-home-2.1.0.ttl` is SOMA-HOME merged with its imports into one Turtle file, made with the ontology tool [ROBOT](https://robot.obolibrary.org):

```bash
java -jar ~/tools/robot/robot.jar merge \
  --catalog ~/ros2_ws/src/soma/owl/catalog-v001.xml \
  --input   ~/ros2_ws/src/soma/owl/SOMA-HOME.owl \
  convert --format ttl \
  --output  ~/ros2_ws/src/cognitive_architectures/awareness_ros/awareness_kb/preload/soma-home-2.1.0.ttl
```
