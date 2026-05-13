// Package assembly contains the typed Go structs for assembly document content,
// including components and 3D mates (SolveSpace solver). These structs map
// directly to the JSON shape in .assembly files.
package assembly

import (
	"encoding/json"
	"fmt"
	"strings"
)

// MateType represents the seven geometric constraint types.
type MateType string

const (
	MateCoincident   MateType = "coincident"
	MateConcentric   MateType = "concentric"
	MateParallel     MateType = "parallel"
	MatePerpendicular MateType = "perpendicular"
	MateDistance     MateType = "distance"
	MateAngle       MateType = "angle"
	MateTangent     MateType = "tangent"
)

// MateFeature represents the geometric entity type on a component.
type MateFeature string

const (
	MateFeatureFace   MateFeature = "face"
	MateFeatureEdge   MateFeature = "edge"
	MateFeatureVertex MateFeature = "vertex"
	MateFeatureAxis   MateFeature = "axis"
)

// DimensionalMateTypes are mate types that carry a value/unit.
var DimensionalMateTypes = map[MateType]bool{
	MateDistance: true,
	MateAngle:   true,
}

// ValidMateFeatures is the set of allowed feature types.
var ValidMateFeatures = map[MateFeature]bool{
	MateFeatureFace:   true,
	MateFeatureEdge:   true,
	MateFeatureVertex: true,
	MateFeatureAxis:   true,
}

// MateRef references a geometric entity on a component.
type MateRef struct {
	ComponentID string      `json:"component_id"`
	Feature     MateFeature `json:"feature"`
	FeatureID   string      `json:"feature_id"`
}

// Validate checks that the reference has all required fields and valid enum values.
func (r MateRef) Validate() error {
	if r.ComponentID == "" {
		return fmt.Errorf("mate ref: missing component_id")
	}
	if !ValidMateFeatures[r.Feature] {
		return fmt.Errorf("mate ref: invalid feature %q", r.Feature)
	}
	if r.FeatureID == "" {
		return fmt.Errorf("mate ref: missing feature_id")
	}
	return nil
}

// Mate represents a single geometric constraint between two component entities.
type Mate struct {
	ID    string   `json:"id,omitempty"`
	Type  MateType `json:"type"`
	A     MateRef  `json:"a"`
	B     MateRef  `json:"b"`
	Value *float64 `json:"value,omitempty"` // Only for distance/angle mates
	Unit  string   `json:"unit,omitempty"`   // Only for distance/angle mates
}

// Validate checks the mate for correctness.
func (m Mate) Validate() error {
	switch MateType(m.Type) {
	case MateCoincident, MateConcentric, MateParallel, MatePerpendicular, MateTangent:
		if m.Value != nil {
			return fmt.Errorf("mate %q: type %q must not have value", m.ID, m.Type)
		}
		if m.Unit != "" {
			return fmt.Errorf("mate %q: type %q must not have unit", m.ID, m.Type)
		}
	case MateDistance, MateAngle:
		if m.Value == nil {
			return fmt.Errorf("mate %q: type %q requires value", m.ID, m.Type)
		}
		if m.Unit == "" {
			return fmt.Errorf("mate %q: type %q requires unit", m.ID, m.Type)
		}
	default:
		return fmt.Errorf("mate %q: unknown type %q", m.ID, m.Type)
	}
	if err := m.A.Validate(); err != nil {
		return fmt.Errorf("mate %q a: %w", m.ID, err)
	}
	if err := m.B.Validate(); err != nil {
		return fmt.Errorf("mate %q b: %w", m.ID, err)
	}
	return nil
}

// ParseMateType validates and returns a MateType from a string.
func ParseMateType(s string) (MateType, error) {
	t := MateType(strings.TrimSpace(strings.ToLower(s)))
	switch t {
	case MateCoincident, MateConcentric, MateParallel, MatePerpendicular, MateDistance, MateAngle, MateTangent:
		return t, nil
	}
	return "", fmt.Errorf("unknown mate type %q", s)
}

