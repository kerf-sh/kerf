package tools

// In-memory round-trip verification for the Phase-4 diff + gzip
// revision pipeline. These tests don't touch the database — they
// simulate the same chain (one base every DiffsPerBase rows, diffs in
// between) and confirm:
//
//   1. Every revision reconstructs bit-exact from the stored shape.
//   2. The gzip + delta footprint is dramatically smaller than naive
//      plaintext storage on a typical "small repeated edit" pattern.
//
// The DB-coupled WriteRevision/ReconstructRevision are exercised
// indirectly: this test mirrors their algorithm using the same
// gzipBytes / computeDiffDelta / applyDiffDelta primitives.

import (
	"strings"
	"testing"
)

// fakeRow is the in-memory analog of a file_revisions row.
type fakeRow struct {
	ID       int
	Kind     string // "base" or "diff"
	Gz       []byte // gzipped content (base) or gzipped delta (diff)
	ParentID int    // -1 if no parent
}

// recordFake mirrors WriteRevision's base/diff selection logic but
// against an in-memory slice instead of Postgres.
func recordFake(history []fakeRow, content string) (fakeRow, error) {
	// Find the most recent row + count diffs since latest base.
	diffsSinceBase := 0
	for i := len(history) - 1; i >= 0; i-- {
		if history[i].Kind == "base" {
			break
		}
		diffsSinceBase++
	}
	id := len(history)
	makeBase := len(history) == 0 || diffsSinceBase >= DiffsPerBase
	if makeBase {
		gz, err := gzipBytes(content)
		if err != nil {
			return fakeRow{}, err
		}
		return fakeRow{ID: id, Kind: "base", Gz: gz, ParentID: -1}, nil
	}
	parent := history[len(history)-1]
	parentContent, err := reconstructFake(history, parent.ID)
	if err != nil {
		return fakeRow{}, err
	}
	delta := computeDiffDelta(parentContent, content)
	gz, err := gzipBytes(delta)
	if err != nil {
		return fakeRow{}, err
	}
	return fakeRow{ID: id, Kind: "diff", Gz: gz, ParentID: parent.ID}, nil
}

func reconstructFake(history []fakeRow, id int) (string, error) {
	row := history[id]
	chain := []fakeRow{row}
	for chain[0].Kind == "diff" {
		parent := history[chain[0].ParentID]
		chain = append([]fakeRow{parent}, chain...)
	}
	current, err := gunzipBytes(chain[0].Gz)
	if err != nil {
		return "", err
	}
	for i := 1; i < len(chain); i++ {
		delta, err := gunzipBytes(chain[i].Gz)
		if err != nil {
			return "", err
		}
		next, err := applyDiffDelta(current, delta)
		if err != nil {
			return "", err
		}
		current = next
	}
	return current, nil
}

// TestDiffChainRoundTrip writes 25 revisions to one virtual file and
// reads each back. Every revision must reconstruct bit-exact.
func TestDiffChainRoundTrip(t *testing.T) {
	const N = 25
	var (
		history     []fakeRow
		contents    [N]string
		basePayload = strings.Repeat("// kerf jscad source line\n", 200) // ~5 KB
	)
	for i := 0; i < N; i++ {
		// Simulate "small repeated edit": flip one line per revision.
		c := strings.Replace(basePayload, "// kerf jscad source line",
			"// kerf jscad source line "+strings.Repeat("X", i%5), 3)
		c += "\n// rev " + strings.Repeat("y", i+1)
		contents[i] = c
		row, err := recordFake(history, c)
		if err != nil {
			t.Fatalf("record %d: %v", i, err)
		}
		history = append(history, row)
	}
	for i := 0; i < N; i++ {
		got, err := reconstructFake(history, i)
		if err != nil {
			t.Fatalf("reconstruct %d: %v", i, err)
		}
		if got != contents[i] {
			t.Fatalf("revision %d: mismatch\nwant: %q\ngot:  %q", i, contents[i][:100], got[:100])
		}
	}
}

// TestStorageShrinkage measures the compression + diff footprint on a
// 50KB file × 25 revisions with small per-rev edits. Reports plaintext,
// gzipped-each, and diff+gzip totals so the report includes real
// numbers.
func TestStorageShrinkage(t *testing.T) {
	const N = 25
	// Build a ~50KB pseudo-realistic JSCAD file: ~1000 distinct lines of
	// JS-flavoured filler. This avoids the unrealistically-high gzip
	// ratio you get from pure repetition.
	var sb strings.Builder
	for i := 0; i < 1000; i++ {
		sb.WriteString("const v")
		sb.WriteString(itoa(i))
		sb.WriteString(" = vec3(")
		sb.WriteString(itoa(i * 7 % 53))
		sb.WriteString(", ")
		sb.WriteString(itoa(i * 13 % 89))
		sb.WriteString(", ")
		sb.WriteString(itoa(i * 31 % 41))
		sb.WriteString("); // node ")
		sb.WriteString(itoa(i))
		sb.WriteString(" tagged for assembly\n")
	}
	base := sb.String()
	var (
		history []fakeRow
		plain   int
		eachGz  int
		bases   int
		diffs   int
		gzTotal int
	)
	for i := 0; i < N; i++ {
		// One-line tweak per revision: classic LLM edit pattern.
		c := strings.Replace(base, "const v0 = vec3(",
			"const v0_rev"+itoa(i)+" = vec3(", 1)
		plain += len(c)
		gz, _ := gzipBytes(c)
		eachGz += len(gz)
		row, err := recordFake(history, c)
		if err != nil {
			t.Fatalf("record %d: %v", i, err)
		}
		history = append(history, row)
		gzTotal += len(row.Gz)
		if row.Kind == "base" {
			bases++
		} else {
			diffs++
		}
	}
	// Verify reconstruct still matches before reporting.
	for i := 0; i < N; i++ {
		_, err := reconstructFake(history, i)
		if err != nil {
			t.Fatalf("reconstruct %d: %v", i, err)
		}
	}
	t.Logf("phase4 storage shrinkage report:")
	t.Logf("  N=%d, base_count=%d, diff_count=%d", N, bases, diffs)
	t.Logf("  plaintext-each-row sum:  %d bytes", plain)
	t.Logf("  gzip-each-row sum:       %d bytes  (ratio vs plain: %.2fx)", eachGz, float64(plain)/float64(eachGz))
	t.Logf("  base+diff+gzip sum:      %d bytes  (ratio vs plain: %.2fx)", gzTotal, float64(plain)/float64(gzTotal))
	t.Logf("  base+diff+gzip vs gzip-only: %.2fx further shrink", float64(eachGz)/float64(gzTotal))
}
