# element_types.md — Type-level vs instance-level parameter management

## Overview

Every family type carries a **type-level default** for each parameter. Instances
inherit those defaults unless they explicitly override them with per-instance
params. The resolution order is:

```
instance.params  →  type.params  →  param.default
```

Changing a type-level param via `bulk_set_type_param` affects **all**
instances that don't have their own override — without touching the instance
records themselves.

## Tools

### bulk_set_type_param

Change the type-level default for a single param.

```json
{
  "family_file_id": "<uuid>",
  "type_id": "type-600x900",
  "param_name": "Glazing",
  "value": "triple"
}
```

All windows of type `type-600x900` now report `"triple"` for `Glazing` unless
an instance has its own `params.Glazing` override.

### apply_type_to_instance

Retarget an existing instance to a different type (the instance retains its
per-instance overrides but adopts the new type's defaults).

```json
{
  "host_file_id": "<uuid>",
  "instance_id": "<uuid>",
  "type_id": "type-900x1200"
}
```

### report_type_usage

Scan all `.bim` files for instances using a given type. Returns a total count
and per-host breakdown.

```json
{
  "family_file_id": "<uuid>",
  "type_id": "type-600x900"
}
```

### clone_type

Duplicate a type with a new id and name. The clone starts with identical
param values; neither the original nor its instances are affected.

```json
{
  "family_file_id": "<uuid>",
  "source_type_id": "type-600x900",
  "new_name": "600x900 Triple-Glazed"
}
```

### delete_type

Remove a type definition. If `reassign_to` is provided, every instance using
the deleted type is updated to point to `reassign_to`. Without `reassign_to`,
instances retain their `type_id` reference but fall back to param defaults.

```json
{
  "family_file_id": "<uuid>",
  "type_id": "type-600x900",
  "reassign_to": "type-900x1200"
}
```

## Workflow examples

### 1. Bulk-change all windows to triple-glazed

A client wants every window to be triple-glazed. Rather than editing each
instance individually, change the type default:

```
bulk_set_type_param(
  family_file_id = "<window-family-uuid>",
  type_id        = "type-600x900",
  param_name     = "Glazing",
  value          = "triple"
)
```

Any instance that already has `params: { Glazing: "double" }` retains its
override. Instances without an explicit override now resolve `Glazing = triple`
from the type. To also clear per-instance overrides, iterate each instance
and use `update_instance` to remove or update the `Glazing` key.

### 2. Swap a beam type across an entire floor

Renumbering `W12x26` to `W14x30` for all beams on level 3:

```
# 1. Clone the new beam type from the old one
clone_type(
  family_file_id  = "<beam-family-uuid>",
  source_type_id  = "W12x26",
  new_name        = "W14x30"
)
→ returns new_type.id = "type-abc123"

# 2. Apply it to every instance on level 3
report_type_usage(family_file_id, "W12x26")
→ returns host file ids and instance counts

# For each host file:
apply_type_to_instance(host_file_id, instance_id, "type-abc123")
```

Or atomically reassign all at delete time:

```
delete_type(
  family_file_id  = "<beam-family-uuid>",
  type_id         = "W12x26",
  reassign_to     = "type-abc123"
)
→ all W12x26 instances are now W14x30
```