// ParseMateRef parses a JSON object into a MateRef.
func ParseMateRef(raw map[string]any) (MateRef, error) {
	cid, _ := raw["component_id"].(string)
	feat, _ := raw["feature"].(string)
	fid, _ := raw["feature_id"].(string)
	ref := MateRef{
		ComponentID: strings.TrimSpace(cid),
		Feature:     MateFeature(strings.TrimSpace(strings.ToLower(feat))),
		FeatureID:   strings.TrimSpace(fid),
	}
	return ref, ref.Validate()
}

// ParseMate parses a raw JSON object into a Mate. Returns nil if invalid.
func ParseMate(raw map[string]any) *Mate {
	if raw == nil {
		return nil
	}
	t, ok := raw["type"].(string)
	if !ok {
		return nil
	}
	mateType, err := ParseMateType(t)
	if err != nil {
		return nil
	}
	aRaw, ok := raw["a"].(map[string]any)
	if !ok {
		return nil
	}
	bRaw, ok := raw["b"].(map[string]any)
	if !ok {
		return nil
	}
	a, err := ParseMateRef(aRaw)
	if err != nil {
		return nil
	}
	b, err := ParseMateRef(bRaw)
	if err != nil {
		return nil
	}
	m := &Mate{
		ID:   strings.TrimSpace(raw["id"].(string)),
		Type: mateType,
		A:    a,
		B:    b,
	}
	if DimensionalMateTypes[mateType] {
		if v, ok := raw["value"].(float64); ok {
			m.Value = &v
		}
		if u, ok := raw["unit"].(string); ok {
			m.Unit = strings.TrimSpace(u)
		}
	}
	return m
}

// ParseMates parses the raw JSON mates slice and returns validated Mate structs.
func ParseMates(raw []any) []*Mate {
	if raw == nil {
		return nil
	}
	out := make([]*Mate, 0, len(raw))
	for _, item := range raw {
		if m, ok := item.(map[string]any); ok {
			if parsed := ParseMate(m); parsed != nil {
				out = append(out, parsed)
			}
		}
	}
	return out
}

// SerializeMate returns a map representation suitable for JSON marshaling.
func SerializeMate(m *Mate) map[string]any {
	out := map[string]any{
		"type": m.Type,
		"a": map[string]any{
			"component_id": m.A.ComponentID,
			"feature":      m.A.Feature,
			"feature_id":   m.A.FeatureID,
		},
		"b": map[string]any{
			"component_id": m.B.ComponentID,
			"feature":      m.B.Feature,
			"feature_id":   m.B.FeatureID,
		},
	}
	if m.ID != "" {
		out["id"] = m.ID
	}
	if DimensionalMateTypes[m.Type] {
		if m.Value != nil {
			out["value"] = *m.Value
		}
		if m.Unit != "" {
			out["unit"] = m.Unit
		}
	}
	return out
}

// ValidateMateSet checks a list of mates for duplicate IDs and reference validity.
// Returns a map of component IDs referenced by the mates.
func ValidateMateSet(mates []*Mate) (map[string]bool, error) {
	seen := make(map[string]bool)
	refs := make(map[string]bool)
	for _, m := range mates {
		if m.ID != "" {
			if seen[m.ID] {
				return nil, fmt.Errorf("duplicate mate id %q", m.ID)
			}
			seen[m.ID] = true
		}
		if err := m.Validate(); err != nil {
			return nil, err
		}
		refs[m.A.ComponentID] = true
		refs[m.B.ComponentID] = true
	}
	return refs, nil
}

// Doc represents the full assembly document (components + mates).
type Doc struct {
	Components []Component   `json:"components"`
	Mates      []*Mate       `json:"mates,omitempty"`
	Overrides  []Override    `json:"overrides,omitempty"`
}

// Component represents an instance of a Part's Object placed in the assembly.
type Component struct {
	ID         string                 `json:"id"`
	FileID     string                 `json:"file_id"`
	ObjectID   string                 `json:"object_id"`
	Transform  []float64              `json:"transform"`
	Params     map[string]any         `json:"params,omitempty"`
	Visible    *bool                  `json:"visible,omitempty"`
	Color      [3]float64             `json:"color,omitempty"`
	ConfigID   string                 `json:"config_id,omitempty"`
	ExternalRef *ExternalRef          `json:"external_ref,omitempty"`
}

// ExternalRef points to geometry from a different project.
type ExternalRef struct {
	ProjectID string `json:"project_id"`
	FileID    string `json:"file_id"`
	Kind      string `json:"kind"`
	Pin       string `json:"pin"`
}

