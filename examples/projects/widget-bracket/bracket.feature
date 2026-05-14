{
  "version": 1,
  "name": "L-bracket feature tree",
  "features": [
    {
      "id": "pad-1",
      "op": "pad",
      "sketch_path": "/bracket.sketch",
      "height": 3,
      "direction": "up"
    },
    {
      "id": "hole-1",
      "op": "hole",
      "target_id": "pad-1",
      "sketch_path": "/bracket.sketch",
      "diameter": 4,
      "depth": 8
    },
    {
      "id": "hole-2",
      "op": "hole",
      "target_id": "pad-1",
      "sketch_path": "/bracket.sketch",
      "diameter": 4,
      "depth": 8
    },
    {
      "id": "hole-3",
      "op": "hole",
      "target_id": "pad-1",
      "sketch_path": "/bracket.sketch",
      "diameter": 4,
      "depth": 8
    },
    {
      "id": "hole-4",
      "op": "hole",
      "target_id": "pad-1",
      "sketch_path": "/bracket.sketch",
      "diameter": 4,
      "depth": 8
    },
    {
      "id": "fillet-1",
      "op": "fillet",
      "target_id": "pad-1",
      "edge_filter": "all",
      "radius": 1
    }
  ],
  "metadata": {}
}