// Override represents a BOM quantity override for a component.
type Override struct {
	PartFileID       string `json:"part_file_id"`
	QuantityOverride *int  `json:"quantity_override,omitempty"`
	NonStocked      bool   `json:"non_stocked,omitempty"`
	Note            string `json:"note,omitempty"`
}

// ParseDoc parses a JSON string into a Doc. Returns an error for invalid JSON.
func ParseDoc(content string) (*Doc, error) {
	if strings.TrimSpace(content) == "" {
		return &Doc{}, nil
	}
	var raw map[string]any
	if err := json.Unmarshal([]byte(content), &raw); err != nil {
		return nil, fmt.Errorf("invalid JSON: %w", err)
	}
	doc := &Doc{}

	if comps, ok := raw["components"].([]any); ok {
		for i, c := range comps {
			if cm, ok := c.(map[string]any); ok {
				comp := Component{
					ID:       getString(cm, "id"),
					FileID:   getString(cm, "file_id"),
					ObjectID: getString(cm, "object_id"),
				}
				if t, ok := cm["transform"].([]any); ok && len(t) == 16 {
					comp.Transform = toFloat64s(t)
				}
				if p, ok := cm["params"].(map[string]any); ok {
					comp.Params = p
				}
				if v, ok := cm["visible"].(bool); ok {
					comp.Visible = &v
				}
				if col, ok := cm["color"].([]any); ok && len(col) >= 3 {
					comp.Color = [3]float64{toFloat(col[0]), toFloat(col[1]), toFloat(col[2])}
				}
				if cfg, ok := cm["config_id"].(string); ok && cfg != "" {
					comp.ConfigID = cfg
				}
				if er, ok := cm["external_ref"].(map[string]any); ok {
					comp.ExternalRef = &ExternalRef{
						ProjectID: getString(er, "project_id"),
						FileID:    getString(er, "file_id"),
						Kind:      getString(er, "kind"),
						Pin:       getString(er, "pin"),
					}
				}
				doc.Components = append(doc.Components, comp)
			} else {
				return nil, fmt.Errorf("component %d: invalid object", i)
			}
		}
	}

	if matesRaw, ok := raw["mates"].([]any); ok {
		doc.Mates = ParseMates(matesRaw)
	}

	if ovRaw, ok := raw["overrides"].([]any); ok {
		for _, o := range ovRaw {
			if om, ok := o.(map[string]any); ok {
				pfid := getString(om, "part_file_id")
				if pfid == "" {
					continue
				}
				o := Override{PartFileID: pfid}
				if q, ok := om["quantity_override"].(float64); ok {
					qty := int(q)
					o.QuantityOverride = &qty
				}
				if ns, ok := om["non_stocked"].(bool); ok {
					o.NonStocked = ns
				}
				if n, ok := om["note"].(string); ok {
					o.Note = n
				}
				doc.Overrides = append(doc.Overrides, o)
			}
		}
	}

	return doc, nil
}

// SerializeDoc returns the JSON string representation of the doc.
func SerializeDoc(doc *Doc) (string, error) {
	raw := map[string]any{
		"components": doc.Components,
	}
	if len(doc.Mates) > 0 {
		matesRaw := make([]map[string]any, len(doc.Mates))
		for i, m := range doc.Mates {
			matesRaw[i] = SerializeMate(m)
		}
		raw["mates"] = matesRaw
	}
	if len(doc.Overrides) > 0 {
		raw["overrides"] = doc.Overrides
	}
	b, err := json.MarshalIndent(raw, "", "  ")
	if err != nil {
		return "", err
	}
	return string(b), nil
}

func getString(m map[string]any, k string) string {
	if v, ok := m[k].(string); ok {
		return strings.TrimSpace(v)
	}
	return ""
}

func toFloat64s(a []any) []float64 {
	out := make([]float64, len(a))
	for i, v := range a {
		out[i] = toFloat(v)
	}
	return out
}

func toFloat(v any) float64 {
	switch n := v.(type) {
	case float64:
		return n
	case float32:
		return float64(n)
	case int:
		return float64(n)
	case int64:
		return float64(n)
	default:
		return 0
	}
}